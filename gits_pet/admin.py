"""Functions for administrating repos.

This module contains functions for administrating repositories, such as
creating student repos from some master repo template. Currently, the
philosophy is that each student has an associated team with the same
name as the student's username. The team is then granted access to repos.

Each public function in this module is to be treated as a self-contained
program.
"""

import shutil
import os
import tempfile
from typing import Iterable, List, Optional
from collections import namedtuple
import daiquiri
from gits_pet import git
from gits_pet import github_api
from gits_pet import util
from gits_pet import tuples
from gits_pet import exception
from gits_pet.github_api import GitHubAPI
from gits_pet.tuples import Team
from gits_pet.git import Push

LOGGER = daiquiri.getLogger(__file__)

MASTER_TEAM = 'master_repos'


def setup_student_repos(master_repo_urls: Iterable[str],
                        students: Iterable[str], user: str,
                        api: GitHubAPI) -> None:
    """Setup student repositories based on master repo templates. Perform three
    primary tasks:

        1. Create one team per student and add the corresponding students to
        the team. If a team already exists, it is left as-is. If a student is
        already in its team, nothing happens. If no account exists with the
        specified username, the team is created regardless but no one is added
        to it.

        2. For each master repository, one private student repo is created and
        added to the corresponding student team. If a repository already
        exists, it is skipped.
        
        3. Files from the master repos are pushed to the corresponding student
        repos.

    Args:
        master_repo_urls: URLs to master repos. Must be in the organization
        that the api is set up for.
        students: An iterable of student GitHub usernames.
        user: Username of the administrator that setting up the repos.
        api: A GitHubAPI instance used to interface with the GitHub instance.
    """
    util.validate_types(user=(user, str), api=(api, GitHubAPI))
    util.validate_non_empty(
        master_repo_urls=master_repo_urls, students=students, user=user)

    urls = list(master_repo_urls)  # safe copy

    with tempfile.TemporaryDirectory() as tmpdir:
        LOGGER.info("cloning into master repos ...")
        master_repo_paths = _clone_all(urls, cwd=tmpdir)

        teams = add_students_to_teams(students, api)
        repo_urls = _create_student_repos(urls, teams, api)

        push_tuples = _create_push_tuples(master_repo_paths, repo_urls)
        LOGGER.info("pushing files to student repos ...")
        git.push(push_tuples, user=user)


def add_students_to_teams(students: Iterable[str],
                          api: GitHubAPI) -> List[Team]:
    """Create one team for each student (with the same name as the student),
    and add the student to the team. If a team already exists, it is not created.
    If a student is already in his/her team, nothing happens.

    Args:
        students: Student GitHub usernames.
        api: A GitHubAPI instance.

    Returns:
        all teams associated with the students in the students list.
    """
    util.validate_types(api=(api, GitHubAPI))
    util.validate_non_empty(students=students)
    # (team_name, member list) mappings, each student gets its own team
    member_lists = {student: [student] for student in students}
    return api.ensure_teams_and_members(member_lists)


def _create_student_repos(master_repo_urls: Iterable[str],
                          teams: Iterable[Team], api: GitHubAPI) -> List[str]:
    """Create student repos. Each team (usually representing one student) is assigned a single repo
    per master repo. Repos that already exist are not created, but their urls are returned all
    the same.

    Args:
        master_repo_urls: URLs to master repos. Must be in the organization that the api is set up for.
        teams: An iterable of namedtuples designating different teams.
        api: A GitHubAPI instance used to interface with the GitHub instance.

    Returns:
        a list of urls to the repos
    """
    LOGGER.info("creating student repos ...")
    repo_infos = _create_repo_infos(master_repo_urls, teams)
    repo_urls = api.create_repos(repo_infos)
    return repo_urls


def _clone_all(urls: Iterable[str], cwd: str):
    """Attempts to clone all urls. If a repo is already present, it is skipped.
    If any one clone fails (except for fails because the repo is local),
    all cloned repos are removed

    Args:
        urls: HTTPS urls to git repositories.
        cwd: Working directory. Use temporary directory for automatic cleanup.
    Returns:
        local paths to the cloned repos.
    """
    if len(set(urls)) != len(urls):
        raise ValueError("master_repo_urls contains duplicates")
    try:
        for url in urls:
            LOGGER.info("cloning into {}".format(url))
            git.clone_single(url, cwd=cwd)
    except exception.CloneFailedError:
        LOGGER.error("error cloning into {}, aborting ...".format(url))
        raise
    paths = [os.path.join(cwd, util.repo_name(url)) for url in urls]
    assert all(map(util.is_git_repo, paths)), "all repos must be git repos"
    return paths


def update_student_repos(master_repo_urls: Iterable[str],
                         students: Iterable[str],
                         user: str,
                         api: GitHubAPI,
                         issue: Optional[tuples.Issue] = None) -> None:
    """Attempt to update all student repos related to one of the master repos.

    Args:
        master_repo_urls: URLs to master repos. Must be in the organization that the api is set up for.
        students: An iterable of student GitHub usernames.
        user: Username of the administrator that setting up the repos.
        api: A GitHubAPI instance used to interface with the GitHub instance.
        issue: An optional issue to open in repos to which pushing fails.
    """
    util.validate_types(
        user=(user, str),
        api=(api, GitHubAPI),
        issue=(issue, (tuples.Issue, type(None))))
    util.validate_non_empty(
        master_repo_urls=master_repo_urls, user=user, students=students)
    urls = list(master_repo_urls)  # safe copy

    if len(set(urls)) != len(urls):
        raise ValueError("master_repo_urls contains duplicates")

    master_repo_names = [util.repo_name(url) for url in urls]
    student_repo_names = util.generate_repo_names(students, master_repo_names)

    repo_urls = api.get_repo_urls(student_repo_names)

    if not repo_urls:
        msg = "No student repos corresponding to the master repos were found"
        LOGGER.error(msg)
        raise exception.APIError(msg)

    with tempfile.TemporaryDirectory() as tmpdir:
        LOGGER.info("cloning into master repos ...")
        master_repo_paths = _clone_all(urls, tmpdir)

        push_tuples = _create_push_tuples(master_repo_paths, repo_urls)

        LOGGER.info("pushing files to student repos ...")
        failed_urls = git.push(push_tuples, user=user)

    if failed_urls and issue:
        LOGGER.info("Opening issue in repos to which push failed")
        _open_issue_by_urls(failed_urls, issue, api)

    LOGGER.info("done!")


def _open_issue_by_urls(repo_urls: Iterable[str], issue: tuples.Issue,
                        api: GitHubAPI) -> None:
    """Open issues in the repos designated by the repo_urls.

    repo_urls: URLs to repos in which to open an issue.
    issue: An issue to open.
    api: A GitHubAPI to use.
    """
    repo_names = [util.repo_name(url) for url in repo_urls]
    api.open_issue(issue, repo_names)


def open_issue(issue: tuples.Issue, master_repo_names: Iterable[str],
               students: Iterable[str], api: GitHubAPI) -> None:
    """Open an issue in student repos.

    Args:
        master_repo_names: Names of master repositories.
        students: An iterable of student GitHub usernames.
        issue: An issue to open.
        api: A GitHubAPI instance used to interface with the GitHub instance.
    """
    util.validate_types(issue=(issue, tuples.Issue), api=(api, GitHubAPI))
    util.validate_non_empty(
        master_repo_names=master_repo_names, students=students, issue=issue)

    repo_names = util.generate_repo_names(students, master_repo_names)

    api.open_issue(issue, repo_names)


def close_issue(title_regex: str, master_repo_names: Iterable[str],
                students: Iterable[str], api: GitHubAPI) -> None:
    """Close issues whose titles match the title_regex in student repos.

    Args:
        title_regex: A regex to match against issue titles.
        master_repo_names: Names of master repositories.
        students: An iterable of student GitHub usernames.
        api: A GitHubAPI instance used to interface with the GitHub instance.
    """
    util.validate_types(title_regex=(title_regex, str), api=(api, GitHubAPI))
    util.validate_non_empty(
        title_regex=title_regex,
        master_repo_names=master_repo_names,
        students=students)

    repo_names = util.generate_repo_names(students, master_repo_names)

    api.close_issue(title_regex, repo_names)


def clone_repos(master_repo_names: Iterable[str], students: Iterable[str],
                api: GitHubAPI) -> None:
    """Clone all student repos related to the provided master repos and students.

    Args:
        master_repo_names: Names of master repos.
        students: Student usernames.
        api: A GitHubAPI instance.
    """
    util.validate_types(api=(api, GitHubAPI))
    util.validate_non_empty(
        master_repo_names=master_repo_names, students=students)

    repo_names = util.generate_repo_names(students, master_repo_names)
    repo_urls = api.get_repo_urls(repo_names)

    LOGGER.info("cloning into student repos ...")
    git.clone(repo_urls)


def migrate_repos(master_repo_urls: Iterable[str], user: str,
                  api: GitHubAPI) -> None:
    """Migrate a repository from an arbitrary URL to the target organization.
    The new repository is added to the master_repos team, which is created if
    it does not already exist.

    Args:
        master_repo_urls: HTTPS URLs to the master repos to migrate.
        user: username of the administrator performing the migration. This is
        the username that is used in the push.
        api: A GitHubAPI instance used to interface with the GitHub instance.
    """
    util.validate_types(user=(user, str), api=(api, GitHubAPI))
    util.validate_non_empty(master_repo_urls=master_repo_urls, user=user)

    master_team, *_ = api.ensure_teams_and_members({MASTER_TEAM: []})

    master_names = [util.repo_name(url) for url in master_repo_urls]

    infos = [
        tuples.Repo(
            name=master_name,
            description="Master repository {}".format(master_name),
            private=True,
            team_id=master_team.id) for master_name in master_names
    ]

    with tempfile.TemporaryDirectory() as tmpdir:
        _clone_all(master_repo_urls, cwd=tmpdir)
        repo_urls = api.create_repos(infos)

        git.push(
            [
                git.Push(
                    local_path=os.path.join(tmpdir, info.name),
                    repo_url=repo_url,
                    branch='master')
                for repo_url, info in zip(repo_urls, infos)
            ],
            user=user)

    LOGGER.info("done!")


def _create_repo_infos(urls: Iterable[str],
                       teams: Iterable[Team]) -> List[tuples.Repo]:
    """Create Repo namedtuples for all combinations of url and team.

    Args:
        urls: Master repo urls.
        teams: Team namedtuples.

    Returns:
        A list of Repo namedtuples with all (url, team) combinations.
    """
    repo_infos = []
    for url in urls:
        repo_base_name = util.repo_name(url)
        repo_infos += [
            tuples.Repo(
                name=util.generate_repo_name(team.name, repo_base_name),
                description="{} created for {}".format(repo_base_name,
                                                       team.name),
                private=True,
                team_id=team.id) for team in teams
        ]
    return repo_infos


def _create_push_tuples(master_repo_paths: Iterable[str],
                        repo_urls: Iterable[str]) -> List[Push]:
    """Create Push namedtuples for all repo urls in repo_urls that share
    repo base name with any of the urls in master_urls.

    Args:
        master_repo_paths: Local paths to master repos.
        repo_urls: Urls to student repos.

    Returns:
        A list of Push namedtuples for all student repo urls that relate to
        any of the master repo urls.
    """
    push_tuples = []
    for path in master_repo_paths:
        repo_base_name = os.path.basename(path)
        push_tuples += [
            git.Push(local_path=path, repo_url=repo_url, branch='master')
            for repo_url in repo_urls if repo_url.endswith(repo_base_name)
        ]
    return push_tuples
