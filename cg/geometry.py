"""Vector geometry from a drawing page: member lines, column symbols, scale."""

import math
import re
from dataclasses import dataclass, field

import pymupdf


@dataclass
class Line:
    p: pymupdf.Point
    q: pymupdf.Point
    width: float
    dashed: bool
    members: list = field(default_factory=list)   # member ids lying on this line

    @property
    def length(self):
        return abs(self.q - self.p)

    @property
    def unit(self):
        d = self.q - self.p
        L = abs(d) or 1.0
        return pymupdf.Point(d.x / L, d.y / L)

    def project(self, pt):
        """(t along line from p, signed perpendicular distance)."""
        u = self.unit
        v = pt - self.p
        return v.x * u.x + v.y * u.y, v.x * -u.y + v.y * u.x

    def at(self, t):
        u = self.unit
        return pymupdf.Point(self.p.x + u.x * t, self.p.y + u.y * t)

    @property
    def angle(self):
        u = self.unit
        return math.degrees(math.atan2(u.y, u.x)) % 180.0


def _raw_segments(page):
    for dr in page.get_drawings():
        color = dr.get("color")
        if color is None or (min(color) > 0.9):    # unstroked or white (text masks)
            continue
        w = dr.get("width") or 0.0
        dashed = str(dr.get("dashes", "[] 0")).strip() not in ("[] 0", "None", "")
        for it in dr["items"]:
            if it[0] == "l":
                yield it[1], it[2], w, dashed
            elif it[0] == "re":
                r = it[1]
                for a, b in ((r.tl, r.tr), (r.tr, r.br), (r.br, r.bl), (r.bl, r.tl)):
                    yield a, b, w, dashed


def member_lines(page, heavy_width, min_len, gap_tol=8.0):
    """Merge collinear heavy (or dashed-heavy) segments into member lines."""
    buckets = {}
    for a, b, w, dashed in _raw_segments(page):
        if w < heavy_width or abs(b - a) < 2.0:
            continue
        ang = math.atan2(b.y - a.y, b.x - a.x)
        if ang < 0:
            ang += math.pi
        if ang >= math.pi - 1e-9:
            ang = 0.0
        ux, uy = math.cos(ang), math.sin(ang)
        off = -uy * a.x + ux * a.y
        key = (round(math.degrees(ang) / 0.5), round(off / 1.0))
        t0, t1 = sorted((a.x * ux + a.y * uy, b.x * ux + b.y * uy))
        buckets.setdefault(key, []).append((t0, t1, w, dashed, ang, off))
    lines = []
    for segs in buckets.values():
        segs.sort()
        cur = list(segs[0])
        for s in segs[1:]:
            if s[0] <= cur[1] + gap_tol:
                cur[1] = max(cur[1], s[1])
                cur[2] = max(cur[2], s[2])
            else:
                lines.append(cur)
                cur = list(s)
        lines.append(cur)
    out = []
    for t0, t1, w, dashed, ang, off in lines:
        if t1 - t0 < min_len:
            continue
        ux, uy = math.cos(ang), math.sin(ang)
        nx, ny = -uy, ux
        p = pymupdf.Point(t0 * ux + off * nx, t0 * uy + off * ny)
        q = pymupdf.Point(t1 * ux + off * nx, t1 * uy + off * ny)
        out.append(Line(p, q, w, dashed))
    return out


def column_symbols(page, heavy_width, max_size, min_size=3.0):
    """Clusters of short heavy strokes / small filled shapes = column symbols."""
    rects = []
    for dr in page.get_drawings():
        r = dr["rect"]
        if r.width > max_size or r.height > max_size:
            continue
        filled = dr.get("fill") is not None and min(dr["fill"]) < 0.5
        heavy = (dr.get("width") or 0) >= heavy_width and dr.get("color") is not None \
            and min(dr["color"]) < 0.5
        if filled or heavy:
            rects.append(pymupdf.Rect(r))
    # cluster touching rects
    clusters = []
    for r in rects:
        g = pymupdf.Rect(r) + (-1.5, -1.5, 1.5, 1.5)
        hit = [c for c in clusters if c.intersects(g)]
        for c in hit:
            clusters.remove(c)
            g |= c
        clusters.append(g)
    cols = []
    for c in clusters:
        w, h = c.width - 3, c.height - 3
        if min_size <= w <= max_size and min_size <= h <= max_size and 0.4 < w / max(h, 1e-6) < 2.5:
            cols.append((c.tl + c.br) / 2)
    return cols


_SCALE_RE = re.compile(r"(\d+(?:\s*\d+)?/\d+|\d+(?:\.\d+)?)\s*[\"”″'']{1,2}\s*=\s*1\s*['’′]\s*-?\s*0?")


def parse_scale(texts):
    """Return paper points per real foot from the most common 'x" = 1'-0"' note."""
    from collections import Counter
    found = Counter()
    for t in texts:
        s = t.text.upper().replace("''", '"')
        for m in _SCALE_RE.finditer(s):
            v = _frac(m.group(1))
            if v and 0.01 < v <= 3:
                found[v] += 1
    if not found:
        return None
    inches = found.most_common(1)[0][0]
    return inches * 72.0


def scale_from_arg(s):
    """'3/16' or '1/8' (inches per foot) or '1:96' -> points per foot."""
    s = s.strip()
    if ":" in s:
        a, b = s.split(":")
        return 72.0 * 12.0 * float(a) / float(b)
    return _frac(s) * 72.0


def _frac(s):
    s = s.replace('"', "").strip()
    try:
        if " " in s.strip():
            w, f = s.split()
            return float(w) + _frac(f)
        if "/" in s:
            a, b = s.split("/")
            return float(a) / float(b)
        return float(s)
    except (ValueError, ZeroDivisionError):
        return None


_FTIN_RE = re.compile(r"(\d+)\s*['’′]\s*-?\s*(\d+)?(?:\s+(\d+)\s*/\s*(\d+))?\s*[\"”″]?")


def parse_ft_in(s):
    """"20'-5 1/2\"" -> 20.458 ft."""
    m = _FTIN_RE.search(s)
    if not m:
        return None
    ft = float(m.group(1))
    inch = float(m.group(2) or 0)
    if m.group(3):
        inch += float(m.group(3)) / float(m.group(4))
    return ft + inch / 12.0
