Podman Compatibility
====================

Kolla Ansible supports deployments with Podman.  Podman 4.9 renamed
some fields returned by ``podman inspect``.  ``PidMode`` became
``PidNS`` and ``CgroupnsMode`` became ``CgroupNS``.  Kolla Ansible now
accepts either name when comparing containers and passes the correct
``--pid`` and ``--cgroupns`` options to ``podman`` when creating
containers.
