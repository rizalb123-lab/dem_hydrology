# -*- coding: utf-8 -*-
"""Bahan bersama untuk laporan Excel dan PDF (tanpa QGIS)."""
from .i18n import tr
import math

from . import registry as R, styles as S

# kunci -> (label, satuan, rumus/keterangan, kunci pustaka)
MORPH_META = [
    ("luas_km2", "Luas (A)", "km2", "Jumlah sel x luas sel", "horton1932"),
    ("keliling_km", "Keliling (P)", "km", "Panjang garis batas poligon yang disederhanakan (toleransi 1 sel)", ""),
    ("L_lintasan_km", "Panjang aliran terpanjang (Lfp)", "km", "Lintasan D8 dari sel terjauh ke outlet", "kirpich1940"),
    ("Lb_km", "Panjang DAS (Lb)", "km", "Jarak lurus terjauh dari outlet ke batas DAS", "schumm1956"),
    ("elev_outlet", "Elevasi outlet", "m", "Elevasi sel outlet pada DEM", ""),
    ("elev_min", "Elevasi minimum", "m", "", ""),
    ("elev_max", "Elevasi maksimum", "m", "", ""),
    ("elev_mean", "Elevasi rata-rata", "m", "", ""),
    ("relief_H_m", "Relief DAS (H)", "m", "H = elevasi maks - elevasi outlet", "schumm1956"),
    ("slope_mean_pct", "Kemiringan lereng rata-rata", "%", "Rata-rata kemiringan sel (Horn)", "horn1981"),
    ("S_alur_1085", "Kemiringan alur utama 10-85 %", "m/m", "(z10 - z85) / (0,75 Lfp)", "taylor1952"),
    ("Rf_form_factor", "Form Factor (Rf)", "-", "Rf = A / Lb^2", "horton1932"),
    ("Re_elongasi", "Elongation Ratio (Re)", "-", "Re = 1,128 sqrt(A) / Lb", "schumm1956"),
    ("Rc_sirkularitas", "Circularity Ratio (Rc)", "-", "Rc = 4 pi A / P^2", "miller1953"),
    ("Kc_kekompakan", "Compactness Coefficient (Kc)", "-", "Kc = 0,2821 P / sqrt(A)", "gravelius1914"),
    ("Rr_relief_ratio", "Relief Ratio (Rr)", "-", "Rr = H / Lb", "schumm1956"),
    ("Rn_ruggedness", "Ruggedness Number (Rn)", "-", "Rn = H x Dd (H dalam km)", "melton1957"),
    ("HI", "Hypsometric Integral (HI)", "-", "(z rata2 - z min) / (z maks - z min)", "strahler1952"),
    ("L_sungai_km", "Panjang total sungai", "km", "Jumlah panjang ruas sungai", "horton1945"),
    ("N_ruas", "Jumlah ruas sungai (Nu)", "buah", "", "horton1945"),
    ("orde_maks", "Orde Strahler tertinggi", "-", "", "strahler1957"),
    ("Dd_km_km2", "Drainage Density (Dd)", "km/km2", "Dd = Lu / A", "horton1932"),
    ("Fs_per_km2", "Stream Frequency (Fs)", "/km2", "Fs = Nu / A", "horton1932"),
    ("Rb_rata2", "Bifurcation Ratio (Rb), rata-rata", "-", "Rb = Nu / Nu+1", "schumm1956"),
    ("Rb_terbobot", "Bifurcation Ratio (Rb), terbobot", "-", "Rata-rata Rb terbobot jumlah ruas", "strahler1957"),
    ("Rt_tekstur", "Texture Ratio (Rt)", "/km", "Rt = Nu / P", "smith1950"),
    ("Infiltration_number", "Infiltration Number (If)", "-", "If = Dd x Fs", "faniran1968"),
    ("C_konstan_pemeliharaan", "Constant of Channel Maintenance (C)", "km2/km", "C = 1 / Dd", "schumm1956"),
    ("Lg_aliran_permukaan_km", "Length of Overland Flow (Lg)", "km", "Lg = 1 / (2 Dd)", "horton1945"),
    ("tc_Kirpich_menit", "Waktu konsentrasi (Kirpich)", "menit", "tc = 0,01947 Lfp^0,77 S^-0,385", "kirpich1940"),
    ("tc_Giandotti_jam", "Waktu konsentrasi (Giandotti)", "jam", "tc = (4 sqrt(A) + 1,5 Lfp) / (0,8 sqrt(Hm))", "giandotti1934"),
]


def morph_meta():
    """MORPH_META with texts translated into the active language."""
    return [(k, tr(l), tr(u), tr(f) if f else f, r) for k, l, u, f, r in MORPH_META]


def method_note():
    return [tr(t) for t in METHOD_NOTE]


def interp_re(v):
    """Bentuk DAS menurut Elongation Ratio (Schumm 1956; Strahler 1964)."""
    if v is None or not math.isfinite(v):
        return ""
    if v >= 0.9:
        return tr("Membulat")
    if v >= 0.8:
        return tr("Oval")
    if v >= 0.7:
        return tr("Agak memanjang")
    if v >= 0.5:
        return tr("Memanjang")
    return tr("Sangat memanjang")


def interp_hi(v):
    """Tahap perkembangan lahan menurut Hypsometric Integral (Strahler 1952)."""
    if v is None or not math.isfinite(v):
        return ""
    if v > 0.6:
        return tr("Muda (belum seimbang)")
    if v >= 0.35:
        return tr("Dewasa (seimbang)")
    return tr("Tua (monadnock)")


def dominant_text(out):
    """Kalimat ringkas hasil: kelas dominan atau sebaran nilai."""
    if out.classes:
        top = sorted(out.classes, key=lambda r: -r["persen"])[:2]
        top = [t for t in top if t["persen"] > 0.05]
        if top:
            s = tr("Kelas terluas: %s (%s %% luas kawasan)") % (top[0]["kelas"], S.fmtnum(top[0]["persen"], 1))
            if len(top) > 1:
                s += tr("; berikutnya %s (%s %%)") % (top[1]["kelas"], S.fmtnum(top[1]["persen"], 1))
            return s + "."
    st = out.stats
    if st and "median" in st:
        u = (" " + out.unit) if out.unit and out.unit not in ("skor 0-1", tr("skor 0-1")) else ""
        return tr("Rentang nilai %s sampai %s%s, median %s%s.") % (S.fmtnum(st["min"]), S.fmtnum(st["max"]), u,
                                                              S.fmtnum(st["median"]), u)
    if out.kind == "vector" and out.n_features:
        return tr("%d objek dihasilkan.") % out.n_features
    return ""


def params_rows(par, selected):
    """Baris tabel parameter: (kelompok, parameter, nilai, satuan)."""
    rows = []
    core = par.get("core", {})
    for p in R.L()["CORE_PARAMS"]:
        rows.append((tr("Umum"), p["label"], core.get(p["key"], p["default"]), p["unit"]))
    for k in selected:
        a = R.L()["ANALYSES"][k]
        for p in a["params"]:
            v = par.get(k, {}).get(p["key"], p["default"])
            if p["type"] == "choice":
                v = dict(p["choices"]).get(v, v)
            rows.append((a["name"], p["label"], v, p["unit"]))
    return rows


def dem_summary(d, pl):
    import numpy as np
    z = d.z[d.inside]
    return [
        (tr("Sistem koordinat kerja"), d.crs.authid() + " - " + d.crs.description()),
        (tr("Ukuran sel analisis"), "%.2f m" % d.cell),
        (tr("Resolusi asli DEM"), tr("%.2f m (resampling: %s)") % (d.src_native, d.resampled)),
        (tr("Dimensi grid analisis"), tr("%d baris x %d kolom") % d.shape),
        (tr("Luas kawasan studi"), "%.2f ha (%.3f km2)" % (d.inside.sum() * d.cell ** 2 / 1e4, d.inside.sum() * d.cell ** 2 / 1e6)),
        (tr("Elevasi minimum / maksimum / rata-rata"), "%.1f / %.1f / %.1f m" % (z.min(), z.max(), z.mean())),
        (tr("Buffer DEM di luar batas"), "%.0f m" % pl.core.get("buffer_m", 0)),
        (tr("Ambang sungai"), "%.1f ha" % pl.core.get("stream_thr_ha", 0)),
    ]


METHOD_NOTE = [
    "Seluruh analisis dihitung dari DEM saja; tidak ada data hujan, tanah, tutupan lahan, atau debit terukur yang dipakai.",
    "Indeks komposit (kerawanan banjir, potensi resapan, kerawanan erosi) berskala 0-1 relatif terhadap kawasan studi "
    "dan bersifat topografis-indikatif. Hasilnya bukan model hidrolika dan bukan pendugaan kehilangan tanah.",
    "Sungai, DAS, dan morfometri bergantung pada ambang luas tangkapan dan resolusi DEM. Validasi dengan citra, peta "
    "sungai resmi, atau pengukuran lapangan sebelum dipakai untuk keputusan teknis.",
    "DSM (misalnya hasil fotogrametri atau LiDAR permukaan) memuat tajuk dan bangunan yang dapat membelokkan aliran; "
    "gunakan DTM bila tersedia.",
    "Pada area yang sangat datar arah aliran ditentukan oleh kemiringan minimum paksa sehingga hasilnya kurang andal.",
]
