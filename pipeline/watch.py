"""Watch the market for one Actions job: refresh, detect, save, deploy, then sleep to the next slot and repeat.

GitHub drops most scheduled runs of a busy cron, so data.yml no longer relies on one run per slot. Each run loops
inside a single job for up to ~5.5 hours and, when its time is up mid-session, dispatches its own successor.
The crons in data.yml are only starters and backups.

Each pass: refresh.py (quotes, prices, calendars, filings), news.py (headlines and X posts), detect.py (queue story
events), health.py (the "Site health" issue), data_push.sh, commit events, dispatch build.yml.

Slots (New York time), around the clock so nights and weekends never go stale (GitHub fired 2 of 39 of the old
night and weekend cron slots, automation audit of 2 Nov 2026):
- weekdays 06:00-19:45: every 15 minutes
- every other time (weekday nights, weekends, holidays): every 30 minutes, at :00 and :30
The loop never runs out of slots, so it always ends by queueing its successor (checked, with retries); the crons in
data.yml only restart the chain if it ever breaks.

  python3 pipeline/watch.py            # loop (what data.yml runs)
  python3 pipeline/watch.py --once     # one pass, no sleeping
  python3 pipeline/watch.py --slots 2026-10-30T19:50   # print the next slots after that time (testing)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import marketdata as md  # noqa: E402

ROOT = md.ROOT
BUDGET = dt.timedelta(minutes=320)  # don't start a pass after this; the job's timeout is 355 minutes
JOB_LIMIT = dt.timedelta(minutes=348)  # stop trying to hand over just before the timeout
REACH = dt.timedelta(minutes=65)    # stay alive only if the next slot is this close


def is_slot(t: dt.datetime) -> bool:
    if t.weekday() < 5 and 6 <= t.hour < 20:
        return t.minute % 15 == 0
    return t.minute % 30 == 0


def next_slot(now: dt.datetime) -> dt.datetime | None:
    t = now.replace(second=0, microsecond=0) + dt.timedelta(minutes=1)
    while t - now <= REACH:
        if is_slot(t):
            return t
        t += dt.timedelta(minutes=1)
    return None


def sh(args: list[str], **kw) -> bool:
    print("$ " + " ".join(args), flush=True)
    r = subprocess.run(args, cwd=ROOT, **kw)
    if r.returncode:
        print(f"::warning::{' '.join(args)} exited {r.returncode}", flush=True)
    return r.returncode == 0


def wake_writer() -> None:
    url, token = os.environ.get("FIRE_URL"), os.environ.get("FIRE_TOKEN")
    if not (url and token):
        print("no routine token set; the scheduled writer runs will pick these up")
        return
    at = md.now_et().strftime("%H:%M ET")
    body = json.dumps({"text": f"Urgent events were queued at {at}. Follow pipeline/WRITER.md now."}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": f"Bearer {token}", "anthropic-version": "2026-10-21", "Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
        print("woke the writer")
    except Exception as e:  # noqa: BLE001
        print(f"::warning::waking the writer failed: {e}")


def sync_main(force: bool = False) -> None:
    """Start every pass from main as it is on GitHub. A failed rebase used to leave the loop stuck on an old tree for
    hours while every run still showed success; the events this loop commits are recomputed by detect.py (seen.json
    keeps that safe), so a hard reset loses nothing."""
    if not force and sh(["git", "pull", "--rebase", "-q", "origin", "main"]):
        return
    sh(["git", "rebase", "--abort"])
    if sh(["git", "fetch", "-q", "origin", "main"]):
        sh(["git", "reset", "-q", "--hard", "origin/main"])


def successor_waiting() -> bool:
    r = subprocess.run(["gh", "run", "list", "--workflow", "data.yml", "--limit", "10", "--json", "status"],
                       cwd=ROOT, capture_output=True, text=True)
    try:
        return r.returncode == 0 and any(x.get("status") in ("queued", "pending", "waiting", "requested")
                                         for x in json.loads(r.stdout or "[]"))
    except ValueError:
        return False


def hand_over(deadline: float) -> None:
    """Queue this workflow's successor; it waits in the data-watch concurrency group until this run ends. Keep trying
    (a GitHub hiccup can last minutes) until shortly before the job's time limit, then raise the Site health issue:
    a run dispatched by the job token emails nobody when it fails, and a broken chain would leave the site stale
    until a cron happened to fire."""
    while True:
        if sh(["gh", "workflow", "run", "data.yml", "--ref", "main"]):
            time.sleep(15)
            if successor_waiting():
                print("handed over to the next run", flush=True)
                return
        if time.monotonic() + 90 > deadline:
            break
        time.sleep(60)
    msg = "The data loop could not queue its successor run; the backup crons and build.yml's watchdog should restart it."
    print(f"::error::{msg}", flush=True)
    subprocess.run(["gh", "issue", "create", "--title", "Site health", "--body", f"@antreev-brar {msg}"], cwd=ROOT)
    sys.exit(1)


def draw_missing_covers() -> None:
    """Covers that failed to draw (the Horde was down) used to wait for the next story push; ask covers.yml again."""
    r = subprocess.run([sys.executable, "pipeline/covers.py", "--dry", "--max", "50"], cwd=ROOT, capture_output=True,
                       text=True)
    if r.returncode == 0 and "nothing to draw" not in r.stdout:
        sh(["gh", "workflow", "run", "covers.yml", "--ref", "main"])


def one_pass() -> None:
    sync_main()
    if not sh([sys.executable, "pipeline/refresh.py"]):
        print("::warning::refresh failed; skipping this pass (nothing saved)")
        return
    # Headlines (pipeline/news.py): the market's every pass, the 150 biggest stocks hourly (and every weekend pass),
    # every stock once a day, and X posts embedded in stories. The detector reads them, so this comes first.
    now = md.now_et()
    news = [sys.executable, "pipeline/news.py", "--market", "--tweets"]
    if now.minute < 15:  # hourly, at every hour of every day
        news += ["--top", "150"]
    if now.weekday() < 5 and now.hour == 6 and now.minute < 15:
        news = [sys.executable, "pipeline/news.py", "--market", "--tweets", "--all"]
    sh(news)
    with tempfile.NamedTemporaryFile("r", suffix=".out") as out:
        sh([sys.executable, "pipeline/detect.py"], env={**os.environ, "GITHUB_OUTPUT": out.name})
        flags = dict(line.strip().split("=", 1) for line in out if "=" in line)
    sh([sys.executable, "pipeline/health.py"])  # opens or closes the "Site health" issue; before the commit (ALERT.md)
    sh(["bash", "pipeline/data_push.sh"])
    sh(["git", "add", "events"])
    if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
        sh(["git", "commit", "-q", "-m", f"events: {md.now_et():%Y-%m-%d %H:%M} ET"])
        for _ in range(3):
            if sh(["git", "pull", "--rebase", "-q", "origin", "main"]) and sh(["git", "push", "-q", "origin", "HEAD:main"]):
                break
            sh(["git", "rebase", "--abort"])
            time.sleep(5)
        else:
            # Main moved under us in a way that won't rebase (the writer closed the same event): start again from main
            # and recompute this pass's events; seen.json makes that safe.
            sync_main(force=True)
            sh([sys.executable, "pipeline/detect.py"])
            sh(["git", "add", "events"])
            if subprocess.run(["git", "diff", "--cached", "--quiet"], cwd=ROOT).returncode:
                sh(["git", "commit", "-q", "-m", f"events: {md.now_et():%Y-%m-%d %H:%M} ET"])
                sh(["git", "push", "-q", "origin", "HEAD:main"])
    if flags.get("wake") == "true":
        wake_writer()
    if now.minute < 15:  # hourly
        draw_missing_covers()
    # build.yml rebuilds and deploys the site with the fresh data (its own concurrency group keeps deploys in order).
    sh(["gh", "workflow", "run", "build.yml", "--ref", "main"])


def main(argv: list[str]) -> None:
    if "--slots" in argv:
        t = dt.datetime.fromisoformat(argv[argv.index("--slots") + 1]).replace(tzinfo=md.ET)
        for _ in range(6):
            t = next_slot(t)
            print(t or "none within reach: exit")
            if not t:
                break
        return
    t0 = time.monotonic()  # the job's own clock: New York wall time jumps an hour twice a year
    while True:
        print(f"::group::pass at {md.now_et():%Y-%m-%d %H:%M:%S} ET", flush=True)
        try:
            one_pass()
        except Exception as e:  # noqa: BLE001  one bad pass must never end the loop (and with it the chain of runs)
            print(f"::warning::the pass failed: {e!r}; trying again at the next slot", flush=True)
        print("::endgroup::", flush=True)
        now = md.now_et()
        nxt = next_slot(now)
        if "--once" in argv or nxt is None:
            print("no slot within reach; done")
            return
        wait = (nxt - md.now_et()).total_seconds()
        if time.monotonic() - t0 + wait > BUDGET.total_seconds():
            # Out of time: queue a successor. It waits in the concurrency group until this run ends.
            if os.environ.get("MM_ENABLED") == "true":
                hand_over(deadline=t0 + JOB_LIMIT.total_seconds())
            return
        print(f"next pass at {nxt:%H:%M} ET (sleeping {wait / 60:.1f} min)", flush=True)
        time.sleep(max(0.0, wait))


if __name__ == "__main__":
    main(sys.argv[1:])
