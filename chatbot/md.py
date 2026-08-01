"""A very small Markdown subset renderer.

Supports exactly what the knowledge base and the flow messages need:
paragraphs, ``- `` bullets, ``1. `` ordered lists, pipe tables, ``**bold**``,
``*italic*``, ``[text](url)`` links and hard line breaks.

Everything is HTML-escaped first, so user supplied text can safely be
interpolated into a message before rendering.
"""

from __future__ import annotations

import html
import re

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_ITALIC = re.compile(r"(?<!\*)\*(?!\s)([^*]+?)(?<!\s)\*(?!\*)")
_LINK = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
_ORDERED = re.compile(r"^(\d+)[.)]\s+(.*)$")
_BULLET = re.compile(r"^[-*•]\s+(.*)$")
_TABLE_SEP = re.compile(r"^\|?\s*:?-{2,}:?\s*(\|\s*:?-{2,}:?\s*)+\|?$")


def _inline(text: str) -> str:
    out = html.escape(text, quote=False)
    out = _LINK.sub(r'<a href="\2" target="_blank" rel="noopener">\1</a>', out)
    out = _BOLD.sub(r"<strong>\1</strong>", out)
    out = _ITALIC.sub(r"<em>\1</em>", out)
    return out


def _split_row(line: str) -> list[str]:
    line = line.strip()
    if line.startswith("|"):
        line = line[1:]
    if line.endswith("|"):
        line = line[:-1]
    return [cell.strip() for cell in line.split("|")]


def render(text: str) -> str:
    """Render a markdown subset into an HTML fragment."""
    lines = (text or "").replace("\r\n", "\n").split("\n")
    out: list[str] = []
    i = 0
    n = len(lines)

    while i < n:
        line = lines[i]
        stripped = line.strip()

        if not stripped:
            i += 1
            continue

        # --- table -------------------------------------------------------
        if "|" in stripped and i + 1 < n and _TABLE_SEP.match(lines[i + 1].strip()):
            header = _split_row(stripped)
            i += 2
            rows: list[list[str]] = []
            while i < n and "|" in lines[i] and lines[i].strip():
                rows.append(_split_row(lines[i]))
                i += 1
            out.append('<div class="md-table-wrap"><table class="md-table"><thead><tr>')
            out.extend(f"<th>{_inline(c)}</th>" for c in header)
            out.append("</tr></thead><tbody>")
            for row in rows:
                out.append("<tr>")
                out.extend(f"<td>{_inline(c)}</td>" for c in row)
                out.append("</tr>")
            out.append("</tbody></table></div>")
            continue

        # --- ordered list ------------------------------------------------
        if _ORDERED.match(stripped):
            out.append("<ol>")
            while i < n and _ORDERED.match(lines[i].strip()):
                out.append(f"<li>{_inline(_ORDERED.match(lines[i].strip()).group(2))}</li>")
                i += 1
            out.append("</ol>")
            continue

        # --- bullet list -------------------------------------------------
        if _BULLET.match(stripped):
            out.append("<ul>")
            while i < n and _BULLET.match(lines[i].strip()):
                out.append(f"<li>{_inline(_BULLET.match(lines[i].strip()).group(1))}</li>")
                i += 1
            out.append("</ul>")
            continue

        # --- paragraph (consecutive plain lines become one <p>) ----------
        buf: list[str] = []
        while i < n:
            cur = lines[i].strip()
            if (
                not cur
                or _BULLET.match(cur)
                or _ORDERED.match(cur)
                or ("|" in cur and i + 1 < n and _TABLE_SEP.match(lines[i + 1].strip()))
            ):
                break
            buf.append(_inline(cur))
            i += 1
        out.append("<p>" + "<br>".join(buf) + "</p>")

    return "".join(out)
