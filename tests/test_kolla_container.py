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
sys.modules['dbus'] = mock.MagicMock()
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
                    "recreate_container",
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
            start=dict(required=False, type="bool", default=True),
            defer_start=dict(required=False, type="bool", default=False),
            wait=dict(required=False, type="bool", default=False),
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


class SpecifiedOptionsTest(base.BaseTestCase):

    def test_collect_specified_options_with_common_options(self):
        raw_args = {
            'ANSIBLE_MODULE_ARGS': {
                'module_args': {
                    'name': 'kolla_toolbox',
                    'image': 'registry.example/centos:latest',
                    'user': 'root',
                    'pid_mode': 'host',
                    'common_options': {
                        'restart_policy': 'unless-stopped',
                    },
                    '_ansible_check_mode': False,
                }
            }
        }

        specified = kc._collect_specified_options(raw_args)

        self.assertSetEqual(
            {
                'name',
                'image',
                'user',
                'pid_mode',
                'restart_policy',
                'common_options.restart_policy',
            },
            specified,
        )

    def test_collect_specified_options_missing_optional_keys(self):
        raw_args = {
            'module_args': {
                'name': 'kolla_toolbox',
                'image': 'registry.example/centos:latest',
            }
        }

        specified = kc._collect_specified_options(raw_args)

        self.assertIn('name', specified)
        self.assertIn('image', specified)
        self.assertNotIn('user', specified)
        self.assertNotIn('pid_mode', specified)

    def test_collect_specified_options_ansible_kwargs_wrapper(self):
        raw_args = {
            '_ansible_kwargs': {
                'name': 'kolla_toolbox',
                'image': 'registry.example/centos:latest',
                'common_options': {
                    'restart_policy': 'unless-stopped',
                },
            }
        }

        specified = kc._collect_specified_options(raw_args)

        self.assertSetEqual(
            {
                'name',
                'image',
                'restart_policy',
                'common_options.restart_policy',
            },
            specified,
        )


def test_compare_volumes_ignores_empty_and_devpts():
    spec = ["a:/a", "", "devpts:/dev/pts"]
    running = ["a:/a"]
    assert cwm._compare_volumes(spec, running) is False


def test_compare_volumes_devpts_representation():
    spec = ["devpts:/dev/pts", "/data:/data"]
    running = [":/dev/pts", "/data:/data"]
    assert cwm._compare_volumes(spec, running) is False


def test_compare_ulimits_missing_key():
    spec = [{"Name": "memlock", "Soft": 64, "Hard": 64}]
    running = []
    assert cwm._compare_ulimits(spec, running) is False


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
    assert "- /bin/old" in diff
    assert "+ /bin/new" in diff


def test_check_container_differs_debug():
    w = DiffWorker()
    w.params["command"] = "/bin/new"
    assert w.check_container_differs() is True
    assert "command differs" in w.result["debug"]


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
        mock_dw.assert_called_once_with(module_mock)
        mock_dw.return_value.compare_container.assert_called_once_with()
    module_mock.exit_json.assert_called_once_with(changed=False, result=True)


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
        mock_dw.assert_called_once_with(module_mock)
        mock_dw.return_value.compare_container.assert_called_once_with()
    module_mock.exit_json.assert_called_once_with(
        changed=False,
        result=True,
        diff={},
        debug=["no differences found"],
    )


@mock.patch("kolla_container.generate_module")
def test_recreate_or_restart_docker_no_change(mock_generate_module):
    module_mock = mock.MagicMock()
    module_mock.params = {
        "name": "test",
        "action": "recreate_or_restart_container",
        "container_engine": "docker",
    }
    mock_generate_module.return_value = module_mock

    with mock.patch(
        "ansible.module_utils.kolla_docker_worker.DockerWorker"
    ) as mock_dw:
        worker = mock_dw.return_value
        worker.recreate_or_restart_container.return_value = None
        worker.changed = False
        worker.result = {}

        kc.main()

        mock_dw.assert_called_once_with(module_mock)
        worker.recreate_or_restart_container.assert_called_once_with()

    module_mock.exit_json.assert_called_once_with(changed=False, result=False)


@mock.patch("kolla_container.generate_module")
def test_recreate_or_restart_podman_no_change(mock_generate_module):
    module_mock = mock.MagicMock()
    module_mock.params = {
        "name": "test",
        "action": "recreate_or_restart_container",
        "container_engine": "podman",
    }
    mock_generate_module.return_value = module_mock

    with mock.patch(
        "ansible.module_utils.kolla_podman_worker.PodmanWorker"
    ) as mock_pw:
        worker = mock_pw.return_value
        worker.recreate_or_restart_container.return_value = None
        worker.changed = False
        worker.result = {"debug": ["no differences found"]}

        kc.main()

        mock_pw.assert_called_once_with(module_mock)
        worker.recreate_or_restart_container.assert_called_once_with()

    module_mock.exit_json.assert_called_once_with(
        changed=False,
        result=False,
        debug=["no differences found"],
    )


@mock.patch("kolla_container.generate_module")
def test_recreate_or_restart_podman_changed(mock_generate_module):
    module_mock = mock.MagicMock()
    module_mock.params = {
        "name": "test",
        "action": "recreate_or_restart_container",
        "container_engine": "podman",
    }
    mock_generate_module.return_value = module_mock

    with mock.patch(
        "ansible.module_utils.kolla_podman_worker.PodmanWorker"
    ) as mock_pw:
        worker = mock_pw.return_value
        worker.recreate_or_restart_container.return_value = True
        worker.changed = True
        worker.result = {}

        kc.main()

        mock_pw.assert_called_once_with(module_mock)
        worker.recreate_or_restart_container.assert_called_once_with()

    module_mock.exit_json.assert_called_once_with(changed=True, result=True)
