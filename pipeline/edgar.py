"""SEC EDGAR: today's 8-K earnings releases (Item 2.02) and their press-release text (exhibit 99.1)."""
from __future__ import annotations

import html
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from marketdata import SEC_UA, get, now_et  # noqa: E402

FEED = ("https://www.sec.gov/cgi-bin/browse-edgar?action=getcurrent&type=8-K&company=&dateb=&owner=include"
        "&start={start}&count=100&output=atom")


def current_8k(pages: int = 4) -> list[dict]:
    """Recent 8-K filings, newest first: cik, company, accession, items, filed (ISO), index URL."""
    out, seen = [], set()
    for p in range(pages):
        s = get(FEED.format(start=p * 100), ua=SEC_UA, accept="application/atom+xml").decode("utf-8", "ignore")
        entries = re.findall(r"<entry>(.*?)</entry>", s, re.S)
        if not entries:
            break
        for e in entries:
            title = html.unescape(re.search(r"<title>(.*?)</title>", e, re.S).group(1))
            m = re.match(r"(8-K(?:/A)?) - (.*) \((\d{10})\)", title)
            if not m:
                continue
            link = re.search(r'<link[^>]*href="(.*?)"', e).group(1)
            summ = html.unescape(re.search(r"<summary[^>]*>(.*?)</summary>", e, re.S).group(1))
            acc = re.search(r"AccNo:</b>\s*([\d-]+)", summ)
            key = acc.group(1) if acc else link
            if key in seen:
                continue
            seen.add(key)
            out.append({"form": m.group(1), "company": m.group(2), "cik": m.group(3), "index": link,
                        "accession": acc.group(1) if acc else None,
                        "items": re.findall(r"Item (\d+\.\d+)", summ),
                        "filed": re.search(r"<updated>(.*?)</updated>", e).group(1)})
        if out and out[-1]["filed"][:10] < now_et().date().isoformat():
            break
    return out


def release_text(filing: dict, max_chars: int = 60000) -> tuple[str | None, str | None]:
    """The text of exhibit 99.1 (the earnings press release) and its URL."""
    cik = str(int(filing["cik"]))
    acc = filing["accession"].replace("-", "")
    base = f"https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/"
    try:
        idx = json.loads(get(base + "index.json", ua=SEC_UA))
    except Exception:  # noqa: BLE001
        return None, None
    names = [i["name"] for i in idx.get("directory", {}).get("item", [])]
    cands = [n for n in names if re.search(r"(ex|exhibit)[-_ ]?99[-_.]?0?1|ex991|exh991|99-1|991", n, re.I)
             and n.lower().endswith((".htm", ".html", ".txt"))]
    if not cands:
        cands = [n for n in names if re.search(r"99", n) and n.lower().endswith((".htm", ".html"))]
    if not cands:
        return None, None
    url = base + cands[0]
    raw = get(url, ua=SEC_UA, accept="text/html").decode("utf-8", "ignore")
    raw = re.sub(r"(?is)<(script|style).*?</\1>", " ", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</h\d>", "\n", raw)
    raw = re.sub(r"(?i)</td>", " | ", raw)
    text = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    text = re.sub(r"[ \t\xa0]+", " ", text)
    text = re.sub(r"\n\s*\n+", "\n\n", text).strip()
    return text[:max_chars], url
