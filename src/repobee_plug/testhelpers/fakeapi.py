"""A faked implementation of the :py:class:`repobee_plug.API` specification
that can be used to test RepoBee and plugins.

.. danger::

    This module is in alpha version, and its behavior may change without
    notice.
"""

import pathlib
import git
import pickle
import datetime
import dataclasses

from typing import List, Iterable, Optional, Set

import repobee_plug as plug

TIME = datetime.datetime.now().isoformat()


@dataclasses.dataclass(frozen=True)
class User:
    username: str


@dataclasses.dataclass
class Issue:
    title: str
    body: str
    number: int
    created_at: str
    author: str
    state: plug.IssueState
    assignees: Set[User]

    def to_plug_issue(self):
        return plug.Issue(
            title=self.title,
            body=self.body,
            number=self.number,
            created_at=self.created_at,
            author=self.author,
            implementation=self,
        )


@dataclasses.dataclass(frozen=True)
class Repo:
    name: str
    description: str
    url: str
    private: bool
    path: pathlib.Path
    issues: List[Issue] = dataclasses.field(default_factory=list)

    def to_plug_repo(self, include_issues=None) -> plug.Repo:
        issues = (
            [
                issue.to_plug_issue()
                for issue in self.issues
                if issue.state == plug.IssueState.ALL
                or issue.state == include_issues
            ]
            if include_issues
            else None
        )

        return plug.Repo(
            name=self.name,
            description=self.description,
            private=self.private,
            url=self.url,
            issues=issues,
            implementation=self,
        )

    def __hash__(self):
        return hash(self.name)


@dataclasses.dataclass(frozen=True)
class Team:
    name: str
    members: Set[User]
    permission: plug.TeamPermission
    id: str
    repos: Set[Repo] = dataclasses.field(default_factory=set)

    def add_members(self, users: List[User]) -> None:
        for user in users:
            self.members.add(user)

    def to_plug_team(
        self, include_repos=False, include_issues=None
    ) -> plug.Team:
        repos = (
            [repo.to_plug_repo(include_issues) for repo in self.repos]
            if include_repos
            else None
        )
        return plug.Team(
            name=self.name,
            members=[mem.username for mem in self.members],
            id=self.id,
            repos=repos,
            implementation=self,
        )


class FakeAPI(plug.API):
    """A fake implementation of the :py:class:`repobee_plug.API` specification,
    which emulates a GitHub-like platform.
    """

    def __init__(self, base_url: str, org_name: str, user: str):
        self._repodir = pathlib.Path(base_url[len("https://") :])
        self._org_name = org_name
        self._user = user

        self._teams = {self._org_name: {}}
        self._repos = {self._org_name: {}}
        self._users = {}
        self._restore_state()

    def create_team(
        self,
        name: str,
        members: Optional[List[str]] = None,
        permission: plug.TeamPermission = plug.TeamPermission.PUSH,
    ) -> plug.Team:
        stored_team = self._teams[self._org_name].setdefault(
            name,
            Team(name=name, members=set(), permission=permission, id=name),
        )
        self.assign_members(
            stored_team.to_plug_team(), members or [], permission
        )
        return stored_team.to_plug_team()

    def assign_members(
        self,
        team: plug.Team,
        members: List[str],
        permission: plug.TeamPermission = plug.TeamPermission.PUSH,
    ) -> None:
        team.implementation.add_members(
            [self._get_user(m) for m in members or []]
        )

    def assign_repo(
        self, team: plug.Team, repo: plug.Repo, permission: plug.TeamPermission
    ) -> None:
        team.implementation.repos.add(repo.implementation)

    def create_repo(
        self,
        name: str,
        description: str,
        private: bool,
        team: Optional[plug.Team] = None,
    ) -> plug.Repo:
        assert not team or team.implementation

        repo_bucket = self._repos.setdefault(self._org_name, {})

        if name in repo_bucket:
            raise plug.APIError(f"{name} already exists")

        repo_path = self._repodir / self._org_name / name
        repo_path.mkdir(parents=True, exist_ok=True)
        git.Repo.init(repo_path, bare=True)
        repo_bucket[name] = Repo(
            name=name,
            description=description,
            url=repo_path.as_uri(),
            private=private,
            path=repo_path,
        )

        repo = repo_bucket[name]

        if team:
            self._get_team(team.id).repos.add(repo)

        return repo.to_plug_repo()

    def get_teams(
        self,
        team_names: Optional[List[str]] = None,
        include_repos: bool = False,
        include_issues: Optional[plug.IssueState] = None,
    ) -> Iterable[plug.Team]:
        team_names = set(team_names or [])
        return [
            team.to_plug_team(include_repos, include_issues)
            for team in self._teams[self._org_name].values()
            if not team_names or team.name in team_names
        ]

    def get_repos(
        self,
        repo_names: Optional[List[str]] = None,
        include_issues: Optional[plug.IssueState] = None,
    ) -> Iterable[plug.Repo]:
        unfiltered_repos = (
            self._repos[self._org_name].get(name) for name in repo_names
        )
        return [
            repo.to_plug_repo(include_issues)
            for repo in unfiltered_repos
            if repo
        ]

    def get_repo(
        self,
        repo_name: str,
        team_name: Optional[str],
        include_issues: Optional[plug.IssueState] = None,
    ) -> plug.Repo:
        repos = (
            self._get_team(team_name).repos
            if team_name
            else self._repos[self._org_name].values()
        )
        for repo in repos:
            if repo.name == repo_name:
                return repo.to_plug_repo(include_issues=include_issues)

        raise plug.NotFoundError(f"{team_name} has no repository {repo_name}")

    def insert_auth(self, url: str) -> str:
        return url

    def create_issue(
        self,
        title: str,
        body: str,
        repo: plug.Repo,
        assignees: Optional[str] = None,
    ) -> plug.Issue:
        assignees = {
            self._get_user(assignee) for assignee in (assignees or [])
        }

        issue = Issue(
            title=title,
            body=body,
            number=len(repo.implementation.issues),
            created_at=TIME,
            author=self._user,
            state=plug.IssueState.OPEN,
            assignees=assignees,
        )
        repo.implementation.issues.append(issue)
        return issue.to_plug_issue()

    def close_issue(self, issue: Issue) -> None:
        issue.implementation.state = plug.IssueState.CLOSED

    def delete_team(self, team: plug.Team) -> None:
        del self._teams[self._org_name][team.implementation.name]

    def get_repo_urls(
        self,
        master_repo_names: Iterable[str],
        org_name: Optional[str] = None,
        teams: Optional[List[plug.Team]] = None,
        insert_auth: bool = False,
    ) -> List[str]:
        assert not insert_auth, "not yet implemented"
        base = self._repodir / (org_name or self._org_name)
        repo_names = (
            master_repo_names
            if not teams
            else plug.generate_repo_names(teams, master_repo_names)
        )
        return [(base / name).as_uri() for name in repo_names]

    def extract_repo_name(self, repo_url: str) -> str:
        return pathlib.Path(repo_url).stem

    @staticmethod
    def verify_settings(
        user: str,
        org_name: str,
        base_url: str,
        token: str,
        master_org_name: Optional[str] = None,
    ) -> None:
        pass

    def __getattribute__(self, key):
        attr = object.__getattribute__(self, key)

        if (
            not key.startswith("_")
            and hasattr(plug.API, key)
            and callable(attr)
        ):
            # automatically save state after each API call

            def _func(*args, **kwargs):
                res = attr(*args, **kwargs)
                self._save_state()
                return res

            return _func

        return attr

    def _save_state(self):
        pickle_path = self._repodir / "state.pickle"
        pickle_path.write_bytes(pickle.dumps(self))

    def _restore_state(self):
        pickle_path = self._repodir / "state.pickle"
        if pickle_path.is_file():
            state = pickle.loads(pickle_path.read_bytes())
            self.__dict__ = state.__dict__

    def _add_users(self, usernames: List[str]) -> None:
        """Add users to this instance.

        .. note::

            This function is public for use in testing.

        Args:
            usernames: A list of usernames to add.
        """
        self._users.update({name: User(name) for name in usernames})
        self._save_state()

    def _get_user(self, username: str) -> User:
        if username not in self._users:
            raise plug.NotFoundError(f"no such user: {username}")
        return self._users[username]

    def _get_team(self, team_id: str) -> Team:
        if team_id not in self._teams[self._org_name]:
            raise plug.NotFoundError(f"invalid team id: {team_id}")
        return self._teams[self._org_name][team_id]


class FakeAPIHooks(plug.Plugin):
    def api_init_requires(self):
        return ("base_url", "org_name", "user")

    def get_api_class(self):
        return FakeAPI
