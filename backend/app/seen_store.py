import json
import os
import time
from pathlib import Path

SEEN_FILE = Path(os.getenv("SEEN_FILE_PATH", "data/seen.json"))


def _load() -> dict:
    """Load seen state from disk. Returns {"ids": [...], "written_at": float}."""
    if not SEEN_FILE.exists():
        return {"ids": [], "written_at": time.time()}
    try:
        return json.loads(SEEN_FILE.read_text())
    except Exception:
        return {"ids": [], "written_at": time.time()}


def _save(data: dict):
    SEEN_FILE.parent.mkdir(parents=True, exist_ok=True)
    SEEN_FILE.write_text(json.dumps(data))


def get_seen_ids() -> list[str]:
    data = _load()
    if time.time() - data.get("written_at", 0) > 86400:
        _save({"ids": [], "written_at": time.time()})
        return []
    return data.get("ids", [])


def mark_seen(new_ids: list[str]) -> list[str]:
    data = _load()
    age = time.time() - data.get("written_at", 0)
    if age > 86400:
        merged = list(set(new_ids))
        _save({"ids": merged, "written_at": time.time()})
    else:
        merged = list(set(data.get("ids", []) + new_ids))
        _save({"ids": merged, "written_at": data["written_at"]})
    return merged


def clear_seen():
    _save({"ids": [], "written_at": time.time()})
