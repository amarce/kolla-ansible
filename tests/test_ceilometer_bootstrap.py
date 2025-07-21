import os
import yaml
from jinja2 import Environment, StrictUndefined
from oslotest import base


class TestCeilometerBootstrap(base.BaseTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        path = os.path.join(
            os.path.dirname(__file__),
            '..', 'ansible', 'roles', 'ceilometer', 'tasks',
            'bootstrap_service.yml')
        with open(path) as f:
            cls.tasks = yaml.safe_load(f)
        cls.env = Environment(undefined=StrictUndefined)

    def test_delegate_to_templates(self):
        self.env.from_string(self.tasks[0]['delegate_to']).render(
            groups={'ceilometer-notification': ['host']},
        )
        self.env.from_string(self.tasks[1]['delegate_to']).render(
            groups={'ceilometer-notification': ['host']},
            ceilometer_notification={'group': 'ceilometer-notification'}
        )

    def test_bootstrap_command(self):
        command = self.tasks[1]['kolla_container']['command']
        self.assertIn('ceilometer-upgrade', command)

    def test_when_prevents_rerun(self):
        cond = self.tasks[1]['when'][0]
        result_first = self.env.from_string(
            '{% if ' + cond + ' %}true{% else %}false{% endif %}'
        ).render(bootstrap_container_facts={'containers': {}})
        self.assertEqual('true', result_first)

        result_second = self.env.from_string(
            '{% if ' + cond + ' %}true{% else %}false{% endif %}'
        ).render(bootstrap_container_facts={'containers': {'bootstrap_ceilometer': {}}})
        self.assertEqual('false', result_second)
