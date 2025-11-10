# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import copy
import json
import logging
import os
import re
import shlex
from abc import ABC, abstractmethod
from difflib import unified_diff

from ansible.module_utils.kolla_systemd_worker import SystemdWorker

COMPARE_CONFIG_CMD = ["/usr/local/bin/kolla_set_configs", "--check"]
LOG = logging.getLogger(__name__)

# functions exported for use by other module_utils
__all__ = ["_as_iter", "_as_dict", "ensure_host_path"]


def _normalise_caps(value):
    """Return a sorted list of unique caps (lower-cased) or []."""
    if not value:
        return []
    if isinstance(value, str):
        value = [value]
    return sorted({cap.lower() for cap in value})


def _normalise_list(value):
    """Return a set built from the value or an empty set."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value}


def _normalise_dict(value):
    """Return a dict without keys whose value evaluates to False."""
    return {k: v for k, v in (value or {}).items() if v not in (None, "", [], {}, ())}


def _lists_differ(spec, live):
    return _normalise_list(spec) != _normalise_list(live)


def _dicts_differ(spec, live):
    return _normalise_dict(spec) != _normalise_dict(live)


def _as_list(value):
    if value in (None, False):
        return []
    return list(value)


def _as_iter(value):
    if value in (None, False):
        return []
    if isinstance(value, (list, tuple, set)):
        return list(value)
    return [value]


def _as_dict(value):
    """Convert *value* into a dict.

    Accepted forms:
    * dict → returned unchanged
    * iterable of "KEY=VAL" strings → {"KEY": "VAL", …}
    * None/empty → {}
    Raises TypeError otherwise.
    """

    if not value:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, (list, tuple, set)):
        out = {}
        for item in value:
            if not isinstance(item, str) or "=" not in item:
                raise TypeError(f"invalid KV item: {item!r}")
            k, v = item.split("=", 1)
            out[k] = v
        return out
    raise TypeError(f"cannot convert {type(value).__name__} to dict")


def _normalise_bind(spec) -> tuple[str, str, str, str]:
    """Return ``(src, dst, access, propagation)`` in a canonical form."""

    if isinstance(spec, dict):
        src = spec.get("Source", "")
        if spec.get("Type") == "volume" and spec.get("Name"):
            name = spec["Name"]
            if src.startswith("/var/lib/containers/storage/volumes/"):
                src = name
        dst = spec.get("Destination", "")
        access = "ro" if not spec.get("RW", True) else "rw"
        propagation = spec.get("Propagation") or ""
    else:
        parts = str(spec).split(":", 2)
        src = parts[0]
        dst = parts[1] if len(parts) > 1 else ""
        opts = parts[2] if len(parts) > 2 else ""
        opts = opts.split(",") if opts else []
        access = "ro" if "ro" in opts else "rw"
        propagation = ""
        for opt in opts:
            if opt in {"shared", "rshared", "slave", "rslave", "private", "rprivate"}:
                propagation = opt

    src = src.rstrip("/")
    dst = dst.rstrip("/")

    if src.startswith("/var/lib/containers/storage/volumes/") and src.endswith(
        "/_data"
    ):
        src = os.path.basename(os.path.dirname(src))

    if propagation.startswith("r"):
        propagation = propagation[1:]
    if propagation == "private":
        propagation = ""

    return src, dst, access, propagation


def _as_set(value):
    """Return a set built from ``value`` or an empty set."""
    if value is None:
        return set()
    if isinstance(value, (list, tuple, set)):
        return set(value)
    return {value}


def _clean_vols(vols):
    """Return ``vols`` with any empty entries removed, preserving order."""
    return [v for v in (vols or []) if v]


def _normalise_volumes(vols):
    """Return a sorted list of volumes, ignoring Podman-injected mounts."""
    vols = _clean_vols(vols)
    pattern = re.compile(r"(^devpts:/dev/pts$|^:/dev/pts$)")
    vols = [v for v in vols if not pattern.match(v)]
    return sorted(vols)


def _normalise_ulimits(spec, actual):
    """Return normalised ulimit mappings for comparison."""

    def to_dict(src):
        d = {}
        for item in src or []:
            if isinstance(item, dict):
                name = item.get("Name") or item.get("name")
                soft = item.get("Soft") if "Soft" in item else item.get("soft")
                hard = item.get("Hard") if "Hard" in item else item.get("hard")
            else:
                name = getattr(item, "name", None)
                soft = getattr(item, "soft", None)
                hard = getattr(item, "hard", None)
            if name is not None:
                d[str(name).lower()] = {"soft": soft, "hard": hard}
        return d

    want = to_dict(spec)
    have = to_dict(actual)

    nproc_key = next((k for k in have if k in {"nproc", "rlimit_nproc"}), None)
    spec_has_nproc = any(k in {"nproc", "rlimit_nproc"} for k in want)
    if nproc_key and not spec_has_nproc:
        want[nproc_key] = have[nproc_key]

    return want, have


def _volume_tuple(item):
    """Return ``(src, dst, opts)`` for comparison or ``None`` to skip."""

    if not item or (isinstance(item, str) and not item.strip()):
        return None

    if isinstance(item, dict):
        src = item.get("Source") or ""
        if item.get("Type") == "volume" and item.get("Name"):
            src = item["Name"]
        dst = item.get("Destination") or ""
        if dst == "/dev/pts" and src in {"devpts", ""}:
            return None
        opts = []
        if item.get("Mode"):
            opts.extend([o for o in str(item["Mode"]).split(";") if o])
        if item.get("Propagation"):
            opts.append(item["Propagation"])
        if item.get("RW") is False:
            opts.append("ro")
        elif item.get("RW") and not opts:
            opts.append("rw")
    else:
        s = str(item)
        if re.match(r"(^devpts:/dev/pts$|^:/dev/pts$)", s):
            return None
        parts = s.split(":", 2)
        src = parts[0]
        dst = parts[1] if len(parts) > 1 else ""
        if dst == "/dev/pts" and src in {"devpts", ""}:
            return None
        opts = parts[2].split(",") if len(parts) > 2 and parts[2] else []

    return (
        src.rstrip("/"),
        dst.rstrip("/"),
        tuple(sorted(o for o in opts if o)),
    )


def _normalize_volume(item):
    """Return canonical ``src:dst`` string or ``None`` to skip.

    Any access mode or other third-field options are ignored.
    """

    t = _volume_tuple(item)
    if t is None:
        return None

    src, dst, _opts = t
    if src:
        vol = f"{src}:{dst}" if dst else src
    else:
        vol = dst
    return vol


def _compare_volumes(spec, running) -> bool:
    """Return ``True`` if volumes differ after normalisation.

    Podman may inject a ``/dev/pts`` pseudo bind mount whose ``Source`` is
    empty.  Old service files might also contain stray empty strings.  These are
    ignored when comparing volumes.  Entries are normalised to ``src:dst`` and
    any access mode such as ``:ro`` or ``:rw`` is discarded before
    comparison.
    """

    def as_set(vols):
        out = set()
        for v in _clean_vols(vols):
            n = _normalize_volume(v)
            if n is not None:
                out.add(n)
        return out

    spec_set = as_set(spec)
    running_set = as_set(running)

    if spec_set != running_set:
        LOG.debug("diff: %s %s", sorted(spec_set), sorted(running_set))
        return True

    return False


def ensure_host_path(path: str) -> None:
    """Ensure that a host directory used for a bind mount exists.

    Creates *path* with ``0755`` permissions if it does not already exist.
    The call is idempotent and will not raise an error if the directory
    exists.
    """

    if not path or not str(path).startswith("/"):
        return
    if not os.path.exists(path):
        os.makedirs(path, mode=0o755, exist_ok=True)


def _compare_ulimits(spec, running) -> bool:
    """Return True if the two ulimit mappings differ."""

    want, have = _normalise_ulimits(spec, running)

    for name in set(want) & set(have):
        if want[name] != have[name]:
            return True

    return False


def _normalise_env(env):
    ordered = {}
    for item in env or []:
        if not item or "=" not in item:
            continue
        key, value = item.split("=", 1)
        ordered[key] = value
    return [f"{k}={ordered[k]}" for k in sorted(ordered)]


def _normalise_container_info(container_info, params):
    if not container_info:
        return container_info

    info = copy.deepcopy(container_info)
    engine = params.get("container_engine")

    config = info.setdefault("Config", {}) or {}
    host_cfg = info.setdefault("HostConfig", {}) or {}

    if engine == "podman":
        if not _as_list(params.get("security_opt")):
            sec_opt = host_cfg.get("SecurityOpt") or []
            host_cfg["SecurityOpt"] = [
                opt for opt in sec_opt if str(opt).lower() != "unmask=all"
            ]

        binds = host_cfg.get("Binds")
        if binds:
            host_cfg["Binds"] = sorted(binds, key=_normalise_bind)

    if config.get("Env"):
        config["Env"] = _normalise_env(config["Env"])

    if config.get("User") == "":
        config["User"] = None

    if not config.get("Volumes"):
        config["Volumes"] = {}

    return info


def _empty_dimensions(d):
    """Return ``True`` if dict is empty or all numeric values are 0/None."""
    if not d:
        return True
    for v in d.values():
        if isinstance(v, (int, float)) and v != 0:
            return False
        if v:
            return False
    return True


class ContainerWorker(ABC):
    def __init__(self, module):
        self.module = module
        self.params = self.module.params
        self.changed = False
        # Use this to store arguments to pass to exit_json().
        self.result = {}

        self.systemd = SystemdWorker(self.params)

        self._diff_keys: list[str] = []
        self._last_container_info: dict | None = None

        # NOTE(mgoddard): The names used by Docker are inconsistent between
        # configuration of a container's resources and the resources in
        # container_info['HostConfig']. This provides a mapping between the two.
        self.dimension_map = {
            "mem_limit": "Memory",
            "mem_reservation": "MemoryReservation",
            "memswap_limit": "MemorySwap",
            "cpu_period": "CpuPeriod",
            "cpu_quota": "CpuQuota",
            "cpu_shares": "CpuShares",
            "cpuset_cpus": "CpusetCpus",
            "cpuset_mems": "CpusetMems",
            "kernel_memory": "KernelMemory",
            "blkio_weight": "BlkioWeight",
            "ulimits": "Ulimits",
        }

    # ------------------------------------------------------------------
    # Helper: emit debug lines only when Ansible is run with -vvv (or more)
    # ------------------------------------------------------------------
    def _debug(self, msg: str) -> None:
        """Print ``msg`` when action debugging is enabled."""
        verbosity = getattr(self.module, "_verbosity", 0)
        if not isinstance(verbosity, int):
            try:
                verbosity = int(verbosity)
            except (TypeError, ValueError):
                verbosity = 0
        env_debug = os.environ.get("KOLLA_ACTION_DEBUG", "").lower() in (
            "1",
            "true",
            "yes",
        )

        if verbosity >= 3 or env_debug:
            # Use module.debug if available to avoid polluting module output
            if hasattr(self.module, "debug"):
                self.module.debug(msg)
            else:
                # Fallback for very-old Ansible or direct execution
                display = getattr(self.module, "_display", None)
                if display:
                    if verbosity >= 3 and hasattr(display, "vvv"):
                        display.vvv(msg)
                    else:
                        display.display(msg)
                else:
                    print(msg)
            # Save debug messages for later inspection
            self.result.setdefault("debug", []).append(msg)

    def _as_empty_list(self, value):
        """Return [] for any "empty" representation of a list-like arg."""
        return [] if value in (None, [], ()) else value

    def _as_empty_dict(self, value):
        """Return {} for any "empty" representation of a dict-like arg."""
        return {} if value in (None, {}, ()) else value

    def _changed_if_differs(self, expected, actual, what):
        if expected != actual:
            self.module.debug(f"{what} differs: expected={expected} actual={actual}")
            return True
        return False

    @abstractmethod
    def check_image(self):
        pass

    @abstractmethod
    def get_container_info(self):
        pass

    @abstractmethod
    def check_container(self):
        pass

    def compare_container(self):
        container = self.check_container()
        differs = False
        if container:
            differs = self.check_container_differs()
        if (
            not container or
            differs or
            self.compare_config() or
            self.systemd.check_unit_change()
        ):
            self.changed = True
        if container and differs:
            self.emit_diff()
        return self.changed

    def check_container_differs(self):
        container_info = self.get_container_info()
        if not container_info:
            self._debug("container does not exist")
            return True

        container_info = _normalise_container_info(container_info, self.params)

        differs = False
        self._diff_keys = []
        self._last_container_info = container_info

        if self.compare_cap_add(container_info):
            self._debug("cap_add differs")
            self._diff_keys.append("cap_add")
            differs = True
        if self.compare_security_opt(container_info):
            self._debug("security_opt differs")
            self._diff_keys.append("security_opt")
            differs = True
        if self.compare_image(container_info):
            self._debug("image differs")
            self._diff_keys.append("image")
            differs = True
        if self.compare_ipc_mode(container_info):
            self._debug("ipc_mode differs")
            self._diff_keys.append("ipc_mode")
            differs = True
        if self.compare_labels(container_info):
            self._debug("labels differ")
            self._diff_keys.append("labels")
            differs = True
        if self.compare_privileged(container_info):
            self._debug("privileged differs")
            self._diff_keys.append("privileged")
            differs = True
        if self.compare_pid_mode(container_info):
            self._debug("pid_mode differs")
            self._diff_keys.append("pid_mode")
            differs = True
        if self.compare_cgroupns_mode(container_info):
            self._debug("cgroupns_mode differs")
            self._diff_keys.append("cgroupns_mode")
            differs = True
        if self.compare_tmpfs(container_info):
            self._debug("tmpfs differs")
            self._diff_keys.append("tmpfs")
            differs = True
        if self.compare_volumes(container_info):
            self._debug("volumes differ")
            self._diff_keys.append("volumes")
            differs = True
        if self.compare_volumes_from(container_info):
            self._debug("volumes_from differs")
            self._diff_keys.append("volumes_from")
            differs = True
        if self.compare_environment(container_info):
            self._debug("environment differs")
            self._diff_keys.append("environment")
            differs = True
        if self.compare_restart_policy(container_info):
            self._debug("restart_policy differs")
            self._diff_keys.append("restart_policy")
            differs = True
        if self.compare_container_state(container_info):
            self._debug("state differs")
            self._diff_keys.append("state")
            differs = True
        if self.compare_dimensions(container_info):
            self._debug("dimensions differ")
            self._diff_keys.append("dimensions")
            differs = True
        if self.compare_command(container_info):
            self._debug("command differs")
            self._diff_keys.append("command")
            differs = True
        if self.compare_user(container_info):
            self._debug("user differs")
            self._diff_keys.append("user")
            differs = True
        if self.compare_healthcheck(container_info):
            self._debug("healthcheck differs")
            self._diff_keys.append("healthcheck")
            differs = True

        debug_enabled = getattr(self.module, "_verbosity", 0) >= 3 or os.environ.get(
            "KOLLA_ACTION_DEBUG", ""
        ).lower() in ("1", "true", "yes")

        if not differs:
            self._debug("no differences found")

        if debug_enabled:
            self.result["container_info"] = container_info
            self.result["container_params"] = self.params

        return differs

    def compare_ipc_mode(self, container_info):
        new_ipc_mode = self.params.get("ipc_mode")
        current_ipc_mode = container_info["HostConfig"].get("IpcMode")
        if not current_ipc_mode:
            current_ipc_mode = None

        # only check IPC mode if it is specified
        if new_ipc_mode is not None and new_ipc_mode != current_ipc_mode:
            return True
        return False

    def compare_cap_add(self, container_info):
        """Return True if requested cap_add differs from running container.

        * None, [] or missing key are treated as identical (no capabilities added).
        * Order is ignored.
        """
        new_caps = self._as_empty_list(self.params.get("cap_add"))
        cur_caps = self._as_empty_list(
            container_info.get("HostConfig", {}).get("CapAdd")
        )

        # Podman automatically injects CAP_AUDIT_WRITE when running
        # non-privileged containers.  If the playbook did not request any
        # extra capabilities we treat that single implicit capability as
        # equivalent to "no extra capabilities".
        if not new_caps and cur_caps == ["CAP_AUDIT_WRITE"]:
            cur_caps = []

        return sorted(new_caps) != sorted(cur_caps)

    def compare_security_opt(self, container_info):
        ipc_mode = self.params.get("ipc_mode")
        pid_mode = self.params.get("pid_mode")
        privileged = self.params.get("privileged", False)
        # NOTE(jeffrey4l) security opt is disabled when using host ipc mode or
        # host pid mode or privileged. So no need to compare security opts
        if ipc_mode == "host" or pid_mode == "host" or privileged:
            return False
        new_sec_opt = _as_list(self.params.get("security_opt"))
        try:
            current_sec_opt = _as_list(container_info["HostConfig"].get("SecurityOpt"))
        except (KeyError, TypeError):
            current_sec_opt = []

        if (
            self.params.get("container_engine") == "podman"
            and not new_sec_opt
        ):
            current_sec_opt = [
                opt for opt in current_sec_opt if str(opt).lower() != "unmask=all"
            ]

        if sorted(new_sec_opt) != sorted(current_sec_opt):
            return True

    @abstractmethod
    def compare_pid_mode(self, container_info):
        pass

    def compare_cgroupns_mode(self, container_info):
        new_cgroupns_mode = self.params.get("cgroupns_mode")
        if new_cgroupns_mode is None:
            # means we don't care what it is
            return False
        current_cgroupns_mode = (
            container_info["HostConfig"].get("CgroupnsMode") or
            container_info["HostConfig"].get("CgroupNS") or
            container_info["HostConfig"].get("CgroupMode")
        )
        if current_cgroupns_mode in ("", None):
            # means the container was created on Docker pre-20.10
            # it behaves like 'host'
            current_cgroupns_mode = "host"
        return new_cgroupns_mode != current_cgroupns_mode

    def compare_privileged(self, container_info):
        new_privileged = self.params.get("privileged")
        current_privileged = container_info["HostConfig"]["Privileged"]
        if new_privileged != current_privileged:
            return True

    @abstractmethod
    def compare_image(self, container_info=None):
        pass

    def compare_labels(self, container_info):
        new_labels = _as_dict(self.params.get("labels"))
        current_labels = _as_dict(container_info["Config"].get("Labels"))
        image_labels = self.check_image().get("Labels", dict())
        for k, v in image_labels.items():
            if k in new_labels:
                if v != new_labels[k]:
                    return True
            else:
                del current_labels[k]

        if new_labels != current_labels:
            return True

    def compare_tmpfs(self, container_info):
        new_tmpfs = _as_list(self.generate_tmpfs())
        current_tmpfs = _as_list(container_info["HostConfig"].get("Tmpfs"))

        if sorted(current_tmpfs) != sorted(new_tmpfs):
            return True

    def compare_volumes_from(self, container_info):
        new_vols_from = _clean_vols(_as_list(self.params.get("volumes_from")))
        current_vols_from = _clean_vols(
            _as_list(container_info["HostConfig"].get("VolumesFrom"))
        )

        if sorted(current_vols_from) != sorted(new_vols_from):
            return True

    def compare_volumes(self, container_info):
        want = self.params.get("volumes") or []
        have = container_info.get("HostConfig", {}).get("Binds", []) or []
        return _compare_volumes(want, have)

    def dimensions_differ(self, a, b, key):
        """Compares two docker dimensions

        As there are two representations of dimensions in docker, we should
        normalize them to compare if they are the same.

        If the dimension is no more supported due docker update,
        an error is thrown to operator to fix the dimensions' config.

        The available representations can be found at:

        https://docs.docker.com/config/containers/resource_constraints/


        :param a: Integer or String that represents a number followed or not
                  by "b", "k", "m" or "g".
        :param b: Integer or String that represents a number followed or not
                  by "b", "k", "m" or "g".
        :return: True if 'a' has the same logical value as 'b' or else
                 False.
        """

        if a is None or b is None:
            msg = (
                "The dimension [%s] is no more supported by Docker, "
                "please remove it from yours configs or change "
                "to the new one."
            ) % key
            LOG.error(msg)
            self.module.fail_json(failed=True, msg=msg)
            return

        unit_sizes = {"b": 1, "k": 1024}
        unit_sizes["m"] = unit_sizes["k"] * 1024
        unit_sizes["g"] = unit_sizes["m"] * 1024
        a = str(a)
        b = str(b)
        a_last_char = a[-1].lower()
        b_last_char = b[-1].lower()
        error_msg = (
            "The docker dimension unit [%s] is not supported for "
            "the dimension [%s]. The currently supported units "
            "are ['b', 'k', 'm', 'g']."
        )
        if not a_last_char.isnumeric():
            if a_last_char in unit_sizes:
                a = str(int(a[:-1]) * unit_sizes[a_last_char])
            else:
                LOG.error(error_msg, a_last_char, a)
                self.module.fail_json(failed=True, msg=error_msg % (a_last_char, a))

        if not b_last_char.isnumeric():
            if b_last_char in unit_sizes:
                b = str(int(b[:-1]) * unit_sizes[b_last_char])
            else:
                LOG.error(error_msg, b_last_char, b)
                self.module.fail_json(failed=True, msg=error_msg % (b_last_char, b))
        return a != b

    def compare_dimensions(self, container_info):
        """Return True if requested dimensions differ from the container."""
        new_dimensions = _as_dict(self.params.get("dimensions"))
        # Nothing requested – nothing to compare
        if not new_dimensions:
            return False
        unsupported = set(new_dimensions) - set(self.dimension_map)
        if unsupported:
            self.module.exit_json(
                failed=True,
                msg=repr("Unsupported dimensions"),
                unsupported_dimensions=unsupported,
            )

        defaults = {
            "PidsLimit": 2048,
            "CpuShares": 0,
            "CpuQuota": 0,
            "CpuPeriod": 0,
            "Memory": 0,
            "MemorySwap": 0,
            "KernelMemory": 0,
            "BlkioWeight": 0,
            "CpusetCpus": "",
            "CpusetMems": "",
        }

        host_cfg = container_info.get("HostConfig", {})

        diff_keys = []
        for spec_key, host_key in self.dimension_map.items():
            cur_val = host_cfg.get(host_key)

            if spec_key == "ulimits":
                new_val = new_dimensions.get(spec_key)
                desired_list = self.build_ulimits(new_val or {})
                if self.compare_ulimits(desired_list, cur_val):
                    diff_keys.append(spec_key)
                continue

            new_val_present = (
                spec_key in new_dimensions and new_dimensions[spec_key] is not None
            )

            if new_val_present:
                new_val = new_dimensions[spec_key]
                if spec_key in {
                    "mem_limit",
                    "mem_reservation",
                    "memswap_limit",
                    "kernel_memory",
                }:
                    if self.dimensions_differ(new_val, cur_val, spec_key):
                        diff_keys.append(spec_key)
                else:
                    if new_val != cur_val:
                        diff_keys.append(spec_key)
            else:
                default_val = defaults.get(host_key)
                if cur_val not in (None, default_val, [], "", 0):
                    diff_keys.append(spec_key)

        if diff_keys:
            # Build a {dimension: {current: …, desired: …}} helper dict
            mismatch = {
                k: {
                    "current": host_cfg.get(self.dimension_map[k]),
                    "desired": new_dimensions.get(k, "<implicit-default>"),
                }
                for k in diff_keys
            }
            self._debug(f"compare_dimensions mismatch (full) → {mismatch}")
            self._debug(f"compare_dimensions mismatch → {diff_keys}")
            return True

        return False

    def compare_environment(self, container_info):
        env_spec = _as_dict(self.params.get("environment"))
        if env_spec:
            current_env = {}
            for kv in container_info["Config"].get("Env", list()):
                k, v = kv.split("=", 1)
                current_env.update({k: v})

            for k, v in env_spec.items():
                if k == "KOLLA_ACTION_DEBUG":
                    continue
                if k not in current_env:
                    return True
                if current_env[k] != v:
                    return True

    def compare_container_state(self, container_info):
        new_state = self.params.get("state")
        current_state = container_info["State"].get("Status")

        if new_state == "started" and current_state == "running":
            return False
        # Podman reports the state of newly created but never started
        # containers as ``configured``.  Such a container is effectively
        # equivalent to one in the ``exited`` state when our desired state
        # is ``exited``.  Treat these states as matching to avoid needless
        # container recreation during deploys and reconfigures.
        if new_state == "exited" and current_state in ("configured", "created"):
            return False
        if new_state != current_state:
            return True

    def compare_restart_policy(self, container_info):
        if self.params.get("container_engine") != "podman":
            return False
        if self.params.get("podman_use_systemd"):
            return False
        desired = self.params.get("restart_policy")
        current = (
            container_info.get("HostConfig", {}).get("RestartPolicy", {}).get("Name")
        )

        # Podman does not honour the restart policy when creating a
        # container.  Empty or missing values therefore correspond to the
        # default behaviour which is effectively "no".
        def norm(val):
            if val in ("", None, "unless-stopped"):
                return "unless-stopped"
            return val

        if desired == "no" and current in ("", None, "unless-stopped"):
            return False

        return norm(desired) != norm(current)

    def compare_ulimits(self, desired, current) -> bool:
        return _compare_ulimits(desired, current)

    def compare_command(self, container_info):
        new_command = self.params.get("command")
        if new_command is not None:
            new_cmd = shlex.split(new_command)

            current_path = os.path.basename(container_info.get("Path", ""))
            current_args = container_info.get("Args")
            if isinstance(current_args, str):
                current_args = shlex.split(current_args)
            current_args = current_args or []
            current_cmd = [current_path] + current_args

            if new_cmd != current_cmd:
                # If the only difference stems from the image entrypoint, and
                # the caller did not override it, treat the commands as
                # identical for idempotency.
                if not self.params.get("entrypoint"):
                    cfg = container_info.get("Config", {})
                    cmd_cfg = cfg.get("Cmd") or []
                    if isinstance(cmd_cfg, str):
                        cmd_cfg = shlex.split(cmd_cfg)
                    ep_cfg = cfg.get("Entrypoint") or []
                    if isinstance(ep_cfg, str):
                        ep_cfg = shlex.split(ep_cfg)
                    cfg_cmd = ep_cfg + cmd_cfg
                    if new_cmd == cmd_cfg and current_cmd == cfg_cmd:
                        return False

                # When podman reports the command as a list without quoting,
                # the logical commands may still match even if the list
                # elements differ.  Fall back to a string comparison to avoid
                # needless container recreation when the commands are
                # effectively the same.
                if " ".join(new_cmd) == " ".join(current_cmd):
                    return False
                return True

    def compare_user(self, container_info):
        new_user = self.params.get("user")
        current_user = container_info.get("Config", {}).get("User")
        if not current_user:
            current_user = None
        if new_user != current_user:
            return True

    def compare_healthcheck(self, container_info):
        new_healthcheck = self.parse_healthcheck(self.params.get("healthcheck"))
        current_healthcheck = container_info["Config"].get("Healthcheck")

        healthcheck_map = {
            "test": "Test",
            "retries": "Retries",
            "interval": "Interval",
            "start_period": "StartPeriod",
            "timeout": "Timeout",
        }

        if new_healthcheck:
            new_healthcheck = new_healthcheck["healthcheck"]
            if current_healthcheck:
                new_healthcheck = dict(
                    (healthcheck_map.get(k, k), v) for (k, v) in new_healthcheck.items()
                )
                return new_healthcheck != current_healthcheck
            else:
                return True
        else:
            if current_healthcheck:
                return True

    def parse_image(self):
        full_image = self.params.get("image")

        if "/" in full_image:
            registry, image = full_image.split("/", 1)
        else:
            image = full_image

        if ":" in image:
            return full_image.rsplit(":", 1)
        else:
            return full_image, "latest"

    @abstractmethod
    def pull_image(self):
        pass

    @abstractmethod
    def remove_container(self):
        pass

    def generate_tmpfs(self):
        tmpfs = self.params.get("tmpfs")
        if tmpfs:
            # NOTE(mgoddard): Filter out any empty strings.
            tmpfs = [t for t in tmpfs if t]
        return tmpfs

    def generate_volumes(self, binds=None):
        if not binds:
            volumes = self.params.get("volumes") or self.params.get("volume")
        else:
            volumes = binds

        if not volumes:
            return None, None

        vol_list = list()
        vol_dict = dict()

        for vol in volumes:
            if len(vol) == 0:
                continue

            if ":" not in vol:
                vol_list.append(vol)
                continue

            split_vol = vol.split(":")

            if len(split_vol) == 2 and ("/" not in split_vol[0] or "/" in split_vol[1]):
                split_vol.append("rw")

            vol_list.append(split_vol[1])
            vol_dict.update(
                {split_vol[0]: {"bind": split_vol[1], "mode": split_vol[2]}}
            )

        return vol_list, vol_dict

    @abstractmethod
    def build_ulimits(self, ulimits):
        pass

    @abstractmethod
    def create_container(self):
        pass

    @abstractmethod
    def recreate_or_restart_container(self):
        pass

    @abstractmethod
    def recreate_container(self):
        pass

    @abstractmethod
    def start_container(self):
        pass

    def parse_healthcheck(self, healthcheck):
        if not healthcheck:
            return None

        result = dict(healthcheck={})

        # All supported healthcheck parameters
        supported = set(["test", "interval", "timeout", "start_period", "retries"])
        unsupported = set(healthcheck) - supported
        missing = supported - set(healthcheck)
        duration_options = set(["interval", "timeout", "start_period"])

        if unsupported:
            self.module.exit_json(
                failed=True,
                msg=repr("Unsupported healthcheck options"),
                unsupported_healthcheck=unsupported,
            )

        if missing:
            self.module.exit_json(
                failed=True,
                msg=repr("Missing healthcheck option"),
                missing_healthcheck=missing,
            )

        for key in healthcheck:
            value = healthcheck.get(key)
            if key in duration_options:
                try:
                    result["healthcheck"][key] = int(value) * 1000000000
                except TypeError:
                    raise TypeError(
                        'Cannot parse healthcheck "{0}". '
                        'Expected an integer, got "{1}".'.format(
                            value, type(value).__name__
                        )
                    )
                except ValueError:
                    raise ValueError(
                        'Cannot parse healthcheck "{0}". '
                        'Expected an integer, got "{1}".'.format(
                            value, type(value).__name__
                        )
                    )
            else:
                if key == "test":
                    # If the user explicitly disables the healthcheck,
                    # return None as the healthcheck object
                    if value in (["NONE"], "NONE"):
                        return None
                    else:
                        if isinstance(value, (tuple, list)):
                            result["healthcheck"][key] = [str(e) for e in value]
                        else:
                            result["healthcheck"][key] = ["CMD-SHELL", str(value)]
                elif key == "retries":
                    try:
                        result["healthcheck"][key] = int(value)
                    except ValueError:
                        raise ValueError(
                            "Cannot parse healthcheck number of retries."
                            'Expected an integer, got "{0}".'.format(type(value))
                        )

        return result

    @abstractmethod
    def stop_container(self):
        pass

    @abstractmethod
    def stop_and_remove_container(self):
        pass

    @abstractmethod
    def restart_container(self):
        pass

    @abstractmethod
    def create_volume(self):
        pass

    @abstractmethod
    def remove_volume(self):
        pass

    @abstractmethod
    def remove_image(self):
        pass

    @abstractmethod
    def ensure_image(self):
        pass

    def _inject_env_var(self, environment_info):
        newenv = {"KOLLA_SERVICE_NAME": self.params.get("name").replace("_", "-")}
        environment_info.update(newenv)
        return environment_info

    def _format_env_vars(self):
        env = self._inject_env_var(self.params.get("environment"))
        return {k: "" if env[k] is None else env[k] for k in env}

    # ------------------------------------------------------------------
    # Diff helpers
    # ------------------------------------------------------------------
    def _current_value(self, info, key):
        hc = info.get("HostConfig", {})
        cfg = info.get("Config", {})
        if key == "command":
            args = info.get("Args")
            if isinstance(args, str):
                args = shlex.split(args)
            return " ".join([info.get("Path", "")] + (args or []))
        if key == "image":
            return cfg.get("Image") or info.get("Image")
        if key == "environment":
            env = {}
            for item in cfg.get("Env", []) or []:
                if "=" in item:
                    k, v = item.split("=", 1)
                    env[k] = v
            return env
        if key == "labels":
            return cfg.get("Labels", {})
        if key == "volumes":
            return sorted(hc.get("Binds", []) or [])
        if key == "volumes_from":
            return sorted(hc.get("VolumesFrom", []) or [])
        if key == "cap_add":
            return sorted(_as_list(hc.get("CapAdd")))
        if key == "security_opt":
            return sorted(_as_list(hc.get("SecurityOpt")))
        if key == "ipc_mode":
            return hc.get("IpcMode") or None
        if key == "pid_mode":
            return (
                hc.get("PidMode") or
                hc.get("PidNS") or
                None
            )
        if key == "cgroupns_mode":
            return (
                hc.get("CgroupnsMode") or
                hc.get("CgroupNS") or
                hc.get("CgroupMode") or
                "host"
            )
        if key == "privileged":
            return hc.get("Privileged")
        if key == "tmpfs":
            return sorted(_as_list(hc.get("Tmpfs")))
        if key == "restart_policy":
            return hc.get("RestartPolicy", {}).get("Name")
        if key == "state":
            return info.get("State", {}).get("Status")
        if key == "dimensions":
            d = {}
            for sk, hk in self.dimension_map.items():
                d[sk] = hc.get(hk)
            return d
        if key == "healthcheck":
            return cfg.get("Healthcheck")
        return info.get(key)

    def _desired_value(self, key):
        val = self.params.get(key)
        if key in {"environment"}:
            env = _as_dict(val)
            env = {k: v for k, v in env.items() if not re.search("pass|token", k, re.I)}
            return env
        if key in {"volumes", "volumes_from", "cap_add", "security_opt", "tmpfs"}:
            return sorted(val or [])
        if key == "labels":
            return _as_dict(val)
        return val

    def emit_diff(self):
        if not self._diff_keys or not self._last_container_info:
            return
        before = {
            k: self._current_value(self._last_container_info, k)
            for k in self._diff_keys
        }
        after = {k: self._desired_value(k) for k in self._diff_keys}
        before_s = json.dumps(before, indent=2, sort_keys=True).splitlines()
        after_s = json.dumps(after, indent=2, sort_keys=True).splitlines()
        diff = unified_diff(before_s, after_s, "current", "desired", lineterm="")
        self.result["diff"] = "\n".join(diff)


if __name__ == "__main__":
    # Basic sanity tests for volume comparison
    assert not _compare_volumes(
        ["/etc/timezone:/etc/timezone:ro"],
        [{"Source": "/etc/timezone", "Destination": "/etc/timezone"}],
    )
    assert not _compare_volumes(
        ["devpts:/dev/pts"],
        [{"Type": "bind", "Source": "", "Destination": "/dev/pts"}],
    )
    assert not _compare_volumes([""], [])
    print("ALL OK")
