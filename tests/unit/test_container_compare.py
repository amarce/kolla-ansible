import sys
from unittest import mock

import pytest

sys.modules['dbus'] = mock.MagicMock()
from ansible.module_utils.kolla_container_worker import ContainerWorker


class DummyModule:
    def __init__(self):
        self.params = {}

    def debug(self, msg):
        pass


class DummyWorker(ContainerWorker):
    def __init__(self):
        super().__init__(DummyModule())

    def check_image(self):
        return {}

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

def worker():
    return DummyWorker()


@pytest.mark.parametrize("spec,current,expect_diff", [
    (None, [], False),
    ([], None, False),
    ([], [], False),
    (["SYS_PTRACE"], [], True),
])
def test_compare_cap_add(worker, spec, current, expect_diff):
    worker.params['cap_add'] = spec
    container = {'HostConfig': {'CapAdd': current}}
    assert worker.compare_cap_add(container) is expect_diff


@pytest.mark.parametrize("spec,current,expect_diff", [
    (None, {}, False),
    ({}, None, False),
    ({}, {}, False),
    ({'cpu_quota': 10}, {}, True),
])
def test_compare_dimensions(worker, spec, current, expect_diff):
    worker.params['dimensions'] = spec
    container = {'HostConfig': {'DeviceCgroupRules': current}}
    assert worker.compare_dimensions(container) is expect_diff
