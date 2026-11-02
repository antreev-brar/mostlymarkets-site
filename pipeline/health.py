"""Tell the owner when the site stops updating, and say so again when it recovers.

Run at the end of every data pass (pipeline/watch.py), before the events commit. It opens, updates or closes one
GitHub issue titled "Site health" (the owner is emailed when it opens), and it never fails the pass. It flags:
- quotes more than 45 minutes old during the session (09:30-16:00 New York time on a trading day);
- an event that has waited in the queue more than 3 hours (07:00-20:00 on a trading day) or 9 hours (otherwise);
- no new story for 3 hours (07:00-20:00 on a trading day) or 12 hours (otherwise);
- events/ALERT.md, the writer's note that something is broken (deleted here once it has been reported for 6 hours
  and nothing else is wrong, because the writer may only add files);
- a failed last run of build.yml or covers.yml.
Why: in the first week every data run showed success while quotes sat still for 5 hours, and nothing read ALERT.md
(automation audit, 2 Nov 2026).

  python3 pipeline/health.py                 # check, and open, update or close the issue
  python3 pipeline/health.py --dry [--at <ISO time in New York>]   # print the problems only
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import subprocess
import sys
import tomllib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marketdata as md  # noqa: E402
from detect import is_trading_day  # noqa: E402

ROOT = md.ROOT
EVENTS = ROOT / "events"
STATE = EVENTS / "health.json"
ALERT = EVENTS / "ALERT.md"
TITLE = "Site health"
OWNER = "@antreev-brar"


def parse(t: str | None) -> dt.datetime | None:
    try:
        d = dt.datetime.fromisoformat(str(t))
    except ValueError:
        return None
    return (d if d.tzinfo else d.replace(tzinfo=md.ET)).astimezone(md.ET)


def hours(td: dt.timedelta) -> str:
    h = td.total_seconds() / 3600
    return f"{h:.1f} h" if h < 48 else f"{h / 24:.1f} days"


def last_run_failed(workflow: str) -> bool:
    r = subprocess.run(["gh", "run", "list", "--workflow", workflow, "--status", "completed", "--limit", "1", "--json",
                        "conclusion"], cwd=ROOT, capture_output=True, text=True)
    try:
        return r.returncode == 0 and json.loads(r.stdout or "[]")[0].get("conclusion") == "failure"
    except (IndexError, ValueError):
        return False


def problems(now: dt.datetime, check_runs: bool = True) -> list[tuple[str, str]]:
    """(key, text) pairs. The key names the problem without the hours in it, so the issue only changes (and emails
    the owner) when the set of problems changes, not on every pass while the same one lasts."""
    out = []
    day = is_trading_day(now.date())
    busy = day and dt.time(7, 0) <= now.time() < dt.time(20, 0)
    q = json.loads((md.DATA / "quotes/latest.json").read_text()) if (md.DATA / "quotes/latest.json").exists() else {}
    asof = parse(q.get("asof"))
    if day and dt.time(9, 30) <= now.time() < dt.time(16, 0) and (asof is None or now - asof > dt.timedelta(minutes=45)):
        out.append(("quotes", f"Quotes are stale: last refreshed {asof:%a %H:%M} ET ({hours(now - asof)} ago) during the session."
                   if asof else "Quotes have no refresh time."))
    waited = []
    for p in sorted((EVENTS / "queue").glob("*.json")) if (EVENTS / "queue").exists() else []:
        try:
            ev = json.loads(p.read_text())
        except ValueError:
            continue
        made, exp = parse(ev.get("created")), parse(ev.get("expires"))
        if made and (exp is None or exp > now):
            waited.append((now - made, ev.get("id", p.stem)))
    limit = dt.timedelta(hours=3 if busy else 9)
    late = sorted((w for w in waited if w[0] > limit), reverse=True)
    if late:
        out.append((f"queue:{late[0][1]}", f"{len(late)} queued event(s) waiting more than {hours(limit)} for the writer; the oldest, "
                   f"`{late[0][1]}`, for {hours(late[0][0])}."))
    newest = None
    for p in (ROOT / "content/articles").glob("*.md"):
        try:
            fm = tomllib.loads(p.read_text().split("+++", 2)[1])
        except (IndexError, tomllib.TOMLDecodeError):
            continue
        t = parse(fm.get("published"))
        if t and fm.get("status") != "draft" and t <= now and (newest is None or t > newest):
            newest = t
    gap = dt.timedelta(hours=3 if busy else 12)
    if newest is None or now - newest > gap:
        out.append(("stories", f"No new story for {hours(now - newest)} (the last went up {newest:%a %d %b %H:%M} ET)."
                    if newest else "No stories found."))
    if ALERT.exists():
        note = ALERT.read_text().strip()
        out.append(("alert", "The writer reported a problem in `events/ALERT.md`:\n\n> " + note[:1500].replace("\n", "\n> ")))
    if check_runs:
        for wf in ("build.yml", "covers.yml"):
            if last_run_failed(wf):
                out.append((f"failed:{wf}", f"The last {wf} run failed: see the Actions tab."))
    return out


def gh(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(["gh", *args], cwd=ROOT, capture_output=True, text=True)


def main(argv: list[str]) -> None:
    now = md.now_et()
    if "--at" in argv:
        now = dt.datetime.fromisoformat(argv[argv.index("--at") + 1]).replace(tzinfo=md.ET)
    dry = "--dry" in argv
    found = problems(now, check_runs=not dry)
    if dry:
        print("\n".join(text for _, text in found) or "healthy")
        return
    state = json.loads(STATE.read_text()) if STATE.exists() else {}
    # The writer's ALERT.md is reported for 6 hours, then cleared if nothing else is wrong.
    if ALERT.exists():
        state.setdefault("alert_since", now.isoformat(timespec="minutes"))
        since = parse(state["alert_since"])
        others = [p for p in found if p[0] != "alert"]
        if since and now - since > dt.timedelta(hours=6) and not others:
            ALERT.unlink()
            state.pop("alert_since", None)
            found = others
    else:
        state.pop("alert_since", None)
    r = gh("issue", "list", "--state", "open", "--search", f'in:title "{TITLE}"', "--json", "number,title", "--limit", "5")
    try:
        issue = next((i["number"] for i in json.loads(r.stdout or "[]") if i["title"] == TITLE), None)
    except ValueError:
        print(f"::warning::health: could not list issues: {r.stderr.strip()}")
        return
    digest = hashlib.sha1("\n".join(sorted(k for k, _ in found)).encode()).hexdigest()[:10]
    if found:
        body = (f"{OWNER} the site isn't updating as it should. Checked {now:%a %d %b %H:%M} ET by the data job "
                f"(pipeline/health.py):\n\n" + "\n".join(f"- {text}" for _, text in found) +
                "\n\nThis issue updates itself and closes when everything is back to normal.")
        if issue is None:
            gh("issue", "create", "--title", TITLE, "--body", body)
            print("health: opened the Site health issue")
        elif state.get("digest") != digest:
            gh("issue", "edit", str(issue), "--body", body)
            gh("issue", "comment", str(issue), "--body", "Updated: " + "; ".join(text.split("\n")[0] for _, text in found))
            print("health: updated the Site health issue")
        for _, text in found:
            print(f"::warning::health: {text.splitlines()[0]}")
    elif issue is not None:
        gh("issue", "close", str(issue), "--comment", f"Back to normal at {now:%a %d %b %H:%M} ET.")
        print("health: all clear; closed the Site health issue")
    state["digest"] = digest if found else None
    STATE.write_text(json.dumps(state, indent=1) + "\n")


if __name__ == "__main__":
    try:
        main(sys.argv[1:])
    except Exception as e:  # noqa: BLE001  the health check must never break a data pass
        print(f"::warning::health check failed: {e!r}")
