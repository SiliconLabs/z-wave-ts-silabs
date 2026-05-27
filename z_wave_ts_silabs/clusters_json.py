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
    board = elt.get("board")
    ctx = f" in cluster {cluster_name!r}" if cluster_name else ""
    if not isinstance(serial, str) or not _SERIAL_RE.fullmatch(serial):
        raise ValueError(f"invalid serial{ctx}: {serial!r} (expected 9 decimal digits)")
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
