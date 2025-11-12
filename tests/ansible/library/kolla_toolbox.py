"""Test stub for the kolla_toolbox Ansible module.

This stub emulates the subset of functionality used by the Open vSwitch
provider bridge tasks.  It keeps Open vSwitch state in a JSON file whose path is
provided via the ``OVS_STATE_PATH`` environment variable.
"""

import json
import os
from pathlib import Path

from ansible.module_utils.basic import AnsibleModule

STATE_TEMPLATE = {"bridges": {}}


def load_state(path: Path) -> dict:
    if path.exists():
        try:
            with path.open("r", encoding="utf-8") as handle:
                return json.load(handle)
        except (json.JSONDecodeError, OSError):
            pass
    return json.loads(json.dumps(STATE_TEMPLATE))


def save_state(path: Path, state: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(state, handle)


def ovs_vsctl(argv, state):
    if not argv:
        return False, 1, "", "missing ovs-vsctl arguments"

    cmd = argv[0]

    if cmd == "br-exists":
        bridge = argv[1]
        exists = bridge in state["bridges"]
        return False, 0 if exists else 2, "", ""

    if cmd == "--may-exist" and len(argv) >= 3 and argv[1] == "add-br":
        bridge = argv[2]
        if bridge in state["bridges"]:
            return False, 0, "", ""
        state["bridges"][bridge] = {"fail_mode": "", "ports": []}
        return True, 0, "", ""

    if cmd == "get-fail-mode":
        bridge = argv[1]
        if bridge not in state["bridges"]:
            return False, 2, "", ""
        fail_mode = state["bridges"][bridge]["fail_mode"]
        return False, 0, fail_mode or "[]", ""

    if cmd == "get" and len(argv) >= 4 and argv[1] == "Bridge" and argv[3] == "fail_mode":
        bridge = argv[2]
        if bridge not in state["bridges"]:
            return False, 2, "", ""
        fail_mode = state["bridges"][bridge]["fail_mode"]
        return False, 0, f'"{fail_mode}"' if fail_mode else "[]", ""

    if cmd == "set-fail-mode" and len(argv) >= 3:
        bridge = argv[1]
        mode = argv[2]
        if bridge not in state["bridges"]:
            return False, 1, "", "bridge does not exist"
        current = state["bridges"][bridge]["fail_mode"]
        if current == mode:
            return False, 0, "", ""
        state["bridges"][bridge]["fail_mode"] = mode
        return True, 0, "", ""

    if cmd == "--may-exist" and len(argv) >= 4 and argv[1] == "add-port":
        bridge = argv[2]
        port = argv[3]
        if bridge not in state["bridges"]:
            return False, 1, "", "bridge does not exist"
        ports = state["bridges"][bridge].setdefault("ports", [])
        if port in ports:
            return False, 0, "", ""
        ports.append(port)
        return True, 0, "", ""

    if cmd == "list-ports" and len(argv) >= 2:
        bridge = argv[1]
        if bridge not in state["bridges"]:
            return False, 1, "", "bridge does not exist"
        ports = state["bridges"][bridge].get("ports", [])
        return False, 0, "\n".join(ports), ""

    return False, 1, "", f"unsupported ovs-vsctl command: {' '.join(argv)}"


def main():
    module = AnsibleModule(
        argument_spec=dict(
            container_engine=dict(type="str", required=False),
            user=dict(type="str", required=False),
            module_name=dict(type="str", required=True),
            module_args=dict(type="dict", required=False, default={}),
        ),
        supports_check_mode=False,
    )

    if module.params["module_name"] != "command":
        module.exit_json(changed=False, rc=0, stdout="", stderr="")

    argv = module.params["module_args"].get("argv", [])
    if not argv:
        module.fail_json(msg="argv is required", rc=1)

    if argv[0] != "ovs-vsctl":
        module.fail_json(msg="only ovs-vsctl commands are supported", rc=1)

    state_path = Path(os.environ.get("OVS_STATE_PATH", "ovs_state.json"))
    state = load_state(state_path)

    changed, rc, stdout, stderr = ovs_vsctl(argv[1:], state)

    if rc != 0 and rc not in (2,):
        module.fail_json(msg=stderr or "ovs-vsctl failed", rc=rc, stdout=stdout)

    if changed:
        save_state(state_path, state)

    module.exit_json(changed=changed, rc=rc, stdout=stdout, stderr=stderr)


if __name__ == "__main__":
    main()
