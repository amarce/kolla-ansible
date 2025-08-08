============================
Podman Container Management
============================

Some Kolla Ansible containers may be started outside of systemd and therefore
lack a corresponding ``container-<name>.service`` unit. A common example is
``kolla_toolbox``, which is launched during bootstrap and left running.

The ``service-check-containers`` and ``service-start-order`` roles manage
containers through their systemd units. Unit files may reside in either
``/etc/systemd/system`` or ``/usr/lib/systemd/system`` and are detected in both
locations. If a running container lacks a unit file, ``service-start-order``
uses ``podman generate systemd`` to create one in ``/etc/systemd/system`` and
reloads systemd.  Containers started via the Podman REST API do not store a
``CreateCommand`` and Podman ``generate systemd --new`` rejects them.  The role
attempts generation with ``--new`` first and falls back to generating a unit
without it so that both CLI- and REST-created containers receive systemd units.

When a service is not deployed on a host, and its container and corresponding
systemd unit are absent or disabled, ``service-check-containers`` skips any
restart or enablement attempts. This allows staged deployments where only a
subset of services are present without causing unnecessary failures.

When unit files are present, the ``service-start-order`` role waits for the
previous container to report a ``healthy`` state via
``podman inspect --format '{{.State.Health.Status}}'`` before starting the next
service. If the check does not report ``healthy`` within
``kolla_service_start_wait_seconds`` seconds (45 by default), the startup
continues. To prevent deadlocks at boot the role also verifies that the
resulting systemd dependency graph is acyclic by running
``systemd-analyze verify`` on the generated units.
