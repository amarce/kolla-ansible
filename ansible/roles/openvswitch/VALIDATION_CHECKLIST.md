# Open vSwitch Provider Interface Validation Checklist

Use this checklist to validate provider interface behavior implemented in:

- `ansible/roles/openvswitch/tasks/post-config.yml`
- `ansible/roles/openvswitch/tasks/provider_interface.yml`

## Prerequisites

- Run against a host in `network` group (or `compute` with `computes_need_external_bridge: true`).
- Ensure `openvswitch_services['openvswitch-vswitchd'].host_in_groups | bool` is true.
- Set at least one mapping in `neutron_bridge_name` and `neutron_external_interface`.
- For option-field checks, set `openvswitch_provider_port_options` for selected ports.

---

## 1) First run: expected changes when ports are missing or options differ

### Setup
- Pick one mapping where the provider port is **not attached** to the target bridge.
- Pick one mapping where the provider port is attached, but one or more of these fields differ from desired state: `tag`, `trunks`, `external_ids`, `other_config`, `type`, `options`.

### Validate
- Run `kolla-ansible -i <inventory> reconfigure --tags openvswitch` (or the equivalent play invoking this role).
- Confirm changes in task output for both files:
  - `post-config.yml`: includes provider mapping preparation and provider interface inclusion.
  - `provider_interface.yml`: shows add-port and/or set Port operations for mismatched fields.
- Verify OVSDB state after run:
  - Missing port mapping now exists on expected bridge.
  - Option fields now match the requested values in `openvswitch_provider_port_options`.

### Expected result
- First run reports `changed` for at least the affected mapping(s)/field(s).
- No failure unless a port is already attached to a **different** bridge (that should fail by design).

---

## 2) Second run: no changes when already converged

### Validate
- Re-run the same command with identical inventory and variables.
- Confirm tasks in both files are idempotent:
  - No additional bridge-port attachments.
  - No option-field updates when canonicalized values already match.

### Expected result
- Second run reports `ok`/`skipped` only for the already converged provider mappings.
- `changed=0` for provider-interface reconciliation path.

---

## 3) Fallback path when bulk port query fails (per-port read still works)

### Setup
- Simulate failure of bulk query in `post-config.yml` task `Bulk query provider port state from OVSDB` (e.g., temporary command fault/injected failure).
- Keep OVSDB otherwise reachable so per-port reads in `provider_interface.yml` can run.

### Validate
- Ensure bulk query returns non-zero or empty usable output.
- Confirm execution continues to `Ensure provider bridge interfaces are attached` include.
- In `provider_interface.yml`, verify `Collect provider interface {{ provider_port }} state` still runs for mappings with option data when preloaded state is absent.

### Expected result
- Role does not abort solely due to bulk query failure.
- Per-port `find Port` reads provide state needed for option reconciliation.
- Final provider bridge/option convergence remains correct.

---

## 4) Existing compatibility behavior for older OVS around `port-to-br` non-zero handling

### Validate
- Exercise a case where `ovs-vsctl port-to-br <port>` returns non-zero for an unattached/nonexistent port.
- Confirm `provider_interface.yml` task `Get current bridge for provider interface {{ provider_port }}` does **not** fail (`failed_when: false`).
- Confirm follow-up logic interprets non-zero as no current bridge and proceeds to attach when appropriate.

### Expected result
- No fatal failure from `port-to-br` non-zero return.
- Behavior remains compatible with older OVS releases lacking robust introspection flags for this command path.

---

## 5) Large-scale scenario sanity check (40+ VLAN mappings)

### Setup
- Define at least 40 provider mappings across `neutron_bridge_name` / `neutron_external_interface`.
- Include realistic `openvswitch_provider_port_options` for many ports.

### Validate
- Run one reconciliation pass and capture task timing/summary.
- Confirm `post-config.yml` executes a single bulk `list Port` query and builds `openvswitch_provider_port_state_map`.
- Confirm `provider_interface.yml` consumes preloaded state (`provider_port_state_preloaded`) and avoids per-port `find Port` reads when preloaded data exists.
- Compare against prior behavior baseline (or expected old pattern):
  - Fewer per-port state-read invocations.
  - Fewer repeated skip-heavy tasks caused by self-mapping/invalid mappings due to pre-filtering/splitting in `post-config.yml`.

### Expected result
- Functional convergence still correct at scale.
- Noticeably reduced OVSDB read churn and cleaner task output for large mapping sets.

---

## Sign-off template

- [ ] First-run convergence (missing attachment + option drift) validated.
- [ ] Second-run idempotency validated.
- [ ] Bulk-query failure fallback validated (per-port read path works).
- [ ] Legacy `port-to-br` non-zero compatibility validated.
- [ ] 40+ mapping large-scale sanity check validated.
