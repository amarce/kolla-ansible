import os
import sys
from importlib.machinery import SourceFileLoader
from unittest import mock
from oslotest import base

this_dir = os.path.dirname(sys.modules[__name__].__file__)
ansible_dir = os.path.join(this_dir, '..', 'ansible')
worker_file = os.path.join(ansible_dir, 'module_utils', 'kolla_podman_worker.py')
pwm = SourceFileLoader('kolla_podman_worker', worker_file).load_module()


class CompareConfigTest(base.BaseTestCase):

    def setUp(self):
        super(CompareConfigTest, self).setUp()
        module = mock.MagicMock()
        module.params = {}
        self.worker = pwm.PodmanWorker(module)
        self.worker.systemd = mock.MagicMock()

    def test_empty_config_files_not_changed(self):
        with mock.patch.object(self.worker, '_has_config_files', return_value=False), \
             mock.patch.object(self.worker, 'check_container', return_value=True), \
             mock.patch.object(self.worker, 'check_container_differs', return_value=False):
            changed = self.worker.compare_container()
            self.assertFalse(changed)
