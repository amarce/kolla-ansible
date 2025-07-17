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
cleanup it exits and remains stopped for manual reuse. A marker file
``/run/kolla/neutron_ovs_cleanup_done`` is created to prevent the container
from running again until the host is rebooted.

Manual execution
----------------

The container can be started manually if needed. For example with Docker:

.. code-block:: console

   docker start -a neutron_ovs_cleanup

To force automatic execution again remove the marker file:

.. code-block:: console

   sudo rm /run/kolla/neutron_ovs_cleanup_done
