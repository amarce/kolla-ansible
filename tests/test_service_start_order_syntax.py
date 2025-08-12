import os
import subprocess  # nosec B404

BASE_DIR = os.path.dirname(os.path.dirname(__file__))
MOLECULE_DIR = os.path.join(BASE_DIR, 'molecule', 'service_start_order')


def test_service_start_order_syntax():
    playbook = os.path.join(MOLECULE_DIR, 'playbook.yml')
    subprocess.check_call(['ansible-playbook', '--syntax-check', playbook])  # nosec B603 B607
