.. _gitlab:

RepoBee and GitLab
******************

As of v2.3.0, RepoBee fully supports GitLab for all commands, both on
https://gitlab.com and on self-hosted GitLab instances. The functionality is
new, so please report any bugs you find on the
`issue tracker <https://github.com/repobee/repobee/issues/new>`. All of
RepoBee's system tests run against a GitLab instances, so we have every intention
of continuing to improve the GitLab experience.

.. note::

   GitLab support is currently in alpha, and may not yet be sufficiently stable
   for production use. Please report any issues on the `issue tracker
   <https://github.com/repobee/repobee/issues/new>`_

.. important::

   RepoBee requires GitLab 11.11 or later. This is only relevant if you have
   a self-hosted GitLab instance.


GitLab terminology
==================

RepoBee uses GitHub terminology, as GitHub is the primary platform. It is
however simple to map the terminology between the two platforms as follows:

============  ========
GitHub        GitLab
============  ========
Organization  Group
Team          Subgroup
Repository    Project
Issue         Issue
============  ========

So, if you read "target organization" in the documentation, that translates
directly to "target group" when using GitLab. Although there are a few
practical differences, the concepts on both platforms are similar enough that
it makes no difference as far as using RepoBee goes. You can read more about
differences and similarities in this `GitLab blog post`_.

How to use RepoBee with GitLab
==============================

You must use the ``gitlab`` plugin for RepoBee to be able to interface with
GitLab. See :ref:`configure_plugs` for instructions on how to use plugins.
Provide the url to a GitLab instance host (*not* to the api endpoint, just to
the host) as an argument to ``--bu|--base-url``, or put it in the config file as
the value for option ``base_url``. Other than that, there are a few important
differences between GitHub and GitLab that the user should be aware of.

* As noted, the base url should be provided to the host of the GitLab instance,
  and not to any specific endpoint (as is the case when using GitHub). When
  using ``github.com`` for example, the url should be provided as
  ``base_url = https://gitlab.com`` in the config.
* The ``org-name`` and ``template-org-name`` arguments should be given the *path*
  of the respective groups. If you create a group with a long name, GitLab may
  shorten the path automatically. For example, I created the group
  ``repobee-master-repos``, and it got the path ``repobee-master``. You can find
  your path by going to the landing page of your group and checking the URL: the
  path is the last part. You can change the path manually by going to your
  group, then `Settings->General->Path,transfer,remove` and changing the group
  path.

.. _gitlab access token:

Getting an access token for GitLab
----------------------------------

Creating a personal access token token for a GitLab API is just as easy as
creating one for GitHub. Just follow `these instructions
<https://docs.gitlab.com/ee/user/profile/personal_access_tokens.html>`_.  The
scopes you need to tick are ``api``, ``read_user``, ``read_repository`` and
``write_repository``. That's it!

.. _`GitLab blog post`: https://about.gitlab.com/2017/09/11/comparing-confusing-terms-in-github-bitbucket-and-gitlab/
