#!/usr/bin/env bash
###############################################################################
# reorder-cgroups.sh – put every running QEMU thread in neat buckets
#
# Supports:
#   pure cgroups-v1        ✔
#   hybrid v2/v1           ✔  (never touches the v2 unified mount)
#   pure cgroups-v2        ✔
#
# Target tree (same logical layout on both v1 and v2):
#
#   clouding/
#   ├─ emulators/<vm>       ← QEMU main + IO + worker threads
#   └─ vcpus/<vm>-<vcpuN>   ← one dir per vCPU thread
#
# On v1: threads organized in cpu/cpuacct/cpuset controllers, then QEMU PIDs
#         moved to clouding/ in ALL remaining controllers (pids, memory,
#         freezer…) to survive podman restart.
#
# On v2: single unified hierarchy, threaded subtree under clouding/ so
#         individual threads can be placed. cpu.weight used instead of
#         cpu.shares. Moving out of container cgroup is a single operation.
#
# Idempotent – run from a hook, cron, or by hand whenever you like.
###############################################################################
set -euo pipefail
shopt -s nullglob

# v1 defaults
DEFAULT_SHARES=1024      # "normal" weight for cpu.shares
DEFAULT_QUOTA=-1         # no CFS hard cap

# v2 defaults
DEFAULT_WEIGHT=100       # "normal" weight for cpu.weight (range 1-10000)

###############################################################################
# Detect cgroups version
###############################################################################
detect_cgroup_version() {
    # Pure v2: /sys/fs/cgroup is a cgroup2 mount with no v1 controllers
    if [[ -f /sys/fs/cgroup/cgroup.controllers ]]; then
        # Check if any v1 controller mounts exist (hybrid mode)
        if awk '$9=="cgroup" {found=1} END {exit !found}' /proc/self/mountinfo 2>/dev/null; then
            echo "hybrid"
        else
            echo "v2"
        fi
    else
        echo "v1"
    fi
}

CGROUP_VERSION=$(detect_cgroup_version)

###############################################################################
#                          CGROUPS V1 FUNCTIONS
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

init_root_dirs_v1() {
    local mnt=$1 dir
    for dir in "$mnt"/clouding{,/emulators,/vcpus}; do
        mkdir -p "$dir"
        [[ -w $dir/cpu.shares       ]] && echo "$DEFAULT_SHARES" >"$dir/cpu.shares"
        [[ -w $dir/cpu.cfs_quota_us ]] && echo "$DEFAULT_QUOTA"  >"$dir/cpu.cfs_quota_us"
        echo 1 >"$dir/cgroup.clone_children" 2>/dev/null || true
    done
}

move_tids_v1() {
    local dst=$1; shift
    (( $# == 0 )) && return
    mkdir -p "$dst"
    local tid
    for tid in "$@"; do
        echo "$tid" >"$dst/tasks" 2>/dev/null || true
    done
}

run_v1() {
    local controllers=(cpu cpuacct cpuset)
    declare -A seen
    local ctl mp mnt

    for ctl in "${controllers[@]}"; do
        if mp=$(find_cg_mount "$ctl"); then
            seen["$mp"]=1
        fi
    done
    [[ ${#seen[@]} -eq 0 ]] && { echo "no legacy controllers – nothing to do"; return; }

    for mnt in "${!seen[@]}"; do
        init_root_dirs_v1 "$mnt"
    done
    local all_mnts=("${!seen[@]}")

    # Organize QEMU threads into emulators/<vm> and vcpus/<vm>-vcpuN
    mapfile -t all_qemu_pids < <(pgrep -f 'qemu-system' 2>/dev/null || true)
    local qemu_pid vm_name tid comm vcpu_num
    for qemu_pid in "${all_qemu_pids[@]}"; do
        [[ -n "$qemu_pid" && -d "/proc/$qemu_pid" ]] || continue

        local cmdline
        cmdline=$(< "/proc/$qemu_pid/cmdline" tr '\0' ' ' 2>/dev/null) || continue
        if [[ "$cmdline" =~ -name\ guest=([^, ]+) ]]; then
            vm_name="${BASH_REMATCH[1]}"
        else
            continue
        fi

        declare -a emu_tids=()
        local tid_dir
        for tid_dir in /proc/"$qemu_pid"/task/*/; do
            [[ -d "$tid_dir" ]] || continue
            tid=$(basename "$tid_dir")
            comm=$(cat "$tid_dir/comm" 2>/dev/null) || continue
            if [[ "$comm" == *"/KVM" ]]; then
                vcpu_num=${comm#CPU }
                vcpu_num=${vcpu_num%/KVM}
                vcpu_num=${vcpu_num// /}
                for mnt in "${all_mnts[@]}"; do
                    move_tids_v1 "$mnt/clouding/vcpus/${vm_name}-vcpu${vcpu_num}" "$tid"
                done
            else
                emu_tids+=("$tid")
            fi
        done

        for mnt in "${all_mnts[@]}"; do
            move_tids_v1 "$mnt/clouding/emulators/$vm_name" "${emu_tids[@]:-}"
        done
        unset emu_tids
    done

    # Move QEMU PIDs and their KVM kernel threads out of the container's
    # cgroup scope in EVERY v1 controller. This prevents podman from killing
    # VMs on restart, while leaving container processes (libvirtd, etc.) in
    # the scope so podman can still manage them.
    #
    # Collect: QEMU PIDs + kvm-* kernel threads (e.g. kvm-nx-lpage-recovery)
    mapfile -t qemu_pids < <(pgrep -f 'qemu-system' 2>/dev/null || true)
    local all_vm_pids=()
    local qpid kvm_tid
    for qpid in "${qemu_pids[@]}"; do
        [[ -n "$qpid" ]] || continue
        all_vm_pids+=("$qpid")
        # kvm kernel threads are named kvm-*-<qemu_pid>
        while IFS= read -r kvm_tid; do
            [[ -n "$kvm_tid" ]] && all_vm_pids+=("$kvm_tid")
        done < <(pgrep -f "kvm-.*-${qpid}$" 2>/dev/null || true)
    done

    if (( ${#all_vm_pids[@]} > 0 )); then
        local ctrl_dir ctrl target pid
        for ctrl_dir in /sys/fs/cgroup/*/; do
            [[ -d "$ctrl_dir" ]] || continue
            [[ -L "${ctrl_dir%/}" ]] && continue
            ctrl=$(basename "$ctrl_dir")
            [[ "$ctrl" == "systemd" || "$ctrl" == "unified" ]] && continue
            # Skip controllers already organized by the top section (cpu/cpuacct/cpuset)
            # — writing cgroup.procs here would undo the per-thread placement
            [[ -n "${seen[${ctrl_dir%/}]+x}" ]] && continue

            target="${ctrl_dir}clouding"
            mkdir -p "$target" 2>/dev/null || true

            for pid in "${all_vm_pids[@]}"; do
                [[ -n "$pid" ]] || continue
                echo "$pid" >"$target/cgroup.procs" 2>/dev/null \
                    || echo "$pid" >"$target/tasks" 2>/dev/null || true
            done
        done
    fi
}

###############################################################################
#                          CGROUPS V2 FUNCTIONS
###############################################################################

init_root_dirs_v2() {
    local base=$1 dir

    # Enable threaded controllers (cpu, cpuset) in the parent
    local controllers
    controllers=$(cat "$base/cgroup.controllers" 2>/dev/null) || true
    for ctl in $controllers; do
        echo "+$ctl" >"$base/cgroup.subtree_control" 2>/dev/null || true
    done

    mkdir -p "$base/clouding"

    # Enable cpu in clouding/'s subtree BEFORE creating children
    for ctl in cpu cpuset; do
        echo "+$ctl" >"$base/clouding/cgroup.subtree_control" 2>/dev/null || true
    done

    # Create first child and set it to "threaded" — this makes clouding/
    # become "domain threaded" (the threaded subtree root). All subsequent
    # children will automatically inherit "threaded" type.
    mkdir -p "$base/clouding/emulators"
    echo "threaded" >"$base/clouding/emulators/cgroup.type" 2>/dev/null || true
    # Now clouding/ should be "domain threaded"

    mkdir -p "$base/clouding/vcpus"
    # vcpus/ auto-inherits "threaded" since parent is now "domain threaded"
    # but set explicitly in case it was created before the parent became threaded
    echo "threaded" >"$base/clouding/vcpus/cgroup.type" 2>/dev/null || true

    for dir in "$base"/clouding/{emulators,vcpus}; do
        [[ -w $dir/cpu.weight ]] && echo "$DEFAULT_WEIGHT" >"$dir/cpu.weight"
    done
}

move_tids_v2() {
    local dst=$1; shift
    (( $# == 0 )) && return
    mkdir -p "$dst"
    echo "threaded" >"$dst/cgroup.type" 2>/dev/null || true
    [[ -w "$dst/cpu.weight" ]] && echo "$DEFAULT_WEIGHT" >"$dst/cpu.weight"
    local tid
    for tid in "$@"; do
        echo "$tid" >"$dst/cgroup.threads" 2>/dev/null || true
    done
}

run_v2() {
    local base="/sys/fs/cgroup"

    init_root_dirs_v2 "$base"

    mapfile -t all_qemu_pids < <(pgrep -f 'qemu-system' 2>/dev/null || true)
    (( ${#all_qemu_pids[@]} == 0 )) && { echo "no QEMU processes found"; return; }

    local qemu_pid vm_name tid comm vcpu_num
    for qemu_pid in "${all_qemu_pids[@]}"; do
        [[ -n "$qemu_pid" && -d "/proc/$qemu_pid" ]] || continue

        local cmdline
        cmdline=$(< "/proc/$qemu_pid/cmdline" tr '\0' ' ' 2>/dev/null) || continue
        if [[ "$cmdline" =~ -name\ guest=([^, ]+) ]]; then
            vm_name="${BASH_REMATCH[1]}"
        else
            continue
        fi

        # Step 1: Move the whole process into clouding/ (the threaded domain
        # root) via cgroup.procs. This associates all threads with the
        # threaded subtree so we can distribute them individually.
        echo "$qemu_pid" >"$base/clouding/cgroup.procs" 2>/dev/null || true

        # Step 2: Distribute threads into emulators/<vm> and vcpus/<vm>-vcpuN
        declare -a emu_tids=()
        local tid_dir
        for tid_dir in /proc/"$qemu_pid"/task/*/; do
            [[ -d "$tid_dir" ]] || continue
            tid=$(basename "$tid_dir")
            comm=$(cat "$tid_dir/comm" 2>/dev/null) || continue
            if [[ "$comm" == *"/KVM" ]]; then
                vcpu_num=${comm#CPU }
                vcpu_num=${vcpu_num%/KVM}
                vcpu_num=${vcpu_num// /}
                move_tids_v2 "$base/clouding/vcpus/${vm_name}-vcpu${vcpu_num}" "$tid"
            else
                emu_tids+=("$tid")
            fi
        done

        move_tids_v2 "$base/clouding/emulators/$vm_name" "${emu_tids[@]:-}"
        unset emu_tids
    done

    # Also move kvm-* kernel threads to clouding/
    for qemu_pid in "${all_qemu_pids[@]}"; do
        [[ -n "$qemu_pid" ]] || continue
        local kvm_tid
        while IFS= read -r kvm_tid; do
            [[ -n "$kvm_tid" ]] && echo "$kvm_tid" >"$base/clouding/cgroup.procs" 2>/dev/null || true
        done < <(pgrep -f "kvm-.*-${qemu_pid}$" 2>/dev/null || true)
    done

    echo "v2: QEMU threads organized under $base/clouding/"
}

###############################################################################
# Cleanup: remove empty leaf cgroup dirs left behind after VMs stop.
# Runs on every invocation — walks depth-first so parent dirs become
# removable after their children are cleaned.
###############################################################################
cleanup_empty_dirs() {
    local base=$1
    [[ -d "$base/clouding" ]] || return 0

    # Walk depth-first: deepest dirs first so parents become empty after
    # children are removed. Only remove dirs inside emulators/ and vcpus/,
    # never the structural dirs (clouding, emulators, vcpus themselves).
    local dir
    while IFS= read -r dir; do
        # Skip the structural dirs we always want to keep
        case "$dir" in
            "$base/clouding"|"$base/clouding/emulators"|"$base/clouding/vcpus") continue ;;
        esac
        # A cgroup dir is empty if it has no tasks/threads and no child dirs
        local has_tasks=0
        if [[ -f "$dir/tasks" ]]; then
            [[ -s "$dir/tasks" ]] && has_tasks=1
        elif [[ -f "$dir/cgroup.threads" ]]; then
            [[ -s "$dir/cgroup.threads" ]] && has_tasks=1
        fi
        if (( ! has_tasks )); then
            # Check no child cgroup dirs exist (only pseudo-files remain)
            local has_children=0
            for child in "$dir"/*/; do
                [[ -d "$child" ]] && { has_children=1; break; }
            done
            (( has_children )) || rmdir "$dir" 2>/dev/null || true
        fi
    done < <(find "$base/clouding/emulators" "$base/clouding/vcpus" \
                  -mindepth 1 -type d 2>/dev/null | sort -r)
}

###############################################################################
#                              MAIN
###############################################################################
echo "Detected cgroups: $CGROUP_VERSION"

case "$CGROUP_VERSION" in
    v1|hybrid)
        # Cleanup stale dirs in all v1 controller mounts
        for cg_mnt in /sys/fs/cgroup/*/; do
            [[ -d "$cg_mnt" ]] || continue
            [[ -L "${cg_mnt%/}" ]] && continue
            cleanup_empty_dirs "${cg_mnt%/}"
        done
        run_v1
        ;;
    v2)
        cleanup_empty_dirs "/sys/fs/cgroup"
        run_v2
        ;;
esac

shopt -u nullglob
exit 0
