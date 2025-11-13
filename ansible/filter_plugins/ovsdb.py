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

"""Filters for working with OVSDB structured data."""

from __future__ import annotations

import json
from typing import Any, Dict, Iterable, List, Tuple


def _convert_ovsdb_value(value: Any) -> Any:
    """Convert an OVSDB JSON value to native Python types."""
    if isinstance(value, list):
        if not value:
            return []
        tag = value[0]
        if tag == "set":
            items = [_convert_ovsdb_value(item) for item in value[1]]
            if len(items) == 0:
                return []
            if len(items) == 1:
                return items[0]
            return items
        if tag == "map":
            return {
                _convert_ovsdb_value(item[0]): _convert_ovsdb_value(item[1])
                for item in value[1]
            }
        if tag in {"uuid", "named-uuid", "string", "integer", "real", "boolean"}:
            return _convert_ovsdb_value(value[1])
        return [_convert_ovsdb_value(item) for item in value]
    return value


def ovsdb_rows(data: Any) -> List[Dict[str, Any]]:
    """Convert the JSON output of ovs-vsctl to a list of dictionaries."""
    if isinstance(data, str):
        data = json.loads(data)
    if not isinstance(data, dict):
        return []
    headings = data.get("headings", [])
    rows = data.get("data", [])
    results: List[Dict[str, Any]] = []
    for row in rows:
        record: Dict[str, Any] = {}
        for heading, value in zip(headings, row):
            record[heading] = _convert_ovsdb_value(value)
        results.append(record)
    return results


def _canonical_sequence(value: Iterable[Any]) -> Tuple[Any, ...]:
    return tuple(sorted(ovsdb_canonical(item) for item in value))


def ovsdb_canonical(value: Any) -> Any:
    """Create a canonical representation suitable for comparisons."""
    if isinstance(value, dict):
        return tuple(sorted((str(key), ovsdb_canonical(val)) for key, val in value.items()))
    if isinstance(value, (list, tuple, set)):
        return _canonical_sequence(value)
    if isinstance(value, bool):
        return value
    if value is None:
        return None
    return str(value)


def _quote_string(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def to_ovsdb(value: Any) -> str:
    """Render a Python value using the ovs-vsctl argument syntax."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if value is None:
        return "[]"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, str):
        return _quote_string(value)
    if isinstance(value, (list, tuple, set)):
        items = [to_ovsdb(item) for item in value]
        return f"[{', '.join(items)}]" if items else "[]"
    if isinstance(value, dict):
        if not value:
            return "{}"
        items = [
            f"{to_ovsdb(key)}={to_ovsdb(val)}"
            for key, val in sorted(value.items(), key=lambda item: str(item[0]))
        ]
        return "{" + ", ".join(items) + "}"
    return _quote_string(str(value))


class FilterModule(object):
    """Expose OVSDB helpers as Jinja2 filters."""

    def filters(self) -> Dict[str, Any]:
        return {
            "ovsdb_rows": ovsdb_rows,
            "ovsdb_canonical": ovsdb_canonical,
            "to_ovsdb": to_ovsdb,
        }
