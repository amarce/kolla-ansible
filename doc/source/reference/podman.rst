============================
Podman Container Management
============================

When using Podman, systemd unit files are generated as
``container-<name>.service`` for each managed container. This differs from
Docker where unit files are named ``kolla-<name>-container.service``.

Some Kolla Ansible containers may be started outside of systemd and therefore
lack a corresponding unit. A common example is ``kolla_toolbox``, which is
launched during bootstrap and left running.

The ``service-check-containers`` and ``service-start-order`` roles verify and
start containers via their systemd units. When using Podman, these roles check
for the presence of a unit file before attempting any systemd operation. If no
unit file is found, systemd actions are skipped and the container is assumed to
be running as-is.

.. note::

   This behaviour ensures deployments succeed even when containers such as
   ``kolla_toolbox`` are running without a systemd unit, both during service
   checks and while applying start-order sequencing.


Reconfigure behaviour
---------------------

When Podman containers are managed through systemd units
(``kolla_podman_use_systemd: true``), ``kolla-ansible reconfigure`` no longer
interprets differences in Podman's implicit restart policy as container drift.
The ``service-check-containers`` role now ignores the ``RestartPolicy`` settings
reported by Podman and compares only the container image, configuration,
healthcheck, and other explicit runtime options.

Operators should ensure ``kolla_podman_use_systemd`` is set to ``true`` in
``/etc/kolla/globals.yml`` when systemd units are used to supervise Podman
containers. With this setting enabled, reconfigure operations leave containers
running unless a configuration, image, or healthcheck change is detected.
