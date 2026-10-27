"""Find members, spans, posted loads and connection ends on drawing pages."""

import math
import re

import pymupdf

from . import geometry as geo
from .shapes import SHAPE_RE, family, normalize_text
from .textsrc import ocr_page, text_layer

_SPAN_RE = re.compile(r"\(\s*(\d+\s*['’′]\s*-?\s*\d*(?:\s+\d+\s*/\s*\d+)?\s*[\"”″]?)\s*\)")
_SHEAR_RE = re.compile(r"(?<![A-Z])(?:R|V|RXN|REACT(?:ION)?)\s*[=:]\s*(\d+(?:\.\d+)?)\s*K")
_AXIAL_RE = re.compile(r"(?<![A-Z])(P|T|C|AXIAL)\s*[=:]\s*([±+\-]?)\s*(\d+(?:\.\d+)?)\s*K")
_MOMENT_RE = re.compile(r"(?<![A-Z])M\s*[=:]\s*(\d+(?:\.\d+)?)\s*(?:K-?FT|FT-?K|K['’]|KIP-?FT)")
_BARE_K_RE = re.compile(r"^[\[(]?(\d+(?:\.\d+)?)\s*K(?:IPS?)?[\])]?$")
# beam legend tokens: R15 (each end reaction), A10 / A20/0 / A25K± (axial), M15/0 (end moments,
# left end / right end). Only read when the text holds nothing but a shape, these tokens and (HIGH)/(LOW).
_LEGEND_RE = re.compile(r"(?<![A-Z0-9./])([RAM])\s?(\d+(?:\.\d+)?)(?:\s?/\s?(\d+(?:\.\d+)?))?"
                        r"(?:\s?K(?:IPS?)?)?(?![\d./A-Z])")
_LEGEND_REST_RE = re.compile(r"\((?:HIGH|LOW)\)|[±�+\-\s(),]")


def select_pages(doc, keywords):
    hits = []
    for p in doc:
        t = p.get_text().upper()
        if any(k in t for k in keywords):
            hits.append(p.number)
    return hits or list(range(len(doc)))


def extract(doc, pages, cfg, scale_override=None, log=print, progress=None):
    """progress(page_no, done_tiles, total_tiles) is called during OCR."""
    """Return (connection rows, page info) for the given 0-based page numbers."""
    rows, info = [], []
    for pno in pages:
        page = doc[pno]
        rot = page.rotation
        if rot:
            page.set_rotation(0)        # work in unrotated space; restored by caller
        r, pi = _extract_page(page, cfg, scale_override, log, progress)
        if rot:
            page.set_rotation(rot)
        rows += r
        info.append(pi)
    return rows, info


def _extract_page(page, cfg, scale_override, log, progress=None):
    pno = page.number + 1
    texts = text_layer(page)
    has_callouts = any(SHAPE_RE.search(normalize_text(t.text)) for t in texts)
    used_ocr = cfg["ocr"] == "always" or (cfg["ocr"] == "auto" and not has_callouts)
    if used_ocr:
        log(f"  page {pno}: running OCR (no member text layer) ...")
        texts += _cached_ocr(page, cfg, progress)

    ppf = scale_override or geo.parse_scale(texts)           # points per foot
    scale_src = "override" if scale_override else ("drawing" if ppf else "assumed 1/8\"=1'-0\"")
    if not ppf:
        ppf = 9.0
    snap = cfg["snap_ft"] * ppf
    lines = geo.member_lines(page, cfg["heavy_line_width"], min_len=1.5 * ppf)
    cols = geo.column_symbols(page, cfg["heavy_line_width"], max_size=2.0 * ppf)
    excl = [re.compile(p) for p in cfg["exclude_patterns"]]

    # ---- member callouts ------------------------------------------------
    members = []
    # example callouts drawn in a legend block ("BEAM LEGEND" etc.) are not members
    legends = [pymupdf.Rect(t.rect.x0 - 20, t.rect.y0, t.rect.x0 + 400, t.rect.y1 + 250)
               for t in texts if re.search(r"\bLEGEND\b", t.text.upper())]
    for t in texts:
        if any(t.center in r for r in legends):
            continue
        norm = normalize_text(t.text)
        for m in SHAPE_RE.finditer(norm):
            shape = m.group(1)
            if any(e.search(shape) for e in excl):
                continue
            members.append(dict(shape=shape, item=t, raw=t.text))
    span_items = [t for t in texts if _SPAN_RE.search(t.text)]
    load_items = [t for t in texts if _parse_loads(t.text)]

    rows = []
    for k, mem in enumerate(members, 1):
        t = mem["item"]
        mid = f"P{pno}-{k:03d}"
        c = t.center
        h = max(t.height, 3.0)
        span_ft, span_src = _find_span(t, span_items, h)
        fam = family(mem["shape"])
        line = _find_line(t, lines, h, ppf)
        role = "BRACE" if fam in ("L", "2L", "WT") else "BEAM"
        if re.search(r"\b(CHORD|TC|BC|WEB|TRUSS)\b", t.text.upper()):
            role = "TRUSS"
        notes = []
        if line is not None:
            line.members.append((mid, mem["shape"], c))
            ang = line.angle
            if role == "BEAM" and min(ang % 90, 90 - ang % 90) > 10:
                role = "BRACE"
            ends = _find_ends(line, c, span_ft * ppf if span_ft else None, cols, lines, snap)
        else:
            notes.append("member line not found - locate manually")
            d = pymupdf.Point(0, 1) if t.vertical else pymupdf.Point(1, 0)
            half = (span_ft * ppf / 2) if span_ft else max(t.rect.width, t.rect.height) / 2
            ends = [(c - d * half, "UNKNOWN", None), (c + d * half, "UNKNOWN", None)]
        if span_ft is None and line is not None:
            span_ft = abs(ends[1][0] - ends[0][0]) / ppf
            span_src = "measured" + (" (scale assumed)" if scale_src.startswith("assumed") else "")
        for tag, (pt, sup, supline) in zip("AB", ends):
            rows.append(dict(
                conn_id=f"{mid}-{tag}", page=pno, member_id=mid, member=mem["shape"],
                callout=mem["raw"], role=role, end=tag, span_ft=_r(span_ft, 2),
                span_src=span_src or "", support_kind=sup, support="",
                _supline=supline, x=round(pt.x, 1), y=round(pt.y, 1),
                cx=round(c.x, 1), cy=round(c.y, 1),
                V_posted=None, Vz_posted=None, PT_posted=None, PC_posted=None, M_posted=None,
                category="", exclude="", notes="; ".join(notes), text_src=t.src,
            ))

    _resolve_supports(rows, lines)
    _assign_loads(rows, members, load_items, ppf)
    for r in rows:
        r.pop("_supline", None)
    info = dict(page=pno, ocr=used_ocr, scale_ppf=ppf, scale_src=scale_src,
                n_text=len(texts), n_members=len(members), n_lines=len(lines), n_cols=len(cols))
    log(f"  page {pno}: {len(members)} member callouts, {len(lines)} member lines, "
        f"{len(cols)} column symbols, scale {ppf / 72:.4g}\"=1'-0\" ({scale_src})")
    return rows, info


def _cached_ocr(page, cfg, progress=None):
    """OCR is slow (~1-2 min/sheet); cache results per file/page/dpi in the temp folder."""
    import hashlib
    import json
    import os
    import tempfile
    from .textsrc import TextItem
    # key on file content so a re-uploaded copy of the same drawings hits the cache
    doc = page.parent
    if not hasattr(doc, "_cg_hash"):
        if doc.name and os.path.exists(doc.name):
            with open(doc.name, "rb") as f:
                doc._cg_hash = hashlib.md5(f.read()).hexdigest()
        else:
            doc._cg_hash = hashlib.md5(doc.tobytes()).hexdigest()
    key = hashlib.md5(f"{doc._cg_hash}|{page.number}|{cfg['ocr_dpi']}|{cfg['ocr_min_conf']}"
                      .encode()).hexdigest()
    path = os.path.join(tempfile.gettempdir(), "lecgi_cg_ocr", key + ".json")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            return [TextItem(d["t"], pymupdf.Rect(d["r"]), d["v"], d["c"], "ocr", d.get("a"))
                    for d in json.load(f)]
    cb = (lambda k, n: progress(page.number + 1, k, n)) if progress else None
    items = ocr_page(page, dpi=cfg["ocr_dpi"], min_conf=cfg["ocr_min_conf"], progress=cb)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump([dict(t=i.text, r=list(i.rect), v=i.vertical, c=i.conf, a=i.angle) for i in items], f)
    return items


def _r(v, n):
    return None if v is None else round(v, n)


def _find_span(t, span_items, h):
    m = _SPAN_RE.search(t.text)
    if m:
        return geo.parse_ft_in(m.group(1)), "drawing"
    best, bd = None, 1e9
    c = t.center
    for s in span_items:
        sc = s.center
        if t.vertical != s.vertical:
            continue
        along, perp = (abs(sc.y - c.y), abs(sc.x - c.x)) if t.vertical else (abs(sc.x - c.x), abs(sc.y - c.y))
        length = t.rect.height if t.vertical else t.rect.width
        if perp < 3.2 * h and along < 0.6 * length + 2 * h and perp < bd:
            best, bd = s, perp
    if best:
        return geo.parse_ft_in(_SPAN_RE.search(best.text).group(1)), "drawing"
    return None, ""


def _find_line(t, lines, h, ppf):
    c = t.center
    want = t.ang
    best, bd = None, 1e9
    for ln in lines:
        dang = abs(ln.angle - want)
        dang = min(dang, 180 - dang)
        tt, perp = ln.project(c)
        if tt < -h or tt > ln.length + h:
            continue
        lim = max(4.0 * h, 1.0 * ppf) if dang < 5 else 1.5 * h
        score = abs(perp) + (0 if dang < 5 else 2 * h)
        if abs(perp) <= lim and score < bd and (dang < 5 or want in (0.0, 90.0)):
            best, bd = ln, score
    return best


def _find_ends(line, c, span_pt, cols, lines, snap):
    tc, _ = line.project(c)
    stops = [(0.0, "UNKNOWN", None), (line.length, "UNKNOWN", None)]
    for col in cols:
        tt, perp = line.project(col)
        if abs(perp) <= snap and -snap <= tt <= line.length + snap:
            stops.append((tt, "COL", None))
    for other in lines:
        if other is line:
            continue
        x = _intersect(line, other, snap)
        if x is None:
            continue
        t_here, s_other = x
        other_end = s_other < snap or s_other > other.length - snap
        this_end = t_here < snap or t_here > line.length - snap
        if other_end and not this_end:
            continue                      # the other member frames into this one
        stops.append((t_here, "BEAM", other))
    margin = 0.5 * snap
    left = [s for s in stops if s[0] < tc - margin] or [stops[0]]
    right = [s for s in stops if s[0] > tc + margin] or [stops[1]]
    rank = {"COL": 0, "BEAM": 1, "UNKNOWN": 2}
    if span_pt:
        best = None
        for a in left:
            for b in right:
                err = abs((b[0] - a[0]) - span_pt) + 0.25 * abs((a[0] + b[0]) / 2 - tc)
                if best is None or err < best[0]:
                    best = (err, a, b)
        _, a, b = best
        if abs((b[0] - a[0]) - span_pt) > 2 * snap:     # no stops match the span
            a = (tc - span_pt / 2, "UNKNOWN", None)
            b = (tc + span_pt / 2, "UNKNOWN", None)
    else:
        a = max(left, key=lambda s: (s[0], -rank[s[1]]))
        b = min(right, key=lambda s: (s[0], rank[s[1]]))
    # a column and a crossing line at the same spot -> column governs
    out = []
    for s in (a, b):
        same = [z for z in stops if abs(z[0] - s[0]) <= snap] or [s]
        s = min(same, key=lambda z: rank[z[1]]) if s[1] == "UNKNOWN" or s[1] == "BEAM" else s
        out.append((line.at(s[0]), s[1], s[2]))
    return out


def _intersect(l1, l2, tol):
    u, v = l1.unit, l2.unit
    den = u.x * v.y - u.y * v.x
    if abs(den) < 0.17:                      # < ~10 deg apart: parallel
        return None
    w = l2.p - l1.p
    t = (w.x * v.y - w.y * v.x) / den
    s = (w.x * u.y - w.y * u.x) / den
    if -tol <= t <= l1.length + tol and -tol <= s <= l2.length + tol:
        return t, s
    return None


def _resolve_supports(rows, lines):
    for r in rows:
        ln = r["_supline"]
        if r["support_kind"] == "BEAM" and ln is not None and ln.members:
            p = pymupdf.Point(r["x"], r["y"])
            mid, shape, _ = min(ln.members, key=lambda m: abs(m[2] - p))
            r["support"] = shape
            r["support_member"] = mid
        elif r["support_kind"] == "COL":
            r["support"] = "COLUMN"
        elif r["support_kind"] == "BEAM":
            r["support"] = "BEAM (size?)"


def _parse_loads(text):
    s = text.upper()
    out = {}
    m = _SHEAR_RE.search(s)
    if m:
        out["V"] = float(m.group(1))
    for m in _AXIAL_RE.finditer(s):
        kind, sign, val = m.group(1), m.group(2), float(m.group(3))
        if kind == "T" or sign == "+":
            out["PT"] = val
        elif kind == "C" or sign == "-":
            out["PC"] = val
        else:                                   # P= or ± -> both directions
            out["PT"] = out["PC"] = val
    m = _MOMENT_RE.search(s)
    if m:
        out["M"] = float(m.group(1))
    if not out:
        out = _parse_legend(s)
    if not out and len(s.strip()) <= 9:
        m = _BARE_K_RE.match(s.strip().replace(" ", ""))
        if m:
            out["V"] = float(m.group(1))
    return out


def _parse_legend(s):
    s = " ".join(w for w in s.upper().split() if not SHAPE_RE.fullmatch(normalize_text(w)))
    if _LEGEND_REST_RE.sub("", _LEGEND_RE.sub("", s)):
        return {}
    out = {}
    for kind, a, b in _LEGEND_RE.findall(s):
        ends = (float(a), float(b) if b else float(a))
        if kind == "R":
            out["V"] = max(ends)
        elif kind == "A":
            out["PT"] = out["PC"] = max(ends)
            out["A_ends"] = ends
        else:
            out["M"] = max(ends)
            out["M_ends"] = ends
    return out


def _is_vertical(rs):
    a, b = rs
    return abs(a["y"] - b["y"]) > abs(a["x"] - b["x"])


def _left_right(rs):
    """Two ends of one member -> (left end, right end) as read on the drawing
    (vertical members: bottom end is the left end of text reading upward)."""
    a, b = rs
    if abs(a["x"] - b["x"]) >= abs(a["y"] - b["y"]):
        return (a, b) if a["x"] <= b["x"] else (b, a)
    return (a, b) if a["y"] >= b["y"] else (b, a)


def _assign_loads(rows, members, load_items, ppf):
    by_member = {}
    for r in rows:
        by_member.setdefault(r["member_id"], []).append(r)
    radius = 4.0 * ppf
    for t in load_items:
        loads = _parse_loads(t.text)
        # load written in the callout itself applies to both ends
        own = [r for r in rows if r["callout"] == t.text and abs(r["cx"] - t.center.x) < 1
               and abs(r["cy"] - t.center.y) < 1]
        if own:
            targets = own
        elif _parse_legend(t.text):
            # legend loads (R15, A10, M15/0) belong to a whole member: nearest member running
            # the same way as the text
            cand = [(abs(pymupdf.Point(rs[0]["cx"], rs[0]["cy"]) - t.center), rs) for rs in by_member.values()
                    if len(rs) == 2 and _is_vertical(rs) == bool(t.vertical)]
            d, rs = min(cand, key=lambda n: n[0], default=(1e9, None))
            if d > radius:
                continue
            targets = rs
        else:
            c = t.center
            d_end, r_end = min(((abs(pymupdf.Point(r["x"], r["y"]) - c), r) for r in rows),
                               key=lambda n: n[0], default=(1e9, None))
            d_mem, r_mem = min(((abs(pymupdf.Point(r["cx"], r["cy"]) - c), r) for r in rows),
                               key=lambda n: n[0], default=(1e9, None))
            if min(d_end, d_mem) > radius:
                continue
            targets = by_member[r_mem["member_id"]] if d_mem < d_end else [r_end]
        per_end = {}
        if len(targets) == 2 and targets[0]["member_id"] == targets[1]["member_id"]:
            for k, cols in (("A_ends", ("PT", "PC")), ("M_ends", ("M",))):
                if k in loads:
                    for r, v in zip(_left_right(targets), loads[k]):
                        per_end.setdefault(r["conn_id"], {}).update({c: v for c in cols})
        for r in targets:
            for k, col in (("V", "V_posted"), ("PT", "PT_posted"), ("PC", "PC_posted"), ("M", "M_posted")):
                v = per_end.get(r["conn_id"], {}).get(k, loads.get(k))
                if v:
                    r[col] = max(r[col] or 0.0, v)
            r["notes"] = "; ".join(x for x in (r["notes"], f"posted: '{t.text}'") if x)
