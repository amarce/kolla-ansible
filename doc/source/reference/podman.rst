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

Operators can further suppress actions for specific containers by setting
``service_check_exclude_services`` to a list of container names. Any container
listed there is ignored by the ``service-check-containers`` role even if the
unit file is missing or the container is stopped.


Container creation ordering
---------------------------

Each role now guarantees container creation before any systemd or
post-configuration steps run. The ``service-check-containers`` role invokes the
shared ``_ensure_service_container`` helper whenever a container is missing and
immediately re-checks for its presence. As a result, Podman systemd unit
generation and subsequent post-configuration logic always see the container in
place. The ensure step also ignores the historical ``service.iterate`` gate, so
first-time container creation is not skipped when a service definition declares
iteration metadata.

When a container drifts or disappears between executions, the
``service-check-containers`` handler path recreates it using the same helper
before attempting restarts. This behaviour is consistent for all services,
including those with custom restart handlers such as Open vSwitch, ensuring that
queued service-check actions always result in a running container before unit or
post-config tasks resume.


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
The restart handlers honour the verified action queue assembled by the
``service-check-containers`` role, so a ``Restart <service> container``
notification is emitted only when a recreate or start is actually required.
The handler name is constructed directly from the service definition to avoid
regex backreferences such as ``\1`` leaking into the notification and to fail
early if a malformed service name is queued for processing.
When ``kolla_podman_use_systemd`` is ``false`` those notifications are suppressed
entirely to avoid referencing non-existent systemd units; container lifecycle is
managed directly through the Podman client instead.
