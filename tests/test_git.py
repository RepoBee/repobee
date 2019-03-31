import os
import subprocess
from unittest.mock import call
from collections import namedtuple

import pytest

from repobee import git
from repobee import exception

import constants
from constants import TOKEN

URL_TEMPLATE = "https://{}github.com/slarse/clanim"
USER = constants.USER

Env = namedtuple("Env", ("expected_url", "expected_url_with_username"))

RunTuple = namedtuple("RunTuple", ("returncode", "stdout", "stderr"))
AioSubproc = namedtuple("AioSubproc", ("create_subprocess", "process"))


@pytest.fixture(scope="function")
def env_setup(mocker):
    mocker.patch(
        "subprocess.run", autospec=True, return_value=RunTuple(0, b"", b"")
    )
    # TOKEN was mocked as the environment token when repobee.git was imported
    expected_url = URL_TEMPLATE.format(TOKEN + "@")
    expected_url_with_username = URL_TEMPLATE.format(
        "{}:{}@".format(USER, TOKEN)
    )
    return Env(
        expected_url=expected_url,
        expected_url_with_username=expected_url_with_username,
    )


@pytest.fixture(scope="function")
def aio_subproc(mocker):
    class Process:
        async def communicate(self):
            return self.stdout, self.stderr

        stdout = b"this is stdout"
        stderr = b"this is stderr"
        returncode = 0

    async def mock_gen(*args, **kwargs):
        return Process()

    create_subprocess = mocker.patch(
        "asyncio.create_subprocess_exec", side_effect=mock_gen
    )
    return AioSubproc(create_subprocess, Process)


@pytest.fixture
def non_zero_aio_subproc(mocker):
    """asyncio.create_subprocess mock with non-zero exit status."""

    class Process:
        async def communicate(self):
            return b"this is stdout", b"this is stderr"

        returncode = 1

    async def mock_gen(*args, **kwargs):
        return Process()

    create_subprocess = mocker.patch(
        "asyncio.create_subprocess_exec", side_effect=mock_gen
    )
    return AioSubproc(create_subprocess, Process)


@pytest.fixture(scope="function")
def push_tuples():
    paths = (
        os.path.join(*dirs)
        for dirs in [
            ("some", "awesome", "path"),
            ("other", "path"),
            ("final",),
        ]
    )
    urls = (
        "https://slarse.se/best-repo.git",
        "https://completely-imaginary-repo-url.com/repo.git",
        "https://somerepourl.git",
    )
    branches = ("master", "other", "development-branch")
    tups = [
        git.Push(local_path=path, repo_url=url, branch=branch)
        for path, url, branch in zip(paths, urls, branches)
    ]
    return tups


def test_insert_token():
    token = "1209487fbfuq324yfqf78b6"
    assert git._insert_token(
        URL_TEMPLATE.format(""), token
    ) == URL_TEMPLATE.format(token + "@")


def test_insert_empty_token_raises():
    with pytest.raises(ValueError) as exc:
        git._insert_token(URL_TEMPLATE.format(""), "")
    assert "empty token" in str(exc)


@pytest.mark.parametrize(
    "repo_url, single_branch, branch, cwd, type_error_arg",
    [
        (32, True, "master", ".", "repo_url"),
        ("some_url", 42, "master", ".", "single_branch"),
        ("some_url", False, 42, ".", "branch"),
        ("some_url", True, "master", 42, "cwd"),
    ],
)
def test_clone_single_raises_on_type_errors(
    env_setup, repo_url, single_branch, branch, cwd, type_error_arg
):
    with pytest.raises(TypeError) as exc_info:
        git.clone_single(repo_url, TOKEN, single_branch, branch, cwd)
    assert type_error_arg in str(exc_info)


def test_clone_single_raises_on_empty_branch(env_setup):
    with pytest.raises(ValueError) as exc:
        git.clone_single(URL_TEMPLATE.format(""), TOKEN, branch="")
    assert "branch must not be empty" in str(exc)


def test_clone_single_raises_on_non_zero_exit_from_git_clone(
    env_setup, mocker
):
    stderr = b"This is pretty bad!"
    # already patched in env_setup fixture
    subprocess.run.return_value = RunTuple(1, "", stderr)

    with pytest.raises(exception.CloneFailedError) as exc:
        git.clone_single("{}".format(URL_TEMPLATE.format("")), TOKEN)
    assert "Failed to clone" in str(exc.value)


def test_clone_single_issues_correct_command_with_defaults(env_setup):
    expected_command = "git clone {} --single-branch".format(
        env_setup.expected_url
    ).split()

    git.clone_single(URL_TEMPLATE.format(""), TOKEN)
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd=".",
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )


def test_clone_single_issues_correct_command_without_single_branch(env_setup):
    expected_command = "git clone {}".format(env_setup.expected_url).split()

    git.clone_single(URL_TEMPLATE.format(""), TOKEN, single_branch=False)
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd=".",
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )


def test_clone_single_issues_correct_command_with_single_other_branch(
    env_setup
):
    branch = "other-branch"
    expected_command = "git clone {} --single-branch -b {}".format(
        env_setup.expected_url, branch
    ).split()

    git.clone_single(
        URL_TEMPLATE.format(""), TOKEN, single_branch=True, branch=branch
    )
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd=".",
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )


def test_clone_single_issues_correct_command_with_cwd(env_setup):
    working_dir = "some/working/dir"
    branch = "other-branch"
    expected_command = "git clone {} --single-branch -b {}".format(
        env_setup.expected_url, branch
    ).split()

    git.clone_single(
        URL_TEMPLATE.format(""),
        TOKEN,
        single_branch=True,
        branch=branch,
        cwd=working_dir,
    )
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd=working_dir,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE,
    )


class TestPush:
    """Tests for push."""

    @pytest.mark.parametrize("tries", [0, -2, -10])
    def test_push_raises_when_tries_is_less_than_one(
        self, env_setup, push_tuples, tries
    ):
        with pytest.raises(ValueError) as exc_info:
            git.push(push_tuples, USER, TOKEN, tries=tries)

        assert "tries must be larger than 0" in str(exc_info)

    def test_raises_on_non_str_user(self, env_setup, push_tuples):
        with pytest.raises(TypeError) as exc_info:
            git.push(push_tuples, 32, TOKEN)
        assert "user" in str(exc_info)

    def test_raises_on_empty_push_tuples(self, env_setup):
        with pytest.raises(ValueError) as exc_info:
            git.push([], USER, TOKEN)
        assert "push_tuples" in str(exc_info)

    def test_raises_on_empty_user(self, env_setup, push_tuples):
        with pytest.raises(ValueError) as exc_info:
            git.push(push_tuples, "", TOKEN)
        assert "user" in str(exc_info)

    def test(self, env_setup, push_tuples, aio_subproc):
        """Test that push works as expected when no exceptions are thrown by
        tasks.
        """
        expected_calls = [
            call(
                *"git push {} {}".format(
                    git._insert_user_and_token(url, USER, TOKEN), branch
                ).split(),
                cwd=os.path.abspath(local_repo),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            for local_repo, url, branch in push_tuples
        ]

        failed_urls = git.push(push_tuples, USER, TOKEN)

        assert not failed_urls
        aio_subproc.create_subprocess.assert_has_calls(expected_calls)

    def test_tries_all_calls_despite_exceptions(
        self, env_setup, push_tuples, mocker
    ):
        """Test that push tries to push all push tuple values even if there
        are exceptions.
        """
        tries = 3
        expected_calls = [
            call(pt, USER, TOKEN)
            for pt in sorted(push_tuples, key=lambda pt: pt.repo_url)
        ] * tries

        async def raise_(pt, user, token):
            raise exception.PushFailedError(
                "Push failed", 128, b"some error", pt.repo_url
            )

        mocker.patch("repobee.git._push_async", side_effect=raise_)
        expected_failed_urls = [pt.repo_url for pt in push_tuples]

        failed_urls = git.push(push_tuples, USER, TOKEN, tries=tries)

        assert sorted(failed_urls) == sorted(expected_failed_urls)
        git._push_async.assert_has_calls(expected_calls, any_order=True)

    def test_stops_retrying_when_failed_pushes_succeed(
        self, env_setup, push_tuples, mocker
    ):
        tried = False
        fail_pt = push_tuples[1]

        async def raise_once(pt, user, token):
            nonlocal tried
            if not tried and pt == fail_pt:
                tried = True
                raise exception.PushFailedError(
                    "Push failed", 128, b"some error", pt.repo_url
                )

        expected_num_calls = len(push_tuples) + 1  # one retry

        async def raise_(pt, user, token):
            raise exception.PushFailedError(
                "Push failed", 128, b"some error", pt.repo_url
            )

        async_push_mock = mocker.patch(
            "repobee.git._push_async", side_effect=raise_once
        )

        git.push(push_tuples, USER, TOKEN, tries=10)

        assert len(async_push_mock.call_args_list) == expected_num_calls

    def test_tries_all_calls_when_repos_up_to_date(
        self, env_setup, push_tuples, aio_subproc
    ):
        aio_subproc.process.stderr = b"Everything up-to-date"

        expected_calls = [
            call(
                *"git push {}".format(
                    git._insert_user_and_token(pt.repo_url, USER, TOKEN)
                ).split(),
                pt.branch,
                cwd=os.path.abspath(pt.local_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            for pt in push_tuples
        ]

        git.push(push_tuples, USER, TOKEN)

        aio_subproc.create_subprocess.assert_has_calls(expected_calls)


class TestClone:
    """Tests for clone."""

    @pytest.mark.parametrize("token", (TOKEN, "something-else-entirely"))
    def test_happy_path(env_setup, push_tuples, aio_subproc, token):
        urls = [pt.repo_url for pt in push_tuples]
        working_dir = "some/working/dir"
        expected_subproc_calls = [
            call(
                *"git clone {} --single-branch".format(
                    git._insert_token(url, token)
                ).split(),
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            for url in urls
        ]

        failed_urls = git.clone(urls, token, cwd=working_dir)

        assert not failed_urls
        aio_subproc.create_subprocess.assert_has_calls(expected_subproc_calls)

    def test_tries_all_calls_despite_exceptions(
        env_setup, push_tuples, mocker
    ):
        urls = [pt.repo_url for pt in push_tuples]
        fail_urls = [urls[0], urls[-1]]

        expected_calls = [call(url, TOKEN, True, cwd=".") for url in urls]

        async def raise_(repo_url, *args, **kwargs):
            if repo_url in fail_urls:
                raise exception.CloneFailedError(
                    "Some error",
                    returncode=128,
                    stderr=b"Something",
                    url=repo_url,
                )

        clone_mock = mocker.patch(
            "repobee.git._clone_async", autospec=True, side_effect=raise_
        )

        failed_urls = git.clone(urls, TOKEN)

        assert failed_urls == fail_urls
        clone_mock.assert_has_calls(expected_calls)

    def test_tries_all_calls_despite_exceptions_lower_level(
        env_setup, push_tuples, mocker, non_zero_aio_subproc
    ):
        """Same test as test_tries_all_calls_desipite_exception, but
        asyncio.create_subprocess_exec is mocked out instead of
        git._clone_async
        """
        urls = [pt.repo_url for pt in push_tuples]

        expected_calls = [
            call(
                *"git clone {} --single-branch".format(
                    git._insert_token(url, TOKEN)
                ).split(),
                cwd=".",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE
            )
            for url in urls
        ]

        failed_urls = git.clone(urls, TOKEN)
        non_zero_aio_subproc.create_subprocess.assert_has_calls(expected_calls)

        assert failed_urls == urls
