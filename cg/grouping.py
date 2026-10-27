"""Group similar connections and keep the worst-case loads of each group."""

from .config import CATEGORY_ORDER
from .shapes import family, nominal_depth, weight

# order of member families within a connection category (channels first, HSS after W)
FAMILY_ORDER = ["C", "MC", "W", "S", "WT", "HSS", "L", "2L"]


def _size_key(shape):
    fam = family(shape)
    return (FAMILY_ORDER.index(fam) if fam in FAMILY_ORDER else len(FAMILY_ORDER), fam,
            nominal_depth(shape), weight(shape), shape)


def mark_key(g):
    """Connection number key: beams share one number per family and nominal depth
    (e.g. all W8 beam-to-beam = BB03); braces and truss members are numbered per group."""
    if g["category"] in ("BR", "TR"):
        return (g["member"], g["support"])
    m = g["members"][0]
    return (family(m), nominal_depth(m))


def _posted(v):
    try:
        return v not in (None, "") and float(v) == float(v)
    except (TypeError, ValueError):
        return False


def group_key(r, mode):
    sup = r.get("support") or r.get("support_kind") or ""
    if mode == "depth":
        fam = family(r["member"])
        mem = f"{fam}{nominal_depth(r['member']):g}" if fam in ("W", "C", "MC", "S") else r["member"]
        sfam = family(sup)
        sup = f"{sfam}{nominal_depth(sup):g}" if sfam in ("W", "C", "MC", "S") else sup
        return (r["category"], mem, sup)
    return (r["category"], r["member"], sup)


def make_groups(rows, mode="shape"):
    """Return groups sorted by category / member size; sets row['mark']."""
    buckets = {}
    for r in rows:
        if str(r.get("exclude", "")).strip():
            r["mark"] = ""
            continue
        buckets.setdefault(group_key(r, mode), []).append(r)

    groups = []
    for (cat, mem, sup), rs in buckets.items():
        g = dict(category=cat, member=mem, support=sup, rows=rs, qty=len(rs),
                 members=sorted({r["member"] for r in rs}, key=_size_key),
                 supports=sorted({r.get("support") or r.get("support_kind") or "" for r in rs}))
        for k in ("V", "Vz", "PT", "PC", "M"):
            vals = [r[k] for r in rs if r.get(k) is not None]
            g[k] = max(vals) if vals else None
        # shear split for the summary: reaction shown on the drawings vs. not shown (rule / minimum)
        shown = [r["V"] for r in rs if r.get("V") is not None and _posted(r.get("V_posted"))]
        other = [r["V"] for r in rs if r.get("V") is not None and not _posted(r.get("V_posted"))]
        g["V_dwg"] = max(shown) if shown else None
        g["V_min"] = max(other) if other else None
        # governing connection = largest shear (or axial) in the group
        gov = max(rs, key=lambda r: ((r.get("V") or 0) + (r.get("PT") or 0) + (r.get("PC") or 0)
                                     + (r.get("M") or 0)))
        g["governing"] = gov["conn_id"]
        g["load_basis"] = gov.get("load_basis", "")
        # depth mode: design the lightest web in the group for the max load
        g["design_member"] = min(g["members"], key=lambda s: (weight(s) or 1e9)) if mode == "depth" else mem
        status = {r.get("status", "OK") for r in rs}
        g["status"] = "NEEDS INPUT" if "NEEDS INPUT" in status else ("VERIFY" if "VERIFY" in status else "OK")
        g["sheets"] = sorted({int(r["page"]) for r in rs if r.get("page") not in (None, "")})
        groups.append(g)

    groups.sort(key=lambda g: (CATEGORY_ORDER.index(g["category"]) if g["category"] in CATEGORY_ORDER else 99,
                               _size_key(g["members"][0]), _size_key(g["support"])))
    marks = {}
    for g in groups:
        key = (g["category"], mark_key(g))
        if key not in marks:
            marks[key] = f"{g['category']}{sum(1 for k in marks if k[0] == g['category']) + 1:02d}"
        g["mark"] = marks[key]
        for r in g["rows"]:
            r["mark"] = g["mark"]
    return groups
