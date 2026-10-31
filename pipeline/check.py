"""Validate stories against docs/FORMAT.md and docs/STYLE.md.

  python3 pipeline/check.py                       # every story
  python3 pipeline/check.py content/articles/X.md # some stories
Exit code 1 if any story fails. Warnings never fail.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import sys
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "pipeline"))
from marketdata import price_path, read_prices  # noqa: E402

TYPES = {
    "market-wrap": (450, 800), "why-it-moved": (280, 520), "movers": (220, 420),
    "earnings-recap": (380, 750), "earnings-preview": (260, 480), "list": (500, 850),
    "macro": (350, 700), "chart": (100, 260), "analysis": (600, 1200), "daily": (650, 1500),
}
REASONS = {"Earnings", "Guidance", "Analyst upgrade", "Analyst downgrade", "Deal", "Product",
           "Legal or regulatory", "Management", "Peer news", "Macro", "Sector move", "No clear news"}
BANNED = ["as an ai", "in conclusion", "delve", "it's worth noting", "it is worth noting", "buckle up",
          "game-changer", "game changer", "to the moon", "skyrocket", "insane"]
EMOJI = re.compile("[\U0001F300-\U0001FAFF\U00002600-\U000027BF\U0001F000-\U0001F2FF⭐⬆⬇✅❌]")
FENCE = re.compile(r"^```(\w+)\s*\n(.*?)^```\s*$", re.S | re.M)
CHART_KINDS = {"price", "bars", "hbars", "line", "compare", "moves", "treemap", "contrib"}
COMPUTED = {"price", "compare", "moves", "treemap", "contrib"}  # drawn from our own price files: no source needed


def split(text: str) -> tuple[dict, str]:
    if not text.startswith("+++"):
        raise ValueError("no +++ front matter")
    _, fm, body = text.split("+++", 2)
    return tomllib.loads(fm), body.strip()


def words(body: str) -> int:
    prose = FENCE.sub(" ", body)
    prose = re.sub(r"[#>*|`\-]", " ", prose)
    return len(re.findall(r"[A-Za-z0-9$%][\w$%.,'’-]*", prose))


def ny_date(published) -> str:
    if isinstance(published, dt.datetime):
        return published.date().isoformat()
    return str(published)[:10]


def check_file(path: Path, universe: set[str], authors: set[str], slugs: dict) -> tuple[list[str], list[str]]:
    errs, warns = [], []
    try:
        fm, body = split(path.read_text())
    except Exception as e:  # noqa: BLE001
        return [f"front matter: {e}"], []
    m = re.match(r"(\d{4}-\d{2}-\d{2})-([a-z0-9-]+)\.md$", path.name)
    if not m:
        errs.append("file name must be YYYY-MM-DD-slug.md (lowercase, hyphens)")
    for k, typ in [("title", str), ("dek", str), ("type", str), ("author", str), ("tickers", list)]:
        if not isinstance(fm.get(k), typ):
            errs.append(f"{k}: missing or not a {typ.__name__}")
    if not isinstance(fm.get("published"), dt.datetime) or fm["published"].tzinfo is None:
        errs.append("published: must be a TOML datetime with an offset, e.g. 2026-10-29T16:45:00-04:00")
    elif m and ny_date(fm["published"]) != m.group(1):
        errs.append(f"file date {m.group(1)} doesn't match published date {ny_date(fm['published'])}")
    if errs:
        return errs, warns
    t = fm["type"]
    if t not in TYPES:
        errs.append(f"type: {t!r} is not one of {sorted(TYPES)}")
        return errs, warns
    if fm["author"] not in authors:
        errs.append(f"author: {fm['author']!r} not in data/authors.json")
    for tk in fm["tickers"]:
        if tk not in universe:
            errs.append(f"tickers: {tk} not in the universe")
    if t == "why-it-moved" and fm.get("reason") not in REASONS:
        errs.append(f"reason: {fm.get('reason')!r} must be one of {sorted(REASONS)}")
    if not (40 <= len(fm["title"]) <= 110):
        warns.append(f"title is {len(fm['title'])} characters (aim for 40-90)")
    if not (70 <= len(fm["dek"]) <= 260):
        warns.append(f"dek is {len(fm['dek'])} characters (aim for 90-220)")
    if t not in ("list", "analysis") and not re.search(r"\d", fm["dek"]):
        errs.append("dek: must hold the main number")
    srcs = fm.get("sources") or []
    if t not in ("chart", "movers", "list") and len(srcs) < 2:
        errs.append("sources: need at least two URLs")
    for mv in fm.get("moves") or []:
        if mv.get("ticker") not in universe:
            errs.append(f"moves: unknown ticker {mv.get('ticker')}")
        if not isinstance(mv.get("price"), (int, float)) or not isinstance(mv.get("change_pct"), (int, float)):
            errs.append(f"moves: {mv.get('ticker')} needs numeric price and change_pct")
    lo, hi = TYPES[t]
    n = words(body)
    if n < lo * 0.85 or n > hi * 1.25:
        errs.append(f"length: {n} words, the {t} range is {lo}-{hi}")
    elif not lo <= n <= hi:
        warns.append(f"length: {n} words, the {t} range is {lo}-{hi}")
    whole = (fm["title"] + " " + fm["dek"] + " " + body)
    low = whole.lower()
    for b in BANNED:
        if b in low:
            errs.append(f"banned phrase: {b!r}")
    if EMOJI.search(whole):
        errs.append("emoji found")
    if re.search(r"^# ", body, re.M):
        errs.append("body has an H1; start sections at ##")
    blocks = FENCE.findall(body)
    kinds = [k for k, _ in blocks]
    for kind, content in blocks:
        if kind == "chart":
            try:
                c = json.loads(content)
            except json.JSONDecodeError as e:
                errs.append(f"chart JSON: {e}")
                continue
            if c.get("kind") not in CHART_KINDS:
                errs.append(f"chart kind {c.get('kind')!r}")
            if not c.get("title"):
                errs.append("chart needs a title that states the insight")
            if c.get("kind") == "price":
                if not price_path(c.get("ticker", "")).exists():
                    errs.append(f"price chart: no price file for {c.get('ticker')}")
                for n in c.get("notes", []):
                    if not re.match(r"^\d{4}-\d\d-\d\d$", str(n.get("date", ""))) or not n.get("label"):
                        errs.append("price chart notes look like {\"date\": \"2026-10-29\", \"label\": \"Q3 results\"}")
                    elif len(n["label"]) > 28:
                        warns.append(f"price chart note {n['label']!r} is long; keep notes under 28 characters")
            elif c.get("kind") in ("compare", "moves"):
                for tk in c.get("tickers", []):
                    if not price_path(tk).exists():
                        errs.append(f"{c['kind']} chart: no price file for {tk}")
                if not c.get("tickers"):
                    errs.append(f"{c['kind']} chart needs tickers")
                if c.get("kind") == "moves" and not re.match(r"^\d{4}-\d\d-\d\d$", str(c.get("from", ""))):
                    errs.append("moves chart needs \"from\": \"YYYY-MM-DD\" (the close the change is measured from)")
            elif c.get("kind") not in COMPUTED and not c.get("source"):
                errs.append(f"{c.get('kind')} chart needs a source")
            if c.get("kind") in ("bars", "hbars"):
                if len(c.get("labels", [])) != len(c.get("values", [])):
                    errs.append("chart labels and values differ in length")
            if c.get("kind") == "line":
                for s in c.get("series", []):
                    if len(s.get("values", [])) != len(c.get("x", [])):
                        errs.append(f"line series {s.get('name')} length != x length")
        elif kind == "picks":
            for line in content.strip().splitlines():
                if ":" not in line:
                    errs.append("picks lines look like 'love: A, B, C'")
                    continue
                for tk in [x.strip() for x in line.split(":", 1)[1].split(",") if x.strip()]:
                    if tk not in universe:
                        errs.append(f"picks: {tk} not in the universe")
        elif kind == "stat":
            try:
                items = json.loads(content)
            except json.JSONDecodeError as e:
                errs.append(f"stat JSON: {e}")
                continue
            for it in (items if isinstance(items, list) else [items]):
                if not it.get("label"):
                    errs.append("stat needs a label")
                if not it.get("value") and not (it.get("ticker") in universe and it.get("metric") in ("day", "week", "month", "ytd")):
                    errs.append("stat needs a value, or a ticker plus metric (day, week, month or ytd) to compute it")
            if isinstance(items, list) and len(items) > 3:
                errs.append("stat: at most 3 numbers in a row")
        elif kind not in ("highlights",):
            errs.append(f"unknown fenced block ```{kind}")
    if t == "earnings-recap" and "highlights" not in kinds:
        errs.append("earnings-recap needs a ```highlights block")
    if t == "daily":
        # The thread: every ### is a take card, and each take carries one picture (a chart or big numbers).
        takes = re.split(r"^### ", FENCE.sub(lambda m: "```" + m.group(1) + "```", body), flags=re.M)[1:]
        if not 5 <= len(takes) <= 9:
            errs.append(f"daily: {len(takes)} takes (### headings); write 5 to 9")
        for tk in takes:
            head = tk.splitlines()[0]
            seg = tk.split("\n## ")[0]
            if "```chart```" not in seg and "```stat```" not in seg:
                errs.append(f"daily take {head!r} has no chart or stat block")
            if len(head) > 70:
                warns.append(f"daily take headline is long ({len(head)} chars): {head!r}")
        if not fm.get("cover_brief"):
            errs.append("daily needs a cover_brief (the scene for its AI cover)")
    if fm.get("cover_brief"):
        cb = re.sub(r"\bno (text|logos?|words|letters|faces|people)\b", "", fm["cover_brief"].lower())
        if len(cb) < 60:
            warns.append("cover_brief is short; describe one strong scene in a sentence or two")
        if re.search(r"\b(logo|text|words|letters|caption|headline|portrait of|photo of)\b", cb):
            errs.append("cover_brief must not ask for text, logos or a portrait: the art is symbolic, never a real person")
        if not fm.get("cover_alt"):
            errs.append("cover_brief needs a cover_alt (alt text describing the art)")
    for tag in re.findall(r"(?<![\w/])\$([A-Z]{1,5}(?:\.[A-Z])?)\b", body):
        if tag not in universe:
            errs.append(f"cashtag ${tag} not in the universe")
    if m:
        slug = m.group(2)
        key = (m.group(1), slug)
        if key in slugs and slugs[key] != path:
            errs.append(f"slug {slug} already used on {m.group(1)} by {slugs[key].name}")
        slugs[key] = path
    # Price sanity for the moves block: compare with our files on that date.
    for mv in fm.get("moves") or []:
        if mv.get("session") in ("regular", "close") and isinstance(mv.get("price"), (int, float)):
            day = ny_date(fm["published"])
            bars = [b for b in read_prices(mv["ticker"]) if b["date"] <= day]
            if bars and bars[-1]["date"] == day and abs(mv["price"] / bars[-1]["close"] - 1) > 0.01:
                warns.append(f"moves: {mv['ticker']} ${mv['price']} vs our close ${bars[-1]['close']} on {day}")
    return errs, warns


def main(argv: list[str]) -> int:
    universe = {u["ticker"] for u in json.loads((ROOT / "data/universe/universe.json").read_text())}
    authors = {a["id"] for a in json.loads((ROOT / "data/authors.json").read_text())}
    allfiles = sorted((ROOT / "content/articles").glob("*.md"))
    targets = [Path(a).resolve() for a in argv] if argv else allfiles
    slugs: dict = {}
    for f in allfiles:  # register existing slugs first
        mm = re.match(r"(\d{4}-\d{2}-\d{2})-([a-z0-9-]+)\.md$", f.name)
        if mm and f.resolve() not in targets:
            slugs[(mm.group(1), mm.group(2))] = f.resolve()
    bad = 0
    for f in targets:
        errs, warns = check_file(f, universe, authors, slugs)
        status = "FAIL" if errs else "ok"
        if errs or warns:
            print(f"{status}  {f.name}")
            for e in errs:
                print("   error:", e)
            for w in warns:
                print("   warn: ", w)
        bad += bool(errs)
    print(f"{len(targets) - bad}/{len(targets)} stories pass")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
