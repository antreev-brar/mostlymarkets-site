"""AI cover art for stories that ask for it (front matter `cover_brief`), in the Mostly Markets house style.

    python3 pipeline/covers.py                 # every story with a cover_brief and no cover yet
    python3 pipeline/covers.py --only <slug>   # one story (re-draws it with --force)
    python3 pipeline/covers.py --brief "..." --name test-1   # a one-off test into assets/covers/story/

Needs OPENAI_API_KEY. Writes assets/covers/story/<slug>-{1600,800,480}.webp (3:2) and keeps the PNG master in
$MM_COVER_MASTERS (default ../cover-masters/story next to the repo, else a temp folder). Pillow is the only
dependency outside the standard library."""
from __future__ import annotations

import argparse
import base64
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
MODEL = os.environ.get("MM_IMAGE_MODEL", "gpt-image-2.5-sunburst")
SIZE = "1536x1024"

# The house style. Our palette, not anyone else's: navy ink, cobalt, lemon yellow on warm paper; red/green only
# where a chart line means down/up. Never real people, logos or lettering: the art illustrates, it doesn't report.
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


def key() -> str:
    k = os.environ.get("OPENAI_API_KEY")
    if not k:
        env = Path.home() / ".config/video-studio/openai.env"
        if env.exists():
            m = re.search(r"OPENAI_API_KEY\s*=\s*['\"]?([^'\"\s]+)", env.read_text())
            k = m.group(1) if m else None
    if not k:
        sys.exit("OPENAI_API_KEY is not set")
    return k


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


def generate(prompt: str, quality: str) -> tuple[bytes, dict]:
    body = json.dumps({"model": MODEL, "prompt": prompt, "size": SIZE, "quality": quality, "n": 1}).encode()
    for attempt in range(4):
        req = urllib.request.Request("https://api.openai.com/v1/images/generations", data=body, method="POST",
                                     headers={"Authorization": f"Bearer {key()}", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                d = json.loads(r.read())
            return base64.b64decode(d["data"][0]["b64_json"]), d.get("usage", {})
        except urllib.error.HTTPError as e:
            msg = e.read().decode(errors="replace")[:400]
            # A 429 is either a rate limit (retry) or an empty prepaid balance (stop): read the body.
            if e.code == 429 and "quota" not in msg and "credit" not in msg and attempt < 3:
                time.sleep(20 * (attempt + 1))
                continue
            raise SystemExit(f"image API {e.code}: {msg}")
    raise SystemExit("image API: gave up after retries")


def save(png: bytes, name: str) -> list[Path]:
    from PIL import Image  # only the cover job needs Pillow
    (masters_dir() / f"{name}.png").write_bytes(png)
    im = Image.open(BytesIO(png)).convert("RGB")
    OUT.mkdir(parents=True, exist_ok=True)
    out = []
    for w, q in ((1600, 68), (800, 70), (480, 68)):
        h = round(w * im.height / im.width)
        p = OUT / f"{name}-{w}.webp"
        im.resize((w, h), Image.LANCZOS).save(p, "WEBP", quality=q, method=6)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only")
    ap.add_argument("--force", action="store_true")
    ap.add_argument("--brief")
    ap.add_argument("--name")
    ap.add_argument("--quality", default=os.environ.get("MM_IMAGE_QUALITY", "high"))
    ap.add_argument("--max", type=int, default=6, help="covers per run, a cost cap")
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
    jobs = jobs[:a.max]
    if not jobs:
        print("covers: nothing to draw")
        return
    for name, brief in jobs:
        prompt = HOUSE + brief.strip()
        if a.dry:
            print(f"{name}: {prompt}\n")
            continue
        t = time.time()
        png, usage = generate(prompt, a.quality)
        save(png, name)
        (masters_dir() / f"{name}.json").write_text(json.dumps({"prompt": prompt, "model": MODEL, "quality": a.quality,
                                                                 "usage": usage}, indent=1))
        print(f"covers: {name} drawn in {time.time() - t:.0f}s ({usage.get('output_tokens', '?')} output tokens)", flush=True)


if __name__ == "__main__":
    main()
