"""Project defaults. Override any key with a JSON file passed via --config."""

import copy
import json

DEFAULTS = {
    "code": "AISC 360-22 (AISC Steel Construction Manual, 16th Ed.), LRFD",
    # --- load criteria -------------------------------------------------
    "udl_fraction": 0.5,          # fraction of beam max. total UDL capacity
    "min_shear_k": 10.0,          # minimum end reaction for any beam connection
    "hss_beam_shear_k": 15.0,     # HSS beams: Vy = Vz = this value unless posted
    "posted_load_minimum": True,  # posted loads are still raised to min_shear_k
    "brace_default": "ask",       # "ask" -> NEEDS INPUT when no axial load posted
    "moment_default": "ask",      # "ask" | "phiMp" (develop beam flexural strength)
    # --- yield strengths (ksi) used for the UDL capacity ---------------
    "fy": {"W": 50.0, "S": 36.0, "C": 36.0, "MC": 36.0, "M": 36.0},
    # --- general notes printed on the schedule -------------------------
    "materials": [
        "W shapes: ASTM A992",
        "Channels, angles, plates: ASTM A36",
        "Stiffener & doubler plates: ASTM A572 Gr. 50",
        "HSS: ASTM A500 Gr. B (verify against project specifications)",
    ],
    "bolts": '3/4" dia. ASTM F3125 Gr. A325-N, U.N.O.',
    "welds": "E70XX electrodes",
    "default_connection": "Beam connections are single-plate shear tabs U.N.O.; "
                          "HSS beams use end-plate/shear connections.",
    # --- extraction ----------------------------------------------------
    "ocr": "auto",                # "auto" | "always" | "never"
    "ocr_dpi": 200,
    "ocr_min_conf": 0.6,
    "page_keywords": ["FRAMING PLAN", "BRACING PLAN", "BRACING ELEVATION", "BRACED FRAME",
                      "FRAME ELEVATION", "TRUSS ELEVATION", "ROOF PLAN", "FLOOR PLAN",
                      "MEZZANINE PLAN", "PLATFORM PLAN"],
    "heavy_line_width": 0.9,      # pt; member lines drawn at least this heavy
    "snap_ft": 1.5,               # ft; end-to-support snapping distance
    "exclude_patterns": [r"^\d+K\d+$", r"^\d+KSP", r"^\d+LH\d+", r"^\d+DLH",
                         r"^\d+G\d+N"],   # joists / joist girders (by others)
    # --- annotation ----------------------------------------------------
    "label_fontsize": 12.0,       # connection numbers on the drawings (plain text along the member)
    "label_color": [0.0, 0.0, 1.0],
    "stamp_fontsize": 7.0,
    "group_by": "shape",          # "shape" (member + support size) | "depth"
}

CATEGORIES = {
    "BB": "Beam-to-Beam",
    "BC": "Beam-to-Column",
    "MBB": "Moment Beam-to-Beam",
    "MBC": "Moment Beam-to-Column",
    "BR": "Bracing",
    "TR": "Truss",
}
CATEGORY_ORDER = ["BB", "BC", "MBB", "MBC", "BR", "TR"]


def load_config(path=None):
    cfg = copy.deepcopy(DEFAULTS)
    if path:
        with open(path, encoding="utf-8") as f:
            user = json.load(f)
        for k, v in user.items():
            if isinstance(v, dict) and isinstance(cfg.get(k), dict):
                cfg[k].update(v)
            else:
                cfg[k] = v
    return cfg
