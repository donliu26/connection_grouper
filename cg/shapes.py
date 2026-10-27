"""Shape properties and shape-name normalization.

The built-in table (d, tw, Zx in inches) covers common W and C shapes for the
50%-UDL calculation. For production use, load the official AISC Shapes Database
v16.0 (aisc.org, free download) with --aisc-db; it overrides the built-in table.
"""

import re

_BUILTIN = """
W8X10 7.89 .170 8.87|W8X13 7.99 .230 11.4|W8X15 8.11 .245 13.6|W8X18 8.14 .230 17.0
W8X21 8.28 .250 20.4|W8X24 7.93 .245 23.1|W8X28 8.06 .285 27.2|W8X31 8.00 .285 30.4
W8X35 8.12 .310 34.7|W8X40 8.25 .360 39.8|W8X48 8.50 .400 49.0|W8X58 8.75 .510 59.8
W8X67 9.00 .570 70.1|W10X12 9.87 .190 12.6|W10X15 9.99 .230 16.0|W10X17 10.1 .240 18.7
W10X19 10.2 .250 21.6|W10X22 10.2 .240 26.0|W10X26 10.3 .260 31.3|W10X30 10.5 .300 36.6
W10X33 9.73 .290 38.8|W10X39 9.92 .315 46.8|W10X45 10.1 .350 54.9|W10X49 10.0 .340 60.4
W10X54 10.1 .370 66.6|W10X60 10.2 .420 74.6|W12X14 11.9 .200 17.4|W12X16 12.0 .220 20.1
W12X19 12.2 .235 24.7|W12X22 12.3 .260 29.3|W12X26 12.2 .230 37.2|W12X30 12.3 .260 43.1
W12X35 12.5 .300 51.2|W12X40 11.9 .295 57.0|W12X45 12.1 .335 64.2|W12X50 12.2 .370 71.9
W12X53 12.1 .345 77.9|W12X58 12.2 .360 86.4|W12X65 12.1 .390 96.8|W12X72 12.3 .430 108
W12X79 12.4 .470 119|W12X87 12.5 .515 132|W12X96 12.7 .550 147|W14X22 13.7 .230 33.2
W14X26 13.9 .255 40.2|W14X30 13.8 .270 47.3|W14X34 14.0 .285 54.6|W14X38 14.1 .310 61.5
W14X43 13.7 .305 69.6|W14X48 13.8 .340 78.4|W14X53 13.9 .370 87.1|W14X61 13.9 .375 102
W14X68 14.0 .415 115|W14X74 14.2 .450 126|W14X82 14.3 .510 139|W14X90 14.0 .440 157
W16X26 15.7 .250 44.2|W16X31 15.9 .275 54.0|W16X36 15.9 .295 64.0|W16X40 16.0 .305 73.0
W16X45 16.1 .345 82.3|W16X50 16.3 .380 92.0|W16X57 16.4 .430 105|W16X67 16.3 .395 130
W16X77 16.5 .455 150|W16X89 16.8 .525 175|W16X100 17.0 .585 198|W18X35 17.7 .300 66.5
W18X40 17.9 .315 78.4|W18X46 18.1 .360 90.7|W18X50 18.0 .355 101|W18X55 18.1 .390 112
W18X60 18.2 .415 123|W18X65 18.4 .450 133|W18X71 18.5 .495 146|W18X76 18.2 .425 163
W18X86 18.4 .480 186|W18X97 18.6 .535 211|W21X44 20.7 .350 95.4|W21X48 20.6 .350 107
W21X50 20.8 .380 110|W21X55 20.8 .375 126|W21X57 21.1 .405 129|W21X62 21.0 .400 144
W21X68 21.1 .430 160|W21X73 21.2 .455 172|W21X83 21.4 .515 196|W21X93 21.6 .580 221
W24X55 23.6 .395 134|W24X62 23.7 .430 153|W24X68 23.7 .415 177|W24X76 23.9 .440 200
W24X84 24.1 .470 224|W24X94 24.3 .515 254|W24X104 24.1 .500 289|W27X84 26.7 .460 244
W27X94 26.9 .490 278|W27X102 27.1 .515 305|W27X114 27.3 .570 343|W30X90 29.5 .470 283
W30X99 29.7 .520 312|W30X108 29.8 .545 346|W30X116 30.0 .565 378|W33X118 32.9 .550 415
W33X130 33.1 .580 467|W36X135 35.6 .600 509|W36X150 35.9 .625 581
C6X8.2 6.00 .200 5.16|C6X10.5 6.00 .314 6.18|C6X13 6.00 .437 7.29|C8X11.5 8.00 .220 9.55
C8X13.75 8.00 .303 11.0|C8X18.75 8.00 .487 13.8|C10X15.3 10.0 .240 15.9|C10X20 10.0 .379 18.7
C10X25 10.0 .526 21.7|C10X30 10.0 .673 24.7|C12X20.7 12.0 .282 25.6|C12X25 12.0 .387 29.4
C12X30 12.0 .510 33.8|C15X33.9 15.0 .400 50.4|C15X40 15.0 .520 57.5|C15X50 15.0 .716 68.2
"""

SHAPE_RE = re.compile(
    r"(?<![A-Z0-9])("
    r"HSS\d+(?:\.\d+)?X\d+(?:\.\d+)?X(?:\d+/\d+|\.\d+|\d+(?:\.\d+)?)"   # rect HSS
    r"|HSS\d+(?:\.\d+)?X(?:\.\d+|\d+/\d+)"                             # round HSS
    r"|2L\d+(?:\.\d+)?X\d+(?:\.\d+)?X\d+/\d+(?:[A-Z]{3})?"
    r"|L\d+(?:\.\d+)?X\d+(?:\.\d+)?X\d+/\d+"
    r"|WT\d+(?:\.\d+)?X\d+(?:\.\d+)?"
    r"|MC\d+X\d+(?:\.\d+)?"
    r"|W\d{1,2}X\d{1,3}(?:\.\d+)?"
    r"|S\d{1,2}X\d+(?:\.\d+)?"
    r"|C\d{1,2}X\d+(?:\.\d+)?"
    r")(?![0-9])"
)


def normalize_text(s):
    """Upper-case, strip spaces and fix common OCR confusions in shape callouts."""
    s = s.upper().replace("×", "X").replace("*", "X").replace(" ", "")
    # W16K26 / W16x26 / W16-26 -> W16X26 (OCR often reads X as K)
    s = re.sub(r"(?<![A-Z0-9])(W|WT|MC|S|C)(\d{1,2})[K\-](\d)", r"\1\2X\3", s)
    s = re.sub(r"(?<![A-Z0-9])(HSS\d+(?:\.\d+)?)[K](\d)", r"\1X\2", s)
    return s


def family(label):
    m = re.match(r"(HSS|2L|L|WT|MC|W|S|C)", label)
    return m.group(1) if m else ""


def nominal_depth(label):
    m = re.match(r"(?:HSS|2L|L|WT|MC|W|S|C)(\d+(?:\.\d+)?)", label)
    return float(m.group(1)) if m else 0.0


def weight(label):
    m = re.search(r"X(\d+(?:\.\d+)?)$", label)
    return float(m.group(1)) if m and family(label) in ("W", "C", "MC", "S", "WT") else 0.0


class ShapeDB:
    def __init__(self):
        self.props = {}
        for rec in _BUILTIN.replace("\n", "|").split("|"):
            rec = rec.split()
            if len(rec) == 4:
                self.props[rec[0]] = dict(d=float(rec[1]), tw=float(rec[2]), Zx=float(rec[3]),
                                          source="built-in")

    def load_aisc_xlsx(self, path):
        """Load AISC Shapes Database (v15/v16 xlsx). US-unit columns are used."""
        import pandas as pd
        xl = pd.ExcelFile(path)
        sheet = next((s for s in xl.sheet_names if "database" in s.lower()), xl.sheet_names[0])
        df = xl.parse(sheet)
        n = 0
        for _, r in df.iterrows():
            lab = str(r.get("AISC_Manual_Label", "")).upper().replace(" ", "")
            try:
                d, tw, zx = float(r["d"]), float(r["tw"]), float(r["Zx"])
            except (KeyError, TypeError, ValueError):
                continue
            self.props[lab] = dict(d=d, tw=tw, Zx=zx, source="AISC DB")
            n += 1
        return n

    def get(self, label):
        return self.props.get(label)
