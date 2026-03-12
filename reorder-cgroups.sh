#!/usr/bin/env bash
###############################################################################
# reorder-cgroups.sh – put every running QEMU thread in neat buckets
#                     (pure v1           ✔)
#                     (hybrid v2/v1      ✔ – never touches the v2 mount)
#
# Tree on *every* legacy controller that still exists:
#
#   clouding/               ← catch-all (spare PIDs get moved here)
#   ├─ emulators/<vm>       ← QEMU main threads
#   └─ vcpus/<vm>-<vcpuN>   ← one dir per vCPU thread
#
# Additionally, QEMU PIDs are moved to clouding/ in ALL other v1
# controllers (pids, memory, freezer…) to prevent podman from killing
# VMs when the nova_libvirt container is restarted.
#
# Idempotent – run from a hook, cron, or by hand whenever you like.
###############################################################################
set -euo pipefail
shopt -s nullglob
RELEASE_AGENT=/clouding/reorder-cgroups/release-agent.sh
DEFAULT_SHARES=1024      # "normal" weight
DEFAULT_QUOTA=-1         # no CFS hard cap
###############################################################################
find_cg_mount() {
    local ctl=$1 mp
    mp=$(awk -v c="$ctl" '$9=="cgroup" && index($10,c){print $5;exit}' \
         /proc/self/mountinfo) || true
    [[ -n $mp ]] && { printf '%s\n' "$mp"; return; }
    for mp in /sys/fs/cgroup/*; do
        [[ -d $mp ]] || continue
        case $ctl in
          cpu)      [[ -e $mp/cpu.stat    ]] && { echo "$mp"; return; } ;;
          cpuacct)  [[ -e $mp/cpuacct.usage ]] && { echo "$mp"; return; } ;;
          cpuset)   [[ -e $mp/cpuset.cpus ]] && { echo "$mp"; return; } ;;
        esac
    done
    return 1
}
###############################################################################
init_root_dirs() {
    local mnt=$1 dir
    # Tell the kernel which helper to run when something goes empty
    [[ -w $mnt/release_agent ]] && printf '%s\n' "$RELEASE_AGENT" >"$mnt/release_agent"
    # Pre-create the three top-level buckets
    for dir in "$mnt"/clouding{,/emulators,/vcpus}; do
        mkdir -p "$dir"
        [[ -w $dir/cpu.shares       ]] && echo "$DEFAULT_SHARES" >"$dir/cpu.shares"
        [[ -w $dir/cpu.cfs_quota_us ]] && echo "$DEFAULT_QUOTA"  >"$dir/cpu.cfs_quota_us"
        echo 1 >"$dir/cgroup.clone_children" 2>/dev/null || true
        echo 1 >"$dir/notify_on_release"     2>/dev/null || true
    done
}
###############################################################################
ensure_notify_recursive() {
    local mnt=$1 f
    while IFS= read -r -d '' f; do
        [[ $(<"$f") == 1 ]] || echo 1 >"$f"
    done < <(find "$mnt/clouding" -type f -name notify_on_release -print0 2>/dev/null || true)
}
###############################################################################
move_pids() {
    local dst=$1; shift
    (( $# == 0 )) && return
    mkdir -p "$dst"
    echo 1 >"$dst/notify_on_release" 2>/dev/null || true
    local pid
    for pid in "$@"; do
        echo "$pid" >"$dst/tasks" 2>/dev/null || true
    done
}
###############################################################################
# MAIN
###############################################################################
controllers=(cpu cpuacct cpuset)
declare -A seen
for ctl in "${controllers[@]}"; do
    if mp=$(find_cg_mount "$ctl"); then
        seen["$mp"]=1
    fi
done
[[ ${#seen[@]} -eq 0 ]] && { echo "no legacy controllers – nothing to do"; exit 0; }
for mnt in "${!seen[@]}"; do
    init_root_dirs          "$mnt"
    ensure_notify_recursive "$mnt"
done
all_mnts=("${!seen[@]}")

declare -a epids vpids

for vm_dir in "${all_mnts[0]}"/machine*/{qemu-*libvirt-qemu,machine-qemu*scope}; do
    [[ -d $vm_dir ]] || continue
    vm_name=$(basename "$vm_dir")

    mapfile -t epids < <(cat "$vm_dir"/emulator/{tasks,cgroup.procs} 2>/dev/null || true)
    for mnt in "${all_mnts[@]}"; do
        move_pids "$mnt/clouding/emulators/$vm_name" "${epids[@]:-}"
    done

    for vdir in "$vm_dir"/vcpu*; do
        [[ -d $vdir ]] || continue
        vname=$(basename "$vdir")
        mapfile -t vpids < <(cat "$vdir"/{tasks,cgroup.procs} 2>/dev/null || true)
        for mnt in "${all_mnts[@]}"; do
            move_pids "$mnt/clouding/vcpus/${vm_name}-${vname}" "${vpids[@]:-}"
        done
    done
done

###############################################################################
# NEW: Move QEMU PIDs out of the container's cgroup in ALL remaining v1
# controllers (pids, memory, freezer, blkio, devices, net_cls, …).
#
# On cgroups-v1, systemd-machined only moves PIDs in the "systemd"
# controller hierarchy. The cpu/cpuacct/cpuset controllers are handled
# above. But podman uses other controllers (typically pids or freezer) to
# track container processes. By moving QEMU PIDs to clouding/ in those
# controllers too, podman stop/restart will no longer kill running VMs.
#
# We use pgrep to find QEMU PIDs directly rather than relying on the
# cgroup directory structure (which varies across libvirt versions).
###############################################################################
mapfile -t qemu_pids < <(pgrep -f 'qemu-system' 2>/dev/null || true)
if (( ${#qemu_pids[@]} > 0 )); then
    for ctrl_dir in /sys/fs/cgroup/*/; do
        [[ -d "$ctrl_dir" ]] || continue
        ctrl=$(basename "$ctrl_dir")
        # Skip systemd/unified (handled by systemd-machined) and already-handled mounts
        [[ "$ctrl" == "systemd" || "$ctrl" == "unified" ]] && continue
        [[ -n "${seen[$ctrl_dir]+x}" ]] && continue

        target="${ctrl_dir}clouding"
        mkdir -p "$target" 2>/dev/null || true
        echo 1 >"$target/notify_on_release" 2>/dev/null || true

        for pid in "${qemu_pids[@]}"; do
            [[ -n "$pid" ]] || continue
            echo "$pid" >"$target/cgroup.procs" 2>/dev/null || true
        done
    done
fi

shopt -u nullglob
exit 0
