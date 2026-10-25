# -*- coding: utf-8 -*-
"""
Analisis HIDROLOGI DEM - indeks turunan (murni numpy/scipy).
Setiap fungsi mencantumkan dasar ilmiahnya; daftar lengkap ada di registry.py.
"""
import math

import numpy as np

from .core_terrain import ndi, fftconvolve, focal_mean, mask_nan
from . import core_flow as F


# ---------------------------------------------------------------------------
# Indeks kebasahan / daya aliran / transpor sedimen / faktor LS
# ---------------------------------------------------------------------------
def twi(sca, tan_b, tan_min=0.001):
    """Topographic Wetness Index = ln(a / tan b)  (Beven & Kirkby 1979)."""
    return np.log(np.maximum(sca, 1e-9) / np.maximum(tan_b, tan_min))


def spi(sca, tan_b):
    """Stream Power Index = a x tan b  (Moore et al. 1991)."""
    return sca * tan_b


def sti(sca, tan_b):
    """Sediment Transport Index (Moore & Burch 1986): (a/22.13)^0.6 (sin b/0.0896)^1.3."""
    sin_b = np.sin(np.arctan(tan_b))
    return (sca / 22.13) ** 0.6 * (sin_b / 0.0896) ** 1.3


def ls_factor(acc_cells, cell, tan_b, dir_code, s_method="mccool", ls_max=0.0):
    """Faktor LS RUSLE: L dari Desmet & Govers (1996), eksponen m dari McCool et al. (1989),
    S dari McCool et al. (1987) atau Nearing (1997)."""
    th = np.arctan(tan_b)
    sin_t = np.maximum(np.sin(th), 1e-6)
    beta = (sin_t / 0.0896) / (3.0 * sin_t ** 0.8 + 0.56)
    m = beta / (1.0 + beta)
    diag = np.isin(dir_code, [2, 8, 32, 128])
    x = np.where(diag, math.sqrt(2), 1.0)
    a_in = np.maximum(acc_cells - 1.0, 0.0) * cell * cell
    D = cell
    L = ((a_in + D * D) ** (m + 1) - a_in ** (m + 1)) / (D ** (m + 2) * x ** m * 22.13 ** m)
    if s_method == "nearing":
        S = -1.5 + 17.0 / (1.0 + np.exp(2.3 - 6.1 * sin_t))
    else:
        S = np.where(tan_b < 0.09, 10.8 * sin_t + 0.03, 16.8 * sin_t - 0.50)
    ls = L * np.maximum(S, 0.0)
    return np.minimum(ls, ls_max) if ls_max and ls_max > 0 else ls


# ---------------------------------------------------------------------------
# Kerapatan drainase (kernel) - Horton (1932)
# ---------------------------------------------------------------------------
def drainage_density(stream_len_m, valid, cell, radius_m):
    """km sungai per km2 dalam lingkaran berjari-jari radius_m di sekitar tiap sel."""
    r = int(max(1, round(radius_m / cell)))
    yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
    k = ((yy ** 2 + xx ** 2) <= r * r).astype(np.float64)
    if fftconvolve is not None:
        s = fftconvolve(np.where(valid, stream_len_m, 0.0), k, mode="same")
        n = fftconvolve(valid.astype(np.float64), k, mode="same")
    else:
        s = ndi.convolve(np.where(valid, stream_len_m, 0.0), k, mode="constant")
        n = ndi.convolve(valid.astype(np.float64), k, mode="constant")
    with np.errstate(invalid="ignore", divide="ignore"):
        dd = (s / 1000.0) / (n * cell * cell / 1e6)
    dd[(n < 1) | ~valid] = np.nan
    return np.maximum(dd, 0.0)


# ---------------------------------------------------------------------------
# Waktu tempuh / isochrone (time-area)
# ---------------------------------------------------------------------------
TR55_K = {"tanah (unpaved)": 4.9178, "perkerasan (paved)": 6.1960}       # m/s per sqrt(m/m)


def travel_time(g, tan_down, stream, step, k_hill=4.9178, manning_n=0.035, hyd_radius=0.5,
                s_min=0.001):
    """Waktu tempuh (menit) tiap sel menuju titik keluar mengikuti D8.
    Lereng: aliran terkonsentrasi dangkal NRCS TR-55: V = k * sqrt(S).
    Alur sungai: Manning V = R^(2/3) S^(1/2) / n."""
    S = np.maximum(tan_down.ravel(), s_min)
    v = np.where(stream, (hyd_radius ** (2.0 / 3.0)) * np.sqrt(S) / manning_n, k_hill * np.sqrt(S))
    dt = step / np.maximum(v, 1e-3)
    return g.downstream_sum(dt) / 60.0


def time_area_histogram(t_min, valid_flat, cell, bin_min=5.0):
    """Fungsi luas-waktu: luas (ha) per kelas waktu tempuh dan kumulatifnya."""
    t = t_min[valid_flat & np.isfinite(t_min)]
    if not t.size:
        return []
    edges = np.arange(0, t.max() + bin_min, bin_min)
    h, e = np.histogram(t, bins=edges)
    ha = h * cell * cell / 1e4
    cum = np.cumsum(ha)
    return [dict(t0=float(e[i]), t1=float(e[i + 1]), area_ha=float(ha[i]), cum_ha=float(cum[i]),
                 cum_pct=float(100 * cum[i] / cum[-1])) for i in range(len(ha))]


# ---------------------------------------------------------------------------
# Skor komposit (overlay terbobot dari beberapa keluaran DEM)
# ---------------------------------------------------------------------------
def norm01(a, valid, invert=False, lo_pct=2.0, hi_pct=98.0):
    """Normalisasi 0-1 dengan pemotongan persentil (kebal terhadap pencilan)."""
    v = a[valid & np.isfinite(a)]
    if not v.size:
        return np.zeros(a.shape)
    lo, hi = np.percentile(v, [lo_pct, hi_pct])
    n = np.clip((np.nan_to_num(a, nan=lo) - lo) / max(hi - lo, 1e-12), 0, 1)
    return 1.0 - n if invert else n


def composite(factors, weights, valid):
    """factors: {nama: (array, invert)}; skor = jumlah(w_i n_i) / jumlah(w_i). NaN -> 0."""
    tot = sum(max(float(weights.get(k, 0)), 0) for k in factors) or 1.0
    s = np.zeros(valid.shape)
    for k, (a, inv) in factors.items():
        n = norm01(a, valid, inv)
        n = np.where(np.isfinite(a), n, 0.0)
        s += max(float(weights.get(k, 0)), 0) * n
    return mask_nan(s / tot, valid)


# ---------------------------------------------------------------------------
# Genangan: HAND bertingkat (Nobre et al. 2016) dan bathtub (Poulter & Halpin 2008)
# ---------------------------------------------------------------------------
def hand_inundation(hand, stage_m):
    """Kedalaman genangan = tinggi muka air (di atas dasar sungai) - HAND, bila positif."""
    d = stage_m - hand
    d = np.where(np.isfinite(hand) & (d > 0), d, 0.0)
    return d


def bathtub(dem, valid, level, connected=True):
    """Genangan 'bathtub': sel dengan z <= level. Bila connected, hanya yang terhubung (8 arah)
    ke tepi domain / tepi area valid (mewakili laut atau muara)."""
    low = valid & (dem <= level)
    if not connected or ndi is None:
        return np.where(low, level - dem, 0.0)
    lab, n = ndi.label(low, structure=np.ones((3, 3)))
    edge = np.zeros_like(valid)
    edge[0, :] = edge[-1, :] = edge[:, 0] = edge[:, -1] = True
    near_bad = ndi.binary_dilation(~valid, structure=np.ones((3, 3))) & valid
    seeds = np.unique(lab[(edge | near_bad) & low])
    keep = np.isin(lab, seeds[seeds > 0])
    return np.where(keep, level - dem, 0.0)


# ---------------------------------------------------------------------------
# Statistik luas per kelas dan statistik kontinu
# ---------------------------------------------------------------------------
def class_stats(cls, mask, cell, labels):
    """labels: {kode: nama}. Mengembalikan baris (kode, nama, luas_ha, persen)."""
    vals = cls[mask]
    tot = max(vals.size, 1)
    rows = []
    for k, name in labels.items():
        n = int((vals == k).sum())
        rows.append(dict(kode=k, nama=name, luas_ha=n * cell * cell / 1e4, persen=100.0 * n / tot))
    return rows


def cont_stats(a, mask):
    v = a[mask & np.isfinite(a)]
    if not v.size:
        return {}
    p = np.percentile(v, [5, 25, 50, 75, 95])
    return dict(min=float(v.min()), p5=float(p[0]), p25=float(p[1]), median=float(p[2]), p75=float(p[3]),
                p95=float(p[4]), max=float(v.max()), mean=float(v.mean()), std=float(v.std()),
                n=int(v.size))


# ---------------------------------------------------------------------------
# Morfometri DAS (Horton 1932/1945; Strahler 1952/1957; Schumm 1956; Miller 1953; Melton 1957)
# ---------------------------------------------------------------------------
def hypsometry(elev, n_pts=21):
    """Kurva hipsometrik: fraksi luas di atas elevasi relatif h/H (Strahler 1952)."""
    e = np.sort(elev[np.isfinite(elev)])
    if e.size < 2 or e[-1] - e[0] < 1e-9:
        return [], float("nan")
    rel = (e - e[0]) / (e[-1] - e[0])
    h = np.linspace(0, 1, n_pts)
    a = [1.0 - float(np.searchsorted(rel, x, side="left")) / e.size for x in h]
    hi = float((e.mean() - e[0]) / (e[-1] - e[0]))                  # integral hipsometrik (Pike & Wilson 1971)
    return [dict(h_rel=float(x), a_rel=float(y)) for x, y in zip(h, a)], hi


def basin_morphometry(idx, ctx, perimeter_m=None, with_flowpath=True):
    """Parameter morfometri satu DAS. idx = indeks datar sel DAS.
    ctx: dict berisi shape, cell, z (asli), zf (terisi), slope_pct, acc, up, dl, rec, step,
         links (daftar ruas), link_start_cell (indeks datar awal ruas, array)."""
    cell, nx = ctx["cell"], ctx["shape"][1]
    z = ctx["z"][idx]
    A = idx.size * cell * cell
    out = dict(luas_km2=A / 1e6, n_sel=int(idx.size))
    out["elev_min"], out["elev_max"], out["elev_mean"] = float(z.min()), float(z.max()), float(z.mean())
    out["slope_mean_pct"] = float(np.nanmean(ctx["slope_pct"][idx]))
    curve, hi = hypsometry(z)
    out["HI"] = hi
    out["_hypso"] = curve
    # ruas sungai di dalam DAS
    inb = np.zeros(ctx["N"], dtype=bool)
    inb[idx] = True
    ls = [l for l in ctx["links"] if inb[l["cells"][0]]]
    byo = {}
    stp = ctx["step"]
    for l in ls:
        d = byo.setdefault(l["order"], dict(n=0, len=0.0))
        d["n"] += 1
        p = l["cells"][:-1]
        # hanya bagian ruas yang berada di dalam DAS (ruas bisa melewati outlet)
        d["len"] += float(stp[p][inb[p]].sum()) if p.size else 0.0
    out["_orders"] = {k: byo[k] for k in sorted(byo)}
    Lsum = sum(v["len"] for v in byo.values()) / 1000.0
    Ntot = sum(v["n"] for v in byo.values())
    A_km = A / 1e6
    out["L_sungai_km"] = Lsum
    out["N_ruas"] = Ntot
    out["orde_maks"] = max(byo) if byo else 0
    out["Dd_km_km2"] = Lsum / A_km if A_km > 0 else float("nan")
    out["Fs_per_km2"] = Ntot / A_km if A_km > 0 else float("nan")
    ords = sorted(byo)
    rb = [byo[o]["n"] / byo[o + 1]["n"] for o in ords[:-1] if byo.get(o + 1, {}).get("n")]
    wts = [byo[o]["n"] + byo[o + 1]["n"] for o in ords[:-1] if byo.get(o + 1, {}).get("n")]
    out["Rb_rata2"] = float(np.mean(rb)) if rb else float("nan")
    out["Rb_terbobot"] = float(np.average(rb, weights=wts)) if rb else float("nan")
    out["Infiltration_number"] = out["Dd_km_km2"] * out["Fs_per_km2"]
    out["C_konstan_pemeliharaan"] = 1.0 / out["Dd_km_km2"] if out["Dd_km_km2"] > 0 else float("nan")
    out["Lg_aliran_permukaan_km"] = 1.0 / (2.0 * out["Dd_km_km2"]) if out["Dd_km_km2"] > 0 else float("nan")
    if perimeter_m:
        P = perimeter_m / 1000.0
        out["keliling_km"] = P
        out["Rc_sirkularitas"] = 4.0 * math.pi * A_km / (P * P)
        out["Kc_kekompakan"] = 0.2821 * P / math.sqrt(A_km)
        out["Rt_tekstur"] = Ntot / P
    if not with_flowpath:
        return out
    # outlet = sel dengan akumulasi terbesar; lintasan terpanjang dari sel terjauh
    acc, dl, rec, zf = ctx["acc"], ctx["dl"], ctx["rec"], ctx["zf"]
    out_cell = int(idx[np.argmax(acc[idx])])
    far = int(idx[np.argmax(dl[idx])])
    Lfp = float(dl[far] - dl[out_cell])
    r_o, c_o = divmod(out_cell, nx)
    rr, cc = np.divmod(idx, nx)
    Lb = float(np.sqrt((rr - r_o) ** 2 + (cc - c_o) ** 2).max() * cell) if idx.size else 0.0
    Lb = max(Lb, cell)
    out.update(L_lintasan_km=Lfp / 1000.0, Lb_km=Lb / 1000.0, elev_outlet=float(ctx["z"].ravel()[out_cell]))
    H = out["elev_max"] - out["elev_outlet"]
    out["relief_H_m"] = H
    out["Rf_form_factor"] = A_km / ((Lb / 1000.0) ** 2)
    out["Re_elongasi"] = 1.128 * math.sqrt(A_km) / (Lb / 1000.0)
    out["Rr_relief_ratio"] = H / Lb
    out["Rn_ruggedness"] = (H / 1000.0) * out["Dd_km_km2"]
    # kemiringan alur utama (10-85%) dari lintasan terjauh
    path, cur, guard = [], far, 0
    while cur != out_cell and cur >= 0 and guard < 10 ** 6:
        path.append(cur)
        cur = int(rec[cur])
        guard += 1
    path.append(out_cell)
    p = np.array(path)
    dist = dl[p[0]] - dl[p]                                   # jarak dari sel terjauh
    zp = zf.ravel()[p]
    if Lfp > 0 and p.size > 3:
        e10, e85 = np.interp([0.10 * Lfp, 0.85 * Lfp], dist, zp)
        out["S_alur_1085"] = float((e10 - e85) / (0.75 * Lfp))
    else:
        out["S_alur_1085"] = float("nan")
    S = out["S_alur_1085"] if np.isfinite(out["S_alur_1085"]) and out["S_alur_1085"] > 0 else max(H / max(Lfp, 1), 1e-4)
    out["tc_Kirpich_menit"] = 0.01947 * Lfp ** 0.77 * S ** -0.385
    Hm = max(out["elev_mean"] - out["elev_outlet"], 1.0)
    out["tc_Giandotti_jam"] = (4.0 * math.sqrt(A_km) + 1.5 * Lfp / 1000.0) / (0.8 * math.sqrt(Hm))
    out["_profile"] = dict(dist=dist.tolist(), z=zp.tolist())
    return out
