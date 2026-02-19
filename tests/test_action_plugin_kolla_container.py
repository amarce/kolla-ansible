from importlib.machinery import SourceFileLoader
import os
from unittest import mock


this_dir = os.path.dirname(__file__)
plugin_file = os.path.join(
    this_dir, '..', 'ansible', 'action_plugins', 'kolla_container.py'
)
plugin = SourceFileLoader('kolla_container_action', plugin_file).load_module()


@mock.patch('ansible.plugins.action.ActionBase.run', return_value={})
def test_changed_container_is_queued(mock_run):
    action = plugin.ActionModule.__new__(plugin.ActionModule)
    action._task = mock.Mock(args={'name': 'nova-api'})
    action._execute_module = mock.Mock(return_value={'changed': True})

    result = action.run(task_vars={'kolla_changed_containers': []})

    assert result['ansible_facts']['kolla_changed_containers'] == ['nova_api']
    assert result['ansible_facts_cacheable'] is True


@mock.patch('ansible.plugins.action.ActionBase.run', return_value={})
def test_unchanged_container_is_not_queued(mock_run):
    action = plugin.ActionModule.__new__(plugin.ActionModule)
    action._task = mock.Mock(args={'name': 'nova-api'})
    action._execute_module = mock.Mock(return_value={'changed': False})

    result = action.run(task_vars={'kolla_changed_containers': []})

    assert 'ansible_facts' not in result
    assert 'ansible_facts_cacheable' not in result
