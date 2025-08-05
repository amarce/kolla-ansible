Podman Compatibility
====================

Kolla Ansible supports deployments with Podman.  Podman 4.9 renamed
some fields returned by ``podman inspect``.  ``PidMode`` became
``PidNS`` and ``CgroupnsMode`` became ``CgroupNS``.  Kolla Ansible now
accepts either name when comparing containers and passes the correct
``--pid`` and ``--cgroupns`` options to ``podman`` when creating
containers.

When using ``*_extra_volumes`` options, Kolla Ansible will automatically
create any missing host directories referenced by bind mounts with
permissions ``0755`` before starting containers.
