"""AI covers for stories (front matter `cover_brief`), in the Mostly Markets house style: a detailed scene that shows
what the story is about, with its company and key figure lettered on big signs, drawn as a richly detailed 3D
animated-film illustration lit in the site's navy and gold (see HOUSE_SHORT and docs/STYLE.md, "Covers").

    python3 pipeline/covers.py                 # every story with a cover_brief and no cover yet
    python3 pipeline/covers.py --only <slug>   # one story (re-draws it with --force)
    python3 pipeline/covers.py --redraw --max 200 --workers 10   # every story again, after a change of house style
    python3 pipeline/covers.py --brief "..." --name test-1   # a one-off test into assets/covers/story/

Two providers (MM_IMAGE_PROVIDER):
  horde   (default, free) AI Horde (aihorde.net), the volunteer-run Stable Horde, with Apache-2.0 models whose
          images can be used commercially and that can letter short signs: Z-Image-Turbo, then Qwen-Image when no
          Z-Image worker is online, and FLUX.1 [schnell] last (it garbles lettering; the covers check redraws those)
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

# The house style (since 2 Nov 2026, v9): a detailed scene that shows what the story is about, the way SemiAnalysis's
# covers do, with the company's name and the story's key figure lettered on big signs (the models can letter 1-3 short
# words), drawn as a richly detailed 3D animated-film illustration lit in the site's navy and gold, so the covers read as
# one family. The owner found v8's single metaphors "an abstract notion of maybe what it is about but not enough
# details"; three judges preferred this look to an ink cartoon and a newspaper collage (2 Nov 2026: it lettered the key
# figures right and reads at 300 px). Never real or recognisable people. The brief comes first and the style stays
# short: the models read the start of the prompt most closely.
HOUSE_SHORT = (
    "Vivid cinematic 3D illustration like a frame from a big-budget animated film, richly detailed: adults with realistic "
    "proportions and expressive faces, glossy materials, dusk or night or a navy-shadowed interior, one warm gold light on "
    "the main subject, deep navy and cobalt blue with gold highlights and red only for alarm, crisp bold capital letters "
    "only on the quoted signs, every other surface plain and unmarked, full bleed edge to edge, no border."
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
# All Apache-2.0, in order of preference (tested 2 Nov 2026, research/2026-11-02-v9/cover-study/models). Z-Image-Turbo
# letters short signs right, draws the house style faithfully and is the fastest; Qwen-Image letters well but is flatter
# and has one or two workers; FLUX.1 schnell garbles lettering, so it is the last resort. MOSS-Image-SFT draws the most
# detail but its anonymous queue took over 40 minutes. Each has its own settings on the Horde: Z-Image-Turbo exactly 9
# steps with the simple scheduler; Qwen-Image 20 steps at cfg 2.5; FLUX 3-8 with karras.
HORDE_PARAMS = {"Z-Image-Turbo": {"steps": 9, "scheduler": "simple", "karras": False},
                "Qwen-Image_fp8": {"steps": 20, "cfg_scale": 2.5, "scheduler": "simple", "karras": False},
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
                # No worker for this model right now? Give one a minute to come back before trying the next model:
                # the later ones letter worse.
                possible = True
                for _ in range(7):
                    time.sleep(3 if _ == 0 else 10)
                    possible = _horde(f"/generate/check/{gid}").get("is_possible", True)
                    if possible:
                        break
                if possible or model == HORDE_MODELS[-1]:
                    break
                _horde_cancel(gid)
            t = time.time()
            stuck = 0
            while time.time() - t < 2400 and time.time() < DEADLINE:
                time.sleep(10)
                chk = _horde(f"/generate/check/{gid}")
                if chk.get("done"):
                    break
                # A lost job never finishes: ask again. "Not possible" often clears within a minute or two (a worker
                # comes back), so only two minutes of it in a row counts as lost.
                stuck = stuck + 1 if chk.get("is_possible") is False else 0
                if chk.get("faulted") or stuck >= 12:
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
