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

@pytest.mark.parametrize("expected,actual,diff", [
    ([], None, False),
    (["SYS_PTRACE"], ["SYS_PTRACE"], False),
    (["A"], ["B"], True),
])
def test_compare_cap_add(expected, actual, diff, cw):
    cw.params['cap_add'] = expected
    container = {'HostConfig': {'CapAdd': actual}}
    assert cw.compare_cap_add(container) is diff

def test_compare_cap_add_case_duplicate(cw):
    cw.params['cap_add'] = ["SYS_ADMIN", "NET_ADMIN"]
    container = {
        'HostConfig': {'CapAdd': ["NET_ADMIN", "SYS_ADMIN", "NET_ADMIN"]}
    }
    assert cw.compare_cap_add(container) is False

def test_compare_dimensions_zero_equals_empty(cw):
    cw.params['dimensions'] = {}
    container = {'HostConfig': {'Resources': {'NanoCPUs': 0, 'Memory': 0}}}
    assert cw.compare_dimensions(container) is False

def test_compare_dimensions_none_vs_empty(cw):
    cw.params['dimensions'] = {}
    container = {'HostConfig': {'Resources': None}}
    assert cw.compare_dimensions(container) is False
