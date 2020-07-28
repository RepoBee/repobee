import os
from unittest import mock

import pytest

import _repobee.constants
from _repobee import config
from _repobee import exception

import constants

STUDENTS = constants.STUDENTS
USER = constants.USER
BASE_URL = constants.BASE_URL
ORG_NAME = constants.ORG_NAME
MASTER_ORG_NAME = constants.MASTER_ORG_NAME
PLUGINS = constants.PLUGINS
CONFIG_TOKEN = constants.CONFIG_TOKEN


class TestGetConfiguredDefaults:
    """Tests for get_configured_defaults"""

    def test_get_configured_defaults_no_config_file(
        self, isfile_mock, unused_path
    ):
        defaults = config.get_configured_defaults(unused_path)
        assert defaults == dict(token=constants.TOKEN)

    def test_get_configured_defaults_empty_file(self, empty_config_mock):
        with pytest.raises(exception.FileError) as exc_info:
            config.get_configured_defaults(str(empty_config_mock))
        assert "does not contain the required [repobee] header" in str(
            exc_info.value
        )

    def test_get_configured_defaults_reads_full_config(
        self, config_mock, students_file, mock_getenv
    ):
        mock_getenv.side_effect = lambda name: None

        defaults = config.get_configured_defaults(str(config_mock))

        assert defaults["user"] == USER
        assert defaults["base_url"] == BASE_URL
        assert defaults["org_name"] == ORG_NAME
        assert defaults["students_file"] == str(students_file)
        assert defaults["plugins"] == ",".join(PLUGINS)
        assert defaults["master_org_name"] == MASTER_ORG_NAME
        assert defaults["token"] == CONFIG_TOKEN

    def test_token_in_env_variable_overrides_configuration_file(
        self, config_mock
    ):
        defaults = config.get_configured_defaults(str(config_mock))
        assert defaults["token"] == constants.TOKEN

    def test_get_configured_defaults_raises_on_invalid_keys(
        self, empty_config_mock, students_file
    ):
        invalid_key = "not_valid_key"
        config_contents = os.linesep.join(
            [
                "[{}]".format(_repobee.constants.CORE_SECTION_HDR),
                "base_url = {}".format(BASE_URL),
                "user = {}".format(USER),
                "org_name = {}".format(ORG_NAME),
                "master_org_name = {}".format(MASTER_ORG_NAME),
                "students_file = {!s}".format(students_file),
                "plugins = {!s}".format(PLUGINS),
                "{} = whatever".format(invalid_key),
            ]
        )
        empty_config_mock.write(config_contents)

        with pytest.raises(exception.FileError) as exc_info:
            config.get_configured_defaults(str(empty_config_mock))

        assert "config file at {} contains invalid default keys".format(
            empty_config_mock
        ) in str(exc_info.value)
        assert str(empty_config_mock) in str(exc_info.value)
        assert invalid_key in str(exc_info.value)

    def test_get_configured_defaults_raises_on_missing_header(
        self, empty_config_mock, students_file
    ):
        config_contents = os.linesep.join(
            [
                "base_url = {}".format(BASE_URL),
                "user = {}".format(USER),
                "org_name = {}".format(ORG_NAME),
                "students_file = {!s}".format(students_file),
            ]
        )
        empty_config_mock.write(config_contents)

        with pytest.raises(exception.FileError) as exc_info:
            config.get_configured_defaults(str(empty_config_mock))

        assert "does not contain the required [repobee] header" in str(
            exc_info.value
        )


class TestGetPluginNames:
    """Tests for get_plugin_names."""

    def test_with_full_config(self, config_mock):
        """Test that plugins are read correctly from a full config file."""
        plugin_names = config.get_plugin_names(str(config_mock))

        assert plugin_names == PLUGINS

    @pytest.mark.parametrize(
        "plugins_string, expected_plugins",
        [
            (",".join(PLUGINS), PLUGINS),
            (", ".join(PLUGINS), PLUGINS),
            ("javac", ["javac"]),
            ("", []),
        ],
    )
    def test_with_only_plugins(
        self, plugins_string, expected_plugins, empty_config_mock
    ):
        contents = os.linesep.join(
            [
                "[{}]".format(_repobee.constants.CORE_SECTION_HDR),
                "plugins = " + plugins_string,
            ]
        )
        empty_config_mock.write(contents)

        plugin_names = config.get_plugin_names(str(empty_config_mock))

        assert plugin_names == expected_plugins


class TestExecuteConfigHooks:
    """Tests for execute_config_hooks."""

    def test_with_no_config_file(self, unused_path, plugin_manager_mock):
        config.execute_config_hooks(config_file=unused_path)
        assert not plugin_manager_mock.hook.config_hook.called

    def test_with_config_file(self, config_mock, plugin_manager_mock):
        config.execute_config_hooks(str(config_mock))

        # TODO assert with a real value instead of mock.ANY
        plugin_manager_mock.hook.config_hook.assert_called_once_with(
            config_parser=mock.ANY
        )


class TestCheckConfigIntegrity:
    """Tests for check_config_integroty."""

    def test_with_well_formed_config(self, config_mock):
        """This should just not raise."""
        config.check_config_integrity(str(config_mock))

    def test_with_well_formed_plugin_options(self, config_mock):
        """Should not raise."""
        config_mock.write(
            os.linesep
            + os.linesep.join(["[some_config]", "option = value", "bla = blu"])
        )

    def test_with_no_config_file_raises(self, unused_path):
        with pytest.raises(exception.FileError) as exc_info:
            config.check_config_integrity(config_file=unused_path)

        assert str(unused_path) in str(exc_info.value)

    def test_with_invalid_defaults_key_raises(self, empty_config_mock):
        empty_config_mock.write(
            os.linesep.join(
                [
                    "[{}]".format(_repobee.constants.CORE_SECTION_HDR),
                    "user = someone",
                    "option = value",
                ]
            )
        )
        with pytest.raises(exception.FileError) as exc_info:
            config.check_config_integrity(str(empty_config_mock))

        assert "config file at {} contains invalid default keys".format(
            empty_config_mock
        ) in str(exc_info.value)
        assert "option" in str(exc_info.value)
        assert "user" not in str(exc_info.value)

    def test_with_valid_but_malformed_default_args_raises(
        self, empty_config_mock
    ):
        empty_config_mock.write(
            os.linesep.join(
                [
                    "[{}]".format(_repobee.constants.CORE_SECTION_HDR),
                    "user = someone",
                    "base_url",
                    "org_name = cool",
                    "plugins  ",
                ]
            )
        )
        with pytest.raises(exception.FileError) as exc_info:
            config.check_config_integrity(str(empty_config_mock))

        assert "user" not in str(exc_info.value)
        assert "org_name" not in str(exc_info.value)
        assert "base_url" in str(exc_info.value)
        assert "plugins" in str(exc_info.value)
