# -*- coding: utf-8 -*-
"""
Simbologi keluaran (murni Python, tanpa QGIS). Satu spesifikasi dipakai untuk:
simbologi layer di QGIS, legenda peta standar, dan tabel di Excel/PDF.

Spesifikasi:
  {"type": "discrete", "items": [{"upper": x, "color": "#rrggbb", "label": "..."}], "title": "...", "unit": "..."}
  {"type": "paletted", "items": [{"value": k, "color": "#rrggbb", "label": "..."}], ...}
  {"type": "gray", "vmin": a, "vmax": b, ...}
"""
import math

import numpy as np
from .i18n import tr

from . import core_terrain as T

RAMPS = {
    "elev": ["#2e7d32", "#7cb342", "#d4e157", "#f5deb3", "#c8a165", "#8d6e63", "#f2f2f2"],
    "blues": ["#eaf3fb", "#c6dcf0", "#93c0e4", "#5a9fd4", "#2f78bc", "#17509a", "#08306b"],
    "wet": ["#fff7d6", "#d9ecb0", "#8fd1b0", "#4fb0c6", "#2b83c4", "#2a4fa8", "#241a7a"],
    "ylorrd": ["#ffffb2", "#fee08b", "#fdae61", "#f46d43", "#d73027", "#a50026", "#67001f"],
    "greens": ["#f1f8e9", "#c5e1a5", "#9ccc65", "#66bb6a", "#2e9e55", "#1b7a40", "#0d4f28"],
    "viridis": ["#fde725", "#b5de2b", "#6ece58", "#35b779", "#1f9e89", "#26828e", "#3e4a89", "#482173"],
    "div": ["#2b5c9e", "#6fa0cf", "#bcd7ee", "#f2f2f2", "#f7c9a8", "#e8854f", "#b8431f"],
    "purples": ["#f3eef8", "#d9cde9", "#b9a4d6", "#9577c1", "#7650a8", "#552b8c", "#331464"],
    "browns": ["#fbf3e0", "#ecd9a8", "#d9b878", "#c0914c", "#9c6b30", "#744a1f", "#4a2c12"],
}

# lima kelas indeks komposit (sangat rendah ... sangat tinggi)
INDEX_LABELS = ["Sangat rendah", "Rendah", "Sedang", "Tinggi", "Sangat tinggi"]  # translated at use
INDEX_COLORS = {
    "flood": ["#2e9e55", "#a8d86a", "#ffe55c", "#f28c38", "#c62828"],
    "erosion": ["#2e9e55", "#a8d86a", "#ffe55c", "#f28c38", "#c62828"],
    "recharge": ["#c62828", "#f28c38", "#ffe55c", "#6bb6d8", "#1a5fa8"],
}
DIR8 = ["#d32f2f", "#f57c00", "#fbc02d", "#7cb342", "#00897b", "#1e88e5", "#5e35b1", "#c2185b"]
ORDER_COLORS = ["#8ecae6", "#4aa3d6", "#1f78b4", "#0b4f9c", "#08306b", "#041c42", "#020d24"]
ORDER_WIDTH = [0.25, 0.45, 0.75, 1.1, 1.5, 2.0, 2.6]


def hexc(rgb):
    return "#%02x%02x%02x" % tuple(int(v) for v in rgb)


def lerp_ramp(ramp, n):
    """Ambil n warna merata dari daftar warna ramp (interpolasi linear)."""
    cols = [tuple(int(c[i:i + 2], 16) for i in (1, 3, 5)) for c in ramp]
    out = []
    for i in range(n):
        t = 0.0 if n == 1 else i / (n - 1)
        x = t * (len(cols) - 1)
        j = min(int(x), len(cols) - 2)
        f = x - j
        out.append(hexc([cols[j][k] * (1 - f) + cols[j + 1][k] * f for k in range(3)]))
    return out


def fmtnum(v, nd=None):
    if v is None or not np.isfinite(v):
        return "-"
    a = abs(v)
    if nd is None:
        nd = 0 if a >= 100 else 1 if a >= 10 else 2 if a >= 1 else 3
    s = f"{v:,.{nd}f}"
    if "." in s and nd > 0:
        s = s.rstrip("0").rstrip(".")
    return s.replace(",", " ") if a >= 10000 else s


def nice_step(raw):
    if raw <= 0 or not np.isfinite(raw):
        return 1.0
    e = math.floor(math.log10(raw))
    f = raw / 10 ** e
    for m in (1, 2, 2.5, 5, 10):
        if f <= m:
            return m * 10 ** e
    return 10 ** (e + 1)


def breaks_nice(a, n=6, lo_pct=2, hi_pct=98):
    v = a[np.isfinite(a)]
    if not v.size:
        return [0.0]
    lo, hi = np.percentile(v, [lo_pct, hi_pct])
    if hi - lo < 1e-12:
        hi = lo + 1.0
    st = nice_step((hi - lo) / n)
    b0 = math.floor(lo / st) * st
    bs = [round(b0 + st * (i + 1), 10) for i in range(n + 2) if b0 + st * (i + 1) < hi + st]
    bs = [x for x in bs if x > lo][:n]
    return bs or [float(np.median(v))]


def breaks_log(a, n=6, floor=None):
    v = a[np.isfinite(a) & (a > 0)]
    if not v.size:
        return [1.0]
    lo = floor if floor else float(np.percentile(v, 2))
    hi = float(np.percentile(v, 99.5))
    e0 = math.floor(math.log10(max(lo, 1e-12)))
    e1 = math.ceil(math.log10(max(hi, lo * 1.01)))
    cand = []
    for e in range(e0, e1 + 1):
        for m in (1, 3):
            cand.append(m * 10.0 ** e)
    cand = [c for c in cand if lo <= c <= hi]
    while len(cand) > n:
        cand = cand[::2] if len(cand) > 2 * n else cand[1::2] if len(cand) % 2 == 0 else cand[::2]
    return cand or [float(np.median(v))]


def breaks_quant(a, n=6):
    v = a[np.isfinite(a)]
    if not v.size:
        return [0.0]
    q = np.unique(np.round(np.percentile(v, np.linspace(0, 100, n + 1)[1:-1]), 4))
    return [float(x) for x in q]


def breaks_sym(a, n=6):
    """Pecahan simetris di sekitar nol untuk kelengkungan/TPI."""
    v = a[np.isfinite(a)]
    if not v.size:
        return [0.0]
    m = float(np.percentile(np.abs(v), 95))
    st = nice_step(m / (n // 2))
    h = n // 2
    pos = [st * i for i in range(1, h + 1)]
    return [-p for p in reversed(pos)] + [0.0] + pos


def discrete(breaks, ramp, unit="", title="", first_label=None, top_label=None, nd=None, colors=None):
    """Kelas bertingkat dari batas atas; kelas terakhir bersifat terbuka (> batas terakhir)."""
    br = [float(b) for b in breaks]
    cols = colors or lerp_ramp(ramp, len(br) + 1)
    items = []
    for i in range(len(br) + 1):
        if i == 0:
            lab = first_label or f"< {fmtnum(br[0], nd)}"
        elif i == len(br):
            lab = top_label or f"> {fmtnum(br[-1], nd)}"
        else:
            lab = f"{fmtnum(br[i - 1], nd)} - {fmtnum(br[i], nd)}"
        up = br[i] if i < len(br) else 1e30
        items.append(dict(upper=up, color=cols[i], label=lab))
    return dict(type="discrete", items=items, unit=unit, title=title)


def paletted(entries, title=""):
    return dict(type="paletted", items=[dict(value=v, color=c, label=l) for v, c, l in entries],
                title=title, unit="")


def classify_style(arr, style):
    """Kelas (1..n) tiap sel menurut spesifikasi discrete; 0 untuk NaN."""
    if style["type"] != "discrete":
        return None
    ups = np.array([i["upper"] for i in style["items"]][:-1])
    out = np.digitize(np.nan_to_num(arr, nan=np.inf), ups, right=True) + 1
    out[~np.isfinite(arr)] = 0
    return out.astype(np.int16)


def class_table(arr, mask, cell, style):
    """Luas (ha) dan persen per kelas simbologi, dalam urutan legenda."""
    rows = []
    v = arr[mask]
    v = v[np.isfinite(v)] if style["type"] == "discrete" else v
    tot = max(v.size, 1)
    if style["type"] == "discrete":
        ups = np.array([i["upper"] for i in style["items"]][:-1])
        k = np.digitize(v, ups, right=True)
        cnt = np.bincount(k, minlength=len(style["items"]))
        for it, c in zip(style["items"], cnt):
            rows.append(dict(kelas=it["label"], luas_ha=c * cell * cell / 1e4, persen=100.0 * c / tot))
    elif style["type"] == "paletted":
        for it in style["items"]:
            c = int((v == it["value"]).sum())
            rows.append(dict(kelas=it["label"], luas_ha=c * cell * cell / 1e4, persen=100.0 * c / tot))
    return rows


def parse_floats(s, default):
    try:
        v = [float(x) for x in str(s).replace(";", ",").split(",") if x.strip() != ""]
        return sorted(v) if v else list(default)
    except ValueError:
        return list(default)


def index_style(kind, breaks, title):
    br = parse_floats(breaks, [0.2, 0.4, 0.6, 0.8])
    cols = INDEX_COLORS[kind]
    labs = INDEX_LABELS
    if len(br) + 1 != 5:
        cols = lerp_ramp(cols, len(br) + 1)
        labs = [None] * (len(br) + 1)
    items = []
    for i in range(len(br) + 1):
        lo = 0.0 if i == 0 else br[i - 1]
        hi = 1.0 if i == len(br) else br[i]
        nm = tr(labs[i]) if labs[i] else tr("Kelas") + f" {i + 1}"
        items.append(dict(upper=br[i] if i < len(br) else 1e30, color=cols[i],
                          label=f"{nm} ({fmtnum(lo)} - {fmtnum(hi)})"))
    return dict(type="discrete", items=items, unit=tr("skor 0-1"), title=title)


def aspect_style(flat=True):
    names = [tr(x) for x in ["Utara", "Timur laut", "Timur", "Tenggara", "Selatan", "Barat daya", "Barat", "Barat laut"]]
    items = []
    if flat:
        items.append(dict(upper=-0.5, color="#bdbdbd", label=tr("Datar")))
    items.append(dict(upper=22.5, color=DIR8[0], label=tr("Utara") + " (0 - 22.5)"))
    for i in range(1, 8):
        lo, hi = 22.5 + 45 * (i - 1), 22.5 + 45 * i
        items.append(dict(upper=hi, color=DIR8[i], label="%s (%s - %s)" % (names[i], fmtnum(lo), fmtnum(hi))))
    items.append(dict(upper=1e30, color=DIR8[0], label=tr("Utara") + " (337.5 - 360)"))
    return dict(type="discrete", items=items, unit=tr("derajat"), title="Aspect (%s)" % tr("derajat"))


def style_for(key, arr, valid, params, cell):
    """Spesifikasi simbologi untuk keluaran `key`. arr sudah dipotong pada area studi."""
    a = arr
    if key == "filled_dem":
        return discrete(breaks_nice(a, 8), RAMPS["elev"], "m", "Filled DEM (m)", nd=0 if np.nanmax(a) > 100 else 1)
    if key == "sink_depth":
        return discrete([0.25, 0.5, 1, 2, 5], RAMPS["ylorrd"], "m", "Sink Depth (m)", first_label="0.1 - 0.25")
    if key == "slope_pct":
        br = parse_floats(params.get("breaks", "8,15,25,45"), [8, 15, 25, 45])
        cols = [c[2] for c in T.SLOPE_CLASSES]
        labs = [c[1] for c in T.SLOPE_CLASSES]
        if len(br) == 4:
            it = [dict(upper=b, color=hexc(c), label=l) for b, c, l in zip(br + [1e30], cols, labs)]
            it[0]["label"], it[1]["label"] = f"0 - {fmtnum(br[0])} % ({tr('Datar')})", f"{fmtnum(br[0])} - {fmtnum(br[1])} % ({tr('Landai')})"
            it[2]["label"], it[3]["label"] = f"{fmtnum(br[1])} - {fmtnum(br[2])} % ({tr('Agak curam')})", f"{fmtnum(br[2])} - {fmtnum(br[3])} % ({tr('Curam')})"
            it[4]["label"] = f"> {fmtnum(br[3])} % ({tr('Sangat curam')})"
            return dict(type="discrete", items=it, unit="%", title="Slope (%)")
        return discrete(br, RAMPS["ylorrd"], "%", "Slope (%)")
    if key == "slope_class":
        return paletted([(i + 1, hexc(c[2]), tr(c[1])) for i, c in enumerate(T.SLOPE_CLASSES)], "Slope Class")
    if key == "aspect":
        return aspect_style(True)
    if key == "dinf_angle":
        return aspect_style(False)
    if key == "hillshade":
        return dict(type="gray", vmin=0, vmax=255, title="Hillshade", unit="", items=[])
    if key in ("profile_curvature", "plan_curvature"):
        s = breaks_sym(a, 6)
        return discrete(s, RAMPS["div"], "100/m", "Profile Curvature" if key[0] == "p" and "pro" in key else "Plan Curvature")
    if key == "tpi":
        return discrete(breaks_sym(a, 6), RAMPS["div"], "m", "TPI (m)")
    if key == "tri":
        return discrete(breaks_nice(a, 6), RAMPS["viridis"][::-1][:7][::-1], "m", "TRI (m)")
    if key == "landform":
        return paletted([(k, hexc(c), tr(n)) for k, n, c in T.LANDFORM_CLASSES], "Landform (TPI)")
    if key == "flow_dir_d8":
        nm = {64: "Utara", 128: "Timur laut", 1: "Timur", 2: "Tenggara", 4: "Selatan", 8: "Barat daya", 16: "Barat", 32: "Barat laut"}
        nm = {k: "%s (%d)" % (tr(v), k) for k, v in nm.items()}
        return paletted([(k, DIR8[i], nm[k]) for i, k in enumerate([64, 128, 1, 2, 4, 8, 16, 32])], "Flow Direction (D8)")
    if key in ("catchment_area_d8", "mfd_area"):
        return discrete(breaks_log(a, 7, floor=max(cell * cell / 1e4, 1e-6)), RAMPS["blues"], "ha", "Catchment Area (ha)")
    if key in ("dinf_sca", "mfd_sca", "spi", "sti"):
        t = {"dinf_sca": "Specific Catchment Area (m2/m)", "mfd_sca": "Specific Catchment Area (m2/m)",
             "spi": "Stream Power Index", "sti": "Sediment Transport Index"}[key]
        return discrete(breaks_log(a, 7), RAMPS["wet"] if "sca" in key else RAMPS["ylorrd"], "", t)
    if key in ("flow_len_down", "flow_len_up", "flow_dist_stream", "euclid_dist_stream"):
        t = {"flow_len_down": "Flow Length Downstream (m)", "flow_len_up": "Flow Length Upstream (m)",
             "flow_dist_stream": "Flow Distance to Stream (m)", "euclid_dist_stream": "Euclidean Distance to Stream (m)"}[key]
        return discrete(breaks_nice(a, 7, 1, 99), RAMPS["purples"], "m", t)
    if key == "strahler_raster":
        mx = int(np.nanmax(a)) if np.isfinite(a).any() else 1
        return paletted([(o, ORDER_COLORS[min(o - 1, 6)], f"{tr('Orde')} {o}") for o in range(1, mx + 1)], "Strahler Order")
    if key == "shreve_raster":
        return discrete([1.5, 3.5, 7.5, 15.5, 31.5, 63.5], RAMPS["blues"], "", "Shreve Magnitude",
                        first_label="1", nd=0)
    if key == "twi":
        return discrete(breaks_nice(a, 7, 2, 99), RAMPS["wet"], "", "Topographic Wetness Index")
    if key == "ls_factor":
        br = parse_floats(params.get("breaks", "1,5,10,20"), [1, 5, 10, 20])
        return discrete(br, RAMPS["ylorrd"], "", "LS Factor")
    if key == "hand":
        return discrete([1, 2, 5, 10, 20, 50], ["#08306b", "#2f78bc", "#6fa8dc", "#b8d8a8", "#f2e394", "#d9a35b", "#8d5524"],
                        "m", "HAND (m)")
    if key == "drainage_density":
        return discrete(breaks_nice(a, 6, 1, 99), RAMPS["greens"], "km/km2", "Drainage Density (km/km2)")
    if key == "travel_time":
        return discrete(breaks_nice(a, 8, 1, 99), RAMPS["viridis"], tr("menit"), "Travel Time (%s)" % tr("menit"))
    if key == "hand_flood":
        st = parse_floats(params.get("stages", "1,2,5,10"), [1, 2, 5, 10])
        cols = lerp_ramp(["#1a5fa8", "#6bb6d8", "#cfe8f3"], len(st))
        return paletted([(i + 1, cols[i], tr("Tergenang pada +%s m") % fmtnum(x)) for i, x in enumerate(st)],
                        "HAND Flood Inundation Zones")
    if key == "bathtub":
        return discrete([0.5, 1, 2, 3, 5], RAMPS["blues"], "m", tr("Kedalaman Genangan") + " (m)", first_label="0 - 0.5")
    if key in ("flood_index", "recharge_index", "erosion_index"):
        kind = key.split("_")[0]
        nm = {"flood": "Flood Susceptibility Index", "recharge": "Recharge Potential Index",
              "erosion": "Erosion Susceptibility Index"}[kind]
        return index_style(kind, params.get("breaks", "0.2,0.4,0.6,0.8"), nm)
    return discrete(breaks_nice(a, 6), RAMPS["viridis"], "", key)
