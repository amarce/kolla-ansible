#!/usr/bin/env python

# Copyright 2016 NEC Corporation
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# FIXME(yoctozepto): tests do not imitate how ansible would handle module args

from importlib.machinery import SourceFileLoader
import os
import sys
from unittest import mock

from oslotest import base

this_dir = os.path.dirname(sys.modules[__name__].__file__)
ansible_dir = os.path.join(this_dir, "..", "ansible")
kolla_container_file = os.path.join(ansible_dir, "library", "kolla_container.py")
docker_worker_file = os.path.join(ansible_dir, "module_utils", "kolla_docker_worker.py")
container_worker_file = os.path.join(
    ansible_dir, "module_utils", "kolla_container_worker.py"
)
kc = SourceFileLoader("kolla_container", kolla_container_file).load_module()
dwm = SourceFileLoader("kolla_docker_worker", docker_worker_file).load_module()
cwm = SourceFileLoader("kolla_container_worker", container_worker_file).load_module()


class ModuleArgsTest(base.BaseTestCase):

    def test_module_args(self):
        argument_spec = dict(
            common_options=dict(required=False, type="dict", default=dict()),
            action=dict(
                required=True,
                type="str",
                choices=[
                    "compare_container",
                    "compare_image",
                    "create_volume",
                    "ensure_image",
                    "pull_image",
                    "recreate_or_restart_container",
                    "remove_container",
                    "remove_image",
                    "remove_volume",
                    "restart_container",
                    "start_container",
                    "stop_container",
                    "stop_and_remove_container",
                ],
            ),
            api_version=dict(required=False, type="str"),
            auth_email=dict(required=False, type="str"),
            auth_password=dict(required=False, type="str", no_log=True),
            auth_registry=dict(required=False, type="str"),
            auth_username=dict(required=False, type="str"),
            command=dict(required=False, type="str"),
            container_engine=dict(required=False, type="str"),
            detach=dict(required=False, type="bool", default=True),
            labels=dict(required=False, type="dict", default=dict()),
            name=dict(required=False, type="str"),
            environment=dict(required=False, type="dict"),
            image=dict(required=False, type="str"),
            ipc_mode=dict(
                required=False, type="str", choices=["", "host", "private", "shareable"]
            ),
            cap_add=dict(required=False, type="list", default=list()),
            security_opt=dict(required=False, type="list", default=list()),
            pid_mode=dict(required=False, type="str", choices=["", "host", "private"]),
            cgroupns_mode=dict(required=False, type="str", choices=["private", "host"]),
            privileged=dict(required=False, type="bool", default=False),
            graceful_timeout=dict(required=False, type="int"),
            remove_on_exit=dict(required=False, type="bool", default=True),
            restart_policy=dict(
                required=False,
                type="str",
                choices=["no", "on-failure", "oneshot", "always", "unless-stopped"],
            ),
            restart_retries=dict(required=False, type="int"),
            state=dict(
                required=False,
                type="str",
                default="running",
                choices=["running", "exited", "paused"],
            ),
            tls_verify=dict(required=False, type="bool", default=False),
            tls_cert=dict(required=False, type="str"),
            tls_key=dict(required=False, type="str"),
            tls_cacert=dict(required=False, type="str"),
            tmpfs=dict(required=False, type="list"),
            volumes=dict(required=False, type="list"),
            volumes_from=dict(required=False, type="list"),
            dimensions=dict(required=False, type="dict", default=dict()),
            tty=dict(required=False, type="bool", default=False),
            client_timeout=dict(required=False, type="int"),
            healthcheck=dict(required=False, type="dict"),
            ignore_missing=dict(required=False, type="bool", default=False),
        )
        required_if = [
            ["action", "pull_image", ["image"]],
            ["action", "start_container", ["image", "name"]],
            ["action", "compare_container", ["name"]],
            ["action", "compare_image", ["name"]],
            ["action", "create_volume", ["name"]],
            ["action", "ensure_image", ["image"]],
            ["action", "recreate_or_restart_container", ["name"]],
            ["action", "recreate_container", ["name"]],
            ["action", "remove_container", ["name"]],
            ["action", "remove_image", ["image"]],
            ["action", "remove_volume", ["name"]],
            ["action", "restart_container", ["name"]],
            ["action", "stop_container", ["name"]],
            ["action", "stop_and_remove_container", ["name"]],
        ]

        kc.AnsibleModule = mock.MagicMock()
        kc.generate_module()
        kc.AnsibleModule.assert_called_with(
            argument_spec=argument_spec, required_if=required_if, bypass_checks=False
        )


def test_compare_volumes_ignores_empty_and_devpts():
    spec = ["a:/a", "", "devpts:/dev/pts"]
    running = ["a:/a"]
    assert cwm._compare_volumes(spec, running) is False  # nosec B101


def test_compare_volumes_devpts_representation():
    spec = ["devpts:/dev/pts", "/data:/data"]
    running = [":/dev/pts", "/data:/data"]
    assert cwm._compare_volumes(spec, running) is False  # nosec B101


def test_compare_ulimits_missing_key():
    spec = [{"Name": "memlock", "Soft": 64, "Hard": 64}]
    running = []
    assert cwm._compare_ulimits(spec, running) is False  # nosec B101


class DiffDummyModule:
    def __init__(self, **params):
        base = {"name": "test", "command": "/bin/new"}
        base.update(params)
        self.params = base

    def debug(self, msg):
        pass


class DiffWorker(cwm.ContainerWorker):
    def __init__(self, module=None):
        super().__init__(module or DiffDummyModule())

    def check_image(self):
        pass

    def get_container_info(self):
        return {
            "Path": "/bin/old",
            "Args": [],
            "Config": {"Image": "img"},
            "HostConfig": {},
            "State": {"Status": "running"},
        }

    def check_container(self):
        pass

    def compare_pid_mode(self, container_info):
        return False

    def compare_image(self, container_info=None):
        return False

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

    def recreate_container(self):
        pass

    def start_container(self):
        pass


def test_emit_diff_command():
    w = DiffWorker()
    w._diff_keys = ["command"]
    w._last_container_info = w.get_container_info()
    w.emit_diff()
    diff = w.result["diff"]
    assert "- /bin/old" in diff  # nosec B101
    assert "+ /bin/new" in diff  # nosec B101


def test_check_container_differs_debug():
    w = DiffWorker()
    w.params["command"] = "/bin/new"
    assert w.check_container_differs() is True  # nosec B101
    assert "command differs" in w.result["debug"]  # nosec B101


@mock.patch("kolla_container.generate_module")
def test_compare_container_no_change(mock_generate_module):
    module_mock = mock.MagicMock()
    module_mock.params = {"name": "test", "action": "compare_container"}
    mock_generate_module.return_value = module_mock
    with mock.patch(
        "ansible.module_utils.kolla_docker_worker.DockerWorker"
    ) as mock_dw:
        mock_dw.return_value.compare_container.return_value = False
        mock_dw.return_value.changed = False
        mock_dw.return_value.result = {}
        kc.main()
        mock_dw.assert_called_once_with(module_mock)  # nosec B101
        mock_dw.return_value.compare_container.assert_called_once_with()  # nosec B101
    module_mock.exit_json.assert_called_once_with(changed=False, result=True)  # nosec B101


@mock.patch("kolla_container.generate_module")
def test_compare_container_no_change_returns_ok(mock_generate_module):
    module_mock = mock.MagicMock()
    module_mock.params = {"name": "test", "action": "compare_container"}
    mock_generate_module.return_value = module_mock
    with mock.patch(
        "ansible.module_utils.kolla_docker_worker.DockerWorker"
    ) as mock_dw:
        mock_dw.return_value.compare_container.return_value = True
        mock_dw.return_value.changed = True
        mock_dw.return_value.result = {
            "diff": {},
            "debug": ["no differences found"],
        }
        kc.main()
        mock_dw.assert_called_once_with(module_mock)  # nosec B101
        mock_dw.return_value.compare_container.assert_called_once_with()  # nosec B101
    module_mock.exit_json.assert_called_once_with(
        changed=False,
        result=True,
        diff={},
        debug=["no differences found"],
    )  # nosec B101
