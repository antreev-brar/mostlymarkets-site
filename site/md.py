"""A small Markdown renderer for the story subset in docs/FORMAT.md. Standard library only."""
from __future__ import annotations

import html
import re
from typing import Callable

FENCE_OPEN = re.compile(r"^```(\w+)\s*$")
CASHTAG = re.compile(r"(?<![\w/&])\$([A-Z]{1,5}(?:\.[A-Z])?)\b")
LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
BOLD = re.compile(r"\*\*(.+?)\*\*")
ITAL = re.compile(r"(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])")


def esc(s: str) -> str:
    return html.escape(s, quote=True)


_NUM = r"(?:\$\d[\d,]*(?:\.\d+)?(?:\s(?:billion|million|trillion))?|\d[\d,]*(?:\.\d+)?%)"
_RANGE = _NUM + r"(?:\s?(?:to|–|-)\s?" + _NUM + r")?"
_MOVE = (r"\b(?:edged up|edged down|slipped|rose|fell|jumped|soared|slid|sank|plunged|tumbled|surged|climbed|dropped|"
         r"gained|lost|grew|declined|increased|shrank)\s+(?:about |nearly |more than |almost )?")
# In order of preference: a price move ("plunged 19.6%"), any change with its verb, then a bare figure or range.
FIGURES = [re.compile(_MOVE + r"\d[\d,]*(?:\.\d+)?%"), re.compile(_MOVE + _RANGE), re.compile(_RANGE)]
MDLINK = re.compile(r"\[[^\]]*\]\([^)]*\)")


def emphasize(text: str) -> str:
    """Bold the figure a paragraph is about (when it has no bold of its own): its price move if it has one,
    otherwise its first figure."""
    if "**" in text:
        return text
    spans = [m.span() for m in MDLINK.finditer(text)]
    for rx in FIGURES:
        for m in rx.finditer(text):
            if any(a <= m.start() < b for a, b in spans):
                continue
            return text[:m.start()] + "**" + m.group(0) + "**" + text[m.end():]
    return text


class Renderer:
    def __init__(self, link_ticker: Callable[[str], str | None], url: Callable[[str], str],
                 blocks: dict[str, Callable[[str], str]], takes: bool = False, page_url: str = ""):
        self.link_ticker = link_ticker  # ticker -> href or None
        self.url = url                  # site path -> prefixed path
        self.blocks = blocks            # fenced block kind -> html
        self.headings: list[tuple[int, str, str]] = []
        # Thread mode (daily editions): every ### opens a numbered take card that runs to the next heading.
        self.take_mode = takes
        self.page_url = page_url
        self.takes: list[dict] = []

    # ------------------------------------------------------------ inline
    def inline(self, s: str) -> str:
        links: list[str] = []

        def keep(h: str) -> str:
            links.append(h)
            return f"\x00{len(links) - 1}\x00"

        def link(m):
            text, href = m.group(1), m.group(2)
            if href.startswith("/"):
                href = self.url(href)
                return keep(f'<a href="{esc(href)}">{self.inline_plain(text)}</a>')
            return keep(f'<a href="{esc(href)}" rel="noopener" target="_blank">{self.inline_plain(text)}</a>')

        s = LINK.sub(link, s)

        def tag(m):
            t = m.group(1)
            href = self.link_ticker(t)
            if not href:
                return m.group(0)
            return keep(f'<a class="tk" href="{esc(href)}">{t}</a>')

        s = CASHTAG.sub(tag, s)
        s = self.inline_plain(s)
        return re.sub(r"\x00(\d+)\x00", lambda m: links[int(m.group(1))], s)

    def inline_plain(self, s: str) -> str:
        parts = re.split(r"(\x00\d+\x00)", s)
        out = []
        for p in parts:
            if p.startswith("\x00"):
                out.append(p)
                continue
            p = esc(p).replace("&#x27;", "’").replace("'", "’")
            p = re.sub(r"&quot;(?=\S)(.+?)(?<=\S)&quot;", r"“\1”", p)
            p = re.sub(r"(^|[\s(—–-])&quot;", r"\1“", p).replace("&quot;", "”")
            p = BOLD.sub(lambda m: f'<strong class="fig">{m.group(1)}</strong>' if re.search(r"\d", m.group(1)) else f"<strong>{m.group(1)}</strong>", p)
            p = ITAL.sub(r"<em>\1</em>", p)
            p = p.replace(" -- ", " – ")
            out.append(p)
        return "".join(out)

    # ------------------------------------------------------------ blocks
    def slug(self, text: str) -> str:
        base = re.sub(r"[^a-z0-9]+", "-", re.sub(r"<[^>]+>", "", text).lower()).strip("-")[:60] or "s"
        n, s = 2, base
        used = {h[1] for h in self.headings}
        while s in used:
            s, n = f"{base}-{n}", n + 1
        return s

    def _open_take(self, out: list[str], sid: str, h: str, total: int):
        n = len(self.takes) + 1
        plain = re.sub(r"<[^>]+>", "", h)
        self.takes.append({"id": sid, "n": n, "total": total, "title": html.unescape(plain), "start": len(out) + 1})
        out.append(f'<article class="take" id="{sid}"><div class="tk-n">{n}<i>/{total}</i></div><h3>{h}</h3>')

    def _close_take(self, out: list[str]):
        if not self.takes or "end" in self.takes[-1]:
            return
        tk = self.takes[-1]
        tk["end"] = len(out)
        tk["body"] = out[tk["start"]:tk["end"]]
        link = f"{self.page_url}#{tk['id']}"
        from urllib.parse import quote
        x = f"https://x.com/intent/post?text={quote(tk['title'])}&url={quote(link, safe='')}"
        out.append(f'<footer class="tk-ft"><button type="button" class="tk-b" data-copy="{esc(link)}">Copy link</button>'
                   f'<a class="tk-b" href="{esc(x)}" target="_blank" rel="noopener">Post on X</a></footer></article>')

    def render(self, text: str) -> str:
        lines = text.replace("\r\n", "\n").split("\n")
        out: list[str] = []
        i = 0
        para: list[str] = []
        total, fenced = 0, False
        for ln in lines:
            if ln.strip().startswith("```"):
                fenced = not fenced
            elif not fenced and ln.strip().startswith("### "):
                total += 1

        emph = [True]  # the next paragraph opens the story or a section

        def flush():
            if para:
                text = " ".join(x.strip() for x in para)
                if emph[0]:
                    text = emphasize(text)
                    emph[0] = False
                out.append(f"<p>{self.inline(text)}</p>")
                para.clear()

        while i < len(lines):
            line = lines[i]
            m = FENCE_OPEN.match(line.strip())
            if m:
                flush()
                kind, body = m.group(1), []
                i += 1
                while i < len(lines) and lines[i].strip() != "```":
                    body.append(lines[i])
                    i += 1
                i += 1
                fn = self.blocks.get(kind)
                out.append(fn("\n".join(body)) if fn else f"<pre>{esc(chr(10).join(body))}</pre>")
                continue
            s = line.strip()
            if not s:
                flush()
                i += 1
                continue
            if s.startswith("### ") or s.startswith("## "):
                flush()
                level = 3 if s.startswith("### ") else 2
                txt = s[level + 1:].strip()
                h = self.inline(txt)
                sid = self.slug(h)
                self.headings.append((level, sid, re.sub(r"<[^>]+>", "", h)))
                emph[0] = True
                if self.take_mode:
                    self._close_take(out)
                    if level == 3:
                        self._open_take(out, sid, h, total)
                        i += 1
                        continue
                out.append(f'<h{level} id="{sid}">{h}</h{level}>')
                i += 1
                continue
            if s in ("---", "***"):
                flush()
                out.append("<hr>")
                i += 1
                continue
            if s.startswith(">"):
                flush()
                q = []
                while i < len(lines) and lines[i].strip().startswith(">"):
                    q.append(lines[i].strip()[1:].strip())
                    i += 1
                out.append(f"<blockquote><p>{self.inline(' '.join(q))}</p></blockquote>")
                continue
            if re.match(r"^[-*] ", s) or re.match(r"^\d+[.)] ", s):
                flush()
                ordered = bool(re.match(r"^\d+[.)] ", s))
                items: list[str] = []
                while i < len(lines):
                    t = lines[i].strip()
                    if ordered and re.match(r"^\d+[.)] ", t):
                        items.append(re.sub(r"^\d+[.)] ", "", t))
                    elif not ordered and re.match(r"^[-*] ", t):
                        items.append(t[2:])
                    elif t and items and lines[i].startswith(("  ", "\t")):
                        items[-1] += " " + t
                    else:
                        break
                    i += 1
                tagname = "ol" if ordered else "ul"
                out.append(f"<{tagname}>" + "".join(f"<li>{self.inline(x)}</li>" for x in items) + f"</{tagname}>")
                continue
            if s.startswith("|"):
                flush()
                rows = []
                while i < len(lines) and lines[i].strip().startswith("|"):
                    rows.append(lines[i].strip())
                    i += 1
                out.append(self.table(rows))
                continue
            para.append(line)
            i += 1
        flush()
        if self.take_mode:
            self._close_take(out)
        return "\n".join(out)

    def table(self, rows: list[str]) -> str:
        def cells(r):
            return [c.strip() for c in r.strip().strip("|").split("|")]
        if len(rows) < 2:
            return ""
        head = cells(rows[0])
        aligns = []
        body_rows = rows[1:]
        if re.match(r"^\|?\s*:?-{2,}", rows[1]):
            for c in cells(rows[1]):
                aligns.append("r" if c.endswith(":") and not c.startswith(":") else "")
            body_rows = rows[2:]
        num = re.compile(r"^[−+\-$]?[\d,.]+[%x]?$|^[▲▼]")

        def cls(j, v):
            if (j < len(aligns) and aligns[j] == "r") or (j > 0 and num.match(v.replace("**", ""))):
                return ' class="n"'
            return ""
        h = "".join(f"<th{cls(j, '1' if j else '')}>{self.inline(c)}</th>" for j, c in enumerate(head))
        b = ""
        for r in body_rows:
            cs = cells(r)
            tds = []
            for j, c in enumerate(cs):
                inner = self.inline(c)
                tone = ""
                if j > 0 and re.match(r"^[−\-]\d", c.replace("**", "")):
                    tone = " down"
                elif j > 0 and re.match(r"^\+\d", c.replace("**", "")):
                    tone = " up"
                k = cls(j, c)
                if tone:
                    k = f' class="n{tone}"'
                tds.append(f"<td{k}>{inner}</td>")
            b += "<tr>" + "".join(tds) + "</tr>"
        return f'<div class="tbl"><table><thead><tr>{h}</tr></thead><tbody>{b}</tbody></table></div>'
