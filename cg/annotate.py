"""Write connection numbers onto the drawing PDF.

Each mark is plain text next to the member end it belongs to, running along the member
(vertical members read bottom to top), e.g. "BC03 (HIGH)".
"""

import datetime
import re

import pymupdf

_LEVEL_RE = re.compile(r"\((HIGH|LOW)\)", re.I)


def _label(r):
    m = _LEVEL_RE.search(str(r.get("callout") or ""))
    return f"{r['mark']} ({m.group(1).upper()})" if m else r["mark"]


def _direction(r, other):
    """Unit vector from this end into the member."""
    e = pymupdf.Point(float(r["x"]), float(r["y"]))
    if other is not None:
        t = pymupdf.Point(float(other["x"]), float(other["y"]))
    else:
        t = pymupdf.Point(float(r.get("cx") or e.x), float(r.get("cy") or e.y))
    d = t - e
    return e, (pymupdf.Point(d.x / abs(d), d.y / abs(d)) if abs(d) > 1e-6 else pymupdf.Point(1, 0))


def _candidates(e, u, tw, fs):
    """(insert point, rotate, box) options: beside the member just inside the end, either side,
    sliding further along the member if the place is taken."""
    gap, inset = fs * 0.35, fs * 0.6
    asc, desc = fs * 0.8, fs * 0.22
    vertical = abs(u.y) > abs(u.x)
    for k in range(6):
        a = inset + k * (fs * 1.2)
        if not vertical:                                   # reads left to right
            x0 = e.x + a if u.x > 0 else e.x - a - tw
            for base in (e.y - gap - desc, e.y + gap + asc):   # above, below
                yield pymupdf.Point(x0, base), 0, pymupdf.Rect(x0, base - asc, x0 + tw, base + desc)
        else:                                              # rotated 90: reads bottom to top
            y0 = e.y - a if u.y < 0 else e.y + a + tw
            for base in (e.x - gap - desc, e.x + gap + asc):   # left, right of the line
                yield pymupdf.Point(base, y0), 90, pymupdf.Rect(base - asc, y0 - tw, base + desc, y0)


def _overlap(box, rects):
    """Overlapping area as a fraction of the box."""
    return sum(abs(box & q) for q in rects if box.intersects(q)) / max(abs(box), 1e-6)


def annotate(doc, rows, cfg, project="", log=print, checked_by=""):
    fs = cfg["label_fontsize"]
    color = tuple(cfg["label_color"])
    by_page, by_member = {}, {}
    for r in rows:
        if r.get("mark") and r.get("x") not in (None, "") and r.get("page") not in (None, ""):
            by_page.setdefault(int(r["page"]), []).append(r)
            by_member.setdefault(r.get("member_id"), []).append(r)

    for pno, rs in sorted(by_page.items()):
        page = doc[pno - 1]
        rot = page.rotation
        if rot:
            page.set_rotation(0)
        # keep clear of the drawing's own text as well as of other marks
        words = [pymupdf.Rect(w[:4]) for w in page.get_text("words")]
        placed = []
        for r in rs:
            other = next((o for o in by_member.get(r.get("member_id"), []) if o is not r), None)
            e, u = _direction(r, other)
            text = _label(r)
            tw = pymupdf.get_text_length(text, fontname="helv", fontsize=fs)
            half = abs(pymupdf.Point(float(other["x"]), float(other["y"])) - e) / 2 if other else 1e9

            def score(o):
                # least cluttered spot: other marks count most, then drawing text, then a label that
                # runs past mid-member (reads as the far end's mark), then distance from the end
                b = o[2]
                near = min((q - e).x * u.x + (q - e).y * u.y for q in (b.tl, b.tr, b.bl, b.br))
                return (10 * _overlap(b, placed) + 3 * _overlap(b, words)
                        + 4 * (near > half) + 0.003 * abs((b.tl + b.br) / 2 - e))

            pt, ang, box = min(_candidates(e, u, tw, fs), key=score)
            placed.append(box)
            page.insert_text(pt, text, fontname="helv", fontsize=fs, rotate=ang, color=color)
        _stamp(page, cfg["stamp_fontsize"], color, project, len(rs), checked_by)
        if rot:
            page.set_rotation(rot)
        log(f"  page {pno}: {len(rs)} connection marks")


def _stamp(page, fs, color, project, n, checked_by=""):
    lines = [
        "CONNECTION NUMBERS - LECGI",
        f"{project}".strip(),
        f"{n} connections marked on this sheet. See Connection Summary for loads.",
        f"Marks: BB beam-beam, BC beam-column, MBB/MBC moment, BR brace, TR truss. "
        f"Issued {datetime.date.today():%m/%d/%Y}",
        f"Checked by: {checked_by}" if checked_by else "",
    ]
    lines = [s for s in lines if s]
    w = max(pymupdf.get_text_length(s, fontname="helv", fontsize=fs) for s in lines) + 10
    h = len(lines) * fs * 1.3 + 6
    r = pymupdf.Rect(20, 20, 20 + w, 20 + h)
    page.draw_rect(r, color=color, fill=(1, 1, 1), width=0.8)
    for i, s in enumerate(lines):
        page.insert_text((r.x0 + 5, r.y0 + 3 + fs * (1.3 * i + 1)), s, fontname="hebo" if i == 0 else "helv",
                         fontsize=fs, color=color)
