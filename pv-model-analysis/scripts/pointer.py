"""Read/write/validate the model-ref pointer that lets pv-result-analysis
find the produced .modelmap docs. Format: plain `key: value` lines, UTF-8."""
from __future__ import annotations
import os

def write_pointer(pointer_path, docs_path, repo, commit, models, date):
    lines = [
        f"path: {docs_path}",
        f"repo: {repo}",
        f"commit: {commit}",
        f"date: {date}",
        f"models: {', '.join(models)}",
    ]
    os.makedirs(os.path.dirname(pointer_path) or ".", exist_ok=True)
    with open(pointer_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

def read_pointer(pointer_path):
    result = {}
    with open(pointer_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or ":" not in line:
                continue
            key, _, val = line.partition(":")
            result[key.strip()] = val.strip()
    result["models"] = [m.strip() for m in result.get("models", "").split(",") if m.strip()]
    return result

def is_stale(pointer, current_commit):
    """True if the pointer's recorded commit differs from the repo's current
    HEAD. A commit of '' or 'no-git' means we can't tell → treat as not stale."""
    c = pointer.get("commit", "")
    if c in ("", "no-git"):
        return False
    return c != current_commit
