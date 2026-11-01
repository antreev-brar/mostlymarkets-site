"""AI covers for stories (front matter `cover_brief`), in the Mostly Markets house style: one witty visual metaphor
per story, drawn as a vivid cinematic 3D illustration in the site's navy and gold (see HOUSE_SHORT and docs/STYLE.md,
"Covers").

    python3 pipeline/covers.py                 # every story with a cover_brief and no cover yet
    python3 pipeline/covers.py --only <slug>   # one story (re-draws it with --force)
    python3 pipeline/covers.py --redraw --max 200 --workers 10   # every story again, after a change of house style
    python3 pipeline/covers.py --brief "..." --name test-1   # a one-off test into assets/covers/story/

Two providers (MM_IMAGE_PROVIDER):
  horde   (default, free) AI Horde (aihorde.net), the volunteer-run Stable Horde, with two Apache-2.0 models whose
          images can be used commercially: Z-Image-Turbo, and FLUX.1 [schnell] when no Z-Image worker is online
          (MM_HORDE_MODEL sets the order). Works anonymously; an AIHORDE_API_KEY (free sign-up) only buys queue
          priority. A cover takes 1-8 minutes in the queue, so several are drawn at once.
  openai  (paid, richer) needs OPENAI_API_KEY. Only used when asked for.

Writes assets/covers/story/<slug>-{1600,800,480}.webp and keeps the master in $MM_COVER_MASTERS (default
../cover-masters/story next to the repo, else a temp folder). Pillow is the only dependency outside the standard
library."""
from __future__ import annotations

import argparse
import atexit
import base64
import concurrent.futures as cf
import json
import os
import re
import signal
import sys
import tempfile
import time
import tomllib
import urllib.error
import urllib.request
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "assets/covers/story"
PROVIDER = os.environ.get("MM_IMAGE_PROVIDER", "horde")

# The house style (since 1 Nov 2026, v8): one witty visual metaphor per story, the way SemiAnalysis's covers work,
# drawn as a vivid cinematic 3D illustration in a signature palette, the site's navy and gold, so the covers read as
# one family the way Opening Bell Daily's red-and-navy collages do. The owner rejected the documentary photos as
# "generic boring covers off the internet", the collages before them as busy, and chart pictures as "ugly graphs".
# Never real or recognisable people, faces, logos, flags or lettering. FLUX and Z-Image read about 256 tokens, so the
# scene goes first and the style stays short.
HOUSE_SHORT = (
    "Vivid cinematic 3D illustration, like a frame from a big-budget animated film: one bold visual metaphor, glossy "
    "materials, dramatic lighting, a signature palette of deep navy and cobalt blue with glowing warm gold highlights "
    "and a touch of red, rich saturated colour, crisp detail, the subject centred on a clean uncluttered background, "
    "full frame. No text, letters, numbers, logos or flags. No human faces."
)
HOUSE = HOUSE_SHORT + " Scene: "  # the paid provider takes the style first
UA = "Mozilla/5.0 (compatible; mostlymarkets-covers/1.0; +https://mostlymarkets.org)"


def masters_dir() -> Path:
    d = os.environ.get("MM_COVER_MASTERS")
    if d:
        p = Path(d)
    elif (ROOT.parent / "cover-masters").exists():
        p = ROOT.parent / "cover-masters/story"
    else:
        p = Path(tempfile.gettempdir()) / "mm-cover-masters"
    p.mkdir(parents=True, exist_ok=True)
    return p


# ---------------------------------------------------------------- AI Horde (free)

HORDE = "https://aihorde.net/api/v2"
# Both Apache-2.0, in order of preference. Z-Image-Turbo draws the house style most faithfully (and had four workers to
# FLUX's one on 1 Nov 2026); FLUX.1 schnell takes over when no Z-Image worker is online. Each has its own settings on
# the Horde (its model reference): Z-Image-Turbo exactly 9 steps with the simple scheduler, FLUX 3-8 with karras.
HORDE_PARAMS = {"Z-Image-Turbo": {"steps": 9, "scheduler": "simple", "karras": False},
                "Flux.1-Schnell fp8 (Compact)": {"steps": 4, "karras": True}}
HORDE_MODELS = [m.strip() for m in os.environ.get("MM_HORDE_MODEL", ",".join(HORDE_PARAMS)).split(",") if m.strip()]
HORDE_MODEL = HORDE_MODELS[0]


def _horde(path: str, body: dict | None = None) -> dict:
    h = {"User-Agent": UA, "apikey": os.environ.get("AIHORDE_API_KEY") or "0000000000",
         "Client-Agent": "mostlymarkets-covers:1.0:bot@mostlymarkets.org", "Content-Type": "application/json"}
    for attempt in range(8):
        req = urllib.request.Request(HORDE + path, data=json.dumps(body).encode() if body else None, headers=h,
                                     method="POST" if body else "GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < 7:  # the Horde allows about 2 requests a second
                time.sleep(2 + attempt * 2)
                continue
            raise


PENDING: set[str] = set()  # requests still in the queue, cancelled if the run is stopped (atexit)
DEADLINE = float("inf")  # main() sets it so a CI run stops waiting in time to commit what it drew


def _cancel_pending() -> None:
    for gid in list(PENDING):
        _horde_cancel(gid)


def _horde_cancel(gid: str) -> None:
    PENDING.discard(gid)
    req = urllib.request.Request(f"{HORDE}/generate/status/{gid}", method="DELETE",
                                 headers={"User-Agent": UA, "apikey": os.environ.get("AIHORDE_API_KEY") or "0000000000",
                                          "Client-Agent": "mostlymarkets-covers:1.0:bot@mostlymarkets.org"})
    try:
        urllib.request.urlopen(req, timeout=30).read()
    except (urllib.error.URLError, TimeoutError):
        pass


def generate_horde(brief: str) -> tuple[bytes, dict]:
    prompt = brief.strip().rstrip(".") + ". " + HOUSE_SHORT
    for attempt in range(3):
        try:
            if time.time() >= DEADLINE:
                raise TimeoutError("out of time for this run")
            for model in HORDE_MODELS:  # the first model with a worker online draws it
                # 1024x640 is the largest an anonymous request may ask for. No upscaling on the Horde: asking for it
                # leaves one worker able to take the job instead of three or four (1 Nov 2026); save() resizes.
                body = {"prompt": prompt, "models": [model], "nsfw": False, "censor_nsfw": True, "r2": True,
                        "params": {"width": 1024, "height": 640, "cfg_scale": 1, "sampler_name": "k_euler", "n": 1,
                                   **HORDE_PARAMS.get(model, {"steps": 4})}}
                try:
                    gid = _horde("/generate/async", body)["id"]
                except urllib.error.HTTPError:
                    if model == HORDE_MODELS[-1]:
                        raise
                    continue  # this model refused the job: try the next
                PENDING.add(gid)
                time.sleep(3)
                if _horde(f"/generate/check/{gid}").get("is_possible", True) or model == HORDE_MODELS[-1]:
                    break
                _horde_cancel(gid)
            t = time.time()
            while time.time() - t < 2400 and time.time() < DEADLINE:
                time.sleep(10)
                chk = _horde(f"/generate/check/{gid}")
                if chk.get("done"):
                    break
                if chk.get("faulted") or chk.get("is_possible") is False:  # a lost job never finishes: ask again
                    _horde_cancel(gid)
                    raise RuntimeError("the Horde dropped the job")
            else:
                _horde_cancel(gid)
                raise TimeoutError("the queue took too long")
            PENDING.discard(gid)
            g = _horde(f"/generate/status/{gid}")["generations"][0]
            if g.get("censored"):
                raise RuntimeError("the worker censored the image")
            img = urllib.request.urlopen(urllib.request.Request(g["img"], headers={"User-Agent": UA}), timeout=120).read()
            return img, {"model": g.get("model"), "worker": g.get("worker_name"), "seed": g.get("seed"), "prompt": prompt}
        except (urllib.error.URLError, TimeoutError, RuntimeError, KeyError) as e:
            if attempt == 2:
                raise SystemExit(f"AI Horde: {e}")
            time.sleep(30)
    raise SystemExit("AI Horde: gave up")


atexit.register(_cancel_pending)


# ---------------------------------------------------------------- OpenAI (paid, optional)

OPENAI_MODEL = os.environ.get("MM_IMAGE_MODEL", "gpt-image-2.5-sunburst")


def generate_openai(brief: str, quality: str = "high") -> tuple[bytes, dict]:
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        raise SystemExit("OPENAI_API_KEY is not set (or use the free default, MM_IMAGE_PROVIDER=horde)")
    body = json.dumps({"model": OPENAI_MODEL, "prompt": HOUSE + brief.strip(), "size": "1536x1024", "quality": quality,
                       "n": 1}).encode()
    for attempt in range(4):
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {k}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.loads(r.read())
            return base64.b64decode(d["data"][0]["b64_json"]), {"model": OPENAI_MODEL, "usage": d.get("usage", {})}
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            # A 429 is either a rate limit (retry) or an empty prepaid balance (stop): read the body.
            if e.code == 429 and "quota" not in msg and "credit" not in msg and attempt < 3:
                time.sleep(20 * (attempt + 1))
                continue
            raise SystemExit(f"image API {e.code}: {msg}")
    raise SystemExit("image API: gave up after retries")


# ---------------------------------------------------------------- output

def save(img: bytes, name: str) -> list[Path]:
    from PIL import Image  # only the cover job needs Pillow
    im = Image.open(BytesIO(img)).convert("RGB")
    im.save(masters_dir() / f"{name}.jpg", "JPEG", quality=92)
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    # The large size is 1280 wide (served as -1600): the art is graphic, and the repo stays small.
    for label, w, q in (("1600", 1280, 70), ("800", 800, 72), ("480", 480, 70)):
        p = OUT / f"{name}-{label}.webp"
        im.resize((w, round(w * im.height / im.width)), Image.LANCZOS).save(p, "WEBP", quality=q, method=6)
        out.append(p)
    return out


def stories():
    for p in sorted((ROOT / "content/articles").glob("*.md")):
        try:
            fm = tomllib.loads(p.read_text().split("+++", 2)[1])
        except Exception:  # noqa: BLE001
            continue
        if fm.get("cover_brief") and fm.get("status") != "draft":
            yield p.stem[11:], fm


def draw(job, provider: str, quality: str) -> str:
    name, brief = job
    t = time.time()
    img, meta = generate_horde(brief) if provider == "horde" else generate_openai(brief, quality)
    save(img, name)
    (masters_dir() / f"{name}.json").write_text(json.dumps({"brief": brief, "provider": provider, **meta}, indent=1))
    return f"covers: {name} drawn in {time.time() - t:.0f}s ({meta.get('model') or provider})"


def main():
    signal.signal(signal.SIGTERM, lambda *_: (_cancel_pending(), os._exit(1)))  # a stopped run frees its queue places
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--brief")
    ap.add_argument("--name")
    ap.add_argument("--provider", default=PROVIDER, choices=("horde", "openai"))
    ap.add_argument("--quality", default=os.environ.get("MM_IMAGE_QUALITY", "high"), help="openai only")
    ap.add_argument("--redraw", action="store_true", help="draw stories that already have a cover too (a new house style)")
    ap.add_argument("--max", type=int, default=12, help="covers per run")
    ap.add_argument("--workers", type=int, default=3, help="covers drawn at once")
    ap.add_argument("--deadline", type=float, default=0, help="minutes after which to stop waiting (0: no limit)")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    if a.deadline:
        global DEADLINE
        DEADLINE = time.time() + a.deadline * 60
    jobs = []
    if a.brief:
        jobs.append((a.name or f"test-{int(time.time())}", a.brief))
    else:
        for slug, fm in stories():
            if a.only and slug != a.only:
                continue
            if (OUT / f"{slug}-800.webp").exists() and not (a.force and a.only) and not a.redraw:
                continue
            jobs.append((slug, fm["cover_brief"]))
    jobs = jobs[::-1][:a.max]  # newest first
    if not jobs:
        print("covers: nothing to draw")
        return
    if a.dry:
        for name, brief in jobs:
            print(f"{name}: {brief}")
        return
    failed = 0
    with cf.ThreadPoolExecutor(max(1, a.workers)) as ex:
        futs = {ex.submit(draw, j, a.provider, a.quality): j for j in jobs}
        for f in cf.as_completed(futs):
            try:
                print(f.result(), flush=True)
            except SystemExit as e:
                failed += 1
                print(f"covers: {futs[f][0]} failed: {e}", flush=True)
    if failed == len(jobs):
        sys.exit(1)


if __name__ == "__main__":
    main()
