import json
import os
from jinja2 import Environment, FileSystemLoader
from oslotest import base


TEMPLATE_DIR = os.path.join(os.path.dirname(__file__), '..', 'ansible', 'roles',
                            'nova-cell', 'templates')


class NovaLibvirtTemplateTest(base.BaseTestCase):

    def setUp(self):
        super().setUp()
        self.env = Environment(loader=FileSystemLoader(TEMPLATE_DIR),
                               autoescape=True)
        self.template = self.env.get_template('nova-libvirt.json.j2')
        self.base_vars = {
            'container_config_directory': '/etc/kolla',
            'nova_backend': 'fake',
            'cinder_backend_ceph': False,
            'libvirt_tls': False,
            'libvirt_enable_sasl': False,
            'kolla_copy_ca_into_containers': False,
        }

    def _render(self, vars):
        rendered = self.template.render(**vars)
        # Validate JSON parses successfully
        json.loads(rendered)

    def test_all_options_disabled(self):
        self._render(self.base_vars)

    def test_libvirt_tls_enabled(self):
        vars = dict(self.base_vars, libvirt_tls=True)
        self._render(vars)

    def test_nova_backend_rbd_enabled(self):
        vars = dict(self.base_vars, nova_backend='rbd')
        self._render(vars)

    def test_cinder_backend_ceph_enabled(self):
        vars = dict(self.base_vars, cinder_backend_ceph=True)
        self._render(vars)

    def test_libvirt_enable_sasl_enabled(self):
        vars = dict(self.base_vars, libvirt_enable_sasl=True)
        self._render(vars)

    def test_kolla_copy_ca_into_containers_enabled(self):
        vars = dict(self.base_vars, kolla_copy_ca_into_containers=True)
        self._render(vars)

    def test_multiple_options_enabled(self):
        vars = dict(self.base_vars,
                    libvirt_tls=True,
                    cinder_backend_ceph=True,
                    libvirt_enable_sasl=True,
                    kolla_copy_ca_into_containers=True,
                    nova_backend='rbd')
        self._render(vars)
