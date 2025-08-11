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
