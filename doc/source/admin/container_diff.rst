============================
Container configuration diff
============================

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


Explicit option detection
-------------------------

The ``kolla_container`` module records a tuple of the parameters that were
explicitly provided to the module in the ``_kolla_specified_options`` field.
This metadata is derived from the structure returned by Ansible's
``_load_params`` helper rather than the module defaults, ensuring that
comparisons only consider options the operator actually set. Nested
``common_options`` entries are tracked using dotted keys such as
``common_options.restart_policy`` so that the container workers can
distinguish between implicit defaults and overrides supplied through group
variables. Optional parameters like ``user`` or ``pid_mode`` are omitted from
the tuple when they are not present in the raw module arguments, preventing
false drift reports when a container is running with engine defaults.
