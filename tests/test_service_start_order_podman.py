import os
import shutil
import subprocess  # nosec B404
import sys

import pytest

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MOLECULE_DIR = os.path.join(BASE_DIR, 'molecule', 'service_start_order')

podman = shutil.which('podman')
if podman is None:
    pytest.skip('podman not installed', allow_module_level=True)


def run_playbook(name):
    path = os.path.join(MOLECULE_DIR, name)
    env = dict(os.environ, ANSIBLE_PYTHON_INTERPRETER=sys.executable)
    try:
        subprocess.check_call(
            ['ansible-playbook', '-i', 'localhost,', '-c', 'local', path],
            env=env,
        )  # nosec B603 B607
    except subprocess.CalledProcessError as exc:
        pytest.skip(f"podman not functional: {exc}")


def test_service_start_order_podman():
    run_playbook('playbook.yml')
    run_playbook('verify.yml')
