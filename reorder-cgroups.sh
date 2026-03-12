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

RELEASE_AGENT=/clouding/reorder-cgroups/release-agent.sh

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
    [[ -w $mnt/release_agent ]] && printf '%s\n' "$RELEASE_AGENT" >"$mnt/release_agent"
    for dir in "$mnt"/clouding{,/emulators,/vcpus}; do
        mkdir -p "$dir"
        [[ -w $dir/cpu.shares       ]] && echo "$DEFAULT_SHARES" >"$dir/cpu.shares"
        [[ -w $dir/cpu.cfs_quota_us ]] && echo "$DEFAULT_QUOTA"  >"$dir/cpu.cfs_quota_us"
        echo 1 >"$dir/cgroup.clone_children" 2>/dev/null || true
        echo 1 >"$dir/notify_on_release"     2>/dev/null || true
    done
}

ensure_notify_recursive_v1() {
    local mnt=$1 f
    while IFS= read -r -d '' f; do
        [[ $(<"$f") == 1 ]] || echo 1 >"$f"
    done < <(find "$mnt/clouding" -type f -name notify_on_release -print0 2>/dev/null || true)
}

move_tids_v1() {
    local dst=$1; shift
    (( $# == 0 )) && return
    mkdir -p "$dst"
    echo 1 >"$dst/notify_on_release" 2>/dev/null || true
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
        init_root_dirs_v1          "$mnt"
        ensure_notify_recursive_v1 "$mnt"
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

    # Move QEMU PIDs out of container cgroup in ALL remaining v1 controllers
    mapfile -t qemu_pids < <(pgrep -f 'qemu-system' 2>/dev/null || true)
    if (( ${#qemu_pids[@]} > 0 )); then
        local ctrl_dir ctrl target pid
        for ctrl_dir in /sys/fs/cgroup/*/; do
            [[ -d "$ctrl_dir" ]] || continue
            [[ -L "${ctrl_dir%/}" ]] && continue
            ctrl=$(basename "$ctrl_dir")
            [[ "$ctrl" == "systemd" || "$ctrl" == "unified" ]] && continue
            [[ -n "${seen[${ctrl_dir%/}]+x}" ]] && continue

            target="${ctrl_dir}clouding"
            mkdir -p "$target" 2>/dev/null || true
            echo 1 >"$target/notify_on_release" 2>/dev/null || true

            for pid in "${qemu_pids[@]}"; do
                [[ -n "$pid" ]] || continue
                echo "$pid" >"$target/cgroup.procs" 2>/dev/null || true
            done
        done
    fi
}

###############################################################################
#                          CGROUPS V2 FUNCTIONS
###############################################################################

# Find which cgroup the container (our process) lives in.
# On v2 everything is under /sys/fs/cgroup/<slice>/<scope>/
find_container_cgroup_v2() {
    local cg
    cg=$(cat /proc/self/cgroup 2>/dev/null) || true
    # v2 line is "0::/<path>"
    if [[ "$cg" =~ 0::(/.*) ]]; then
        echo "/sys/fs/cgroup${BASH_REMATCH[1]}"
    else
        echo "/sys/fs/cgroup"
    fi
}

init_root_dirs_v2() {
    local base=$1 dir

    # Enable controllers in the parent so children can use them
    # We need cpu and cpuset at minimum
    local available
    available=$(cat "$base/cgroup.subtree_control" 2>/dev/null) || true

    # Enable all available controllers for the subtree
    local controllers
    controllers=$(cat "$base/cgroup.controllers" 2>/dev/null) || true
    for ctl in $controllers; do
        echo "+$ctl" >"$base/cgroup.subtree_control" 2>/dev/null || true
    done

    mkdir -p "$base/clouding"

    # Enable controllers in clouding/ subtree
    controllers=$(cat "$base/clouding/cgroup.controllers" 2>/dev/null) || true
    for ctl in $controllers; do
        echo "+$ctl" >"$base/clouding/cgroup.subtree_control" 2>/dev/null || true
    done

    # Make clouding/ a threaded subtree — this allows per-thread placement
    # and avoids the "no internal processes" rule
    echo "threaded" >"$base/clouding/cgroup.type" 2>/dev/null || true

    for dir in "$base"/clouding/{emulators,vcpus}; do
        mkdir -p "$dir"
        echo "threaded" >"$dir/cgroup.type" 2>/dev/null || true
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

    # On pure v2, we create our tree directly under /sys/fs/cgroup
    # The container cgroup is somewhere deeper; we move QEMU threads up and out
    init_root_dirs_v2 "$base"

    # Organize QEMU threads into emulators/<vm> and vcpus/<vm>-vcpuN
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

    # On v2, moving threads to clouding/ subtree already takes them out of
    # the container's cgroup (single hierarchy). No extra per-controller
    # loop needed — that's the beauty of unified v2.
    echo "v2: QEMU threads organized under $base/clouding/"
}

###############################################################################
#                              MAIN
###############################################################################
echo "Detected cgroups: $CGROUP_VERSION"

case "$CGROUP_VERSION" in
    v1|hybrid)
        run_v1
        ;;
    v2)
        run_v2
        ;;
esac

shopt -u nullglob
exit 0
