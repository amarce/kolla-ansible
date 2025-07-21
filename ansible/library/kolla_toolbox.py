# Copyright 2016 99cloud Inc.
#
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

import json
import re
import traceback

from ansible.module_utils.basic import AnsibleModule

DOCUMENTATION = '''
---
module: kolla_toolbox
short_description: >
  Module for invoking ansible module in kolla_toolbox container.
description:
  - A module targerting at invoking ansible module in kolla_toolbox
    container as used by Kolla project.
options:
  container_engine:
    description:
      - Name of container engine to use
    required: True
    type: str
    choices: ['docker', 'podman']
  module_name:
    description:
      - The module name to invoke
    required: True
    type: str
  module_args:
    description:
      - The module args use by the module
    required: False
    type: dict
  module_extra_vars:
    description:
      - The extra variables used by the module
    required: False
    type: dict
  user:
    description:
      - The user to execute Ansible inside kolla_toolbox with
    required: False
    type: str
  api_version:
    description:
      - The version of the API for client to use when contacting container API
    required: False
    type: str
    default: auto
  timeout:
    description:
      - The default timeout for client when contacting container API
    required: False
    type: int
    default: 180
authors: Jeffrey Zhang, Roman Krček
'''

EXAMPLES = '''
- hosts: controller
  tasks:
    - name: Ensure the directory is removed
      kolla_toolbox:
        container_engine: podman
        module_name: file
        module_args:
          path: /tmp/a
          state: absent
    - name: Create mysql database
      kolla_toolbox:
        container_engine: docker
        module_name: mysql_db
        module_args:
          login_host: 192.168.1.10
          login_user: root
          login_password: admin
          name: testdb
    - name: Create default user role
      kolla_toolbox:
        container_engine: docker
        module_name: openstack.cloud.identity_role
        module_args:
          name: member
          auth: "{{ '{{ openstack_keystone_auth }}' }}"
        module_extra_vars:
          openstack_keystone_auth:
            auth_url: http://127.0.0.1:5000
            username: admin
            password: password
            project_name: "admin"
            domain_name: "default"
'''


class KollaToolboxWorker():
    def __init__(self, module, client, container_errors) -> None:
        self.module = module
        self.client = client
        self.container_errors = container_errors
        self.result = dict()

    def _get_toolbox_container(self):
        """Get the kolla_toolbox container object, if up and running."""
        cont = self.client.containers.list(
            filters=dict(name='kolla_toolbox', status='running')
        )
        if not cont:
            self.module.fail_json(
                msg='kolla_toolbox container is missing or not running!'
            )
        return cont[0]

    def _format_module_args(self, module_args: dict) -> list:
        """Format dict of module parameters into list of 'key=value' pairs."""
        pairs = list()
        for key, value in module_args.items():
            if isinstance(value, dict):
                value_json = json.dumps(value)
                pairs.append(f"{key}='{value_json}'")
            else:
                pairs.append(f"{key}='{value}'")
        return pairs

    def _generate_command(self) -> list:
        """Generate the command that will be executed inside kolla_toolbox."""
        args_formatted = self._format_module_args(
            self.module.params.get('module_args'))
        extra_vars_formatted = self._format_module_args(
            self.module.params.get('module_extra_vars'))

        command = ['ansible', 'localhost']
        command.extend(['-m', self.module.params.get('module_name')])
        if args_formatted:
            command.extend(['-a', ' '.join(args_formatted)])
        if extra_vars_formatted:
            command.extend(['-e', ' '.join(extra_vars_formatted)])
        if self.module.check_mode:
            command.append('--check')

        return command

    def _run_command(self, kolla_toolbox, command, *args, **kwargs) -> bytes:
        """
        Execute *command* inside the running kolla-toolbox container and return
        the tuple (stdout_bytes, stderr_bytes).
        """
        try:
            rc, raw = kolla_toolbox.exec_run(command, *args, **kwargs)

            # ── podman multiplexed frames: 8-byte header + payload ──────────
            if isinstance(raw, bytes):
                pos, stdout_buf, stderr_buf = 0, bytearray(), bytearray()
                while pos + 8 <= len(raw):
                    stream_id = raw[pos]          # 1 = stdout, 2 = stderr
                    length    = int.from_bytes(raw[pos+4:pos+8], "big")
                    pos += 8
                    data, pos = raw[pos:pos+length], pos + length
                    (stdout_buf if stream_id == 1 else stderr_buf).extend(data)
                stdout, stderr = bytes(stdout_buf), bytes(stderr_buf)
            else:                                 # Docker-py style tuple
                stdout, stderr = raw
        except self.container_errors.APIError as e:
            self.module.fail_json(
                msg=f"Container engine client encountered API error: {e.explanation}"
            )

        # expose stderr to the caller (for troubleshooting etc.)
        if stderr:
            self.result["stderr"] = stderr.decode(errors="ignore")

        return stdout, stderr


    def _process_container_output(self, output_raw: bytes | tuple[bytes, bytes]) -> dict:
        """
        Convert toolbox exec output to a result dict, accepting that the JSON
        might be on *either* stream and may be preceded by warnings.
        """
        if isinstance(output_raw, tuple):
            stdout, stderr = output_raw
        else:                                   # backward-compat — only stdout
            stdout, stderr = output_raw, b""

        # choose the stream that actually contains the JSON
        candidate = stdout if stdout.strip() else stderr

        # OPTIONAL ultra-verbose dump
        verbosity = getattr(self.module, "_verbosity", 0)
        try:
            verbosity = int(verbosity)
        except (TypeError, ValueError):
            verbosity = 0
        if verbosity >= 4:
            with open("/tmp/ktbw.raw", "wb") as f:
                f.write(candidate)

        if not candidate.strip():
            self.module.fail_json(msg="kolla_toolbox: no JSON produced",
                                  **self.result)

        # remove ANSI colour and everything before the first '{'
        clean = re.sub(rb"\x1B\[[0-9;]*[mK]", b"", candidate)
        json_start = clean.find(b"{")
        if json_start == -1:
            self.module.fail_json(msg="kolla_toolbox: JSON not found in output",
                                  stdout=clean.decode(errors="ignore"),
                                  **self.result)
        clean = clean[json_start:]

        try:
            output_json = json.loads(clean.decode())
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            self.module.fail_json(msg=f"Bad JSON from kolla_toolbox: {exc}",
                                  stdout=clean.decode(errors="ignore"),
                                  **self.result)

        # ── normalise old/new callback formats ─────────────────────────────
        if isinstance(output_json, dict) and "plays" in output_json:
            try:
                result = output_json["plays"][0]["tasks"][0]["hosts"]["localhost"]
            except (KeyError, IndexError):
                self.module.fail_json(
                    msg=f"Ansible JSON output has unexpected format: {output_json}"
                )
        else:
            result = output_json

        result.pop("_ansible_no_log", None)
        return result


    def main(self) -> None:
        """Run command inside the kolla_toolbox container with defined args."""

        kolla_toolbox = self._get_toolbox_container()
        command = self._generate_command()
        environment = {'ANSIBLE_STDOUT_CALLBACK': 'json',
                       'ANSIBLE_LOAD_CALLBACK_PLUGINS': 'True'}

        output_raw = self._run_command(kolla_toolbox,
                                       command,
                                       environment=environment,
                                       tty=True,
                                       user=self.module.params.get('user'))

        self.result = self._process_container_output(output_raw)


def create_container_client(module: AnsibleModule):
    """Return container engine client based on the parameters."""
    container_engine = module.params.get('container_engine')
    api_version = module.params.get('api_version')
    timeout = module.params.get('timeout')

    if container_engine == 'docker':
        try:
            import docker
            import docker.errors as container_errors
        except ImportError:
            module.fail_json(
                msg='The docker library could not be imported!'
            )
        client = docker.DockerClient(
            base_url='http+unix:/var/run/docker.sock',
            version=api_version,
            timeout=timeout)
    else:
        try:
            import podman
            import podman.errors as container_errors
        except ImportError:
            module.fail_json(
                msg='The podman library could not be imported!'
            )
        # NOTE(r-krcek): PodmanClient has a glitch in which when you pass
        # 'auto' to api_version, it literally creates an url of /vauto
        # for API calls, instead of actually finding the compatible version
        # like /v5.0.0, this leads to 404 Error when accessing the API.
        if api_version == 'auto':
            client = podman.PodmanClient(
                base_url='http+unix:/run/podman/podman.sock',
                timeout=timeout)
        else:
            client = podman.PodmanClient(
                base_url='http+unix:/run/podman/podman.sock',
                version=api_version,
                timeout=timeout)
    return client, container_errors


def create_ansible_module() -> AnsibleModule:
    argument_spec = dict(
        container_engine=dict(type='str',
                              choices=['podman', 'docker'],
                              required=True),
        module_name=dict(type='str', required=True),
        module_args=dict(type='dict', default=dict()),
        module_extra_vars=dict(type='dict', default=dict()),
        api_version=dict(type='str', default='auto'),
        timeout=dict(type='int', default=180),
        user=dict(type='str'),
    )

    return AnsibleModule(argument_spec=argument_spec,
                         supports_check_mode=True)


def main():
    module = create_ansible_module()
    client, container_errors = create_container_client(module)
    ktbw = KollaToolboxWorker(module, client, container_errors)

    try:
        ktbw.main()
        module.exit_json(**ktbw.result)
    except Exception:
        module.fail_json(changed=True,
                         msg=repr(traceback.format_exc()))


if __name__ == '__main__':
    main()
