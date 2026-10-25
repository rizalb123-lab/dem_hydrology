# -*- coding: utf-8 -*-
"""
Analisis HIDROLOGI DEM - mesin aliran (murni numpy).

Arah aliran: D8 (O'Callaghan & Mark 1984), D-infinity (Tarboton 1997),
MFD (Quinn et al. 1991; Freeman 1991).  Semua dibangun di atas satu struktur
graf aliran (DAG) yang ditelusuri per "gelombang" (algoritma Kahn) sehingga
akumulasi, panjang aliran, HAND, dan pelabelan DAS semuanya vektor numpy.
"""
import math

import numpy as np

from .core_terrain import D8_DR, D8_DC, D8_DIST

# kode arah D8 gaya ESRI untuk urutan N, NE, E, SE, S, SW, W, NW
D8_CODE = np.array([64, 128, 1, 2, 4, 8, 16, 32], dtype=np.int16)


# ---------------------------------------------------------------------------
# Graf aliran
# ---------------------------------------------------------------------------
class FlowGraph:
    """Setiap sel punya hingga K penerima (indeks datar, -1 = tidak ada) dan proporsi."""

    def __init__(self, shape, valid, rc, rw):
        self.shape = shape
        self.N = shape[0] * shape[1]
        self.valid = valid.ravel()
        self.rc = rc                      # (K, N) int32
        self.rw = rw                      # (K, N) float32
        self.K = rc.shape[0]
        self.levels, self.cyclic = self._levels()

    def _levels(self):
        N, K = self.N, self.K
        indeg = np.zeros(N, dtype=np.int32)
        for k in range(K):
            r = self.rc[k]
            indeg += np.bincount(r[r >= 0], minlength=N).astype(np.int32)
        cur = np.flatnonzero(self.valid & (indeg == 0))
        levels, seen = [], 0
        while cur.size:
            levels.append(cur)
            seen += cur.size
            nxt = []
            for k in range(K):
                r = self.rc[k][cur]
                r = r[r >= 0]
                if r.size:
                    np.add.at(indeg, r, -1)
                    nxt.append(r)
            if not nxt:
                break
            cand = np.concatenate(nxt)
            cur = np.unique(cand[indeg[cand] == 0])
        return levels, seen != int(self.valid.sum())

    def accumulate(self, init=None):
        """Jumlah `init` (default 1 per sel) dari seluruh sel di hulu, termasuk sel itu sendiri."""
        acc = np.zeros(self.N) if init is None else np.asarray(init, dtype=np.float64).ravel().copy()
        if init is None:
            acc[self.valid] = 1.0
        for cur in self.levels:
            a = acc[cur]
            for k in range(self.K):
                r = self.rc[k][cur]
                m = r >= 0
                if m.any():
                    np.add.at(acc, r[m], a[m] * self.rw[k][cur][m])
        return acc

    def upstream_max(self, step):
        """Jarak aliran terpanjang ke hulu (m) dari tiap sel, memakai penerima utama (slot 0)."""
        up = np.zeros(self.N)
        for cur in self.levels:
            r = self.rc[0][cur]
            m = r >= 0
            if m.any():
                np.maximum.at(up, r[m], up[cur][m] + step[cur][m])
        return up

    def downstream_sum(self, step):
        """Jarak aliran menuju titik keluar (m) lewat penerima utama (slot 0)."""
        dl = np.zeros(self.N)
        for cur in reversed(self.levels):
            r = self.rc[0][cur]
            m = r >= 0
            dl[cur[m]] = dl[r[m]] + step[cur[m]]
        return dl

    def propagate_down(self, values, stop_mask=None):
        """Nilai tiap sel = nilainya sendiri bila `stop_mask` benar, selain itu nilai penerima
        (slot 0). Dipakai untuk HAND, label DAS, dsb. Sel tanpa jalur ke 'stop' -> NaN."""
        out = np.full(self.N, np.nan)
        for cur in reversed(self.levels):
            r = self.rc[0][cur]
            has = r >= 0
            v = np.full(cur.size, np.nan)
            v[has] = out[r[has]]
            if stop_mask is not None:
                s = stop_mask[cur]
                v[s] = values[cur][s]
            out[cur] = v
        return out


# ---------------------------------------------------------------------------
# Pembangun arah aliran
# ---------------------------------------------------------------------------
def _nbz(zp, d, ny, nx):
    return zp[1 + D8_DR[d]:1 + D8_DR[d] + ny, 1 + D8_DC[d]:1 + D8_DC[d] + nx]


def _flat_nb(ny, nx):
    r, c = np.mgrid[0:ny, 0:nx]
    return r, c


def build_d8(z, valid, cell):
    """D8: penerima = tetangga dengan penurunan (drop/jarak) terbesar. Mengembalikan
    (graf, kode_arah, tan_lereng_maks)."""
    ny, nx = z.shape
    zp = np.pad(np.where(valid, z, np.nan), 1, constant_values=np.nan)
    best = np.zeros(z.shape)
    idx = np.full(z.shape, -1, dtype=np.int8)
    for d in range(8):
        drop = (z - _nbz(zp, d, ny, nx)) / (cell * D8_DIST[d])
        drop = np.where(np.isnan(drop), -1.0, drop)
        better = drop > best
        best[better] = drop[better]
        idx[better] = d
    r, c = _flat_nb(ny, nx)
    has = (idx >= 0) & valid
    dr = np.where(has, D8_DR[np.maximum(idx, 0)], 0)
    dc = np.where(has, D8_DC[np.maximum(idx, 0)], 0)
    rec = np.where(has, (r + dr) * nx + (c + dc), -1).astype(np.int32)
    code = np.where(has, D8_CODE[np.maximum(idx, 0)], 0).astype(np.int16)
    g = FlowGraph(z.shape, valid, rec.ravel()[None, :], np.ones((1, z.size), dtype=np.float32))
    return g, code, np.where(has, best, 0.0)


_FACETS = [(2, 1, 0, 1), (0, 1, 1, -1), (0, 7, 1, 1), (6, 7, 2, -1),
           (6, 5, 2, 1), (4, 5, 3, -1), (4, 3, 3, 1), (2, 3, 4, -1)]


def build_dinf(z, valid, cell):
    """D-infinity (Tarboton 1997). Mengembalikan (graf, sudut_kompas_derajat)."""
    ny, nx = z.shape
    zp = np.pad(np.where(valid, z, np.nan), 1, constant_values=np.nan)
    best_s = np.zeros(z.shape)
    best_r = np.zeros(z.shape)
    best_f = np.full(z.shape, -1, dtype=np.int8)
    q = math.pi / 4.0
    for f, (i1, i2, _ac, _af) in enumerate(_FACETS):
        e1, e2 = _nbz(zp, i1, ny, nx), _nbz(zp, i2, ny, nx)
        s1, s2 = (z - e1) / cell, (e1 - e2) / cell
        r = np.arctan2(s2, s1)
        s = np.hypot(s1, s2)
        neg = r < 0
        r = np.where(neg, 0.0, r)
        s = np.where(neg, s1, s)
        big = r > q
        r = np.where(big, q, r)
        s = np.where(big, (z - e2) / (cell * math.sqrt(2)), s)
        s = np.where(np.isnan(s), -1.0, s)
        better = (s > best_s) & valid
        best_s[better], best_r[better], best_f[better] = s[better], r[better], f
    has = best_f >= 0
    fi = np.maximum(best_f, 0)
    i1 = np.array([f[0] for f in _FACETS])[fi]
    i2 = np.array([f[1] for f in _FACETS])[fi]
    ac = np.array([f[2] for f in _FACETS])[fi]
    af = np.array([f[3] for f in _FACETS])[fi]
    wd = np.clip(best_r / q, 0, 1)
    wc = 1.0 - wd
    r, c = _flat_nb(ny, nx)
    rc = np.full((2, z.size), -1, dtype=np.int32)
    rw = np.zeros((2, z.size), dtype=np.float32)
    ok1 = has & (wc > 1e-9)
    ok2 = has & (wd > 1e-9)
    rc[0] = np.where(ok1, (r + D8_DR[i1]) * nx + (c + D8_DC[i1]), -1).ravel()
    rc[1] = np.where(ok2, (r + D8_DR[i2]) * nx + (c + D8_DC[i2]), -1).ravel()
    rw[0], rw[1] = np.where(ok1, wc, 0).ravel(), np.where(ok2, wd, 0).ravel()
    # penerima utama (slot 0) harus ada bila ada aliran: bila hanya diagonal, tukar
    only2 = (rc[0] < 0) & (rc[1] >= 0)
    rc[0, only2], rc[1, only2] = rc[1, only2], -1
    rw[0, only2], rw[1, only2] = rw[1, only2], 0
    ang = np.degrees(af * best_r + ac * math.pi / 2.0)          # CCW dari timur
    comp = (90.0 - ang) % 360.0
    comp[~has] = -1.0
    return FlowGraph(z.shape, valid, rc, rw), np.where(valid, comp, np.nan)


_L_CARD, _L_DIAG = 0.5, 0.354


def build_mfd(z, valid, cell, p=1.1, method="quinn"):
    """MFD. 'quinn': bobot = (tanB^p x L) dengan panjang kontur L (Quinn et al. 1991);
    'freeman': bobot = tanB^p (Freeman 1991). Mengembalikan (graf, lebar_kontur_efektif)."""
    ny, nx = z.shape
    zp = np.pad(np.where(valid, z, np.nan), 1, constant_values=np.nan)
    r, c = _flat_nb(ny, nx)
    rc = np.full((8, z.size), -1, dtype=np.int32)
    wts = np.zeros((8, z.size))
    wid = np.zeros(z.shape)
    for d in range(8):
        tan_b = (z - _nbz(zp, d, ny, nx)) / (cell * D8_DIST[d])
        down = (tan_b > 0) & valid
        L = (_L_CARD if d % 2 == 0 else _L_DIAG) * cell if method == "quinn" else cell
        w = np.where(down, np.where(down, tan_b, 0) ** p * (L if method == "quinn" else 1.0), 0.0)
        wts[d] = w.ravel()
        rc[d] = np.where(down, (r + D8_DR[d]) * nx + (c + D8_DC[d]), -1).ravel()
        if method == "quinn":
            wid += np.where(down, L, 0.0)
    tot = wts.sum(0)
    with np.errstate(invalid="ignore", divide="ignore"):
        rw = np.where(tot > 0, wts / tot, 0.0).astype(np.float32)
    if method != "quinn":
        wid = np.full(z.shape, cell)
    # slot 0 = penerima dengan bobot terbesar (dipakai untuk jalur utama)
    order = np.argsort(-rw, axis=0, kind="stable")
    rc = np.take_along_axis(rc, order, 0)
    rw = np.take_along_axis(rw, order, 0)
    return FlowGraph(z.shape, valid, rc, rw), np.where(wid > 0, wid, cell)


# ---------------------------------------------------------------------------
# Jaringan sungai: ekstraksi, orde Strahler, magnitudo Shreve, ruas (link)
# ---------------------------------------------------------------------------
def step_lengths(code, cell):
    """Panjang langkah ke penerima D8 (m): cell (kardinal) atau cell*sqrt2 (diagonal)."""
    out = np.zeros(code.shape)
    for d in range(8):
        out[code == D8_CODE[d]] = cell * D8_DIST[d]
    return out.ravel()


def strahler_shreve(g, stream):
    """Orde Strahler (1957) dan magnitudo Shreve (1967) pada sel sungai. `stream` datar bool."""
    N = g.N
    rec = g.rc[0]
    to_stream = stream & (rec >= 0)
    to_stream[to_stream] = stream[rec[to_stream]]
    n_in = np.bincount(rec[to_stream], minlength=N)
    mo = np.zeros(N, dtype=np.int32)       # orde maksimum dari hulu
    mc = np.zeros(N, dtype=np.int32)       # banyaknya hulu dengan orde maksimum
    order = np.zeros(N, dtype=np.int32)
    for cur in g.levels:
        cs = cur[stream[cur]]
        if not cs.size:
            continue
        o = np.where(n_in[cs] == 0, 1, mo[cs] + (mc[cs] >= 2))
        order[cs] = o
        r = rec[cs]
        m = (r >= 0) & stream[np.maximum(r, 0)]
        if not m.any():
            continue
        rr, vv = r[m], o[m]
        old = mo[rr].copy()
        np.maximum.at(mo, rr, vv)
        chg = np.unique(rr[mo[rr] > old])
        mc[chg] = 0
        eq = vv == mo[rr]
        np.add.at(mc, rr[eq], 1)
    init = (stream & (n_in == 0)).astype(np.float64)
    shreve = g.accumulate(init)
    shreve[~stream] = 0
    return order, shreve, n_in


def build_links(g, stream, order, shreve, n_in, step, z):
    """Pecah jaringan menjadi ruas (link) antara sumber/pertemuan. Mengembalikan
    (daftar ruas, id ruas per sel [0 = bukan sungai])."""
    N = g.N
    rec = g.rc[0]
    node = stream & ((n_in == 0) | (n_in >= 2))
    starts = np.flatnonzero(node)
    link_of_node = np.zeros(N, dtype=np.int32)
    link_of_node[starts] = np.arange(1, starts.size + 1)
    cur, lid = starts.copy(), np.arange(1, starts.size + 1)
    rows_l, rows_s, rows_c = [lid], [np.zeros(lid.size, dtype=np.int32)], [cur]
    step_no = 0
    while cur.size:
        nxt = rec[cur]
        go = (nxt >= 0)
        go[go] = stream[nxt[go]]
        cur2, lid2 = nxt[go], lid[go]
        if not cur2.size:
            break
        step_no += 1
        rows_l.append(lid2)
        rows_s.append(np.full(lid2.size, step_no, dtype=np.int32))
        rows_c.append(cur2)
        stop = node[cur2]
        cur, lid = cur2[~stop], lid2[~stop]
    L, S, C = np.concatenate(rows_l), np.concatenate(rows_s), np.concatenate(rows_c)
    o = np.lexsort((S, L))
    L, S, C = L[o], S[o], C[o]
    bounds = np.flatnonzero(np.diff(L)) + 1
    cell_paths = np.split(C, bounds)
    link_cell = np.zeros(N, dtype=np.int32)
    links = []
    for i, path in enumerate(cell_paths):
        k = i + 1
        end = path[-1]
        own = path if not (node[end] and path.size > 1) else path[:-1]
        link_cell[own] = k
        ln = float(step[path[:-1]].sum()) if path.size > 1 else 0.0
        nxt_link = int(link_of_node[end]) if (node[end] and path.size > 1) else 0
        links.append(dict(id=k, cells=path, order=int(order[path[0]]), shreve=int(shreve[path[0]]),
                          length=ln, down=nxt_link, z_start=float(z[path[0]]), z_end=float(z[end])))
    return links, link_cell


def local_catchments(g, link_cell):
    """Setiap sel diberi id ruas sungai tempat air dari sel itu masuk (DAS lokal tiap ruas)."""
    lab = link_cell.astype(np.int32).copy()
    rec = g.rc[0]
    for cur in reversed(g.levels):
        r = rec[cur]
        m = (lab[cur] == 0) & (r >= 0)
        lab[cur[m]] = lab[r[m]]
    return lab


def merge_by_order(links, lab, min_order):
    """Sub-DAS: gabungkan DAS lokal ruas berorde < min_order ke ruas hilir berorde >= min_order."""
    target = np.zeros(len(links) + 1, dtype=np.int32)
    for lk in links:                       # urutan id tidak topologis -> telusuri ke hilir
        k = lk["id"]
        seen = 0
        while k and links[k - 1]["order"] < min_order and seen < len(links) + 2:
            k = links[k - 1]["down"]
            seen += 1
        target[lk["id"]] = k if k else lk["id"]
    return target[lab]


# ---------------------------------------------------------------------------
# DAS dari titik outlet (pour point)
# ---------------------------------------------------------------------------
def snap_pour_point(acc, valid, r, c, radius_cells):
    ny, nx = acc.shape
    r0, r1 = max(0, r - radius_cells), min(ny, r + radius_cells + 1)
    c0, c1 = max(0, c - radius_cells), min(nx, c + radius_cells + 1)
    win = np.where(valid[r0:r1, c0:c1], acc[r0:r1, c0:c1], -1)
    i = np.unravel_index(np.argmax(win), win.shape)
    return r0 + i[0], c0 + i[1]


def basins_from_points(g, pour_cells):
    """Label DAS inkremental (sel -> titik outlet terdekat di hilir) dan induk bersarang."""
    lab = np.zeros(g.N, dtype=np.int32)
    for i, p in enumerate(pour_cells, start=1):
        lab[p] = i
    rec = g.rc[0]
    for cur in reversed(g.levels):
        r = rec[cur]
        m = (lab[cur] == 0) & (r >= 0)
        lab[cur[m]] = lab[r[m]]
    parent = {}
    for i, p in enumerate(pour_cells, start=1):
        r = rec[p]
        parent[i] = int(lab[r]) if r >= 0 else 0
    return lab, parent


def full_basin_mask(lab, parent, i):
    """DAS penuh titik i = label i + label semua titik di hulunya (bersarang)."""
    members = {i}
    changed = True
    while changed:
        changed = False
        for j, pj in parent.items():
            if pj in members and j not in members:
                members.add(j)
                changed = True
    return np.isin(lab, list(members))


# ---------------------------------------------------------------------------
# HAND dan jarak ke sungai
# ---------------------------------------------------------------------------
def hand_and_distance(g, z, stream, step):
    """HAND = elevasi sel - elevasi sel sungai tempat jalur alirannya bermuara (Renno et al. 2008;
    Nobre et al. 2011). Juga jarak aliran ke sungai (m). NaN bila jalur tidak mencapai sungai."""
    ref = g.propagate_down(z.ravel(), stop_mask=stream)
    hand = z.ravel() - ref
    dist = np.full(g.N, np.nan)
    rec = g.rc[0]
    dist[stream] = 0.0
    for cur in reversed(g.levels):
        r = rec[cur]
        m = (r >= 0) & ~stream[cur]
        dist[cur[m]] = dist[r[m]] + step[cur[m]]
    hand = np.where(np.isnan(ref), np.nan, np.maximum(hand, 0.0))
    return hand.reshape(z.shape), dist.reshape(z.shape)
