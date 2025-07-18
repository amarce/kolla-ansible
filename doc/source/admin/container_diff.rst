========================
Container configuration diff
========================

``kolla_container`` now reports container changes using the Ansible diff
mechanism.  When running a playbook with ``--diff`` any container that
would be recreated shows a unified diff of the relevant parameters.

Example::

   $ ansible-playbook -i inventory all.yml --diff -t neutron
   ...
   TASK [neutron : Start container neutron_ovs_cleanup]
   --- current
   +++ desired
   @@
   - /usr/local/bin/neutron-ovs-cleanup
   + /usr/local/bin/neutron-ovs-cleanup --debug

Sensitive values are omitted from the output.
