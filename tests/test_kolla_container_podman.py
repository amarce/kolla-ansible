import sys
import types
from unittest import mock

# Provide stubs for external deps
podman = types.ModuleType('podman')
podman.errors = types.ModuleType('podman.errors')
class APIError(Exception):
    pass
podman.errors.APIError = APIError
class PodmanClient:
    def __init__(self, *a, **kw):
        pass
podman.PodmanClient = PodmanClient
sys.modules['podman'] = podman
sys.modules['podman.errors'] = podman.errors
sys.modules['dbus'] = mock.MagicMock()

from ansible.module_utils.kolla_podman_worker import PodmanWorker


class DummyModule:
    def __init__(self, **params):
        base = {
            'name': 'test',
            'container_engine': 'podman',
            'volumes': ['/data:/data'],
            'restart_policy': 'unless-stopped',
            'dimensions': {},
            'detach': True,
        }
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

    def fail_json(self, **kwargs):
        raise Exception(kwargs)


def test_compare_container_podman_no_change():
    pw = PodmanWorker(DummyModule())
    info = {
        'HostConfig': {
            'Binds': ['devpts:/dev/pts', '/data:/data'],
            'Ulimits': [
                {'Name': 'RLIMIT_NPROC', 'Soft': 4194304, 'Hard': 4194304},
            ],
            'RestartPolicy': {'Name': ''},
        },
        'Config': {'Env': [], 'User': 'root'},
        'State': {'Status': 'running'},
        'Image': 'imageid',
    }
    pw.check_container = mock.MagicMock(return_value=True)
    pw.get_container_info = mock.MagicMock(return_value=info)
    pw.compare_config = mock.MagicMock(return_value=False)
    pw.systemd.check_unit_change = mock.MagicMock(return_value=False)

    assert pw.compare_container() is False
    assert pw.changed is False


def test_compare_container_podman_root_variants_no_change():
    pw = PodmanWorker(DummyModule())
    info = {
        'HostConfig': {
            'Binds': ['devpts:/dev/pts', '/data:/data'],
            'Ulimits': [
                {'Name': 'RLIMIT_NPROC', 'Soft': 4194304, 'Hard': 4194304},
            ],
            'RestartPolicy': {'Name': ''},
        },
        'Config': {'Env': [], 'User': '0:0'},
        'State': {'Status': 'running'},
        'Image': 'imageid',
    }
    pw.check_container = mock.MagicMock(return_value=True)
    pw.get_container_info = mock.MagicMock(return_value=info)
    pw.compare_config = mock.MagicMock(return_value=False)
    pw.systemd.check_unit_change = mock.MagicMock(return_value=False)

    assert pw.compare_container() is False
    assert pw.changed is False


def test_compare_container_podman_detects_user_drift():
    pw = PodmanWorker(DummyModule(user='nova'))
    info = {
        'HostConfig': {
            'Binds': ['devpts:/dev/pts', '/data:/data'],
            'Ulimits': [
                {'Name': 'RLIMIT_NPROC', 'Soft': 4194304, 'Hard': 4194304},
            ],
            'RestartPolicy': {'Name': ''},
        },
        'Config': {'Env': [], 'User': 'root'},
        'State': {'Status': 'running'},
        'Image': 'imageid',
    }
    pw.check_container = mock.MagicMock(return_value=True)
    pw.get_container_info = mock.MagicMock(return_value=info)
    pw.compare_config = mock.MagicMock(return_value=False)
    pw.systemd.check_unit_change = mock.MagicMock(return_value=False)

    assert pw.compare_container() is True
    assert pw.changed is True
    assert pw.result.get('container_needs_recreate') is True
    assert 'user' in pw.result.get('container_recreate_reasons', [])


def test_wait_overrides_defer_start():
    module = DummyModule(defer_start=True, wait=True)
    pw = PodmanWorker(module)
    created = mock.MagicMock()
    created.status = "created"
    created.attrs = {'State': {'Status': 'created', 'Health': {'Status': 'starting'}}}
    running = mock.MagicMock()
    running.status = "running"
    running.attrs = {'State': {'Status': 'running', 'Health': {'Status': 'healthy'}}}
    created.start = mock.MagicMock()
    pw.check_container = mock.MagicMock(side_effect=[created, running, running])
    pw.check_container_differs = mock.MagicMock(return_value=False)
    pw.ensure_image = mock.MagicMock()
    pw.systemd.create_unit_file = mock.MagicMock()
    pw.start_container()
    created.start.assert_called_once()


def test_start_before_wait():
    module = DummyModule(start=True, wait=True)
    pw = PodmanWorker(module)
    created = mock.MagicMock()
    created.status = "created"
    created.attrs = {'State': {'Status': 'created', 'Health': {'Status': 'starting'}}}
    created.start = mock.MagicMock()
    pw.check_container = mock.MagicMock(return_value=created)
    pw.check_container_differs = mock.MagicMock(return_value=False)
    pw.ensure_image = mock.MagicMock()
    pw.systemd.create_unit_file = mock.MagicMock()
    pw._wait_for_container = mock.MagicMock()
    pw.start_container()
    created.start.assert_called_once()
    pw._wait_for_container.assert_called_once()


def test_wait_triggers_start():
    module = DummyModule(start=False, wait=True)
    pw = PodmanWorker(module)
    created = mock.MagicMock()
    created.status = "created"
    created.attrs = {'State': {'Status': 'created', 'Health': {'Status': 'starting'}}}
    created.start = mock.MagicMock()
    pw.check_container = mock.MagicMock(return_value=created)
    pw.check_container_differs = mock.MagicMock(return_value=False)
    pw.ensure_image = mock.MagicMock()
    pw.systemd.create_unit_file = mock.MagicMock()
    pw._wait_for_container = mock.MagicMock()
    pw.start_container()
    created.start.assert_called_once()
    pw._wait_for_container.assert_called_once()
