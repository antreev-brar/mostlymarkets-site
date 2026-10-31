"""AI cover art for stories that ask for it (front matter `cover_brief`), in the Mostly Markets house style.

    python3 pipeline/covers.py                 # every story with a cover_brief and no cover yet
    python3 pipeline/covers.py --only <slug>   # one story (re-draws it with --force)
    python3 pipeline/covers.py --brief "..." --name test-1   # a one-off test into assets/covers/story/

Two providers (MM_IMAGE_PROVIDER):
  horde   (default, free) FLUX.1 [schnell] on AI Horde (aihorde.net), the volunteer-run Stable Horde. FLUX.1 schnell is
          Apache-2.0, so its images can be used commercially. Works anonymously; an AIHORDE_API_KEY (free sign-up)
          only buys queue priority. A cover takes 1-5 minutes in the queue, so several are drawn at once.
  openai  (paid, richer) needs OPENAI_API_KEY. Only used when asked for.

Writes assets/covers/story/<slug>-{1600,800,480}.webp and keeps the master in $MM_COVER_MASTERS (default
../cover-masters/story next to the repo, else a temp folder). Pillow is the only dependency outside the standard
library."""
from __future__ import annotations

import argparse
import base64
import concurrent.futures as cf
import json
import os
import re
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

# The house style. Our palette, not anyone else's: navy ink, cobalt, lemon yellow on warm paper. Never real people,
# logos or lettering: the art illustrates, it doesn't report.
HOUSE = (
    "Editorial collage illustration for the cover of a modern financial newsletter. Layered torn-paper shapes and "
    "cut-out photographic objects with a white cut-out outline, halftone dot texture, risograph grain and visible "
    "paper fibres, on a warm off-white paper ground. Limited palette: deep navy ink (#101a3a), electric cobalt blue "
    "(#3355ff) and bright lemon yellow (#ffe45c), with small accents of signal red and signal green used only for "
    "stock-chart lines and candlesticks. Bold, graphic and high-contrast, cinematic depth, one dominant subject in the "
    "centre of the frame so it survives a square or vertical crop, generous breathing room around it. "
    "Strictly no text, letters, numbers, words, tickers or logos anywhere, no brand marks or trade dress, and no real "
    "or recognisable people: any human figures are anonymous, in silhouette or seen from behind. "
    "Scene: "
)
# FLUX reads about 256 tokens, so the scene goes first and the style stays short.
HOUSE_SHORT = (
    "Editorial torn-paper collage illustration for a financial newsletter cover: layered cut paper, halftone dots, "
    "risograph grain, warm off-white paper background, palette of deep navy, cobalt blue and lemon yellow with small red "
    "accents, bold graphic shapes, one central subject. No text, no letters, no numbers, no logos, no faces."
)
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
HORDE_MODEL = os.environ.get("MM_HORDE_MODEL", "Flux.1-Schnell fp8 (Compact)")


def _horde(path: str, body: dict | None = None) -> dict:
    h = {"User-Agent": UA, "apikey": os.environ.get("AIHORDE_API_KEY") or "0000000000",
         "Client-Agent": "mostlymarkets-covers:1.0:bot@mostlymarkets.org", "Content-Type": "application/json"}
    req = urllib.request.Request(HORDE + path, data=json.dumps(body).encode() if body else None, headers=h,
                                 method="POST" if body else "GET")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read())


def generate_horde(brief: str) -> tuple[bytes, dict]:
    prompt = brief.strip().rstrip(".") + ". " + HOUSE_SHORT
    body = {"prompt": prompt, "models": [HORDE_MODEL], "nsfw": False, "censor_nsfw": True, "r2": True,
            "params": {"width": 1024, "height": 640, "steps": 4, "cfg_scale": 1, "sampler_name": "k_euler", "n": 1,
                       "post_processing": ["RealESRGAN_x2plus"]}}
    for attempt in range(3):
        try:
            gid = _horde("/generate/async", body)["id"]
            t = time.time()
            while time.time() - t < 1200:
                time.sleep(10)
                if _horde(f"/generate/check/{gid}").get("done"):
                    break
            else:
                raise TimeoutError("queue took over 20 minutes")
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
    return f"covers: {name} drawn in {time.time() - t:.0f}s ({provider})"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--brief")
    ap.add_argument("--name")
    ap.add_argument("--provider", default=PROVIDER, choices=("horde", "openai"))
    ap.add_argument("--quality", default=os.environ.get("MM_IMAGE_QUALITY", "high"), help="openai only")
    ap.add_argument("--max", type=int, default=12, help="covers per run")
    ap.add_argument("--workers", type=int, default=3, help="covers drawn at once")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()
    jobs = []
    if a.brief:
        jobs.append((a.name or f"test-{int(time.time())}", a.brief))
    else:
        for slug, fm in stories():
            if a.only and slug != a.only:
                continue
            if (OUT / f"{slug}-800.webp").exists() and not (a.force and a.only):
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
