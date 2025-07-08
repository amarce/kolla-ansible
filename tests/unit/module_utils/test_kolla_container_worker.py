import sys
from unittest import mock

import pytest

from ansible.module_utils.kolla_container_worker import ContainerWorker

sys.modules['dbus'] = mock.MagicMock()


class DummyModule:
    def __init__(self):
        self.params = {'name': None}

    def debug(self, msg):
        pass


class DummyWorker(ContainerWorker):
    def __init__(self):
        super().__init__(DummyModule())

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

    def compare_volumes(self, container_info):
        pass

    def pull_image(self):
        pass

    def remove_container(self):
        pass

    def build_ulimits(self, ulimits):
        pass

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


@pytest.mark.parametrize("expected,actual,match", [
    ([], None, True),
    (["SYS_PTRACE"], ["SYS_PTRACE"], True),
    (["A"], ["B"], False),
])
def test_compare_cap_add(expected, actual, match, cw):
    cw.params['cap_add'] = expected
    container = {'HostConfig': {'CapAdd': actual}}
    assert cw.compare_cap_add(container) is (not match)


def test_compare_dimensions_none_equals_empty(cw):
    cw.params['dimensions'] = {}
    container = {'HostConfig': {'Resources': None}}
    assert cw.compare_dimensions(container) is False
