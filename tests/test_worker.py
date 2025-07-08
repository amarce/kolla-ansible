import sys
from unittest import mock

import pytest

sys.modules["dbus"] = mock.MagicMock()

from ansible.module_utils.kolla_container_worker import ContainerWorker, _as_dict


class DummyModule:
    def __init__(self):
        self.params = {"name": "test"}

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


PLAYBOOK_LIST = [
    "/etc/kolla/openvswitch-vswitchd/:/var/lib/kolla/config_files/:ro",
    "/etc/localtime:/etc/localtime:ro",
    "/etc/timezone:/etc/timezone:ro",
    "/lib/modules:/lib/modules:ro",
    "/run/openvswitch:/run/openvswitch:shared",
    "kolla_logs:/var/log/kolla/",
]

PODMAN_INSPECT_SNIPPET = {
    "Mounts": [
        {
            "Type": "volume",
            "Name": "kolla_logs",
            "Source": "/var/lib/containers/storage/volumes/kolla_logs/_data",
            "Destination": "/var/log/kolla/",
            "RW": True,
            "Propagation": "rprivate",
        },
        {
            "Type": "bind",
            "Source": "/etc/kolla/openvswitch-vswitchd",
            "Destination": "/var/lib/kolla/config_files/",
            "RW": False,
            "Propagation": "rprivate",
        },
        {
            "Type": "bind",
            "Source": "/etc/localtime",
            "Destination": "/etc/localtime",
            "RW": False,
            "Propagation": "rprivate",
        },
        {
            "Type": "bind",
            "Source": "/etc/timezone",
            "Destination": "/etc/timezone",
            "RW": False,
            "Propagation": "rprivate",
        },
        {
            "Type": "bind",
            "Source": "/lib/modules",
            "Destination": "/lib/modules",
            "RW": False,
            "Propagation": "rprivate",
        },
        {
            "Type": "bind",
            "Source": "/run/openvswitch",
            "Destination": "/run/openvswitch",
            "RW": True,
            "Propagation": "shared",
        },
    ],
    "HostConfig": {
        "Binds": [
            "kolla_logs:/var/log/kolla/:rw,rprivate,nosuid,nodev,rbind",
            "/etc/kolla/openvswitch-vswitchd:/var/lib/kolla/config_files/:rprivate,ro,rbind",
            "/etc/localtime:/etc/localtime:rprivate,ro,rbind",
            "/etc/timezone:/etc/timezone:rprivate,ro,rbind",
            "/lib/modules:/lib/modules:rprivate,ro,rbind",
            "/run/openvswitch:/run/openvswitch:shared,rw,noexec,nosuid,nodev,rbind",
        ],
    },
}


def test_compare_volumes_ignores_benign_diffs(worker):
    worker.params["volumes"] = PLAYBOOK_LIST
    assert not worker.compare_volumes(PODMAN_INSPECT_SNIPPET)


def test__as_dict():
    assert _as_dict(None) == {}
    assert _as_dict({"a": "b"}) == {"a": "b"}
    assert _as_dict(["x=1", "y=2"]) == {"x": "1", "y": "2"}
    with pytest.raises(TypeError):
        _as_dict(["no_equal"])
