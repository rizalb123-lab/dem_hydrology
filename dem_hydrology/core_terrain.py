# -*- coding: utf-8 -*-
"""
Analisis HIDROLOGI DEM - mesin terrain (murni numpy/scipy, tanpa PyQGIS).

Konvensi: grid persegi, baris 0 = utara, `valid` = mask sel yang dianalisis
(sel di luar batas studi / nodata = False dan dianggap titik keluar air).
"""
import heapq
import math

import numpy as np

try:
    from scipy import ndimage as ndi
    from scipy.signal import fftconvolve
except ImportError:  # scipy dibundel QGIS; fallback tetap tersedia
    ndi = None
    fftconvolve = None

D8_DR = np.array([-1, -1, 0, 1, 1, 1, 0, -1])     # urutan: N, NE, E, SE, S, SW, W, NW
D8_DC = np.array([0, 1, 1, 1, 0, -1, -1, -1])
D8_DIST = np.array([1, math.sqrt(2)] * 4)          # jarak relatif terhadap ukuran sel


# ---------------------------------------------------------------------------
# Utilitas
# ---------------------------------------------------------------------------
def nb8(z, valid):
    """Delapan tetangga (N, NE, E, SE, S, SW, W, NW). Tetangga di luar grid atau
    di luar `valid` diganti nilai sel pusat (gradien nol), sehingga tepi tidak
    mencemari turunan."""
    z = np.where(valid, z, 0.0)
    p = np.pad(z, 1, mode="edge")
    pv = np.pad(valid, 1, mode="constant", constant_values=False)
    out = []
    for dr, dc in zip(D8_DR, D8_DC):
        sl = (slice(1 + dr, 1 + dr + z.shape[0]), slice(1 + dc, 1 + dc + z.shape[1]))
        out.append(np.where(pv[sl], p[sl], z))
    return out


def focal_mean(z, valid, radius_cells, circular=True):
    """Rata-rata fokal hanya dari sel valid (normalisasi oleh jumlah sel valid)."""
    r = int(max(1, round(radius_cells)))
    zz = np.where(valid, z, 0.0).astype(np.float64)
    vv = valid.astype(np.float64)
    if fftconvolve is not None:
        yy, xx = np.mgrid[-r:r + 1, -r:r + 1]
        k = ((yy ** 2 + xx ** 2) <= r * r).astype(np.float64) if circular else np.ones((2 * r + 1,) * 2)
        s = fftconvolve(zz, k, mode="same")
        n = fftconvolve(vv, k, mode="same")
    else:  # jendela persegi via citra integral
        def box(a):
            c = np.cumsum(np.cumsum(np.pad(a, ((r + 1, r), (r + 1, r))), 0), 1)
            h, w = a.shape
            return c[2 * r + 1:2 * r + 1 + h, 2 * r + 1:2 * r + 1 + w] - c[:h, 2 * r + 1:2 * r + 1 + w] \
                - c[2 * r + 1:2 * r + 1 + h, :w] + c[:h, :w]
        s, n = box(zz), box(vv)
    with np.errstate(invalid="ignore", divide="ignore"):
        m = s / n
    m[(n < 0.5) | ~valid] = np.nan
    return m


def mask_nan(a, valid):
    a = np.asarray(a, dtype=np.float64).copy()
    a[~valid] = np.nan
    return a


# ---------------------------------------------------------------------------
# Fill Sinks - Priority-Flood (Barnes et al. 2014) dengan kemiringan minimum
# ---------------------------------------------------------------------------
def fill_sinks(dem, valid, cell, min_slope_deg=0.01, progress=None):
    """Mengisi cekungan dengan Priority-Flood (Barnes, Lehman & Mulla 2014).
    min_slope_deg = 0 -> pengisian murni (tanpa kemiringan paksa). Bila > 0,
    area datar diberi gradien minimum (setara Wang & Liu 2006) sehingga aliran
    dapat dirutekan tanpa sel datar.  Sel di tepi grid atau berbatasan dengan
    sel tidak valid dianggap titik keluar."""
    ny, nx = dem.shape
    w2 = nx + 2
    pad = np.full((ny + 2, w2), np.nan)
    pad[1:-1, 1:-1] = np.where(valid, dem, np.nan)
    z = pad.ravel().copy()
    ok = ~np.isnan(z)
    done = np.zeros(z.size, dtype=bool)
    off = [-w2, -w2 + 1, 1, w2 + 1, w2, w2 - 1, -1, -w2 - 1]
    e_card = math.tan(math.radians(min_slope_deg)) * cell
    eps = [e_card, e_card * math.sqrt(2)] * 4

    # semua sel valid yang bertetangga dengan sel tidak valid / tepi = titik keluar
    inner = np.zeros((ny + 2, w2), dtype=bool)
    inner[1:-1, 1:-1] = valid
    nb_bad = np.zeros_like(inner)
    for dr, dc in zip(D8_DR, D8_DC):
        sh = np.roll(np.roll(~inner, -dr, 0), -dc, 1)
        nb_bad |= sh
    seeds = np.flatnonzero((inner & nb_bad).ravel())
    heap = [(z[i], i) for i in seeds]
    heapq.heapify(heap)
    done[seeds] = True
    pop, push = heapq.heappop, heapq.heappush
    n_valid = int(ok.sum())
    cnt = 0
    while heap:
        zc, c = pop(heap)
        for k in range(8):
            n = c + off[k]
            if done[n] or not ok[n]:
                continue
            done[n] = True
            zn = z[n]
            lim = zc + eps[k]
            if zn < lim:
                zn = lim
                z[n] = zn
            push(heap, (zn, n))
        cnt += 1
        if progress is not None and (cnt & 0x3FFFF) == 0:
            if progress(cnt / float(n_valid)) is False:
                raise InterruptedError("dibatalkan")
    out = z.reshape(ny + 2, w2)[1:-1, 1:-1].copy()
    out[~valid] = np.nan
    return out


# ---------------------------------------------------------------------------
# Analisis cekungan (depression / sink)
# ---------------------------------------------------------------------------
def depression_analysis(dem, filled_exact, valid, cell, min_depth=0.05):
    """Cekungan = sel dengan (DEM terisi - DEM asli) > min_depth.
    Mengembalikan (kedalaman, label, tabel). Volume = jumlah(kedalaman) x luas sel."""
    depth = np.where(valid, filled_exact - dem, 0.0)
    depth[depth < min_depth] = 0.0
    mask = depth > 0
    if ndi is None:
        return depth, mask.astype(np.int32), []
    lab, n = ndi.label(mask, structure=np.ones((3, 3)))
    rows = []
    if n:
        idx = np.arange(1, n + 1)
        area = ndi.sum(mask, lab, idx) * cell * cell
        vol = ndi.sum(depth, lab, idx) * cell * cell
        dmax = ndi.maximum(depth, lab, idx)
        dmean = ndi.mean(depth, lab, idx)
        cy, cx = zip(*ndi.center_of_mass(mask, lab, idx))
        for i in range(n):
            rows.append(dict(id=i + 1, area_m2=float(area[i]), depth_max=float(dmax[i]),
                             depth_mean=float(dmean[i]), volume_m3=float(vol[i]),
                             row=float(cy[i]), col=float(cx[i])))
        rows.sort(key=lambda r: -r["volume_m3"])
    return depth, lab.astype(np.int32), rows


# ---------------------------------------------------------------------------
# Turunan permukaan: Slope, Aspect, Hillshade (Horn 1981), Curvature (Zevenbergen & Thorne 1987)
# ---------------------------------------------------------------------------
def gradients(z, valid, cell):
    """dz/dx (timur positif) dan dz/dy (utara positif) memakai kernel Horn (1981)."""
    N, NE, E, SE, S, SW, W, NW = nb8(z, valid)
    dzdx = ((NE + 2 * E + SE) - (NW + 2 * W + SW)) / (8.0 * cell)
    dzdy = ((NW + 2 * N + NE) - (SW + 2 * S + SE)) / (8.0 * cell)
    return dzdx, dzdy


def slope_aspect(z, valid, cell):
    dzdx, dzdy = gradients(z, valid, cell)
    tan_b = np.hypot(dzdx, dzdy)
    slope_pct = mask_nan(100.0 * tan_b, valid)
    slope_deg = mask_nan(np.degrees(np.arctan(tan_b)), valid)
    asp = np.degrees(np.arctan2(-dzdx, -dzdy)) % 360.0       # azimut arah lereng menurun
    asp[tan_b < 1e-9] = -1.0                                 # datar
    return slope_pct, slope_deg, mask_nan(asp, valid), tan_b


def hillshade(z, valid, cell, azimuth=315.0, altitude=45.0, z_factor=1.0):
    dzdx, dzdy = gradients(z * z_factor, valid, cell)
    az, alt = math.radians(azimuth), math.radians(altitude)
    lx, ly, lz = math.sin(az) * math.cos(alt), math.cos(az) * math.cos(alt), math.sin(alt)
    s = (-dzdx * lx - dzdy * ly + lz) / np.sqrt(dzdx ** 2 + dzdy ** 2 + 1.0)
    return mask_nan(255.0 * np.clip(s, 0, 1), valid)


def curvature(z, valid, cell):
    """Kelengkungan profil & plan (Zevenbergen & Thorne 1987), satuan 100/m.
    Tanda: positif = cembung, negatif = cekung (kedua jenis)."""
    nb = nb8(z, valid)                       # N, NE, E, SE, S, SW, W, NW
    z2, z8, z4, z6 = nb[0], nb[4], nb[6], nb[2]
    z1, z3, z7, z9 = nb[7], nb[1], nb[5], nb[3]
    z5 = np.where(valid, z, 0.0)
    L = cell
    D = ((z4 + z6) / 2.0 - z5) / L ** 2
    E = ((z2 + z8) / 2.0 - z5) / L ** 2
    F = (-z1 + z3 + z7 - z9) / (4.0 * L ** 2)
    G = (-z4 + z6) / (2.0 * L)
    H = (z2 - z8) / (2.0 * L)
    den = G ** 2 + H ** 2
    with np.errstate(invalid="ignore", divide="ignore"):
        prof = -2.0 * (D * G ** 2 + E * H ** 2 + F * G * H) / den
        plan = -2.0 * (D * H ** 2 + E * G ** 2 - F * G * H) / den
    prof[den < 1e-12] = 0.0
    plan[den < 1e-12] = 0.0
    return mask_nan(prof * 100.0, valid), mask_nan(plan * 100.0, valid)


# ---------------------------------------------------------------------------
# TPI (Weiss 2001), TRI (Riley et al. 1999), klasifikasi bentuk lahan
# ---------------------------------------------------------------------------
def tpi(z, valid, cell, radius_m):
    m = focal_mean(z, valid, radius_m / cell)
    return mask_nan(z - m, valid)


def tri(z, valid, cell):
    nb = nb8(z, valid)
    z5 = np.where(valid, z, 0.0)
    return mask_nan(np.sqrt(sum((n - z5) ** 2 for n in nb)), valid)


LANDFORM_CLASSES = [
    (1, "Canyons, deeply incised streams", (38, 70, 140)),
    (2, "Midslope drainages, shallow valleys", (66, 121, 187)),
    (3, "Upland drainages, headwaters", (125, 175, 219)),
    (4, "U-shaped valleys", (88, 150, 90)),
    (5, "Plains", (233, 226, 170)),
    (6, "Open slopes", (235, 192, 110)),
    (7, "Upper slopes, mesas", (214, 154, 78)),
    (8, "Local ridges, hills in valleys", (193, 120, 80)),
    (9, "Midslope ridges, small hills in plains", (160, 82, 60)),
    (10, "Mountain tops, high ridges", (120, 50, 45)),
]


def landform_tpi(z, valid, cell, r_small_m, r_large_m, slope_deg, flat_deg=5.0):
    """Weiss (2001): 10 kelas bentuk lahan dari TPI terstandar dua skala."""
    def std_tpi(r):
        t = tpi(z, valid, cell, r)
        return (t - np.nanmean(t)) / max(np.nanstd(t), 1e-9)
    sn, ln = std_tpi(r_small_m), std_tpi(r_large_m)
    out = np.zeros(z.shape, dtype=np.int16)
    sl = np.nan_to_num(slope_deg)
    out[(sn <= -1) & (ln <= -1)] = 1
    out[(sn <= -1) & (ln > -1) & (ln < 1)] = 2
    out[(sn <= -1) & (ln >= 1)] = 3
    out[(sn > -1) & (sn < 1) & (ln <= -1)] = 4
    mid = (sn > -1) & (sn < 1) & (ln > -1) & (ln < 1)
    out[mid & (sl <= flat_deg)] = 5
    out[mid & (sl > flat_deg)] = 6
    out[(sn > -1) & (sn < 1) & (ln >= 1)] = 7
    out[(sn >= 1) & (ln <= -1)] = 8
    out[(sn >= 1) & (ln > -1) & (ln < 1)] = 9
    out[(sn >= 1) & (ln >= 1)] = 10
    out[~valid] = 0
    return out


# ---------------------------------------------------------------------------
# Kelas lereng - SK Mentan No. 837/Kpts/Um/11/1980
# ---------------------------------------------------------------------------
SLOPE_CLASSES = [
    (8.0, "0 - 8 % (Datar)", (56, 142, 60)),
    (15.0, "8 - 15 % (Landai)", (165, 214, 100)),
    (25.0, "15 - 25 % (Agak curam)", (255, 235, 59)),
    (45.0, "25 - 45 % (Curam)", (255, 152, 0)),
    (1e9, "> 45 % (Sangat curam)", (211, 47, 47)),
]


def classify(a, breaks, valid=None):
    """Kelas 1..n+1 menurut batas atas (kelas k berlaku jika a <= breaks[k-1])."""
    out = np.digitize(np.nan_to_num(a, nan=np.inf), np.asarray(breaks, dtype=np.float64), right=True) + 1
    out = out.astype(np.int16)
    bad = np.isnan(a) | (~valid if valid is not None else False)
    out[bad] = 0
    return out
