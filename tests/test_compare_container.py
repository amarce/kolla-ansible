import sys
from unittest import mock

import pytest

sys.modules['dbus'] = mock.MagicMock()

from ansible.module_utils.kolla_container_worker import ContainerWorker

class DummyModule:
    def __init__(self, **params):
        self.params = {'name': 'test'}
        self.params.update(params)
    def debug(self, msg):
        pass

class DummyWorker(ContainerWorker):
    def __init__(self, **params):
        super().__init__(DummyModule(**params))
    def check_image(self):
        pass
    def get_container_info(self):
        pass
    def check_container(self):
        pass
    def compare_pid_mode(self, container_info):
        pass
    def compare_image(self, container_info=None):
        pass
    def pull_image(self):
        pass
    def remove_container(self):
        pass
    def build_ulimits(self, ulimits):
        out = []
        for name, val in (ulimits or {}).items():
            out.append({'Name': name, 'Soft': val.get('soft'), 'Hard': val.get('hard')})
        return out
    def create_container(self):
        pass
    def recreate_or_restart_container(self):
        pass
    def start_container(self):
        pass
    def stop_container(self):
        pass
    def stop_and_remove_container(self):
        pass
    def restart_container(self):
        pass
    def create_volume(self):
        pass
    def remove_volume(self):
        pass
    def remove_image(self):
        pass
    def ensure_image(self):
        pass

@pytest.fixture
def cw():
    return DummyWorker()


def test_compare_volumes_ignores_empty_strings(cw):
    cw.params['volumes'] = ['a:/a', '', 'b:/b']
    info = {'HostConfig': {'Binds': ['b:/b', 'a:/a']}}
    assert cw.compare_volumes(info) is False


def test_compare_ulimits_order_and_difference(cw):
    desired = [
        {'Name': 'n1', 'Soft': 1, 'Hard': 1},
        {'Name': 'n2', 'Soft': 2, 'Hard': 2},
    ]
    current_same = [
        {'Name': 'n2', 'Soft': 2, 'Hard': 2},
        {'Name': 'n1', 'Soft': 1, 'Hard': 1},
    ]
    current_diff = [
        {'Name': 'n1', 'Soft': 1, 'Hard': 2},
    ]

    assert cw.compare_ulimits(desired, current_same) is False
    assert cw.compare_ulimits(desired, current_diff) is True
