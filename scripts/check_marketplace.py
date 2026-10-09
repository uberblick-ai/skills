#!/usr/bin/env python3
"""The Claude Code marketplace lists every skill, once, in the plugin named for its group, and nothing else."""

import json
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
listed = {}
for plugin in json.loads((root / ".claude-plugin/marketplace.json").read_text())["plugins"]:
    for path in plugin.get("skills", []):
        listed.setdefault(path, []).append(plugin["name"])
present = {f"./{p.parent.relative_to(root).as_posix()}": p.parent.parent.name
           for p in root.glob("skills/*/*/SKILL.md")}
problems = [f"{path} is missing from the plugin {group}" for path, group in sorted(present.items())
            if path not in listed]
problems += [f"{path} is listed in {', '.join(names)}, expected only {present[path]}"
             for path, names in sorted(listed.items()) if path in present and names != [present[path]]]
problems += [f"{path} is listed but has no SKILL.md" for path in sorted(listed) if path not in present]
if problems:
    sys.exit("marketplace.json: " + "; ".join(problems))
print(f"marketplace.json lists every skill: {len(present)}")
