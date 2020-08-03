"""GitLab API module.

This module contains the :py:class:`GitLabAPI` class, which is meant to be the
prime means of interacting with the GitLab API in RepoBee. The methods of
GitLabAPI are mostly high-level bulk operations.

.. module:: gitlab
    :synopsis: Top level interface for interacting with a GitLab instance
        within _repobee.

.. moduleauthor:: Simon Larsén
"""
import os
import collections
import contextlib
import pathlib
from typing import List, Iterable, Optional, Generator, Tuple

import daiquiri
import gitlab
import requests.exceptions

import repobee_plug as plug

from _repobee import exception

LOGGER = daiquiri.getLogger(__file__)


ISSUE_GENERATOR = Generator[plug.Issue, None, None]


# see https://docs.gitlab.com/ee/api/issues.html for mapping details
_ISSUE_STATE_MAPPING = {
    plug.IssueState.OPEN: "opened",
    plug.IssueState.CLOSED: "closed",
    plug.IssueState.ALL: "all",
}
# see https://docs.gitlab.com/ee/user/permissions.html for permission details
_TEAM_PERMISSION_MAPPING = {
    plug.TeamPermission.PULL: gitlab.REPORTER_ACCESS,
    plug.TeamPermission.PUSH: gitlab.DEVELOPER_ACCESS,
}


@contextlib.contextmanager
def _convert_404_to_not_found_error(msg):
    try:
        yield
    except gitlab.exceptions.GitlabError as exc:
        if exc.response_code == 404:
            raise plug.NotFoundError(msg)
        raise plug.UnexpectedException(
            f"An unexpected exception occured. {type(exc).__name__}: {exc}"
        )


@contextlib.contextmanager
def _convert_error(expected, conversion, msg):
    try:
        yield
    except expected as exc:
        raise conversion(msg) from exc


@contextlib.contextmanager
def _try_api_request(ignore_statuses: Optional[Iterable[int]] = None):
    """Context manager for trying API requests.

    Args:
        ignore_statuses: One or more status codes to ignore (only
        applicable if the exception is a gitlab.exceptions.GitlabError).
    """
    try:
        yield
    except gitlab.exceptions.GitlabError as e:
        if ignore_statuses and e.response_code in ignore_statuses:
            return

        if e.response_code == 404:
            raise plug.NotFoundError(str(e), status=404) from e
        elif e.response_code == 401:
            raise plug.BadCredentials(
                "credentials rejected, verify that token has correct access.",
                status=401,
            ) from e
        else:
            raise plug.APIError(str(e), status=e.response_code) from e
    except (exception.RepoBeeException, plug.PlugError):
        raise
    except Exception as e:
        raise plug.UnexpectedException(
            f"a {type(e).__name__} occured unexpectedly: {str(e)}"
        ) from e


class GitLabAPI(plug.API):
    _User = collections.namedtuple("_User", ("id", "login"))

    def __init__(self, base_url, token, org_name):
        # ssl turns off only for
        self._user = "oauth2"
        self._gitlab = gitlab.Gitlab(
            base_url, private_token=token, ssl_verify=self._ssl_verify()
        )
        self._group_name = org_name
        self._token = token
        self._base_url = base_url

        with _try_api_request():
            self._gitlab.auth()
            self._actual_user = self._gitlab.user.username
            self._group = self._get_organization(self._group_name)

    # START EXPERIMENTAL API
    def create_team(
        self,
        name: str,
        members: Optional[List[str]] = None,
        permission: plug.TeamPermission = plug.TeamPermission.PUSH,
    ) -> plug.Team:
        with _try_api_request():
            team = self._wrap_group(
                self._gitlab.groups.create(
                    {"name": name, "path": name, "parent_id": self._group.id}
                )
            )

        return self.assign_members(team, members or [], permission)

    def assign_members(
        self,
        team: plug.Team,
        members: List[str],
        permission: plug.TeamPermission = plug.TeamPermission.PUSH,
    ) -> plug.Team:
        assert team.implementation
        raw_permission = _TEAM_PERMISSION_MAPPING[permission]
        group = team.implementation

        with _try_api_request():
            for user in self._get_users(members):
                group.members.create(
                    {"user_id": user.id, "access_level": raw_permission}
                )

        return self._wrap_group(group)

    def assign_repo(
        self, team: plug.Team, repo: plug.Repo, permission: plug.TeamPermission
    ) -> None:
        repo.implementation.share(
            team.id, group_access=_TEAM_PERMISSION_MAPPING[permission]
        )

    def create_repo(
        self,
        name: str,
        description: str,
        private: bool,
        team: Optional[plug.Team] = None,
    ) -> plug.Repo:
        group = team.implementation if team else self._group

        with _try_api_request(ignore_statuses=[400]):
            project = self._gitlab.projects.create(
                {
                    "name": name,
                    "path": name,
                    "description": description,
                    "visibility": "private" if private else "public",
                    "namespace_id": group.id,
                }
            )
            return self._wrap_project(project)

        with _try_api_request():
            path = (
                [self._group.path]
                + ([group.path] if group != self._group else [])
                + [name]
            )
            project = self._gitlab.projects.get("/".join(path))

        return self._wrap_project(project)

    def get_teams_(
        self,
        team_names: Optional[List[str]] = None,
        include_repos: bool = False,
        include_issues: Optional[plug.IssueState] = None,
    ) -> Iterable[plug.Team]:
        assert not include_issues or include_repos

        team_names = set(team_names or [])
        with _try_api_request():
            return (
                self._wrap_group(group, include_repos, include_issues)
                for group in self._gitlab.groups.list(
                    id=self._group.id, all=True
                )
                if not team_names or group.path in team_names
            )

    def get_repos(
        self,
        repo_names: Optional[List[str]] = None,
        include_issues: Optional[plug.IssueState] = None,
    ) -> Iterable[plug.Repo]:
        projects = []
        for name in repo_names:
            candidates = self._group.projects.list(
                include_subgroups=True, search=name, all=True
            )
            for candidate in candidates:
                if candidate.name == name:
                    projects.append(candidate.name)
                    yield self._wrap_project(
                        self._gitlab.projects.get(candidate.id), include_issues
                    )

        missing = set(repo_names) - set(projects)
        if missing:
            msg = f"Can't find repos: {', '.join(missing)}"
            LOGGER.warning(msg)

    def insert_auth(self, url: str) -> str:
        return self._insert_auth(url)

    def create_issue(
        self,
        title: str,
        body: str,
        repo: plug.Repo,
        assignees: Optional[str] = None,
    ) -> Tuple[plug.Repo, plug.Issue]:
        project = repo.implementation
        member_ids = [user.id for user in self._get_users(assignees or [])]
        issue = project.issues.create(
            dict(title=title, description=body, assignee_ids=member_ids),
        )
        return (
            self._wrap_project(
                repo.implementation, include_issues=plug.IssueState.ALL
            ),
            self._wrap_issue(issue),
        )

    def close_issue_(self, issue: plug.Issue) -> plug.Issue:
        assert issue.implementation
        issue_impl = issue.implementation
        issue_impl.state_event = "close"
        issue_impl.save()
        return self._wrap_issue(issue_impl)

    def delete_team(self, team: plug.Team) -> None:
        team.implementation.delete()

    def _wrap_group(
        self, group, include_repos=False, include_issues=None
    ) -> plug.Team:
        assert not include_issues or include_repos

        repos = (
            [
                self._wrap_project(
                    self._gitlab.projects.get(gp.id), include_issues
                )
                for gp in group.projects.list(all=True, include_subgroups=True)
            ]
            if include_repos
            else None
        )
        return plug.Team(
            name=group.name,
            members=[
                m.username
                for m in group.members.list()
                if m.access_level != gitlab.OWNER_ACCESS
            ],
            id=group.id,
            repos=repos,
            implementation=group,
        )

    def _wrap_issue(self, issue) -> plug.Issue:
        return plug.Issue(
            title=issue.title,
            body=issue.description,
            number=issue.iid,
            created_at=issue.created_at,
            author=issue.author["username"],
            implementation=issue,
        )

    def _wrap_project(self, project, include_issues=None) -> plug.Repo:
        issues = (
            [
                self._wrap_issue(issue)
                for issue in project.issues.list(
                    all=True, state=_ISSUE_STATE_MAPPING[include_issues]
                )
            ]
            if include_issues
            else None
        )
        return plug.Repo(
            name=project.path,
            description=project.description,
            private=project.visibility == "private",
            team_id=project.namespace_id,
            url=project.attributes["http_url_to_repo"],
            implementation=project,
            issues=issues,
        )

    # END EXPERIMENTAL API

    @staticmethod
    def _ssl_verify():
        ssl_verify = not os.getenv("REPOBEE_NO_VERIFY_SSL") == "true"
        if not ssl_verify:
            LOGGER.warning("SSL verification turned off, only for testing")
        return ssl_verify

    def _get_organization(self, org_name):
        matches = [
            g
            for g in self._gitlab.groups.list(search=org_name)
            if g.path == org_name
        ]

        if not matches:
            raise plug.NotFoundError(org_name, status=404)

        return matches[0]

    def _get_users(self, usernames):
        users = []
        for name in usernames:
            user = self._gitlab.users.list(username=name)
            # if not user:
            # LOGGER.warning(f"user {user} could not be found")
            users += user
        return users

    def get_repo_urls(
        self,
        master_repo_names: Iterable[str],
        org_name: Optional[str] = None,
        teams: Optional[List[plug.Team]] = None,
        insert_auth: bool = False,
    ) -> List[str]:
        """See :py:meth:`repobee_plug.API.get_repo_urls`."""
        group_name = org_name if org_name else self._group_name
        group_url = f"{self._base_url}/{group_name}"
        repo_urls = (
            [f"{group_url}/{repo_name}.git" for repo_name in master_repo_names]
            if not teams
            else [
                f"{group_url}/{team}/"
                f"{plug.generate_repo_name(str(team), master_repo_name)}.git"
                for team in teams
                for master_repo_name in master_repo_names
            ]
        )
        return (
            list(repo_urls)
            if not insert_auth
            else [self.insert_auth(url) for url in repo_urls]
        )

    def extract_repo_name(self, repo_url: str) -> str:
        """See :py:meth:`repobee_plug.API.extract_repo_name`."""
        return pathlib.Path(repo_url).stem

    def _insert_auth(self, repo_url: str):
        """Insert an authentication token into the url.

        Args:
            repo_url: A HTTPS url to a repository.
        Returns:
            the input url with an authentication token inserted.
        """
        if not repo_url.startswith("https://"):
            raise ValueError(
                f"unsupported protocol in '{repo_url}', please use https:// "
            )
        auth = f"{self._user}:{self._token}"
        return repo_url.replace("https://", f"https://{auth}@")

    @staticmethod
    def verify_settings(
        user: str,
        org_name: str,
        base_url: str,
        token: str,
        master_org_name: Optional[str] = None,
    ):
        """See :py:meth:`repobee_plug.API.verify_settings`."""
        LOGGER.info("GitLabAPI is verifying settings ...")
        if not token:
            raise plug.BadCredentials(
                msg="Token is empty. Check that REPOBEE_TOKEN environment "
                "variable is properly set, or supply the `--token` option."
            )

        gl = gitlab.Gitlab(
            base_url, private_token=token, ssl_verify=GitLabAPI._ssl_verify()
        )

        LOGGER.info(f"Authenticating connection to {base_url}...")
        with _convert_error(
            gitlab.exceptions.GitlabAuthenticationError,
            plug.BadCredentials,
            "Could not authenticate token",
        ), _convert_error(
            requests.exceptions.ConnectionError,
            plug.APIError,
            f"Could not connect to {base_url}, please check the URL",
        ):
            gl.auth()
        LOGGER.info(
            f"SUCCESS: Authenticated as {gl.user.username} at {base_url}"
        )

        GitLabAPI._verify_group(org_name, gl)
        if master_org_name:
            GitLabAPI._verify_group(master_org_name, gl)

        LOGGER.info("GREAT SUCCESS: All settings check out!")

    @staticmethod
    def _verify_group(group_name: str, gl: gitlab.Gitlab) -> None:
        """Check that the group exists and that the user is an owner."""
        user = gl.user.username

        LOGGER.info(f"Trying to fetch group {group_name}")
        slug_matched = [
            group
            for group in gl.groups.list(search=group_name)
            if group.path == group_name
        ]
        if not slug_matched:
            raise plug.NotFoundError(
                f"Could not find group with slug {group_name}. Verify that "
                f"you have access to the group, and that you've provided "
                f"the slug (the name in the address bar)."
            )
        group = slug_matched[0]
        LOGGER.info(f"SUCCESS: Found group {group.name}")

        LOGGER.info(
            f"Verifying that user {user} is an owner of group {group_name}"
        )
        matching_members = [
            member
            for member in group.members.list()
            if member.username == user
            and member.access_level == gitlab.OWNER_ACCESS
        ]
        if not matching_members:
            raise plug.BadCredentials(
                f"User {user} is not an owner of {group_name}"
            )
        LOGGER.info(f"SUCCESS: User {user} is an owner of group {group_name}")


class GitLabAPIHook(plug.Plugin):
    def api_init_requires(self):
        return ("base_url", "token", "org_name")

    def get_api_class(self):
        return GitLabAPI
