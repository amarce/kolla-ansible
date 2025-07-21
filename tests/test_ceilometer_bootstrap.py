import os
import yaml
from jinja2 import Environment, StrictUndefined
from oslotest import base


class TestCeilometerBootstrap(base.BaseTestCase):
    def test_delegate_to_templates(self):
        path = os.path.join(
            os.path.dirname(__file__),
            '..', 'ansible', 'roles', 'ceilometer', 'tasks',
            'bootstrap_service.yml')
        with open(path) as f:
            tasks = list(yaml.safe_load_all(f))

        env = Environment(undefined=StrictUndefined)
        # First task should not require ceilometer_notification variable
        env.from_string(tasks[0]['delegate_to']).render(
            groups={'ceilometer-notification': ['host']}
        )

        # Second task uses ceilometer_notification variable
        env.from_string(tasks[1]['delegate_to']).render(
            groups={'ceilometer-notification': ['host']},
            ceilometer_notification={'group': 'ceilometer-notification'}
        )

