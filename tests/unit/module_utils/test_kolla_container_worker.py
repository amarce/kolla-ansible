from unittest import mock

import pytest
import sys

from ansible.module_utils.kolla_container_worker import (
    ContainerWorker,
    _normalise_container_info,
)

sys.modules['dbus'] = mock.MagicMock()


class DummyModule:
    def __init__(self):
        self.params = {'name': None}

    def debug(self, msg):
        pass

    def exit_json(self, **kwargs):
        raise AssertionError(f"Unexpected exit_json: {kwargs}")


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
    worker = DummyWorker()
    worker.params['container_engine'] = 'docker'
    return worker


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
    container = {'HostConfig': {'DeviceCgroupRules': None}}
    assert cw.compare_dimensions(container) is False


def test_compare_security_opt_ignores_podman_default(cw):
    cw.params.update({'container_engine': 'podman', 'security_opt': []})
    container = {'HostConfig': {'SecurityOpt': ['unmask=all']}}
    assert cw.compare_security_opt(container) is False


def test_compare_restart_policy_ignored_with_systemd(cw):
    cw.params.update({
        'container_engine': 'podman',
        'restart_policy': 'unless-stopped',
        'podman_use_systemd': True,
    })
    container = {'HostConfig': {'RestartPolicy': {'Name': ''}}}
    assert cw.compare_restart_policy(container) is False


def test_compare_volumes_reordered_mounts(cw):
    cw.params['volumes'] = ['/etc:/etc:ro', '/var:/var:rw']
    container = {'HostConfig': {'Binds': ['/var:/var:rw', '/etc:/etc:ro']}}
    assert cw.compare_volumes(container) is False


def test_compare_healthcheck_detects_test_change(cw):
    cw.params['healthcheck'] = {
        'test': ['CMD-SHELL', 'check-a'],
        'interval': 1,
        'timeout': 1,
        'start_period': 0,
        'retries': 3,
    }
    container = {
        'Config': {
            'Healthcheck': {
                'Test': ['CMD-SHELL', 'check-b'],
                'Interval': 1000000000,
                'Timeout': 1000000000,
                'StartPeriod': 0,
                'Retries': 3,
            }
        }
    }
    assert cw.compare_healthcheck(container) is True


def test_compare_user_ignored_when_unspecified(cw):
    cw.params['user'] = 'nova'
    container = {'Config': {'User': 'root'}}

    assert cw.compare_user(container) is False


def test_compare_user_detects_drift_when_specified(cw):
    cw.params['user'] = 'nova'
    cw.specified_options = {'user'}
    container = {'Config': {'User': 'root'}}

    assert cw.compare_user(container) is True


def test_compare_user_detects_drift_when_specified_via_common_options(cw):
    cw.params['user'] = 'nova'
    cw.specified_options = {'common_options.user'}
    container = {'Config': {'User': 'root'}}

    assert cw.compare_user(container) is True


def test_normalise_container_info_strips_security_opt_default():
    params = {'container_engine': 'podman', 'security_opt': []}
    info = {'HostConfig': {'SecurityOpt': ['unmask=all', 'label=disable']}}
    normalised = _normalise_container_info(info, params)
    assert normalised['HostConfig']['SecurityOpt'] == ['label=disable']
    assert info['HostConfig']['SecurityOpt'] == ['unmask=all', 'label=disable']


def test_normalise_container_info_sorts_binds():
    params = {'container_engine': 'podman'}
    info = {
        'HostConfig': {
            'Binds': [
                '/var:/var:rw,rprivate',
                '/etc:/etc:ro',
            ]
        }
    }
    normalised = _normalise_container_info(info, params)
    assert normalised['HostConfig']['Binds'] == ['/etc:/etc:ro', '/var:/var:rw,rprivate']
