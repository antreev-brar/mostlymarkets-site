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


class Renderer:
    def __init__(self, link_ticker: Callable[[str], str | None], url: Callable[[str], str],
                 blocks: dict[str, Callable[[str], str]]):
        self.link_ticker = link_ticker  # ticker -> href or None
        self.url = url                  # site path -> prefixed path
        self.blocks = blocks            # fenced block kind -> html
        self.headings: list[tuple[int, str, str]] = []

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
            p = BOLD.sub(r"<strong>\1</strong>", p)
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

    def render(self, text: str) -> str:
        lines = text.replace("\r\n", "\n").split("\n")
        out: list[str] = []
        i = 0
        para: list[str] = []

        def flush():
            if para:
                out.append(f"<p>{self.inline(' '.join(x.strip() for x in para))}</p>")
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
