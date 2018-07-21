import sys
import os
import pytest
import subprocess
from asyncio import coroutine
from unittest.mock import patch, PropertyMock, MagicMock, call
from collections import namedtuple

from conftest import TOKEN

from gits_pet import git
from gits_pet import exception

URL_TEMPLATE = 'https://{}github.com/slarse/clanim'
USER = pytest.constants.USER

Env = namedtuple('Env', ('expected_url', 'expected_url_with_username'))

RunTuple = namedtuple('RunTuple', ('returncode', 'stdout', 'stderr'))
AioSubproc = namedtuple('AioSubproc', ('create_subprocess', 'process'))


@pytest.fixture(scope='function')
def env_setup(mocker):
    mocker.patch(
        'subprocess.run', autospec=True, return_value=RunTuple(0, b'', b''))
    # TOKEN was mocked as the environment token when gits_pet.git was imported
    expected_url = URL_TEMPLATE.format(TOKEN + '@')
    expected_url_with_username = URL_TEMPLATE.format("{}:{}@".format(
        USER, TOKEN))
    return Env(
        expected_url=expected_url,
        expected_url_with_username=expected_url_with_username)


@pytest.fixture(scope='function')
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
        'asyncio.create_subprocess_exec', side_effect=mock_gen)
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
        'asyncio.create_subprocess_exec', side_effect=mock_gen)
    return AioSubproc(create_subprocess, Process)


@pytest.fixture(scope='function')
def push_tuples():
    paths = (os.path.join(*dirs)
             for dirs in [('some', 'awesome', 'path'), ('other',
                                                        'path'), ('final', )])
    urls = ('https://slarse.se/best-repo.git',
            'https://completely-imaginary-repo-url.com/repo.git',
            'https://somerepourl.git')
    branches = ('master', 'other', 'development-branch')
    tups = [
        git.Push(local_path=path, repo_url=url, branch=branch)
        for path, url, branch in zip(paths, urls, branches)
    ]
    return tups


def test_insert_token():
    token = '1209487fbfuq324yfqf78b6'
    assert git._insert_token(URL_TEMPLATE.format(''),
                             token) == URL_TEMPLATE.format(token + '@')


def test_insert_empty_token_raises():
    with pytest.raises(ValueError) as exc:
        git._insert_token(URL_TEMPLATE.format(''), '')
    assert 'empty token' in str(exc)


@pytest.mark.parametrize(
    'repo_url, single_branch, branch, cwd, type_error_arg',
    [(32, True, 'master', '.', 'repo_url'),
     ('some_url', 42, 'master', '.', 'single_branch'),
     ('some_url', False, 42, '.', 'branch'),
     ('some_url', True, 'master', 42, 'cwd')])
def test_clone_single_raises_on_type_errors(env_setup, repo_url, single_branch,
                                            branch, cwd, type_error_arg):
    with pytest.raises(TypeError) as exc_info:
        git.clone_single(repo_url, single_branch, branch, cwd)
    assert type_error_arg in str(exc_info)


def test_clone_single_raises_on_empty_branch(env_setup):
    with pytest.raises(ValueError) as exc:
        git.clone_single(URL_TEMPLATE.format(''), branch='')
    assert 'branch must not be empty' in str(exc)


def test_clone_single_raises_on_non_zero_exit_from_git_clone(
        env_setup, mocker):
    stderr = b'This is pretty bad!'
    # already patched in env_setup fixture
    subprocess.run.return_value = RunTuple(1, '', stderr)

    with pytest.raises(exception.CloneFailedError) as exc:
        git.clone_single("{}".format(URL_TEMPLATE.format('')))
    assert "Failed to clone" in str(exc.value)


def test_clone_single_issues_correct_command_with_defaults(env_setup):
    expected_command = "git clone {} --single-branch".format(
        env_setup.expected_url).split()

    git.clone_single(URL_TEMPLATE.format(''))
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd='.',
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)


def test_clone_single_issues_correct_command_without_single_branch(env_setup):
    expected_command = "git clone {}".format(env_setup.expected_url).split()

    git.clone_single(URL_TEMPLATE.format(''), single_branch=False)
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd='.',
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)


def test_clone_single_issues_correct_command_with_single_other_branch(
        env_setup):
    branch = 'other-branch'
    expected_command = "git clone {} --single-branch -b {}".format(
        env_setup.expected_url, branch).split()

    git.clone_single(
        URL_TEMPLATE.format(''), single_branch=True, branch=branch)
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd='.',
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)


def test_clone_single_issues_correct_command_with_cwd(env_setup):
    working_dir = 'some/working/dir'
    branch = 'other-branch'
    expected_command = "git clone {} --single-branch -b {}".format(
        env_setup.expected_url, branch).split()

    git.clone_single(
        URL_TEMPLATE.format(''),
        single_branch=True,
        branch=branch,
        cwd=working_dir)
    subprocess.run.assert_called_once_with(
        expected_command,
        cwd=working_dir,
        stderr=subprocess.PIPE,
        stdout=subprocess.PIPE)


class TestPushSingle:
    """Tests for push_single."""

    def test_raises_on_non_string_args(self, env_setup):
        with pytest.raises(TypeError) as exc:
            git.push_single(1, user=USER, repo_url='some_url')
        assert 'local_repo' in str(exc)
        assert 'expected str' in str(exc)

        with pytest.raises(TypeError) as exc:
            git.push_single('something', user=2, repo_url='some_url')
        assert 'user' in str(exc)
        assert 'expected str' in str(exc)

        with pytest.raises(TypeError) as exc:
            git.push_single('something', user=USER, repo_url=1)
        assert 'repo_url' in str(exc)
        assert 'expected str' in str(exc)

        with pytest.raises(TypeError) as exc:
            git.push_single(
                'something', user=USER, repo_url='some_url', branch=3)
        assert 'branch' in str(exc)
        assert 'expected str' in str(exc)

    def test_raises_on_empty_local_repo(self, env_setup):
        with pytest.raises(ValueError) as exc:
            git.push_single('', user=USER, repo_url='some_url')
        assert 'local_repo must not be empty' in str(exc)

    def test_raises_on_empty_user(self, env_setup):
        with pytest.raises(ValueError) as exc:
            git.push_single('something', user='', repo_url='some_url')
        assert 'user must not be empty' in str(exc)

    def test_raises_on_empty_repo_url(self, env_setup):
        with pytest.raises(ValueError) as exc:
            git.push_single('something', user=USER, repo_url='')
        assert 'repo_url must not be empty' in str(exc)

    def test_raises_on_empty_branch(self, env_setup):
        with pytest.raises(ValueError) as exc:
            git.push_single(
                'something', user=USER, repo_url='some_url', branch='')
        assert 'branch must not be empty' in str(exc)

    def test_raises_on_async_push_exception(self, env_setup, mocker):
        url = 'some_url'

        async def raise_(pt, branch):
            raise exception.PushFailedError("Push failed", 128, b"some error",
                                            pt.repo_url)

        mocker.patch('gits_pet.git._push_async', side_effect=raise_)

        with pytest.raises(exception.PushFailedError) as exc_info:
            git.push_single('some_repo', USER, url)

        assert exc_info.value.url == url

    def test_issues_correct_command_with_defaults(self, env_setup,
                                                  aio_subproc):
        branch = 'master'
        user = USER
        local_repo = os.sep.join(['path', 'to', 'repo'])
        expected_command = "git push {} {}".format(
            env_setup.expected_url_with_username, branch).split()

        git.push_single(
            local_repo,
            user=user,
            repo_url=URL_TEMPLATE.format(''),
            branch=branch)

        aio_subproc.create_subprocess.assert_called_once_with(
            *expected_command,
            cwd=os.path.abspath(local_repo),
            # TODO the piping is not obvious from the test, refactor
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def test_issues_correct_command(self, env_setup, aio_subproc):
        branch = 'development-branch'
        user = USER
        expected_command = "git push {} {}".format(
            env_setup.expected_url_with_username, branch).split()
        local_repo = os.sep.join(['path', 'to', 'repo'])

        git.push_single(
            local_repo,
            user=user,
            repo_url=URL_TEMPLATE.format(''),
            branch=branch)

        aio_subproc.create_subprocess.assert_called_once_with(
            *expected_command,
            cwd=os.path.abspath(local_repo),
            # TODO the piping is not obvious from the test, refactor
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE)

    def test_raises_on_non_zero_exit_from_git_push(self, env_setup,
                                                   aio_subproc):
        aio_subproc.process.returncode = 128

        with pytest.raises(exception.PushFailedError) as exc:
            git.push_single(
                'some_repo', user='some_user', repo_url='https://some_url.org')


class TestPush:
    """Tests for push."""

    @pytest.mark.parametrize('tries', [0, -2, -10])
    def test_push_raises_when_tries_is_less_than_one(self, env_setup,
                                                     push_tuples, tries):
        with pytest.raises(ValueError) as exc_info:
            git.push(push_tuples, USER, tries=tries)

        assert "tries must be larger than 0" in str(exc_info)

    def test_raises_on_non_str_user(self, env_setup, push_tuples):
        with pytest.raises(TypeError) as exc_info:
            git.push(push_tuples, 32)
        assert 'user' in str(exc_info)

    def test_raises_on_empty_push_tuples(self, env_setup):
        with pytest.raises(ValueError) as exc_info:
            git.push([], USER)
        assert 'push_tuples' in str(exc_info)

    def test_raises_on_empty_user(self, env_setup, push_tuples):
        with pytest.raises(ValueError) as exc_info:
            git.push(push_tuples, '')
        assert 'user' in str(exc_info)

    def test(self, env_setup, push_tuples, aio_subproc):
        """Test that push many works as expected when no exceptions are thrown by
        tasks.
        """
        expected_calls = [
            call(
                *"git push {} {}".format(
                    git._insert_user_and_token(url, USER), branch).split(),
                cwd=os.path.abspath(local_repo),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
            for local_repo, url, branch in push_tuples
        ]

        failed_urls = git.push(push_tuples, USER)

        assert not failed_urls
        aio_subproc.create_subprocess.assert_has_calls(expected_calls)

    def test_tries_all_calls_despite_exceptions(self, env_setup, push_tuples,
                                                mocker):
        """Test that push tries to push all push tuple values even if there
        are exceptions.
        """
        tries = 3
        expected_calls = [
            call(pt, USER)
            for pt in sorted(push_tuples, key=lambda pt: pt.repo_url)
        ] * tries

        async def raise_(pt, user):
            raise exception.PushFailedError("Push failed", 128, b"some error",
                                            pt.repo_url)

        mocker.patch('gits_pet.git._push_async', side_effect=raise_)
        expected_failed_urls = [pt.repo_url for pt in push_tuples]

        failed_urls = git.push(push_tuples, USER, tries=tries)

        assert sorted(failed_urls) == sorted(expected_failed_urls)
        git._push_async.assert_has_calls(expected_calls, any_order=True)

    def test_stops_retrying_when_failed_pushes_succeed(self, env_setup,
                                                       push_tuples, mocker):
        tried = False
        fail_pt = push_tuples[1]

        async def raise_once(pt, user):
            nonlocal tried
            if not tried and pt == fail_pt:
                tried = True
                raise exception.PushFailedError("Push failed", 128,
                                                b"some error", pt.repo_url)

        expected_num_calls = len(push_tuples) + 1  # one retry

        async def raise_(pt, user):
            raise exception.PushFailedError("Push failed", 128, b"some error",
                                            pt.repo_url)

        async_push_mock = mocker.patch(
            'gits_pet.git._push_async', side_effect=raise_once)

        git.push(push_tuples, USER, tries=10)

        assert len(async_push_mock.call_args_list) == expected_num_calls

    def test_does_tries_all_calls_when_repos_up_to_date(
            self, env_setup, push_tuples, aio_subproc):
        aio_subproc.process.stderr = b"Everything up-to-date"

        expected_calls = [
            call(
                *"git push {}".format(
                    git._insert_user_and_token(pt.repo_url, USER)).split(),
                pt.branch,
                cwd=os.path.abspath(pt.local_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE) for pt in push_tuples
        ]

        git.push(push_tuples, USER)

        aio_subproc.create_subprocess.assert_has_calls(expected_calls)


class TestClone:
    """Tests for clone."""

    def test_happy_path(env_setup, push_tuples, aio_subproc):
        urls = [pt.repo_url for pt in push_tuples]
        working_dir = 'some/working/dir'
        expected_subproc_calls = [
            call(
                *"git clone {} --single-branch".format(
                    git._insert_token(url)).split(),
                cwd=working_dir,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE) for url in urls
        ]

        failed_urls = git.clone(urls, cwd=working_dir)

        assert not failed_urls
        aio_subproc.create_subprocess.assert_has_calls(expected_subproc_calls)

    def test_tries_all_calls_despite_exceptions(env_setup, push_tuples,
                                                mocker):
        urls = [pt.repo_url for pt in push_tuples]
        fail_urls = [urls[0], urls[-1]]

        expected_calls = [call(url, True, cwd='.') for url in urls]

        async def raise_(repo_url, *args, **kwargs):
            if repo_url in fail_urls:
                raise exception.CloneFailedError(
                    "Some error",
                    returncode=128,
                    stderr=b"Something",
                    url=repo_url)

        clone_mock = mocker.patch(
            'gits_pet.git._clone_async', autospec=True, side_effect=raise_)

        failed_urls = git.clone(urls)

        assert failed_urls == fail_urls
        clone_mock.assert_has_calls(expected_calls)

    def test_tries_all_calls_despite_exceptions_lower_level(
            env_setup, push_tuples, mocker, non_zero_aio_subproc):
        """Same test as test_tries_all_calls_desipite_exception, but
        asyncio.create_subprocess_exec is mocked out instead of
        git._clone_async
        """
        urls = [pt.repo_url for pt in push_tuples]

        expected_calls = [
            call(
                *'git clone {} --single-branch'.format(
                    git._insert_token(url)).split(),
                cwd='.',
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE) for url in urls
        ]

        failed_urls = git.clone(urls)
        non_zero_aio_subproc.create_subprocess.assert_has_calls(expected_calls)

        assert failed_urls == urls
