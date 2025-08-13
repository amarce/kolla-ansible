from ansible.plugins.action import ActionBase

class ActionModule(ActionBase):
    """Action plugin to wrap kolla_container module.

    Records names of containers that are created, recreated or otherwise
    changed during a playbook run. Changed container names are normalised to
    use underscores and appended to the ``kolla_changed_containers`` fact so
    that the ``service-start-order`` role can restart them under systemd.
    """

    TRANSFERS_FILES = False

    def run(self, tmp=None, task_vars=None):
        if task_vars is None:
            task_vars = {}
        result = super(ActionModule, self).run(tmp, task_vars)
        module_args = self._task.args.copy()
        name = module_args.get('name')
        action_result = self._execute_module(
            module_name='kolla_container',
            module_args=module_args,
            task_vars=task_vars,
            tmp=tmp,
        )
        result.update(action_result)

        if action_result.get('changed') and name:
            svc = name.replace('-', '_')
            current = task_vars.get('kolla_changed_containers', []) or []
            if svc not in current:
                current.append(svc)
            result.setdefault('ansible_facts', {})['kolla_changed_containers'] = current
        return result
