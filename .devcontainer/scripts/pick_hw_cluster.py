#!/usr/bin/env python3
"""List available clusters from the file pointed by config.json (clusters_json).
Let user pick one and update config.json default_cluster.
"""

import json
import sys
from pathlib import Path


def main() -> int:
    script_dir = Path(__file__).resolve().parent
    workspace_dir = script_dir.parent.parent
    config_path = workspace_dir / "config.json"

    if not config_path.exists():
        print(f"Config file not found: {config_path}", file=sys.stderr)
        return 1

    with open(config_path) as f:
        config = json.load(f)

    clusters_json_path = config.get("clusters_json")
    if not clusters_json_path:
        print("config.json has no 'clusters_json' key.", file=sys.stderr)
        return 1

    clusters_path = (workspace_dir / clusters_json_path).resolve()
    if not clusters_path.exists():
        print(f"Clusters file not found: {clusters_path}", file=sys.stderr)
        return 1

    with open(clusters_path) as f:
        clusters = json.load(f)

    names = sorted(clusters.keys())
    if not names:
        print("No clusters defined in clusters file.", file=sys.stderr)
        return 1

    print(f"Available clusters ({clusters_json_path}):")
    print()
    for i, name in enumerate(names, 1):
        count = len(clusters[name]) if isinstance(clusters[name], list) else 0
        print(f"  {i:2}. {name}  ({count} WPK)")
    current = config.get("default_cluster")
    if current:
        print(f"\nCurrent default: {current}")
    print()

    while True:
        try:
            choice = input("Cluster number or name (Enter = cancel): ").strip()
        except EOFError:
            return 0
        if not choice:
            print("Cancelled.")
            return 0
        if choice.isdigit():
            idx = int(choice)
            if 1 <= idx <= len(names):
                chosen = names[idx - 1]
                break
            print("Invalid number.")
        else:
            if choice in names:
                chosen = choice
                break
            print("Unknown cluster name.")

    config["default_cluster"] = chosen
    with open(config_path, "w") as f:
        json.dump(config, f, indent=2)

    print(f"\nSelected cluster: {chosen}")
    print(f"Updated config.json default_cluster: {config_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
