from unittest import TestCase, mock

from ansible.module_utils.kolla_container_worker import ensure_host_path


class TestEnsureHostPath(TestCase):
    def test_creates_missing_dir(self):
        with mock.patch('os.path.exists', return_value=False), \
             mock.patch('os.makedirs') as makedirs:
            ensure_host_path('/var/lib/custom')
            makedirs.assert_called_once_with('/var/lib/custom', mode=0o755, exist_ok=True)

    def test_skips_existing_dir(self):
        with mock.patch('os.path.exists', return_value=True), \
             mock.patch('os.makedirs') as makedirs:
            ensure_host_path('/var/lib/custom')
            makedirs.assert_not_called()
