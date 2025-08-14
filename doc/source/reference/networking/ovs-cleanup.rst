.. _ovs-cleanup:

=========================
Neutron OVS cleanup
=========================

Kolla Ansible deploys a ``neutron-ovs-cleanup`` container on hosts running the
``neutron-openvswitch-agent`` service. The container removes stale Open
vSwitch ports that may remain after a reboot.

Operation
---------

During deployment the container runs once per host boot. After completing the
cleanup it exits and remains stopped for manual reuse. The container itself
creates a marker file ``/tmp/kolla/neutron_ovs_cleanup_marker/done`` to prevent
further automatic executions until the host is rebooted. If the container
configuration changes, the playbook recreates the container so the updated
settings will be applied on the next run, but the container does not execute
again while the marker file exists. Because ``/tmp`` is an ephemeral
filesystem, the container recreates ``/tmp/kolla`` with mode ``1777``
and copies the cleanup script to ``/tmp/kolla/neutron_ovs_cleanup``
each time it starts so that the non-root ``neutron`` user can write to it.
The marker path can be changed by overriding the variable
``neutron_ovs_cleanup_marker_file``.

The container executes the cleanup script as root directly, avoiding
any reliance on ``sudo`` or interactive prompts.  It now explicitly
runs as the root user so that ``kolla_set_configs`` can create and
populate ``/etc/kolla/defaults`` before the cleanup script runs.

The container reads its configuration from
``/etc/kolla/neutron-ovs-cleanup/config.json`` before the cleanup
script runs.  To ensure this is always accessible, Kolla Ansible creates
the configuration directory with ``0755`` permissions and installs the
``config.json`` file with mode ``0644``.

The container forms part of the compute service start sequence. The
``service-start-order`` role configures systemd dependencies so that the
``neutron_openvswitch_agent`` unit waits for the cleanup to complete. When
Podman is used these dependencies reference
``container-neutron_ovs_cleanup.service`` and
``container-neutron_openvswitch_agent.service`` units.
Once the marker file is present the role skips restarting the cleanup
container and does not wait for it to start.

Manual execution
----------------

The container can be started manually if needed. For example with Docker:

.. code-block:: console

   docker start -a neutron_ovs_cleanup

Or with Podman:

.. code-block:: console

   podman start -a neutron_ovs_cleanup

To force automatic execution again remove the marker file:

.. code-block:: console

   sudo rm /tmp/kolla/neutron_ovs_cleanup_marker/done
