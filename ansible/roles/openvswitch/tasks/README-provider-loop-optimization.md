# Design note: provider loop optimization in `openvswitch` role

## Scope

This note describes the current execution flow and optimization direction for:

- `ansible/roles/openvswitch/tasks/post-config.yml`
- `ansible/roles/openvswitch/tasks/provider_interface.yml`

It targets high-scale deployments where many provider mappings are processed in one Ansible run.

## 1) Current behavior summary

### `tasks/post-config.yml`

1. Initializes and probes OVSDB reachability (`ovsdb_reachable`) for managed or external DB paths.
2. Applies global Open_vSwitch settings (`external_ids:system-id`, `external_ids:hostname`, `other_config:hw-offload`) when reachable.
3. Ensures provider bridges exist (via `include_tasks: provider_bridge.yml`) when bridge management conditions are met.
4. Builds `openvswitch_provider_interface_mappings` by pairing:
   - `neutron_bridge_name` entries (bridge side)
   - `neutron_external_interface` entries (port/interface side)
   - optional per-port `openvswitch_provider_port_options`
5. Iterates mappings and calls `include_tasks: provider_interface.yml` once per mapping with:
   - `provider_bridge`
   - `provider_port`
   - `provider_port_options`

The mapping loop is currently the fan-out point that drives repeated per-port work.

### `tasks/provider_interface.yml`

For each mapping entry:

1. **Early guards / no-op paths**
   - Skip empty bridge name.
   - Skip empty interface.
   - Warn and skip when `provider_bridge == provider_port` (bridge-to-self case).
2. **Bridge membership check and attach path**
   - `ovs-vsctl port-to-br <provider_port>` to detect current bridge.
   - Fail if attached to another bridge (`current_bridge != provider_bridge`).
   - Attach with `ovs-vsctl --may-exist add-port` when currently unattached.
3. **Port state + option updates**
   - If `provider_port_options` is non-empty, read port state via:
     - `ovs-vsctl --format=json --columns=... find Port "name=..."`
   - Parse JSON and compare canonicalized values.
   - Conditionally run `ovs-vsctl set Port` for each key present in options:
     - `tag`, `trunks`, `external_ids`, `other_config`, `type`, `options`

This keeps idempotency by comparing desired and current state before each setter task.

## 2) Typical high-scale case and repeated `ovs-vsctl` calls

In environments with 40+ provider/VLAN mappings (for example one bridge per provider network or dense trunk definitions):

- `post-config.yml` invokes `provider_interface.yml` 40+ times.
- Each iteration may call at least:
  - one `port-to-br` read, and
  - one `find Port` read when options are supplied.
- Setter tasks (`set Port ...`) are conditional, but read operations are still repeated per mapping.

Therefore, repeated OVS queries occur in `provider_interface.yml` at:

- **Get current bridge for provider interface** (`ovs-vsctl ... port-to-br`)
- **Collect provider interface state** (`ovs-vsctl ... find Port ...`)

At high scale, these per-item reads dominate task count and control-plane overhead.

## 3) Optimization goals

### Goal A: Minimize per-port state reads via one bulk query

Refactor flow so per-run OVS state is prefetched once (or in a small fixed number of calls), then consumed by each mapping iteration.

Suggested implementation shape:

1. In `post-config.yml` (before `include_tasks: provider_interface.yml` loop), add a bulk gather task that returns bridge membership and relevant `Port` columns for all ports.
2. Parse into dictionaries keyed by port name (for example `openvswitch_port_to_bridge_map`, `openvswitch_port_state_map`).
3. Pass maps (or set as facts) for lookup in `provider_interface.yml`.
4. In `provider_interface.yml`, replace per-port read commands with map lookups.

### Goal B: Keep existing safety checks

Maintain the current safeguards exactly:

- Empty bridge name skip.
- Empty interface skip.
- `provider_bridge == provider_port` skip/warn.
- Fail when an interface is already attached to a different bridge.

### Goal C: Preserve idempotency and `provider_port_options` semantics

Retain current compare-before-set behavior:

- Keep canonical comparison logic for `tag`, `trunks`, `external_ids`, `other_config`, `type`, `options`.
- Continue updating only keys explicitly provided in `provider_port_options`.
- Avoid changing behavior for mappings with empty/no options.

## 4) Acceptance criteria

1. **Fewer tasks executed in large mapping runs**
   - For 40+ mappings, total executed tasks in provider interface handling is measurably lower than current per-mapping read pattern.
2. **Fewer OVS queries**
   - Per-port `port-to-br` and per-port `find Port` calls are removed/reduced in favor of bulk retrieval.
3. **No functional regressions**
   - Guard behavior remains unchanged for empty values and bridge-self case.
   - Attached-to-other-bridge still fails.
   - Port attach behavior and option application are unchanged.
   - Idempotency remains intact across repeated runs.

## Implementation mapping reference

- Loop construction and include fan-out:
  - `ansible/roles/openvswitch/tasks/post-config.yml`
  - task: **Build provider bridge interface mappings**
  - task: **Ensure provider bridge interfaces are attached**
- Per-mapping logic:
  - `ansible/roles/openvswitch/tasks/provider_interface.yml`
  - task: **Get current bridge for provider interface ...**
  - task: **Collect provider interface ... state**
  - tasks: **Configure provider interface ... {tag,trunks,external_ids,other_config,type,options}**
