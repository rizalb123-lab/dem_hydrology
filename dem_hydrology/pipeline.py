# -*- coding: utf-8 -*-
"""
Pipeline: menjalankan analisis terpilih secara malas (lazy). Setiap keluaran antara
(DEM terisi, D8, akumulasi, sungai, HAND, dst.) dihitung sekali lalu dipakai bersama,
sehingga analisis turunan otomatis memicu prasyaratnya.
"""
from .i18n import tr
import os
import time
import traceback

import numpy as np

from . import core_terrain as T, core_flow as F, core_indices as I, styles as S, registry as R
from . import qgis_io as Q
from .pipeline_basin import BasinMixin


class Out:
    """Satu keluaran: raster, vektor, atau tabel."""

    def __init__(self, analysis, key, title, kind):
        self.analysis, self.key, self.title, self.kind = analysis, key, title, kind
        self.arr = None
        self.style = None
        self.stats = {}
        self.classes = []
        self.path = None
        self.layer = None
        self.extra = {}
        self.unit = ""
        self.n_features = 0


class Pipeline(BasinMixin):
    def __init__(self, domain, params, selected, outdir, pour_layer=None, pour_name_field=None,
                 log=None, progress=None, load_layers=True):
        self.d = domain
        self.par = params                       # {'core': {...}, '<analisis>': {...}}
        self.sel = [k for k in R.ANALYSES if k in selected]
        self.outdir = outdir
        self.pour_layer, self.pour_name_field = pour_layer, pour_name_field
        self.log = log or (lambda m: None)
        self.progress = progress or (lambda f, m: None)
        self.load_layers = load_layers
        self.cache = {}
        self.outs = []
        self.warnings = []
        self.status = {}
        self.timing = {}
        os.makedirs(outdir, exist_ok=True)
        self.cell = domain.cell
        self.shape = domain.shape
        self.N = domain.shape[0] * domain.shape[1]
        self.inside = domain.inside                     # dalam batas & DEM valid
        self.core = params.get("core", {})
        self._seq = 0

    # ------------------------------------------------------------------ util
    def p(self, key):
        d = dict(R.defaults().get(key, {}))
        d.update(self.par.get(key, {}))
        return d

    def memo(self, name, fn):
        if name not in self.cache:
            t = time.time()
            self.cache[name] = fn()
            self.timing[name] = time.time() - t
        return self.cache[name]

    def warn(self, msg):
        self.warnings.append(msg)
        self.log(tr("PERINGATAN: ") + msg)

    @property
    def z(self):
        return self.d.z

    @property
    def valid(self):
        return self.d.valid

    # ------------------------------------------------ keluaran antara (bersama)
    def filled(self):
        def f():
            self.log(tr("Mengisi cekungan (Priority-Flood)..."))
            return T.fill_sinks(self.z, self.valid, self.cell, self.core.get("fill_slope_deg", 0.01),
                                lambda fr: self.progress(None, ""))
        return self.memo("filled", f)

    def filled_exact(self):
        return self.memo("filled_exact", lambda: T.fill_sinks(self.z, self.valid, self.cell, 0.0))

    def terrain(self):
        return self.memo("terrain", lambda: T.slope_aspect(self.z, self.valid, self.cell))

    def d8(self):
        def f():
            self.log(tr("Membangun arah aliran D8..."))
            g, code, tb = F.build_d8(self.filled(), self.valid, self.cell)
            if g.cyclic:
                raise RuntimeError("Graf aliran D8 mengandung siklus; periksa DEM.")
            return g, code.reshape(self.shape), tb
        return self.memo("d8", f)

    def acc8(self):
        return self.memo("acc8", lambda: self.d8()[0].accumulate())

    def acc8_ha(self):
        return self.acc8().reshape(self.shape) * self.cell ** 2 / 1e4

    def step(self):
        return self.memo("step", lambda: F.step_lengths(self.d8()[1], self.cell))

    def stream(self):
        def f():
            thr = self.core.get("stream_thr_ha", 25.0)
            s = (self.acc8() * self.cell ** 2 / 1e4 >= thr) & self.valid.ravel()
            if not s.any():
                self.warn(tr("Tidak ada sel sungai pada ambang %.1f ha; turunkan ambang luas tangkapan.") % thr)
            return s
        return self.memo("stream", f)

    def order(self):
        return self.memo("order", lambda: F.strahler_shreve(self.d8()[0], self.stream()))

    def links(self):
        def f():
            order, shreve, n_in = self.order()
            return F.build_links(self.d8()[0], self.stream(), order, shreve, n_in, self.step(),
                                 self.filled().ravel())
        return self.memo("links", f)

    def hand(self):
        def f():
            self.log(tr("Menghitung HAND dan jarak ke sungai..."))
            z = np.where(self.valid, self.z, 0.0)
            return F.hand_and_distance(self.d8()[0], z, self.stream(), self.step())
        return self.memo("hand", f)

    def dinf(self):
        def f():
            self.log(tr("Menghitung D-infinity..."))
            g, ang = F.build_dinf(self.filled(), self.valid, self.cell)
            acc = g.accumulate().reshape(self.shape)
            return g, ang, acc
        return self.memo("dinf", f)

    def mfd(self):
        def f():
            pr = self.p("flow_mfd")
            self.log(tr("Menghitung MFD (%s, p=%.2f)...") % (pr["method"], pr["p"]))
            g, wid = F.build_mfd(self.filled(), self.valid, self.cell, pr["p"], pr["method"])
            acc = g.accumulate().reshape(self.shape)
            return g, wid, acc
        return self.memo("mfd", f)

    def sca(self, source):
        """Luas tangkapan spesifik (m2/m)."""
        c = self.cell
        if source == "d8":
            return self.acc8().reshape(self.shape) * c
        if source == "dinf":
            return self.dinf()[2] * c
        pr = self.p("flow_mfd")
        # untuk indeks turunan selalu pakai pengaturan MFD pengguna
        _, wid, acc = self.mfd()
        return acc * c * c / wid

    def tanb(self):
        return self.terrain()[3]

    def drainage_density_arr(self):
        def f():
            pr = self.p("drainage_density")
            sl = np.where(self.stream().reshape(self.shape), self.step().reshape(self.shape), 0.0)
            return I.drainage_density(sl, self.valid, self.cell, pr["radius_m"])
        return self.memo("dd", f)

    def travel(self):
        def f():
            pr = self.p("travel_time")
            self.log(tr("Menghitung waktu tempuh..."))
            g, code, tb = self.d8()
            return I.travel_time(g, tb, self.stream(), self.step(), pr["k_hill"], pr["manning_n"],
                                 pr["hyd_radius"], pr["s_min"]).reshape(self.shape)
        return self.memo("travel", f)

    # ------------------------------------------------------------ pencatat keluaran
    def _clip(self, arr):
        a = np.array(arr, dtype=np.float64)
        a[~self.inside] = np.nan
        return a

    def raster(self, analysis, key, title, arr, dtype="float32", style=None, zero_nodata=False,
               params=None, extra_stats=True):
        o = Out(analysis, key, title, "raster")
        a = np.array(arr, dtype=np.float64)
        if zero_nodata:
            a = np.where(a > 0, a, np.nan)
        a_in = self._clip(a)
        if not np.isfinite(a_in).any():
            self.warn(tr("Keluaran '%s' kosong (tidak ada nilai di dalam batas studi, misalnya tidak ada area yang "
                      "memenuhi syarat) sehingga tidak disimpan.") % title)
            return None
        o.arr = a_in
        o.style = style or S.style_for(key, a_in, self.inside, params if params is not None else self.p(analysis),
                                       self.cell)
        o.unit = o.style.get("unit", "")
        if extra_stats:
            o.stats = I.cont_stats(a_in, self.inside)
            if o.style["type"] in ("discrete", "paletted"):
                o.classes = S.class_table(a_in, self.inside, self.cell, o.style)
        self._seq += 1
        o.path = os.path.join(self.outdir, tr("%02d_%s.tif") % (self._seq, key))
        nd = -9999.0 if dtype == "float32" else -32768 if dtype != "byte" else 255
        Q.write_raster(o.path, a, self.d, nodata=nd, dtype=dtype)
        if self.load_layers:
            from qgis.core import QgsRasterLayer
            lyr = QgsRasterLayer(o.path, title)
            if lyr.isValid():
                vals = o.stats
                Q.style_raster(lyr, o.style, vals.get("min"), vals.get("max"))
                Q.add_to_project(lyr)
                o.layer = lyr
        self.outs.append(o)
        return o

    def table(self, analysis, key, title, rows, extra=None):
        o = Out(analysis, key, title, "table")
        o.extra = extra or {}
        o.extra["rows"] = rows
        o.n_features = len(rows)
        self.outs.append(o)
        return o

    # ------------------------------------------------------------ eksekusi
    def run(self):
        runners = self.runners()
        todo = [k for k in self.sel if k in runners]
        n = len(todo)
        for i, k in enumerate(todo):
            a = R.L()["ANALYSES"][k]
            self.progress(i / max(n, 1), "%s (%d/%d)" % (a["name"], i + 1, n))
            self.log("== %s" % a["name"])
            t = time.time()
            try:
                runners[k]()
                self.status[k] = "ok"
            except InterruptedError:
                raise
            except Exception as e:
                self.status[k] = tr("gagal: %s") % e
                self.log(tr("GAGAL %s: %s\n%s") % (k, e, traceback.format_exc()))
                self.warnings.append(tr("Analisis '%s' gagal: %s") % (a["name"], e))
            self.timing["run_" + k] = time.time() - t
        self.progress(1.0, tr("Selesai"))
        return self.outs

    def runners(self):
        m = {
            "fill": self.r_fill, "depressions": self.r_depressions, "slope": self.r_slope,
            "aspect": self.r_aspect, "hillshade": self.r_hillshade, "curvature": self.r_curvature,
            "tpi": self.r_tpi, "tri": self.r_tri, "landform": self.r_landform,
            "flow_dir_d8": self.r_dir8, "flow_acc_d8": self.r_acc8, "flow_dinf": self.r_dinf,
            "flow_mfd": self.r_mfd, "flow_length": self.r_flowlen, "twi": self.r_twi, "spi": self.r_spi,
            "sti": self.r_sti, "ls": self.r_ls, "hand": self.r_hand,
            "drainage_density": self.r_dd, "travel_time": self.r_travel, "hand_flood": self.r_handflood,
            "bathtub": self.r_bathtub, "flood_index": self.r_flood, "recharge_index": self.r_recharge,
            "erosion_index": self.r_erosion,
        }
        m.update(self.basin_runners())
        return m

    # ---------------------------------------------------------------- pra-proses
    def r_fill(self):
        zf = self.filled()
        o = self.raster("fill", "filled_dem", "Filled DEM (Conditioned)", zf)
        if o is None:
            return
        diff = np.where(self.valid, zf - self.z, 0.0)
        o.extra["max_rise_m"] = float(np.nanmax(diff[self.inside])) if self.inside.any() else 0.0
        o.extra["mean_rise_m"] = float(np.nanmean(diff[self.inside]))
        if o.extra["max_rise_m"] > 5.0:
            self.warn(tr("Pengisian cekungan menaikkan elevasi hingga %.1f m; periksa DEM (cekungan besar/danau).") %
                      o.extra["max_rise_m"])

    def r_depressions(self):
        pr = self.p("depressions")
        depth, lab, rows = T.depression_analysis(self.z, self.filled_exact(), self.valid, self.cell, pr["min_depth"])
        self.raster("depressions", "sink_depth", "Sink Depth", depth, zero_nodata=True)
        self.depression_polygons(lab, depth)

    # ---------------------------------------------------------------- terrain
    def r_slope(self):
        pr = self.p("slope")
        sp = self.terrain()[0]
        br = S.parse_floats(pr["breaks"], [8, 15, 25, 45])
        self.raster("slope", "slope_pct", "Slope (%)", sp, params=pr)
        cls = T.classify(sp, br, self.valid)
        st = S.style_for("slope_class", None, None, pr, self.cell)
        if len(br) == 4:
            lab = S.style_for("slope_pct", sp, None, pr, self.cell)["items"]
            for it, l in zip(st["items"], lab):
                it["label"] = l["label"]
        self.raster("slope", "slope_class", "Slope Class", np.where(cls > 0, cls, np.nan), dtype="int16", style=st)

    def r_aspect(self):
        self.raster("aspect", "aspect", "Aspect", self.terrain()[2])

    def r_hillshade(self):
        pr = self.p("hillshade")
        self.raster("hillshade", "hillshade", "Hillshade",
                    T.hillshade(self.z, self.valid, self.cell, pr["azimuth"], pr["altitude"], pr["z_factor"]),
                    extra_stats=False)

    def r_curvature(self):
        prof, plan = T.curvature(self.z, self.valid, self.cell)
        o = self.raster("curvature", "profile_curvature", "Profile Curvature", prof)
        if o is None:
            return
        o.style["title"] = "Profile Curvature (100/m)"
        o2 = self.raster("curvature", "plan_curvature", "Plan Curvature", plan)
        if o2 is None:
            return
        o2.style["title"] = "Plan Curvature (100/m)"

    def r_tpi(self):
        self.raster("tpi", "tpi", "Topographic Position Index (TPI)",
                    T.tpi(self.z, self.valid, self.cell, self.p("tpi")["radius_m"]))

    def r_tri(self):
        self.raster("tri", "tri", "Terrain Ruggedness Index (TRI)", T.tri(self.z, self.valid, self.cell))

    def r_landform(self):
        pr = self.p("landform")
        sd = self.terrain()[1]
        lf = T.landform_tpi(self.z, self.valid, self.cell, pr["r_small"], pr["r_large"], sd, pr["flat_deg"])
        self.raster("landform", "landform", "Landform Classification (TPI)", np.where(lf > 0, lf, np.nan),
                    dtype="int16")

    # ---------------------------------------------------------------- aliran
    def r_dir8(self):
        code = self.d8()[1].astype(float)
        self.raster("flow_dir_d8", "flow_dir_d8", "Flow Direction (D8)", np.where(code > 0, code, np.nan),
                    dtype="int16")

    def r_acc8(self):
        a = np.where(self.valid, self.acc8_ha(), np.nan)
        self.raster("flow_acc_d8", "catchment_area_d8", "Catchment Area (D8)", a)

    def r_dinf(self):
        g, ang, acc = self.dinf()
        a = np.where(self.terrain()[3] < 1e-9, -1.0, ang)
        self.raster("flow_dinf", "dinf_angle", "D-Infinity Flow Direction", np.where(self.valid, ang, np.nan))
        self.raster("flow_dinf", "dinf_sca", "D-Infinity Specific Catchment Area",
                    np.where(self.valid, acc * self.cell, np.nan))

    def r_mfd(self):
        g, wid, acc = self.mfd()
        self.raster("flow_mfd", "mfd_area", "Catchment Area (MFD)",
                    np.where(self.valid, acc * self.cell ** 2 / 1e4, np.nan))
        self.raster("flow_mfd", "mfd_sca", "Specific Catchment Area (MFD)",
                    np.where(self.valid, acc * self.cell ** 2 / wid, np.nan))

    def r_flowlen(self):
        g = self.d8()[0]
        st = self.step()
        dl = g.downstream_sum(st).reshape(self.shape)
        up = g.upstream_max(st).reshape(self.shape)
        self.cache["dl"], self.cache["up"] = dl.ravel(), up.ravel()
        self.raster("flow_length", "flow_len_down", "Flow Length (Downstream)", np.where(self.valid, dl, np.nan))
        self.raster("flow_length", "flow_len_up", "Flow Length (Upstream, longest)", np.where(self.valid, up, np.nan))

    # ---------------------------------------------------------------- indeks
    def r_twi(self):
        pr = self.p("twi")
        t = I.twi(self.sca(pr["sca_source"]), self.tanb(), pr["tan_min"])
        self.raster("twi", "twi", "Topographic Wetness Index (TWI)", np.where(self.valid, t, np.nan))

    def r_spi(self):
        pr = self.p("spi")
        self.raster("spi", "spi", "Stream Power Index (SPI)",
                    np.where(self.valid, I.spi(self.sca(pr["sca_source"]), self.tanb()), np.nan))

    def r_sti(self):
        pr = self.p("sti")
        self.raster("sti", "sti", "Sediment Transport Index (STI)",
                    np.where(self.valid, I.sti(self.sca(pr["sca_source"]), self.tanb()), np.nan))

    def ls_arr(self):
        def f():
            pr = self.p("ls")
            ls = I.ls_factor(self.acc8().reshape(self.shape), self.cell, self.tanb(), self.d8()[1],
                             pr["s_method"], pr["ls_max"])
            return np.where(self.valid, ls, np.nan)
        return self.memo("ls", f)

    def r_ls(self):
        self.raster("ls", "ls_factor", "LS Factor (RUSLE)", self.ls_arr())

    def r_hand(self):
        hand, fd = self.hand()
        self.raster("hand", "hand", "Height Above Nearest Drainage (HAND)", hand)
        self.raster("hand", "flow_dist_stream", "Flow Distance to Stream", fd)
        from scipy import ndimage as ndi
        e = ndi.distance_transform_edt(~self.stream().reshape(self.shape)) * self.cell
        self.raster("hand", "euclid_dist_stream", "Euclidean Distance to Stream", np.where(self.valid, e, np.nan))

    def r_dd(self):
        self.raster("drainage_density", "drainage_density", "Drainage Density", self.drainage_density_arr())

    def r_travel(self):
        tt = self.travel()
        o = self.raster("travel_time", "travel_time", tr("Travel Time / Isochrone (menit)"), np.where(self.valid, tt, np.nan))
        if o is None:
            return
        pr = self.p("travel_time")
        ta = I.time_area_histogram(tt.ravel(), self.inside.ravel(), self.cell, pr["bin_min"])
        o.extra["time_area"] = {tr("Seluruh area studi"): ta}
        self.cache["time_area_whole"] = ta
        if self.pour_layer is not None and "watershed_points" in self.sel:
            try:
                w = self.ws_data()
                t = tt.ravel()
                for i, m in enumerate(w["masks"]):
                    rel = t[m] - t[w["cells"][i]]
                    full = np.full(self.N, np.nan)
                    full[m] = np.maximum(rel, 0.0)
                    o.extra["time_area"][w["names"][i]] = I.time_area_histogram(full, m, self.cell, pr["bin_min"])
            except Exception as e:
                self.warn(tr("Time-area per DAS dilewati: %s") % e)

    # ---------------------------------------------------------------- genangan
    def r_handflood(self):
        pr = self.p("hand_flood")
        hand = self.hand()[0]
        st = sorted(S.parse_floats(pr["stages"], [1, 2, 5, 10]))
        first = np.full(self.shape, np.nan)
        for i in range(len(st) - 1, -1, -1):
            first = np.where(hand <= st[i], i + 1, first)
        o = self.raster("hand_flood", "hand_flood", "HAND Flood Inundation Zones", first, dtype="int16",
                        params=dict(pr, stages=",".join(str(x) for x in st)))
        if o is None:
            return
        rows = []
        for s in st:
            dep = I.hand_inundation(hand, s)
            m = self.inside & (dep > 0)
            rows.append(dict(muka_air_m=s, luas_ha=float(m.sum() * self.cell ** 2 / 1e4),
                             persen=float(100.0 * m.sum() / max(self.inside.sum(), 1)),
                             kedalaman_rata2_m=float(dep[m].mean()) if m.any() else 0.0,
                             volume_m3=float(dep[m].sum() * self.cell ** 2)))
        o.extra["stage_table"] = rows
        if not self.stream().any():
            self.warn(tr("HAND flood: tidak ada sungai, hasil kosong."))

    def r_bathtub(self):
        pr = self.p("bathtub")
        dep = I.bathtub(self.z, self.valid, pr["level"], bool(pr["connected"]))
        o = self.raster("bathtub", "bathtub", "Bathtub Inundation Depth", dep, zero_nodata=True)
        m = self.inside & (dep > 0)
        if o is None:
            return
        o.extra["summary"] = dict(level_m=pr["level"], luas_ha=float(m.sum() * self.cell ** 2 / 1e4),
                                  volume_m3=float(dep[m].sum() * self.cell ** 2),
                                  persen=float(100.0 * m.sum() / max(self.inside.sum(), 1)))

    # ---------------------------------------------------------------- komposit
    def _w(self, pr, keys):
        return {k: pr.get("w_" + k, 1.0) for k in keys}

    def r_flood(self):
        pr = self.p("flood_index")
        hand, fd = self.hand()
        twi = I.twi(self.sca("mfd"), self.tanb())
        facs = {"hand": (hand, True), "slope": (self.terrain()[0], True), "twi": (twi, False),
                "acc": (np.log10(np.maximum(self.acc8().reshape(self.shape), 1)), False), "dist": (fd, True)}
        sc = I.composite(facs, self._w(pr, facs), self.inside)
        o = self.raster("flood_index", "flood_index", "Topographic Flood Susceptibility Index", sc)
        if o is None:
            return
        o.extra["weights"] = self._w(pr, facs)

    def r_recharge(self):
        pr = self.p("recharge_index")
        twi = I.twi(self.sca("mfd"), self.tanb())
        facs = {"slope": (self.terrain()[0], True), "twi": (twi, False),
                "dd": (self.drainage_density_arr(), True), "tri": (T.tri(self.z, self.valid, self.cell), True)}
        sc = I.composite(facs, self._w(pr, facs), self.inside)
        o = self.raster("recharge_index", "recharge_index", "Topographic Recharge Potential Index", sc)
        if o is None:
            return
        o.extra["weights"] = self._w(pr, facs)

    def r_erosion(self):
        pr = self.p("erosion_index")
        sca = self.sca("mfd")
        facs = {"ls": (self.ls_arr(), False), "spi": (np.log10(1.0 + I.spi(sca, self.tanb())), False),
                "slope": (self.terrain()[0], False)}
        sc = I.composite(facs, self._w(pr, facs), self.inside)
        o = self.raster("erosion_index", "erosion_index", "Topographic Erosion Susceptibility Index", sc)
        if o is None:
            return
        o.extra["weights"] = self._w(pr, facs)
