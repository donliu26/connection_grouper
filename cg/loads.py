"""Connection categories and design loads (LRFD, AISC 360-22).

Beam end shear when no load is posted on the drawings:
    W_c   = min(8*phiMp/L, 2*phiVn)          max. total uniform load (Manual Table 3-6 basis)
    phiMp = 0.90*Fy*Zx                        (F2.1, full lateral support assumed)
    phiVn = phi_v*0.6*Fy*(d*tw)*Cv1           (G2.1; phi_v = 1.0, Cv1 = 1.0 for rolled W
                                               meeting G2.1(a); phi_v = 0.9 otherwise)
    R     = max(udl_fraction * W_c / 2, min_shear)
"""

from .shapes import family


def classify(r):
    """Fill the category from role + support unless the reviewer already set it."""
    if r.get("category"):
        return r["category"]
    role = r.get("role", "BEAM")
    if role == "BRACE":
        return "BR"
    if role == "TRUSS":
        return "TR"
    moment = role == "MOMENT" or (role == "BEAM" and bool(_num(r.get("M_posted"))))
    if r.get("support_kind") == "BEAM":
        return "MBB" if moment else "BB"
    return "MBC" if moment else "BC"


def udl_capacity(shape, span_ft, db, cfg):
    """Return (W_c kips, phiMp k-ft, phiVn k, governing) or None if not computable."""
    p = db.get(shape)
    fam = family(shape)
    fy = cfg["fy"].get(fam)
    if not p or not fy or not span_ft:
        return None
    phi_mp = 0.9 * fy * p["Zx"] / 12.0                      # k-ft
    phi_v = 1.0 if fam == "W" else 0.9
    phi_vn = phi_v * 0.6 * fy * p["d"] * p["tw"]            # k
    w_m = 8.0 * phi_mp / span_ft
    w_v = 2.0 * phi_vn
    return (min(w_m, w_v), phi_mp, phi_vn, "flexure" if w_m < w_v else "shear")


def _src(r):
    """Loads read off the drawings carry a 'posted:' note; anything else was typed in."""
    return "posted on drawings" if "posted:" in str(r.get("notes") or "") else "entered by engineer"


def design_loads(r, db, cfg):
    """Set V, Vz, PT, PC, M, load_basis and status on a connection row."""
    cat = r["category"]
    fam = family(r["member"])
    vmin = cfg["min_shear_k"]
    r.update(V=None, Vz=None, PT=None, PC=None, M=None, load_basis="", status="OK")
    basis = []

    if cat in ("BB", "BC", "MBB", "MBC"):
        if _num(r.get("V_posted")):
            v = float(r["V_posted"])
            if cfg["posted_load_minimum"] and v < vmin:
                basis.append(f"posted {v:g}k < min -> {vmin:g}k")
                v = vmin
            else:
                basis.append(_src(r))
            r["V"] = v
            if fam == "HSS":
                r["Vz"] = _num(r.get("Vz_posted")) or v
        elif fam == "HSS":
            r["V"] = r["Vz"] = cfg["hss_beam_shear_k"]
            basis.append(f"HSS beam default Vy=Vz={cfg['hss_beam_shear_k']:g}k")
        else:
            cap = udl_capacity(r["member"], _num(r.get("span_ft")), db, cfg)
            if cap:
                w_c, phi_mp, phi_vn, gov = cap
                v = cfg["udl_fraction"] * w_c / 2.0
                basis.append(f"{cfg['udl_fraction']:.0%} UDL: Wc={w_c:.1f}k ({gov}), L={float(r['span_ft']):.2f}ft")
                if v < vmin:
                    basis.append(f"min {vmin:g}k governs")
                    v = vmin
                r["V"] = round(v, 1)
            else:
                why = "span unknown" if not _num(r.get("span_ft")) else f"no properties for {r['member']}"
                r["status"] = "NEEDS INPUT"
                basis.append(f"shear needed ({why})")
        if cat in ("MBB", "MBC"):
            if _num(r.get("M_posted")):
                r["M"] = float(r["M_posted"])
                basis.append("M " + _src(r))
            elif cfg["moment_default"] == "phiMp":
                cap = udl_capacity(r["member"], 1.0, db, cfg)
                if cap:
                    r["M"] = round(cap[1], 1)
                    basis.append("M = phiMp of beam")
            if r["M"] is None:
                r["status"] = "NEEDS INPUT"
                basis.append("moment needed")
        if _num(r.get("PT_posted")) or _num(r.get("PC_posted")):
            r["PT"] = _num(r.get("PT_posted"))
            r["PC"] = _num(r.get("PC_posted"))
            basis.append("axial " + _src(r))

    else:                                        # BR, TR
        r["PT"] = _num(r.get("PT_posted"))
        r["PC"] = _num(r.get("PC_posted"))
        if _num(r.get("V_posted")):
            r["V"] = float(r["V_posted"])
        if r["PT"] is None and r["PC"] is None:
            r["status"] = "NEEDS INPUT"
            basis.append("axial load needed (not posted)")
        else:
            basis.append(_src(r))

    if r.get("support_kind") == "UNKNOWN" and cat not in ("BR", "TR"):
        r["status"] = "VERIFY" if r["status"] == "OK" else r["status"]
        basis.append("support not identified")
    r["load_basis"] = "; ".join(basis)
    return r


def _num(v):
    try:
        if v is None or v == "" or (isinstance(v, float) and v != v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None
