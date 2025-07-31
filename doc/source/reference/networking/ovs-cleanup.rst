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
creates a marker file ``/tmp/kolla/neutron_ovs_cleanup/done`` to prevent
further automatic executions until the host is rebooted. If the container
configuration changes, the playbook recreates the container so the updated
settings will be applied on the next run, but the container does not execute
again while the marker file exists.
The marker path can be changed by overriding the variable
``neutron_ovs_cleanup_marker_file``.

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

   sudo rm /tmp/kolla/neutron_ovs_cleanup/done
