from __future__ import annotations

import json
from pathlib import Path

from loguru import logger


def save_schema_snapshot(payload: dict, week: str, snapshots_dir: Path) -> None:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    keys = list(payload.keys())
    snapshot = {"week": week, "keys": keys}
    path = snapshots_dir / f"{week}-schema.json"
    path.write_text(json.dumps(snapshot, indent=2), encoding="utf-8")
    logger.debug(f"Saved schema snapshot for week {week} to {path}")


def detect_drift(payload: dict, week: str, snapshots_dir: Path) -> list[str]:
    snapshots_dir.mkdir(parents=True, exist_ok=True)
    current_keys = set(payload.keys())

    snapshot_files = sorted(snapshots_dir.glob("*-schema.json"))
    previous_snapshot = None
    for sf in snapshot_files:
        if sf.stem.replace("-schema", "") < week:
            previous_snapshot = sf

    if previous_snapshot is None:
        logger.debug(f"No previous snapshot found, no drift to detect for week {week}")
        return []

    try:
        prev_data = json.loads(previous_snapshot.read_text(encoding="utf-8"))
        prev_keys = set(prev_data.get("keys", []))
    except Exception as e:
        logger.warning(f"Could not read previous snapshot {previous_snapshot}: {e}")
        return []

    changes: list[str] = []
    added = current_keys - prev_keys
    removed = prev_keys - current_keys

    for key in sorted(added):
        msg = f"DRIFT: new field '{key}' appeared in week {week}"
        logger.warning(msg)
        changes.append(msg)

    for key in sorted(removed):
        msg = f"DRIFT: field '{key}' missing in week {week} (was present before)"
        logger.warning(msg)
        changes.append(msg)

    if not changes:
        logger.debug(f"No schema drift detected for week {week}")

    return changes
