============================
Podman Container Management
============================

Some Kolla Ansible containers may be started outside of systemd and therefore
lack a corresponding ``container-<name>.service`` unit. A common example is
``kolla_toolbox``, which is launched during bootstrap and left running.

The ``service-check-containers`` role verifies that containers and their
systemd units are active. When using Podman, the role now checks for the
presence of a unit file before attempting to manage it. If no unit file is
found, systemd operations are skipped and the container is assumed to be
running as-is.

.. note::

   This behaviour ensures deployments succeed even when containers such as
   ``kolla_toolbox`` are running without a systemd unit.
