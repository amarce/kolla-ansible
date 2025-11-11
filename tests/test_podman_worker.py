import sys
from unittest import mock

import pytest

sys.modules['dbus'] = mock.MagicMock()

from ansible.module_utils.kolla_podman_worker import PodmanWorker


class DummyModule:
    def __init__(self, **params):
        base = {'name': 'test'}
        base.update(params)
        common_opts = base.pop('common_options', None)
        specified = {k for k in params.keys() if k != 'common_options'}
        if isinstance(common_opts, dict):
            for key, value in common_opts.items():
                base.setdefault(key, value)
            specified.update(common_opts.keys())
            specified.update(f"common_options.{key}" for key in common_opts)
        if specified:
            base['_kolla_specified_options'] = list(specified)
        self.params = base

    def debug(self, msg):
        pass


@pytest.fixture
def pw():
    return PodmanWorker(DummyModule())


def test_compare_volumes_ignores_empty_strings(pw):
    pw.params['volumes'] = ['a:/a', '', 'b:/b']
    info = {'HostConfig': {'Binds': ['b:/b', 'a:/a']}}
    assert pw.compare_volumes(info) is False


def test_compare_ulimits_order_and_difference(pw):
    pw.params['dimensions'] = {
        'ulimits': {
            'n1': {'soft': 1, 'hard': 1},
            'n2': {'soft': 2, 'hard': 2},
        }
    }
    info_same = {
        'HostConfig': {
            'Ulimits': [
                {'Name': 'n2', 'Soft': 2, 'Hard': 2},
                {'Name': 'n1', 'Soft': 1, 'Hard': 1},
            ]
        }
    }
    info_diff = {
        'HostConfig': {
            'Ulimits': [
                {'Name': 'n1', 'Soft': 1, 'Hard': 2},
            ]
        }
    }

    assert pw.compare_ulimits(info_same) is False
    assert pw.compare_ulimits(info_diff) is True


def test_blank_volume_entries_ignored_podman():
    worker = PodmanWorker(DummyModule(volumes=['/foo:/foo', '']))
    info = {'HostConfig': {'Binds': ['/foo:/foo']}}
    assert worker.compare_volumes(info) is False


def test_no_ulimits_equivalent_podman():
    worker = PodmanWorker(DummyModule())
    assert worker.compare_ulimits({'HostConfig': {}}) is False

