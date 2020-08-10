"""Plugin manager for RepoBee when installed with RepoBee's distribution
tooling.

.. danger::

    This plugin should only be used when using an installed version of RepoBee.
"""
import json
import pathlib
import subprocess
import sys
import textwrap

from typing import Tuple

import tabulate
import bullet

import repobee_plug as plug

from _repobee import disthelpers

PLUGIN = "pluginmanager"

plugin_category = plug.cli.category(
    name="plugin",
    action_names=["install", "uninstall", "list", "activate"],
    help="manage plugins",
    description="Manage plugins.",
)


class ListPluginsCommand(plug.Plugin, plug.cli.Command):
    """Extension command for listing available plugins."""

    __settings__ = plug.cli.command_settings(
        action=plugin_category.list,
        help="list available plugins",
        description="List available plugins. Available plugins are fetched "
        "from https://repobee.org.",
    )

    plugin_name = plug.cli.option(help="A plugin to list detailed info for.")

    def command(self, api: None) -> None:
        """List available plugins."""
        plugins = disthelpers.get_plugins_json()
        installed_plugins = json.loads(
            disthelpers.get_installed_plugins_path().read_text("utf8")
        )

        if not self.plugin_name:
            _list_all_plugins(plugins, installed_plugins)
        else:
            _list_plugin(self.plugin_name, plugins)


class InstallPluginCommand(plug.Plugin, plug.cli.Command):
    """Extension command for installing a plugin."""

    __settings__ = plug.cli.command_settings(
        action=plugin_category.install,
        help="install a plugin",
        description="Install a plugin.",
    )

    def command(self, api: None) -> None:
        """Install a plugin."""
        plugins = disthelpers.get_plugins_json()
        installed_plugins_path = disthelpers.get_installed_plugins_path()
        installed_plugins = json.loads(
            installed_plugins_path.read_text("utf8")
        )

        plug.echo("Available plugins:")
        _list_all_plugins(plugins, installed_plugins)
        name, version = _select_plugin(plugins)

        plug.echo(f"Installing {name}@{version}")
        _install_plugin(name, version, plugins)

        plug.echo(f"Successfully installed {name}@{version}")

        installed_plugins[name] = dict(version=version)
        installed_plugins_path.write_text(json.dumps(installed_plugins))


def _select_plugin(plugins: dict) -> Tuple[str, str]:
    """Interactively select a plugin."""
    selected_plugin_name = bullet.Bullet(
        prompt="Select a plugin to install:", choices=list(plugins.keys())
    ).launch()

    selected_plugin_attrs = plugins[selected_plugin_name]

    _list_plugin(selected_plugin_name, plugins)

    selected_version = bullet.Bullet(
        prompt="Select a version to install:",
        choices=list(selected_plugin_attrs["versions"].keys()),
    ).launch()

    return selected_plugin_name, selected_version


def _install_plugin(name: str, version: str, plugins: dict) -> None:
    install_url = f"git+{plugins[name]['url']}@{version}"

    cmd = [
        str(disthelpers.get_pip_path()),
        "install",
        "--upgrade",
        install_url,
    ]
    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        plug.log.error(proc.stderr.decode(sys.getdefaultencoding()))
        raise plug.PlugError(f"could not install {name} {version}")


class UninstallPluginCommand(plug.Plugin, plug.cli.Command):
    """Extension command for uninstall a plugin."""

    __settings__ = plug.cli.command_settings(
        action=plugin_category.uninstall,
        help="uninstall a plugin",
        description="Uninstall a plugin.",
    )

    def command(self, api: None) -> None:
        """Uninstall a plugin."""
        installed_plugins_path = disthelpers.get_installed_plugins_path()
        installed_plugins = json.loads(
            installed_plugins_path.read_text("utf8")
        )

        if not installed_plugins:
            plug.echo("No plugins installed")
            return

        plug.echo("Installed plugins:")
        _list_installed_plugins(installed_plugins)

        selected_plugin_name = bullet.Bullet(
            prompt="Select a plugin to uninstall:",
            choices=list(installed_plugins.keys()),
        ).launch()

        plug.echo(f"Uninstalling {selected_plugin_name} ...")

        plug.echo(f"Successfully uninstalled {selected_plugin_name}")

        del installed_plugins[selected_plugin_name]
        installed_plugins_path.write_text(
            json.dumps(installed_plugins), encoding="utf8"
        )


def _uninstall_plugin(plugin_name: str) -> None:
    cmd = [
        str(disthelpers.get_pip_path()),
        "uninstall",
        "-y",
        f"repobee-{plugin_name}",
    ]
    proc = subprocess.run(cmd, capture_output=True)

    if proc.returncode != 0:
        plug.log.error(proc.stderr.decode(sys.getdefaultencoding()))
        raise plug.PlugError(f"could not uninstall {plugin_name}")


class ActivatePluginCommand(plug.Plugin, plug.cli.Command):
    """Extension command for activating and deactivating plugins."""

    __settings__ = plug.cli.command_settings(
        action=plugin_category.activate,
        help="activate a plugin",
        description="Activate a plugin.",
    )

    single_file_plugin = plug.cli.option(
        converter=pathlib.Path, help="path to a single-file plugin to activate"
    )

    def command(self, api: None) -> None:
        """Activate a plugin."""
        installed_plugins_path = disthelpers.get_installed_plugins_path()
        installed_plugins = json.loads(
            installed_plugins_path.read_text("utf8")
        )

        if self.single_file_plugin:
            abspath = self.single_file_plugin.resolve(strict=True)
            installed_plugins[str(abspath)] = dict(
                version="local", active=False
            )
        else:
            names = list(installed_plugins.keys())

            if not names:
                plug.echo("No plugins installed")
                return

            default = [
                names.index(name)
                for name, attrs in installed_plugins.items()
                if attrs.get("active")
            ]

            selection = bullet.Check(
                choices=names,
                prompt="Select plugins to activate (space to check/un-check, "
                "enter to confirm selection):",
            ).launch(default=default)

            for name in names:
                installed_plugins[name]["active"] = name in selection

        installed_plugins_path.write_text(json.dumps(installed_plugins))


def _wrap_cell(text: str, width: int = 40) -> str:
    return "\n".join(textwrap.wrap(text, width=width))


def _list_all_plugins(plugins: dict, installed_plugins: dict) -> None:
    headers = ["Name", "Description", "URL", "Latest", "Installed"]
    plugins_table = []
    for plugin_name, attrs in plugins.items():
        latest_version = list(attrs["versions"].keys())[0]
        installed_version = (
            installed_plugins[plugin_name]["version"]
            if plugin_name in installed_plugins
            else "-"
        )
        plugins_table.append(
            [
                plugin_name,
                _wrap_cell(attrs["description"]),
                attrs["url"],
                latest_version,
                installed_version,
            ]
        )

    plug.echo(tabulate.tabulate(plugins_table, headers, tablefmt="fancy_grid"))


def _list_installed_plugins(installed_plugins: dict) -> None:
    headers = ["Name", "Installed version"]
    plugins_table = []
    for plugin_name, attrs in installed_plugins.items():
        plugins_table.append([plugin_name, attrs["version"]])

    plug.echo(
        tabulate.tabulate(
            plugins_table, headers=headers, tablefmt="fancy_grid"
        )
    )


def _list_plugin(plugin_name: str, plugins: dict) -> None:
    attrs = plugins[plugin_name]
    table = [
        ["Name", plugin_name],
        ["Description", _wrap_cell(attrs["description"])],
        ["Versions", _wrap_cell(" ".join(attrs["versions"].keys()))],
        ["URL", attrs["url"]],
    ]
    plug.echo(tabulate.tabulate(table, tablefmt="fancy_grid"))
