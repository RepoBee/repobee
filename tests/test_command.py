import sys
import os
import pytest
from unittest.mock import patch, MagicMock, Mock, call, ANY

import repomate
from repomate import command
from repomate import github_api
from repomate import git
from repomate import tuples
from repomate import util
from repomate import exception
from repomate import plugin

from repomate_plug import HookResult, repomate_hook, Status

from_magic_mock_issue = pytest.functions.from_magic_mock_issue
to_magic_mock_issue = pytest.functions.to_magic_mock_issue
User = pytest.classes.User

RANDOM_DATE = pytest.functions.RANDOM_DATE

OPEN_ISSUES = [
    tuples.Issue('close this issue', 'This is a body', 3, RANDOM_DATE(),
                 'slarse'),
    tuples.Issue("Don't close this issue", 'Another body', 4, RANDOM_DATE(),
                 'glassey')
]

CLOSED_ISSUES = [
    tuples.Issue('This is a closed issue',
'With an uninteresting body that has a single very,'
'very long line that would probably break the implementation '
'if something was off with the line limit function.', 1,
                 RANDOM_DATE(), 'tmore'),
    tuples.Issue('Yet another closed issue', 'Even less interesting body', 2,
                 RANDOM_DATE(), 'viklu')
]

USER = 'slarse'
ORG_NAME = 'test-org'
GITHUB_BASE_URL = 'https://some_enterprise_host/api/v3'
API = github_api.GitHubAPI("bla", "bla", "bla")
ISSUE = tuples.Issue("Oops, something went wrong!",
                     "This is the body **with some formatting**.")
PLUGINS = pytest.constants.PLUGINS
STUDENTS = pytest.constants.STUDENTS

GENERATE_TEAM_REPO_URL = lambda student, base_name:\
        "https://slarse.se/repos/{}".format(
            util.generate_repo_name(student, base_name))

GENERATE_REPO_URL = lambda name: GENERATE_TEAM_REPO_URL(name, 'd')[:-2]

MASTER_NAMES = ('week-1', 'week-2', 'week-3')
MASTER_URLS = tuple(GENERATE_REPO_URL(name) for name in MASTER_NAMES)

STUDENT_REPO_NAMES = tuple(
    util.generate_repo_name(student, master_name)
    for master_name in MASTER_NAMES for student in STUDENTS)

raise_ = pytest.functions.raise_


@pytest.fixture(autouse=True)
def validate_types_mock(request, mocker):
    """Mock util.validate_types to only work on non-mock items."""
    if 'novalidatemock' in request.keywords:
        return
    util_validate = util.validate_types

    def validate(**kwargs):
        """Mocked validate that skips Mock objects as types."""
        remove = set()
        for param_name, (argument, expected_types) in kwargs.items():
            if isinstance(expected_types, (Mock, MagicMock))\
                    or isinstance( expected_types, tuple)\
                    and any(isinstance(obj, (Mock, MagicMock))
                                   for obj in expected_types):
                remove.add(param_name)
        util_validate(
            **{key: val
               for key, val in kwargs.items() if key not in remove})

    return mocker.patch('repomate.util.validate_types', side_effect=validate)


@pytest.fixture(autouse=True)
def git_mock(request, mocker):
    """Mocks the whole git module so that there are no accidental
    pushes/clones.
    """
    if 'nogitmock' in request.keywords:
        return
    pt = repomate.git.Push
    git_mock = mocker.patch('repomate.command.git', autospec=True)
    git_mock.Push = pt
    return git_mock


def _get_issues(repo_names, state='open', title_regex=""):
    """Bogus version of GitHubAPI.get_issues"""
    for repo_name in repo_names:
        if repo_name == STUDENT_REPO_NAMES[-2]:
            # repo without issues
            yield repo_name, iter([])
        elif repo_name in STUDENT_REPO_NAMES:
            if state == 'open':
                issues = iter(OPEN_ISSUES)
            elif state == 'closed':
                issues = iter(CLOSED_ISSUES)
            elif state == 'all':
                issues = iter(OPEN_ISSUES + CLOSED_ISSUES)
            else:
                raise ValueError("Unexpected value for 'state': ", state)
            yield repo_name, issues


@pytest.fixture(autouse=True)
def api_mock(request, mocker):
    if 'noapimock' in request.keywords:
        return
    mock = MagicMock(spec=repomate.command.GitHubAPI)
    api_class = mocker.patch('repomate.command.GitHubAPI', autospec=True)
    api_class.return_value = mock

    url_from_repo_info = lambda repo_info: GENERATE_REPO_URL(repo_info.name)
    mock.get_repo_urls.side_effect = lambda repo_names: list(map(GENERATE_REPO_URL, repo_names))
    mock.create_repos.side_effect =\
        lambda repo_infos: list(map(url_from_repo_info, repo_infos))
    mock.get_issues = MagicMock(
        spec='repomate.github_api.GitHubAPI.get_issues',
        side_effect=_get_issues)
    return mock


@pytest.fixture
def students():
    return list(STUDENTS)


@pytest.fixture
def ensure_teams_and_members_mock(api_mock, students):
    api_mock.ensure_teams_and_members.side_effect = lambda member_lists: [tuples.Team(student, [student], id)
                    for id, student
                    in enumerate(students)]


@pytest.fixture
def master_urls():
    return list(MASTER_URLS)


@pytest.fixture
def master_names():
    return list(MASTER_NAMES)


@pytest.fixture
def repo_infos(master_urls, students):
    """Students are here used as teams, remember that they have same names as
    students.
    """
    repo_infos = []
    for url in master_urls:
        repo_base_name = util.repo_name(url)
        repo_infos += [
            tuples.Repo(
                name=util.generate_repo_name(student, repo_base_name),
                description="{} created for {}".format(repo_base_name,
                                                       student),
                private=True,
                team_id=cur_id) for cur_id, student in enumerate(students)
        ]
    return repo_infos


@pytest.fixture
def push_tuples(master_urls, students, tmpdir):

    push_tuples = [
        git.Push(
            local_path=os.path.join(str(tmpdir), util.repo_name(url)),
            repo_url=GENERATE_TEAM_REPO_URL(student, util.repo_name(url)),
            branch='master')
        # note that the order here is significant, must correspond with util.generate_repo_names
        for url in master_urls for student in students
    ]
    return push_tuples


@pytest.fixture
def push_tuple_lists(master_urls, students):
    """Create an expected push tuple list for each master url."""
    pts = []
    for url in master_urls:
        repo_base_name = util.repo_name(url)


@pytest.fixture(scope='function', autouse=True)
def rmtree_mock(mocker):
    return mocker.patch('shutil.rmtree', autospec=True)


@pytest.fixture(autouse=True)
def is_git_repo_mock(mocker):
    return mocker.patch(
        'repomate.util.is_git_repo', return_value=True, autospec=True)


@pytest.fixture(autouse=True)
def tmpdir_mock(mocker, tmpdir):
    mock = mocker.patch('tempfile.TemporaryDirectory', autospec=True)
    mock.return_value.__enter__.return_value = str(tmpdir)
    return mock


def assert_raises_on_duplicate_master_urls(function, master_urls, students):
    """Test for functions that take master_urls and students args."""

    master_urls.append(master_urls[0])

    with pytest.raises(ValueError) as exc_info:
        function(master_urls, USER, students, ORG_NAME, GITHUB_BASE_URL)
    assert str(exc_info.value) == "master_repo_urls contains duplicates"


RAISES_ON_EMPTY_ARGS_PARAMETRIZATION = (
    'master_urls, students, user, empty_arg',
    [([], list(STUDENTS), USER, 'master_repo_urls'),
     (list(MASTER_URLS), [], USER, 'students'),
     (list(MASTER_URLS), list(STUDENTS), '', 'user')])

RAISES_ON_EMPTY_ARGS_IDS = [
    "|".join([str(val) for val in line])
    for line in RAISES_ON_EMPTY_ARGS_PARAMETRIZATION[1]
]

RAISES_ON_INVALID_TYPE_PARAMETRIZATION = (
    'user, api, type_error_arg',
    [(3, API, 'user'), ("slarse", 4, 'api')],
)

RAISES_ON_EMPTY_INVALID_TYPE_IDS = [
    "|".join([str(val) for val in line])
    for line in RAISES_ON_INVALID_TYPE_PARAMETRIZATION[1]
]


class TestSetupStudentRepos:
    """Tests for setup_student_repos."""

    @pytest.fixture(autouse=True)
    def is_git_repo_mock(self, mocker):
        return mocker.patch('repomate.util.is_git_repo', return_value=True)

    def test_raises_on_clone_failure(self, master_urls, students, git_mock,
                                     api_mock):
        git_mock.clone_single.side_effect = lambda url, cwd: \
            raise_(exception.CloneFailedError("clone failed", 128, b"some error", url))()

        with pytest.raises(exception.CloneFailedError) as exc_info:
            command.setup_student_repos(master_urls, students, USER, api_mock)

        assert exc_info.value.url == master_urls[0]

    def test_raises_on_duplicate_master_urls(self, mocker, master_urls,
                                             students, api_mock):
        master_urls.append(master_urls[0])

        with pytest.raises(ValueError) as exc_info:
            command.setup_student_repos(master_urls, students, USER, api_mock)
        assert str(exc_info.value) == "master_repo_urls contains duplicates"

    @pytest.mark.parametrize(
        *RAISES_ON_EMPTY_ARGS_PARAMETRIZATION, ids=RAISES_ON_EMPTY_ARGS_IDS)
    def test_raises_empty_args(self, mocker, api_mock, master_urls, user,
                               students, empty_arg):
        """None of the arguments are allowed to be empty."""
        with pytest.raises(ValueError) as exc_info:
            command.setup_student_repos(master_urls, students, user, api_mock)

    @pytest.mark.noapimock
    @pytest.mark.parametrize(
        *RAISES_ON_INVALID_TYPE_PARAMETRIZATION,
        ids=RAISES_ON_EMPTY_INVALID_TYPE_IDS)
    def test_raises_on_invalid_type(self, master_urls, students, user, api,
                                    type_error_arg):
        """Test that the non-itrable arguments are type checked."""
        with pytest.raises(TypeError) as exc_info:
            command.setup_student_repos(master_urls, students, user, api)
        assert type_error_arg in str(exc_info.value)

    def test_happy_path(self, mocker, master_urls, students, api_mock,
                        git_mock, repo_infos, push_tuples,
                        ensure_teams_and_members_mock, tmpdir):
        """Test that setup_student_repos makes the correct function calls."""
        expected_clone_calls = [
            call(url, cwd=str(tmpdir)) for url in master_urls
        ]
        expected_ensure_teams_arg = {
            student: [student]
            for student in students
        }

        command.setup_student_repos(master_urls, students, USER, api_mock)

        git_mock.clone_single.assert_has_calls(expected_clone_calls)
        api_mock.ensure_teams_and_members.assert_called_once_with(
            expected_ensure_teams_arg)
        api_mock.create_repos.assert_called_once_with(repo_infos)
        git_mock.push.assert_called_once_with(push_tuples, user=USER)

    @pytest.mark.skip(msg="Check iterable contents is not yet implemented")
    def test_raises_on_invalid_iterable_contents(self):
        pass


class TestUpdateStudentRepos:
    """Tests for update_student_repos."""

    def test_raises_on_duplicate_master_urls(self, mocker, master_urls,
                                             students, api_mock):
        master_urls.append(master_urls[0])

        with pytest.raises(ValueError) as exc_info:
            command.update_student_repos(master_urls, students, USER, api_mock)
        assert str(exc_info.value) == "master_repo_urls contains duplicates"

    @pytest.mark.parametrize(
        *RAISES_ON_EMPTY_ARGS_PARAMETRIZATION, ids=RAISES_ON_EMPTY_ARGS_IDS)
    def test_raises_empty_args(self, mocker, api_mock, master_urls, user,
                               students, empty_arg):
        """None of the arguments are allowed to be empty."""
        with pytest.raises(ValueError) as exc_info:
            command.update_student_repos(
                master_repo_urls=master_urls,
                students=students,
                user=user,
                api=api_mock)
        assert empty_arg in str(exc_info)

    @pytest.mark.noapimock
    @pytest.mark.parametrize(
        *RAISES_ON_INVALID_TYPE_PARAMETRIZATION,
        ids=RAISES_ON_EMPTY_INVALID_TYPE_IDS)
    def test_raises_on_invalid_type(self, master_urls, students, user, api,
                                    type_error_arg):
        """Test that the non-itrable arguments are type checked."""
        with pytest.raises(TypeError) as exc_info:
            command.update_student_repos(master_urls, students, user, api)
        assert type_error_arg in str(exc_info.value)

    @pytest.mark.skip(
        msg="as get_repo_urls generates urls instead of fetching, "
        "a separate checking of each individual url is required for this feature"
    )
    def test_raises_when_no_student_repos_are_found(
            self, master_urls, master_names, students, api_mock):
        """Test that an APIError is raised if no student repos corresponding to
        the master repos are found.
        """
        # only master urls are found
        # TODO this is incorrect for how get_repo_urls currently works, it returns
        # a single list now
        api_mock.get_repo_urls.side_effect = lambda repo_names:\
                ([GENERATE_REPO_URL(name)
                    for name in repo_names
                    if name in master_names], [])

        with pytest.raises(exception.APIError) as exc_info:
            command.update_student_repos(master_urls, students, USER, api_mock)

    @pytest.mark.skip(msg="Checking if repos exist is not implemented anymore")
    def test_does_not_raise_when_some_student_repos_are_not_found(
            self, api_mock, git_mock, master_urls, master_names, students,
            tmpdir):
        """Test that update_student_repos does not raise if at least
        one student repo is found.
        """
        # only one of the student repos is found, but all master repos are found
        found_repo_name = util.generate_repo_name(students[2], master_names[1])
        not_found_repo_names = [
            util.generate_repo_name(students[i], master_names[j])
            for i in range(len(students)) for j in range(len(master_names))
            if not (i == 2 and j == 1)
        ]
        api_mock.get_repo_urls.side_effect = lambda repo_names: \
                ([GENERATE_REPO_URL(name)
                    for name in repo_names
                    if name in (*master_names, found_repo_name)], not_found_repo_names)

        push_tuples = [
            git.Push(
                local_path=os.path.join(str(tmpdir), master_names[1]),
                repo_url=GENERATE_TEAM_REPO_URL(students[2], master_names[1]),
                branch='master')
        ]

        command.update_student_repos(master_urls, students, USER, api_mock)

        git_mock.push.assert_called_once_with(push_tuples, user=USER)

    def test_happy_path(self, git_mock, master_urls, students, api_mock,
                        push_tuples, rmtree_mock, tmpdir):
        """Test that update_student_repos makes the correct function calls.
        
        NOTE: Ignores the git mock.
        """
        expected_clone_calls = [
            call(url, cwd=str(tmpdir)) for url in master_urls
        ]

        api_mock.get_repo_urls.side_effect = lambda repo_names: \
            list(map(GENERATE_REPO_URL, repo_names))

        command.update_student_repos(master_urls, students, USER, api_mock)

        git_mock.clone_single.assert_has_calls(expected_clone_calls)
        git_mock.push.assert_called_once_with(push_tuples, user=USER)

    @pytest.mark.nogitmock
    @pytest.mark.parametrize(
        'issue',
        [tuples.Issue("Oops", "Sorry, we failed to push to your repo!"), None])
    def test_issues_on_exceptions(self, issue, mocker, api_mock, repo_infos,
                                  push_tuples, rmtree_mock):
        """Test that issues are opened in repos where pushing fails, if and only if
        the issue is not None.
        
        IMPORTANT NOTE: the git_mock fixture is ignored in this test. Be careful.
        """
        students = list('abc')
        master_name = 'week-1'
        master_urls = [
            'https://some-host/repos/{}'.format(name)
            for name in [master_name, 'week-3']
        ]


        generate_url = lambda repo_name: "{}/{}/{}".format(GITHUB_BASE_URL, ORG_NAME, repo_name)
        fail_repo_names = [
            util.generate_repo_name(stud, master_name) for stud in ['a', 'c']
        ]
        fail_repo_urls = [generate_url(name) for name in fail_repo_names]

        api_mock.get_repo_urls.side_effect = lambda repo_names: [generate_url(name) for name in repo_names]

        async def raise_specific(pt, user):
            if pt.repo_url in fail_repo_urls:
                raise exception.PushFailedError("Push failed", 128,
                                                b"some error", pt.repo_url)

        git_push_async_mock = mocker.patch(
            'repomate.git._push_async', side_effect=raise_specific)
        git_clone_mock = mocker.patch('repomate.git.clone_single')

        command.update_student_repos(master_urls, students, USER, api_mock,
                                     issue)

        if issue:  # expect issue to be opened
            call_list = api_mock.open_issue.call_args_list
            call = call_list[0]
            args = call[0]
            assert len(call_list) == 1
            assert args[0] == issue
            assert sorted(args[1]) == sorted(fail_repo_names)
        else:  # expect issue not to be opened
            assert not api_mock.open_issue.called

    @pytest.mark.nogitmock
    def test_issues_arent_opened_on_exceptions_if_unspeficied(
            self, mocker, api_mock, repo_infos, push_tuples, rmtree_mock):
        """Test that issues are not opened in repos where pushing fails, no
        issue has been given.
        
        IMPORTANT NOTE: the git_mock fixture is ignored in this test. Be careful.
        """
        students = list('abc')
        master_name = 'week-1'
        master_urls = [
            'https://some-host/repos/{}'.format(name)
            for name in [master_name, 'week-3']
        ]

        generate_url = lambda repo_name: "{}/{}/{}".format(GITHUB_BASE_URL, ORG_NAME, repo_name)
        fail_repo_names = [
            util.generate_repo_name(stud, master_name) for stud in ['a', 'c']
        ]
        fail_repo_urls = [generate_url(name) for name in fail_repo_names]

        api_mock.get_repo_urls.side_effect = lambda repo_names: [generate_url(name) for name in repo_names]
        issue = tuples.Issue("Oops", "Sorry, we failed to push to your repo!")

        async def raise_specific(pt, branch):
            if pt.repo_url in fail_repo_urls:
                raise exception.PushFailedError("Push failed", 128,
                                                b"some error", repo_url)

        git_push_async_mock = mocker.patch(
            'repomate.git._push_async', side_effect=raise_specific)
        git_clone_mock = mocker.patch('repomate.git.clone_single')

        command.update_student_repos(master_urls, students, USER, api_mock)

        assert not api_mock.open_issue.called


class TestOpenIssue:
    """Tests for open_issue."""

    # TODO expand to also test org_name and github_api_base_url
    # can probably use the RAISES_ON_EMPTY_ARGS_PARAMETRIZATION for that,
    # somehow
    @pytest.mark.parametrize('master_repo_names, students, empty_arg', [
        ([], list(STUDENTS), 'master_repo_names'),
        (list(MASTER_NAMES), [], 'students'),
    ])
    def test_raises_on_empty_args(self, api_mock, master_repo_names, students,
                                  empty_arg):
        with pytest.raises(ValueError) as exc_info:
            command.open_issue(ISSUE, master_repo_names, students, api_mock)
        assert empty_arg in str(exc_info)

    def test_happy_path(self, mocker, api_mock):
        title = "Best title"
        body = "This is some **cool** markdown\n\n### Heading!"
        master_names = ['week-1', 'week-2']
        students = list('abc')
        expected_repo_names = [
            'a-week-1', 'b-week-1', 'c-week-1', 'a-week-2', 'b-week-2',
            'c-week-2'
        ]

        issue = tuples.Issue(
            "A title", "And a nice **formatted** body\n### With headings!")
        command.open_issue(issue, master_names, students, api_mock)

        api_mock.open_issue.assert_called_once_with(issue, expected_repo_names)


class TestCloseIssue:
    """Tests for close_issue."""

    @pytest.mark.parametrize('master_repo_names, students, empty_arg', [
        ([], list(STUDENTS), 'master_repo_names'),
        (list(MASTER_NAMES), [], 'students'),
    ])
    def test_raises_on_empty_args(self, api_mock, master_repo_names, students,
                                  empty_arg):
        """only the regex is allowed ot be empty."""
        with pytest.raises(ValueError) as exc_info:
            command.close_issue('someregex', master_repo_names, students,
                                api_mock)
        assert empty_arg in str(exc_info)

    @pytest.mark.noapimock
    @pytest.mark.parametrize('title_regex, api, type_error_arg', [
        (2, API, 'title_regex'),
        ("someregex", 41, 'api'),
    ])
    def test_raises_on_invalid_type(self, master_names, students, title_regex,
                                    api, type_error_arg):
        """Test that the non-itrable arguments are type checked."""
        with pytest.raises(TypeError) as exc_info:
            command.close_issue(title_regex, master_names, students, api)
        assert type_error_arg in str(exc_info.value)

    def test_happy_path(self, api_mock):
        title_regex = r"some-regex\d\w"
        master_names = ['week-1', 'week-2']
        students = list('abc')
        expected_repo_names = [
            'a-week-1', 'b-week-1', 'c-week-1', 'a-week-2', 'b-week-2',
            'c-week-2'
        ]

        command.close_issue(title_regex, master_names, students, api_mock)

        api_mock.close_issue.assert_called_once_with(title_regex,
                                                     expected_repo_names)


class TestCloneRepos:
    """Tests for clone_repos."""

    @pytest.fixture
    def register_default_plugins(self, config_mock):
        modules = plugin.load_plugin_modules(str(config_mock))
        plugin.register_plugins(modules)

    @pytest.fixture
    def act_hook_mocks(self, monkeypatch, config_mock):
        """Mocks for the act_on_cloned_repo functions and method. This is a bit
        messy as the functions must be marked with the
        repomate_plug.repomate_hook decorator to be picked up by pluggy.
        """
        javac_hook = MagicMock(
            spec='repomate.ext.javac.JavacCloneHook._class.act_on_cloned_repo',
            return_value=HookResult('javac', Status.SUCCESS, 'Great success!'))
        pylint_hook = MagicMock(
            spec='repomate.ext.pylint.act_on_cloned_repo',
            return_value=HookResult('pylint', Status.WARNING,
                                    'Minor warning.'))

        @repomate_hook
        def act_hook_func(path):
            return pylint_hook(path)

        @repomate_hook
        def act_hook_meth(self, path):
            return javac_hook(self, path)

        monkeypatch.setattr(
            'repomate.ext.javac.JavacCloneHook.act_on_cloned_repo',
            act_hook_meth)
        monkeypatch.setattr('repomate.ext.pylint.act_on_cloned_repo',
                            act_hook_func)

        modules = plugin.load_plugin_modules(str(config_mock))
        plugin.register_plugins(modules)

        return javac_hook, pylint_hook

    @pytest.fixture
    def get_plugin_names_mock(self, mocker):
        return mocker.patch(
            'repomate.config.get_plugin_names', return_value=PLUGINS)

    @pytest.mark.parametrize('master_repo_names, students, empty_arg',
                             [([], list(STUDENTS), 'master_repo_names'),
                              (list(MASTER_NAMES), [], 'students')])
    def test_raises_on_empty_args(self, api_mock, master_repo_names, students,
                                  empty_arg):
        with pytest.raises(ValueError) as exc_info:
            command.clone_repos(master_repo_names, students, api_mock)
        assert empty_arg in str(exc_info)

    def test_happy_path(self, api_mock, git_mock, master_names, students):
        """Tests that the correct calls are made when there are no errors."""
        expected_urls = [
            GENERATE_REPO_URL(name)
            for name in util.generate_repo_names(students, master_names)
        ]
        command.clone_repos(master_names, students, api_mock)

        git_mock.clone.assert_called_once_with(expected_urls)

    def test_executes_act_hooks(self, api_mock, git_mock, master_names,
                                students, act_hook_mocks):
        javac_hook, pylint_hook = act_hook_mocks
        repo_names = util.generate_repo_names(students, master_names)
        expected_pylint_calls = [
            call(os.path.abspath(repo_name)) for repo_name in repo_names
        ]
        expected_javac_calls = [
            call(ANY, os.path.abspath(repo_name)) for repo_name in repo_names
        ]

        with patch('os.listdir', return_value=repo_names):
            command.clone_repos(master_names, students, api_mock)

        javac_hook.assert_has_calls(expected_javac_calls, any_order=True)
        pylint_hook.assert_has_calls(expected_pylint_calls)


class TestMigrateRepo:
    """Tests for migrate_repo."""

    @pytest.mark.parametrize('master_repo_urls, user, , empty_arg',
                             [([], USER, 'master_repo_urls'),
                              (['https://some_url'], '', 'user')])
    def test_raises_on_empty_args(self, api_mock, master_repo_urls, user,
                                  empty_arg):
        with pytest.raises(ValueError) as exc_info:
            command.migrate_repos(master_repo_urls, user, api_mock)
        assert empty_arg in str(exc_info)

    @pytest.mark.nogitmock
    def test_happy_path(self, mocker, api_mock, ensure_teams_and_members_mock,
                        tmpdir):
        """Test that the correct calls are made to the api and git.
        
        IMPORTANT: Note that this test ignores the git mock. Be careful.
        """
        master_urls = [
            "https://some-url-to-/master/repos/week-1",
            "https://some-url-to-/master/repos/week-5"
        ]
        master_names = [util.repo_name(url) for url in master_urls]
        expected_push_urls = [GENERATE_REPO_URL(name) for name in master_names]
        expected_pts = [
            git.Push(
                local_path=os.path.join(str(tmpdir), name),
                repo_url=url,
                branch='master')
            for name, url in zip(master_names, expected_push_urls)
        ]
        expected_clone_calls = [
            call(url, cwd=str(tmpdir)) for url in master_urls
        ]

        api_mock.create_repos.side_effect = lambda infos: [GENERATE_REPO_URL(info.name) for info in infos]
        git_clone_mock = mocker.patch(
            'repomate.git.clone_single', autospec=True)
        git_push_mock = mocker.patch('repomate.git.push', autospec=True)

        command.migrate_repos(master_urls, USER, api_mock)

        git_clone_mock.assert_has_calls(expected_clone_calls)
        assert api_mock.create_repos.called
        api_mock.ensure_teams_and_members.assert_called_once_with({
            command.MASTER_TEAM: []
        })
        git_push_mock.assert_called_once_with(expected_pts, user=USER)


class TestListIssues:
    """Tests for list_issues. Since this is essentially just a print command,
    it is only tested for stability.
    """

    @pytest.mark.parametrize('state', ('open', 'closed', 'all'))
    @pytest.mark.parametrize('regex', ('', r'^.*$'))
    @pytest.mark.parametrize('show_body', (True, False))
    def test_happy_path(self, master_names, students, api_mock, state, regex,
                        show_body):
        command.list_issues(
            master_names,
            students,
            api_mock,
            state=state,
            title_regex=regex,
            show_body=show_body)

        api_mock.get_issues.assert_called_once_with(
            list(STUDENT_REPO_NAMES), state, regex)
