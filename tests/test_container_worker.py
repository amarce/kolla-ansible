import pytest

from ansible.module_utils.kolla_container_worker import ContainerWorker

class DummyModule:
    def __init__(self):
        self.params = {'name': None}
    def debug(self, msg):
        pass

class DummyWorker(ContainerWorker):
    def __init__(self):
        super().__init__(DummyModule())
    def check_image(self):
        pass
    def get_container_info(self):
        pass
    def check_container(self):
        pass

@pytest.fixture
def cw():
    return DummyWorker()

@pytest.mark.parametrize("expected,actual,match", [
    ([], None, True),
    (["NET_ADMIN"], [], False),
    (["NET_ADMIN"], ["net_admin"], True),
    (["SYS_ADMIN", "NET_ADMIN"], ["NET_ADMIN", "SYS_ADMIN", "NET_ADMIN"], True),
])
def test_compare_cap_add(expected, actual, match, cw):
    cw.params['cap_add'] = expected
    container = {'HostConfig': {'CapAdd': actual}}
    assert cw.compare_cap_add(container) is (not match)

def test_compare_dimensions_zero_equals_empty(cw):
    cw.params['dimensions'] = {}
    container = {'HostConfig': {'Resources': {'NanoCPUs': 0, 'Memory': 0}}}
    assert cw.compare_dimensions(container) is False
