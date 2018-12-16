.. _configuration:

Configuration
*************
``repomate`` *must* be configured with a mandatory environment variable (see
oauth_). Additionally, some of the command line parameters can be
pre-configured with e.g. the GitHub instances' API url and the target
organization's name (see `config`_). 

.. important::

    The :ref:`userguide` expects there to be
    a configuration file as described in :ref:`getting_started`.

.. _oauth:

OAUTH token
===================================
For repomate to work at all, it needs access to an OAUTH token. See the `GitHub
OAUTH docs`_ for how to create a token. Make sure that it has the ``repo`` and
``admin:org`` permissions. There are two ways to hand the token to repomate:

1. Put it in the ``REPOMATE_OAUTH`` environment variable.
   - On a unix system, this is as simple as ``export
   REPOMATE_OAUTH=<YOUR_TOKEN>``
2. Put it in the configuration file (see :ref:`config`).

.. _config:

Configuration file
==================
An optional configuration file can be added, specifying defaults for several of
the most frequently used cli options line options. This is especially useful
for teachers ant TAs who are managing repos for a single course (and, as a
consequence, a single organization).

.. code-block:: bash

    [DEFAULTS]
    github_base_url = https://some-api-v3-url
    user = YOUR_USERNAME
    org_name = ORGANIZATION_NAME
    master_org_name = MASTER_ORGANIZATION_NAME
    students_file = STUDENTS_FILE_ABSOLUTE_PATH
    token = SUPER_SECRET_TOKEN

.. important::

    If the configuration file exists, it *must* contain the ``[DEFAULTS]``
    header. This is to minimize the risk of misconfiguration by novice users.

**To find out where to place the configuration file (and what to name it)**,
run ``repomate show-config``. The configuration file can also be used to
configure ``repomate`` plugins. See the :ref:`configure_plugs` section for more
details.

.. important::

    Do note that the configuration file contains only default values. Specifying
    any of the parameters on the command line will override the configuration
    file's values.

.. note::

    You can run ``repomate verify-settings`` to verify the basic configuration.
    This will check the most important settings configurable in ``DEFAULTS``.

.. _`GitHub OAUTH docs`: https://help.github.com/articles/creating-a-personal-access-token-for-the-command-line/
