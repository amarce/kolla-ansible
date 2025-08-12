============================
Distributing Kolla secrets
============================

Kolla Ansible can distribute service specific secret files from the deploy host
to target nodes as part of the ``bootstrap-servers`` play. Files placed under
``/etc/kolla/config/secrets/<group>/`` on the control host will be copied to
``/etc/kolla/secrets/<group>/`` on hosts that belong to the matching inventory
group.

The source and destination directories can be customised with the variables
``kolla_secrets_src`` (default ``/etc/kolla/config/secrets``) and
``kolla_secrets_dest`` (default ``/etc/kolla/secrets``).

Destination directories are created with permissions ``0700``. Private keys
such as ``gitlab_key`` are written with mode ``0600``. Public keys and files
like ``known_hosts`` are written with mode ``0644``.

Example:

.. code-block:: text

    /etc/kolla/config/secrets/compute/gitlab_key
    /etc/kolla/config/secrets/compute/gitlab_key.pub
    /etc/kolla/config/secrets/compute/known_hosts

After running ``kolla-ansible bootstrap-servers`` the files will be available
on all hosts in the ``compute`` group:

.. code-block:: text

    /etc/kolla/secrets/compute/gitlab_key
    /etc/kolla/secrets/compute/gitlab_key.pub
    /etc/kolla/secrets/compute/known_hosts

Empty secret directories are skipped but a debug message is logged.
