============================
Distributing Kolla secrets
============================

Kolla Ansible can distribute service specific secret files from the deploy host
to target nodes. Secrets are synchronised automatically during
``bootstrap-servers``, ``deploy``, ``deploy-containers``, ``reconfigure`` and
``upgrade``. Files placed under ``/etc/kolla/config/secrets/<group>/`` on the
control host will be copied to ``/etc/kolla/secrets/<group>/`` on hosts that
belong to the matching inventory group.

The source and destination directories can be customised with the variables
``kolla_secrets_src`` (default ``/etc/kolla/config/secrets``) and
``kolla_secrets_dest`` (default ``/etc/kolla/secrets``).
Secret directories are matched to inventory groups based on their name. This
behaviour can be overridden with ``kolla_secrets_group_map`` which maps a
secret directory to one or more inventory groups.

Destination directories are created with permissions ``0700``. Private keys
such as ``gitlab_key`` are written with mode ``0600``. Public keys and files
like ``known_hosts`` are written with mode ``0644``.

Example:

.. code-block:: text

    /etc/kolla/config/secrets/compute/gitlab_key
    /etc/kolla/config/secrets/compute/gitlab_key.pub
    /etc/kolla/config/secrets/compute/known_hosts

When executing any of the above commands the files will be available on all
hosts in the ``compute`` group:

.. code-block:: text

    /etc/kolla/secrets/compute/gitlab_key
    /etc/kolla/secrets/compute/gitlab_key.pub
    /etc/kolla/secrets/compute/known_hosts

Empty secret directories are skipped but a debug message is logged. The
distribution can also be triggered manually using the
``kolla-ansible distribute-secrets`` command.
