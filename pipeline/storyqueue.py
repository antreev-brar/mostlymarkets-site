"""The story queue the writer works through.

  python3 pipeline/storystoryqueue.py list                 # open events, highest priority first
  python3 pipeline/storyqueue.py show <id>            # one event with its data pack
  python3 pipeline/storyqueue.py done <id> <story.md> # mark written (moves it to events/done/)
  python3 pipeline/storyqueue.py skip <id> "<why>"    # mark skipped, with the reason
"""
from __future__ import annotations

import datetime as dt
import json
import sys
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
Q, D = ROOT / "events/queue", ROOT / "events/done"
ET = ZoneInfo("America/New_York")


def events() -> list[dict]:
    now = dt.datetime.now(tz=ET)
    out = []
    for p in Q.glob("*.json"):
        e = json.loads(p.read_text())
        e["_expired"] = dt.datetime.fromisoformat(e["expires"]) < now
        out.append(e)
    out.sort(key=lambda e: (e["_expired"], -e["priority"], e["created"]))
    return out


def close(eid: str, outcome: str, **extra) -> None:
    p = Q / f"{eid}.json"
    if not p.exists():
        raise SystemExit(f"no queued event {eid}")
    e = json.loads(p.read_text())
    e.update(outcome=outcome, closed=dt.datetime.now(tz=ET).isoformat(timespec="seconds"), **extra)
    D.mkdir(parents=True, exist_ok=True)
    (D / p.name).write_text(json.dumps(e, indent=1))
    p.unlink()
    print(f"{eid}: {outcome}")


def main(argv: list[str]) -> None:
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        evs = events()
        if not evs:
            print("queue empty")
        for e in evs:
            flag = "EXPIRED " if e["_expired"] else ""
            print(f"{flag}{e['priority']:>3}  {e['id']:<44} {e['story_type']:<17} {e['headline_hint']}")
    elif cmd == "show":
        print(json.dumps(json.loads((Q / f"{argv[1]}.json").read_text()), indent=1))
    elif cmd == "done":
        story = Path(argv[2])
        if not story.exists():
            raise SystemExit(f"no story file {story}")
        close(argv[1], "written", story=str(story.relative_to(ROOT) if story.is_absolute() else story))
    elif cmd == "skip":
        close(argv[1], "skipped", reason=" ".join(argv[2:]) or "no reason given")
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
