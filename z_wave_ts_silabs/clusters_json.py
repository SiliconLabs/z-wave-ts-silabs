"""Load clusters description JSON: legacy flat map or schema_version 1 (nested clusters + devices)."""

from __future__ import annotations

import json
import re
from pathlib import Path

from .session_context import Clusters, Wpk

_SERIAL_RE = re.compile(r"^\d{9}$")
_BOARD_RE = re.compile(r"^brd\d{4}[a-zA-Z]$")


def _validate_wpk_dict(elt: dict, *, cluster_name: str | None = None) -> None:
    serial = elt.get("serial")
    ip = elt.get("ip")
    board = elt.get("board")
    ctx = f" in cluster {cluster_name!r}" if cluster_name else ""
    if serial is None and ip is None:
        raise ValueError(f"missing serial or ip{ctx}")
    if serial is not None and (not isinstance(serial, str) or not _SERIAL_RE.fullmatch(serial)):
        raise ValueError(f"invalid serial{ctx}: {serial!r} (expected 9 decimal digits)")
    if ip is not None and (not isinstance(ip, str) or not re.fullmatch(r"(?:\d{1,3}\.){3}\d{1,3}", ip)):
        raise ValueError(f"invalid ip{ctx}: {ip!r}")
    if not isinstance(board, str) or not _BOARD_RE.fullmatch(board):
        raise ValueError(
            f"invalid board{ctx}: {board!r} (expected brd + 4 digits + 1 letter, e.g. brd4205b)"
        )


def _wpk_list_from_devices(devices: list, *, cluster_name: str) -> list[Wpk]:
    for d in devices:
        if isinstance(d, dict):
            _validate_wpk_dict(d, cluster_name=cluster_name)
    return Wpk.from_json_list(devices)


def _clusters_from_v1(raw: dict) -> Clusters:
    out: Clusters = {}
    clusters = raw.get("clusters")
    if not isinstance(clusters, dict):
        return out
    for name, spec in clusters.items():
        if not isinstance(spec, dict):
            continue
        devices = spec.get("devices", [])
        if not isinstance(devices, list):
            continue
        out[name] = _wpk_list_from_devices(devices, cluster_name=name)
    return out


def _clusters_from_legacy(raw: dict) -> Clusters:
    out: Clusters = {}
    for name, wpk_list in raw.items():
        if not isinstance(wpk_list, list):
            continue
        out[name] = _wpk_list_from_devices(wpk_list, cluster_name=name)
    return out


def load_clusters_json(path: Path) -> Clusters:
    """Parse clusters JSON: schema_version 1 (metadata + ``clusters``) or legacy top-level map name -> [wpk, ...]."""
    with path.open() as f:
        raw: dict = json.load(f)
    if raw.get("schema_version") == 1 and "clusters" in raw:
        return _clusters_from_v1(raw)
    return _clusters_from_legacy(raw)


def load_cluster_domain(path: Path, cluster_name: str) -> str | None:
    """Return a cluster-specific WPK DNS domain, if one is configured."""
    with path.open() as f:
        raw: dict = json.load(f)

    clusters = raw.get("clusters") if raw.get("schema_version") == 1 else raw
    if not isinstance(clusters, dict):
        return None

    spec = clusters.get(cluster_name)
    if not isinstance(spec, dict):
        return None

    domain_name = spec.get("domain_name")
    return domain_name if isinstance(domain_name, str) and domain_name else None
