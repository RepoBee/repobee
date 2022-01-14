"""Wrapper functions for git commands that perform local git operations.

.. module:: git
    :synopsis: Wrapper functions for git commands that perform local git
    operations, such as initializing git repository, stashing changes, etc.

.. moduleauthor:: Simon Larsén
"""

import pathlib
from typing import (
    List,
    Mapping,
    Any,
)

import git

import repobee_plug as plug
from _repobee.git._util import captured_run


def set_gitconfig_options(
    repo_path: pathlib.Path, options: Mapping[str, Any]
) -> None:
    """Set gitconfig options in the repository.

    Args:
        repo_path: Path to a repository.
        options: A mapping (option_name -> option_value)
    """
    repo = git.Repo(repo_path)
    for key, value in options.items():
        repo.git.config("--local", key, value)


def active_branch(repo_path: pathlib.Path) -> str:
    """Get the active branch from the given repo.

    Args:
        repo_path: Path to a repo.
    Returns:
        The active branch of the repo.
    """
    return git.Repo(repo_path).active_branch.name


def stash_changes(local_repos: List[plug.StudentRepo]) -> None:
    for repo in local_repos:
        captured_run("git stash".split(), cwd=repo.path)


def git_init(dirpath):
    captured_run(["git", "init"], cwd=str(dirpath))
