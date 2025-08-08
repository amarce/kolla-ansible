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
reloads systemd.

When unit files are present, the ``service-start-order`` role waits for the
previous container to report a ``healthy`` state via
``podman inspect --format '{{.State.Health.Status}}'`` before starting the next
service. If the check does not report ``healthy`` within
``kolla_service_start_wait_seconds`` seconds (45 by default), the startup
continues.
