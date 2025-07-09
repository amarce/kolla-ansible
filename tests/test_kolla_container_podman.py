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
        }
        base.update(params)
        self.params = base

    def debug(self, msg):
        pass


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
        'Config': {'Env': []},
        'State': {'Status': 'running'},
        'Image': 'imageid',
    }
    pw.check_container = mock.MagicMock(return_value=True)
    pw.get_container_info = mock.MagicMock(return_value=info)
    pw.compare_config = mock.MagicMock(return_value=False)
    pw.systemd.check_unit_change = mock.MagicMock(return_value=False)

    assert pw.compare_container() is False
    assert pw.changed is False
