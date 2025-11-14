from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar


def render_validation_lists(restart_services, known_service_names):
    templar = Templar(
        loader=DataLoader(),
        variables={
            'service_check_restart_services': restart_services,
            'service_check_known_service_names': known_service_names,
        },
    )
    non_strings = templar.template(
        "{{ service_check_restart_services | reject('string') | list }}"
    )
    invalid_entries = templar.template(
        "{{ service_check_restart_services | select('string')"
        " | reject('in', service_check_known_service_names) | list }}"
    )
    return non_strings, invalid_entries


def test_restart_services_all_valid():
    non_strings, invalid_entries = render_validation_lists(
        ['openvswitch-vswitchd', 'nova-compute'],
        ['openvswitch-vswitchd', 'nova-compute', 'neutron-openvswitch-agent'],
    )

    assert non_strings == []
    assert invalid_entries == []


def test_restart_services_with_invalid_name():
    non_strings, invalid_entries = render_validation_lists(
        ['openvswitch-vswitchd', 'not-a-real-service'],
        ['openvswitch-vswitchd', 'neutron-openvswitch-agent'],
    )

    assert non_strings == []
    assert invalid_entries == ['not-a-real-service']


def test_restart_services_with_non_string_entry():
    non_strings, invalid_entries = render_validation_lists(
        ['openvswitch-vswitchd', {'service': 'nova-compute'}],
        ['openvswitch-vswitchd', 'nova-compute'],
    )

    assert non_strings == [{'service': 'nova-compute'}]
    assert invalid_entries == []
