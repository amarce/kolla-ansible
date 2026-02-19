import json
import os
import shutil
import subprocess  # nosec B404
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent
ANSIBLE_PLAYBOOK = shutil.which("ansible-playbook")

if ANSIBLE_PLAYBOOK is None:
    pytest.skip("ansible-playbook not installed", allow_module_level=True)


def _run_playbook(playbook, inventory, state_file, command_log_file=None, check=True):
    env = os.environ.copy()
    stub_library = REPO_ROOT / "ansible" / "library"
    real_library = REPO_ROOT.parent / "ansible" / "library"
    library_parts = [str(stub_library), str(real_library)]
    existing_library = env.get("ANSIBLE_LIBRARY")
    if existing_library:
        library_parts.append(existing_library)

    env.update(
        {
            "ANSIBLE_PYTHON_INTERPRETER": sys.executable,
            "ANSIBLE_LIBRARY": os.pathsep.join(library_parts),
            "ANSIBLE_ROLES_PATH": str(REPO_ROOT.parent / "ansible" / "roles"),
            "OVS_STATE_PATH": str(state_file),
        }
    )

    if command_log_file is not None:
        env["OVS_COMMAND_LOG_PATH"] = str(command_log_file)

    result = subprocess.run(  # nosec B603 B607
        [ANSIBLE_PLAYBOOK, "-i", str(inventory), str(playbook)],
        check=check,
        capture_output=True,
        text=True,
        env=env,
    )
    return result


def _extract_changed(summary):
    for line in summary.splitlines():
        if "changed=" in line and line.strip().startswith("localhost"):
            for part in line.replace(":", " ").split():
                if part.startswith("changed="):
                    return int(part.split("=", 1)[1])
    raise AssertionError(f"Unable to locate changed= summary in output:\n{summary}")


@pytest.mark.parametrize("fail_mode", ["secure", "standalone"])
def test_provider_bridges_are_idempotent_with_explicit_fail_mode(tmp_path, fail_mode):
    inventory = tmp_path / "inventory"
    python_path = sys.executable
    inventory.write_text(
        f"[network]\nlocalhost ansible_connection=local ansible_python_interpreter={python_path}\n",
        encoding="utf-8",
    )

    playbook = tmp_path / "playbook.yml"
    playbook.write_text(
        f"""---
- hosts: network
  gather_facts: false
  vars:
    kolla_action: deploy
    kolla_container_engine: podman
    ovs_provider_fail_mode: {fail_mode}
    provider_bridges:
      - br-provider
      - br-floating
  tasks:
    - name: Manage provider bridges
      include_role:
        name: openvswitch
        tasks_from: provider_bridge
""",
        encoding="utf-8",
    )

    state_file = tmp_path / "ovs_state.json"

    first_run = _run_playbook(playbook, inventory, state_file).stdout
    assert _extract_changed(first_run) > 0

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert sorted(state["bridges"].keys()) == ["br-floating", "br-provider"]
    for bridge in ("br-floating", "br-provider"):
        assert state["bridges"][bridge]["fail_mode"] == fail_mode

    second_run = _run_playbook(playbook, inventory, state_file).stdout
    assert _extract_changed(second_run) == 0


@pytest.mark.parametrize(
    "raw_fail_mode",
    ['"SECURE"', " secure ", "SECURE"],
)
def test_provider_bridge_fail_mode_normalization_is_idempotent(tmp_path, raw_fail_mode):
    inventory = tmp_path / "inventory"
    python_path = sys.executable
    inventory.write_text(
        f"[network]\nlocalhost ansible_connection=local ansible_python_interpreter={python_path}\n",
        encoding="utf-8",
    )

    playbook = tmp_path / "playbook.yml"
    playbook.write_text(
        """---
- hosts: network
  gather_facts: false
  vars:
    kolla_action: deploy
    kolla_container_engine: podman
    ovs_provider_fail_mode: "  Secure  "
    provider_bridges:
      - br-provider
  tasks:
    - name: Manage provider bridges
      include_role:
        name: openvswitch
        tasks_from: provider_bridge
""",
        encoding="utf-8",
    )

    state_file = tmp_path / "ovs_state.json"
    state_file.write_text(
        json.dumps({"bridges": {"br-provider": {"fail_mode": raw_fail_mode, "ports": []}}}),
        encoding="utf-8",
    )

    first_run = _run_playbook(playbook, inventory, state_file).stdout
    assert _extract_changed(first_run) == 0

    second_run = _run_playbook(playbook, inventory, state_file).stdout
    assert _extract_changed(second_run) == 0


def test_large_provider_bridge_list_uses_bulk_state_and_is_idempotent(tmp_path):
    inventory = tmp_path / "inventory"
    python_path = sys.executable
    inventory.write_text(
        f"[network]\nlocalhost ansible_connection=local ansible_python_interpreter={python_path}\n",
        encoding="utf-8",
    )

    bridge_count = 40
    provider_bridges = [f"br-provider-{index}" for index in range(bridge_count)]

    playbook = tmp_path / "playbook.yml"
    playbook.write_text(
        """---
- hosts: network
  gather_facts: false
  vars:
    kolla_action: deploy
    kolla_container_engine: podman
    ovs_provider_fail_mode: standalone
    provider_bridges: {{ provider_bridges_json }}
  tasks:
    - name: Manage provider bridges
      include_role:
        name: openvswitch
        tasks_from: provider_bridge
""".replace("{{ provider_bridges_json }}", json.dumps(provider_bridges)),
        encoding="utf-8",
    )

    state_file = tmp_path / "ovs_state.json"
    command_log = tmp_path / "ovs_commands.log"

    first_run = _run_playbook(playbook, inventory, state_file, command_log).stdout
    assert _extract_changed(first_run) > 0

    second_run = _run_playbook(playbook, inventory, state_file, command_log).stdout
    assert _extract_changed(second_run) == 0

    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert sorted(state["bridges"].keys()) == sorted(provider_bridges)
    for bridge in provider_bridges:
        assert state["bridges"][bridge]["fail_mode"] == "standalone"

    commands = [line.strip() for line in command_log.read_text(encoding="utf-8").splitlines() if line.strip()]
    assert any(command == "--format=json --columns=name,fail_mode list Bridge" for command in commands)
    assert all(not command.startswith("br-exists ") for command in commands)
    assert all(not command.startswith("get Bridge ") for command in commands)


def test_missing_explicit_provider_fail_mode_fails_fast_when_required(tmp_path):
    inventory = tmp_path / "inventory"
    python_path = sys.executable
    inventory.write_text(
        """[network]
localhost ansible_connection=local ansible_python_interpreter={python_path}
[compute]
[neutron-dhcp-agent]
[neutron-l3-agent]
[neutron-metadata-agent]
[manila-share]
""".format(python_path=python_path),
        encoding="utf-8",
    )

    playbook = tmp_path / "playbook.yml"
    playbook.write_text(
        """---
- hosts: network
  gather_facts: false
  vars:
    kolla_action: deploy
    kolla_container_engine: podman
    neutron_bridge_name: br-provider
    openvswitch_require_explicit_provider_fail_mode: true
    openvswitch_services:
      openvswitch-vswitchd:
        host_in_groups: false
  tasks:
    - name: Run post-config checks
      include_role:
        name: openvswitch
        tasks_from: post-config
""",
        encoding="utf-8",
    )

    state_file = tmp_path / "ovs_state.json"

    failed_run = _run_playbook(playbook, inventory, state_file, check=False)
    assert failed_run.returncode != 0
    combined_output = f"{failed_run.stdout}\n{failed_run.stderr}"
    assert "openvswitch_require_explicit_provider_fail_mode=true requires" in combined_output
    assert "group_vars/network/openvswitch.yml" in combined_output
    assert "/etc/kolla/globals.yml" in combined_output
