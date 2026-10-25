# -*- coding: utf-8 -*-
"""Bagian pipeline untuk jaringan sungai, sub-DAS, DAS titik, depresi, dan morfometri."""
from .i18n import tr
import os

import numpy as np

from . import core_flow as F, core_indices as I, styles as S
from . import qgis_io as Q

PASTEL = ["#8dd3c7", "#ffffb3", "#bebada", "#fb8072", "#80b1d3", "#fdb462", "#b3de69", "#fccde5",
          "#d9d9d9", "#bc80bd", "#ccebc5", "#ffed6f"]


def _wkb(name):
    from qgis.core import QgsWkbTypes
    return getattr(QgsWkbTypes, name)


class BasinMixin:
    # ------------------------------------------------------------ pembantu vektor
    def vector(self, analysis, key, title, wkb, fields, rows, styler=None, style_spec=None):
        from .pipeline import Out
        o = Out(analysis, key, title, "vector")
        o.style = style_spec or {}
        self._seq += 1
        o.path = os.path.join(self.outdir, tr("%02d_%s.gpkg") % (self._seq, key))
        o.n_features = Q.write_vector(o.path, key, wkb, self.d.crs, fields, rows)
        if self.load_layers:
            from qgis.core import QgsVectorLayer
            lyr = QgsVectorLayer(tr("%s|layername=%s") % (o.path, key), title, "ogr")
            if lyr.isValid():
                if styler:
                    styler(lyr)
                Q.add_to_project(lyr)
                o.layer = lyr
        self.outs.append(o)
        return o

    def basin_runners(self):
        return {"stream_network": self.r_streams, "subbasins": self.r_sub,
                "watershed_points": self.r_ws, "basin_morphometry": self.r_morph}

    # ------------------------------------------------------------ depresi
    def depression_polygons(self, lab, depth):
        d = self.d
        geoms = Q.clip_geoms(Q.polygonize(lab, d, window=d.win), d)
        n = int(lab.max())
        cnt = np.bincount(lab.ravel(), minlength=n + 1)
        vol = np.bincount(lab.ravel(), weights=np.where(lab > 0, depth, 0.0).ravel(), minlength=n + 1)
        dmax = np.zeros(n + 1)
        np.maximum.at(dmax, lab.ravel(), np.where(lab > 0, depth, 0.0).ravel())
        rows = []
        for k, g in geoms.items():
            c = max(cnt[k], 1)
            rows.append((g, [int(k), float(cnt[k] * self.cell ** 2), float(dmax[k]), float(vol[k] / c),
                             float(vol[k] * self.cell ** 2)]))
        rows.sort(key=lambda r: -r[1][4])
        rows = rows[:5000]
        o = self.vector("depressions", "depressions", "Depressions (Polygon)", _wkb("MultiPolygon"),
                        [("id", "int"), ("area_m2", "double"), ("depth_max", "double"), ("depth_mean", "double"),
                         ("volume_m3", "double")], rows,
                        styler=lambda l: Q.style_single_polygon(l, "#ef5350", "#8e0000"),
                        style_spec=dict(type="polygon", items=[dict(label="Cekungan (depresi)", color="#ef5350")]))
        o.stats = dict(jumlah=len(rows), luas_total_ha=sum(r[1][1] for r in rows) / 1e4,
                       volume_total_m3=sum(r[1][4] for r in rows),
                       kedalaman_maks_m=max([r[1][2] for r in rows], default=0.0))
        o.extra["rows"] = [dict(id=r[1][0], luas_m2=r[1][1], kedalaman_maks_m=r[1][2], kedalaman_rata2_m=r[1][3],
                                volume_m3=r[1][4]) for r in rows[:50]]

    # ------------------------------------------------------------ jaringan sungai
    def stream_geoms(self):
        """Geometri ruas sungai (dipangkas ke batas) dan panjang ruas di dalam batas."""
        def f():
            from qgis.core import QgsGeometry, QgsPointXY
            links, link_cell = self.links()
            d = self.d
            ins = d.inside_all.ravel()
            acc = self.acc8()
            z = self.filled().ravel()
            out = []
            for lk in links:
                path = lk["cells"]
                if path.size < 2:
                    continue
                m = ins[path]
                if not m.any():
                    continue
                xs, ys = Q.xy(d, path)
                g = QgsGeometry.fromPolylineXY([QgsPointXY(x, y) for x, y in zip(xs, ys)])
                L = lk["length"]
                if not m.all():
                    g = g.intersection(d.boundary_geom)
                    if g is None or g.isEmpty():
                        continue
                    L = g.length()
                last = path[-2] if lk["down"] > 0 else path[-1]
                slope = (lk["z_start"] - lk["z_end"]) / lk["length"] * 100.0 if lk["length"] > 0 else 0.0
                out.append(dict(lk=lk, geom=g, len_in=L, up_ha=float(acc[last] * self.cell ** 2 / 1e4),
                                slope=slope))
            return out
        return self.memo("stream_geoms", f)

    def r_streams(self):
        order, shreve, _ = self.order()
        st = self.stream()
        self.raster("stream_network", "strahler_raster", "Strahler Order",
                    np.where(st, order, 0).reshape(self.shape).astype(float), dtype="int16", zero_nodata=True)
        self.raster("stream_network", "shreve_raster", "Shreve Magnitude",
                    np.where(st, shreve, 0).reshape(self.shape), dtype="int32", zero_nodata=True)
        sg = self.stream_geoms()
        rows = [(s["geom"], [s["lk"]["id"], s["lk"]["order"], s["lk"]["shreve"], float(s["len_in"]), s["up_ha"],
                             float(s["slope"]), s["lk"]["down"]]) for s in sg]
        spec = dict(type="lines", title="Strahler Order",
                    items=[dict(label=tr("Orde %d") % k, color=S.ORDER_COLORS[min(k - 1, 6)],
                                width=S.ORDER_WIDTH[min(k - 1, 6)]) for k in sorted({s["lk"]["order"] for s in sg})])
        o = self.vector("stream_network", "stream_lines", "Stream Network (Strahler Order)", _wkb("MultiLineString"),
                        [("link_id", "int"), ("strahler", "int"), ("shreve", "int"), ("length_m", "double"),
                         ("up_area_ha", "double"), ("slope_pct", "double"), ("down_id", "int")], rows,
                        styler=lambda l: Q.style_streams(l, S.ORDER_COLORS, S.ORDER_WIDTH), style_spec=spec)
        area_km2 = self.inside.sum() * self.cell ** 2 / 1e6
        byo = {}
        for s in sg:
            e = byo.setdefault(s["lk"]["order"], dict(n=0, len=0.0))
            e["n"] += 1
            e["len"] += s["len_in"]
        orders = sorted(byo)
        trows = []
        for i, k in enumerate(orders):
            nxt = byo.get(k + 1)
            trows.append(dict(orde=k, jumlah_ruas=byo[k]["n"], panjang_total_km=byo[k]["len"] / 1000.0,
                              panjang_rata2_km=byo[k]["len"] / 1000.0 / byo[k]["n"],
                              Rb=(byo[k]["n"] / nxt["n"]) if nxt else None))
        tot = sum(v["len"] for v in byo.values()) / 1000.0
        o.extra["orders"] = trows
        o.extra["summary"] = dict(ambang_ha=self.core.get("stream_thr_ha", 25.0), jumlah_ruas=len(sg),
                                  panjang_total_km=tot, orde_maks=max(orders) if orders else 0,
                                  Dd_km_km2=tot / area_km2 if area_km2 > 0 else float("nan"))
        o.stats = o.extra["summary"]
        self.cache["orders_in"] = {s["lk"]["id"]: s["len_in"] for s in sg}

    # ------------------------------------------------------------ sub-DAS
    def subbasin_data(self):
        def f():
            pr = self.p("subbasins")
            links, link_cell = self.links()
            if not links:
                raise ValueError("Tidak ada ruas sungai; turunkan ambang luas tangkapan sungai.")
            lab_local = F.local_catchments(self.d8()[0], link_cell)
            merged = F.merge_by_order(links, lab_local, int(pr["min_order"])).astype(np.int32)
            merged[~self.valid.ravel()] = 0
            d = self.d
            m2 = merged.reshape(self.shape)
            # buang sub-DAS yang tidak menyentuh batas studi
            keep = np.unique(m2[d.inside_all])
            keep = keep[keep > 0]
            m2 = np.where(np.isin(m2, keep), m2, 0)
            geoms = Q.polygonize(m2, d)
            return m2, geoms
        return self.memo("subbasins", f)

    def r_sub(self):
        pr = self.p("subbasins")
        m2, full = self.subbasin_data()
        d = self.d
        links, _ = self.links()
        flat = m2.ravel()
        n = int(flat.max()) + 1
        cnt = np.bincount(flat, minlength=n)
        zf = np.where(self.valid, self.z, 0.0).ravel()
        sl = np.nan_to_num(self.terrain()[0]).ravel()
        zsum = np.bincount(flat, weights=zf, minlength=n)
        ssum = np.bincount(flat, weights=sl, minlength=n)
        rows = []
        for k, g in sorted(full.items()):
            gc = g.intersection(d.boundary_geom)
            if gc is None or gc.isEmpty():
                continue
            c = max(cnt[k], 1)
            od = links[k - 1]["order"]
            per = g.simplify(self.cell).length() / 1000.0
            rows.append((gc, [int(k), int(od), float(cnt[k] * self.cell ** 2 / 1e4), float(gc.area() / 1e4),
                              float(zsum[k] / c), float(ssum[k] / c), float(per)]))
        spec = dict(type="polygon_ids", title=tr("Sub-DAS (Strahler >= %d)") % pr["min_order"],
                    items=[dict(label=tr("Sub-DAS (%d unit)") % len(rows), color=PASTEL[0])])
        o = self.vector("subbasins", "subbasins", "Sub-Watersheds", _wkb("MultiPolygon"),
                        [("id", "int"), ("strahler", "int"), ("area_ha", "double"), ("area_in_ha", "double"),
                         ("mean_elev", "double"), ("mean_slope_pct", "double"), ("perimeter_km", "double")], rows,
                        styler=lambda l: Q.style_polygons_by_id(l, "id", PASTEL), style_spec=spec)
        o.stats = dict(jumlah=len(rows), orde_min=int(pr["min_order"]))
        o.extra["rows"] = [dict(id=r[1][0], strahler=r[1][1], luas_ha=r[1][2], luas_dalam_batas_ha=r[1][3],
                                elev_rata2_m=r[1][4], lereng_rata2_pct=r[1][5], keliling_km=r[1][6]) for r in rows]

    # ------------------------------------------------------------ DAS dari titik
    def ws_data(self):
        def f():
            from qgis.core import QgsCoordinateTransform, QgsProject
            if self.pour_layer is None:
                raise ValueError("Layer titik outlet (pour point) belum dipilih pada tab Data.")
            d = self.d
            pr = self.p("watershed_points")
            xf = None
            if self.pour_layer.crs() != d.crs:
                xf = QgsCoordinateTransform(self.pour_layer.crs(), d.crs, QgsProject.instance())
            rad = int(round(pr["snap_m"] / self.cell))
            acc2 = self.acc8().reshape(self.shape)
            cells, names, moved, accs, pts = [], [], [], [], []
            for i, f_ in enumerate(self.pour_layer.getFeatures()):
                g = f_.geometry()
                if g.isNull() or g.isEmpty():
                    continue
                if xf is not None:
                    g.transform(xf)
                p = g.asPoint() if not g.isMultipart() else g.asMultiPoint()[0]
                r, c = Q.cell_of(d, p.x(), p.y())
                nm = None
                if self.pour_name_field and self.pour_name_field in f_.fields().names():
                    nm = f_[self.pour_name_field]
                nm = str(nm) if nm not in (None, "", "NULL") else tr("Titik %d") % (len(cells) + 1)
                if not (0 <= r < self.shape[0] and 0 <= c < self.shape[1]) or not self.valid[r, c]:
                    self.warn(tr("Titik '%s' berada di luar DEM dan dilewati.") % nm)
                    continue
                r2, c2 = F.snap_pour_point(acc2, self.valid, r, c, rad)
                x2, y2 = Q.xy(d, r2 * self.shape[1] + c2)
                dist = float(np.hypot(x2 - p.x(), y2 - p.y()))
                a_ha = float(acc2[r2, c2] * self.cell ** 2 / 1e4)
                if dist > 0.9 * pr["snap_m"] and pr["snap_m"] > 0:
                    self.warn(tr("Titik '%s' digeser %.0f m ke sungai; periksa posisinya.") % (nm, dist))
                if a_ha < self.core.get("stream_thr_ha", 25.0):
                    self.warn(tr("Titik '%s' berada di sel dengan luas tangkapan %.1f ha (di bawah ambang sungai).") % (nm, a_ha))
                cells.append(r2 * self.shape[1] + c2)
                names.append(nm)
                moved.append(dist)
                accs.append(a_ha)
                pts.append((float(x2), float(y2)))
            if not cells:
                raise ValueError("Tidak ada titik outlet valid di dalam DEM.")
            lab, parent = F.basins_from_points(self.d8()[0], cells)
            masks, geoms = [], []
            for i in range(1, len(cells) + 1):
                m = F.full_basin_mask(lab, parent, i).reshape(self.shape) & self.valid
                rr, cc = np.where(m)
                win = (max(rr.min() - 1, 0), rr.max() + 2, max(cc.min() - 1, 0), cc.max() + 2)
                gg = Q.polygonize(m.astype(np.int32), d, window=win).get(1)
                masks.append(m.ravel())
                geoms.append(gg)
                if m[0, :].any() or m[-1, :].any() or m[:, 0].any() or m[:, -1].any():
                    self.warn(tr("DAS '%s' menyentuh tepi DEM; perbesar buffer DEM agar DAS utuh.") % names[i - 1])
            return dict(cells=cells, names=names, moved=moved, accs=accs, pts=pts, lab=lab, parent=parent,
                        masks=masks, geoms=geoms)
        return self.memo("ws", f)

    def r_ws(self):
        w = self.ws_data()
        z = self.z.ravel()
        pts_rows = [(self._pt(x, y), [i + 1, w["names"][i], w["accs"][i], w["moved"][i]])
                    for i, (x, y) in enumerate(w["pts"])]
        self.vector("watershed_points", "pour_points", "Pour Points (snapped)", _wkb("Point"),
                    [("id", "int"), ("nama", "string"), ("acc_ha", "double"), ("digeser_m", "double")], pts_rows,
                    styler=Q.style_points,
                    style_spec=dict(type="points", items=[dict(label="Titik outlet (hasil snapping)", color="#d50000")]))
        rows = []
        for i, g in enumerate(w["geoms"]):
            cnt = int(w["masks"][i].sum())
            rows.append((g, [i + 1, w["names"][i], cnt * self.cell ** 2 / 1e4, float(z[w["cells"][i]]),
                             w["parent"][i + 1]]))
        spec = dict(type="polygon_ids", title="DAS dari titik outlet",
                    items=[dict(label=w["names"][i], color=PASTEL[i % len(PASTEL)]) for i in range(len(rows))])
        o = self.vector("watershed_points", "watersheds", "Watersheds", _wkb("MultiPolygon"),
                        [("id", "int"), ("nama", "string"), ("area_ha", "double"), ("elev_outlet", "double"),
                         ("induk_id", "int")], rows,
                        styler=lambda l: Q.style_polygons_by_id(l, "nama", PASTEL, 0.7, 0.5), style_spec=spec)
        o.extra["rows"] = [dict(id=r[1][0], nama=r[1][1], luas_ha=r[1][2], elev_outlet_m=r[1][3], induk=r[1][4])
                           for r in rows]

    def _pt(self, x, y):
        from qgis.core import QgsGeometry, QgsPointXY
        return QgsGeometry.fromPointXY(QgsPointXY(x, y))

    # ------------------------------------------------------------ morfometri
    def r_morph(self):
        d = self.d
        links, _ = self.links()
        g = self.d8()[0]
        st = self.step()
        ctx = dict(shape=self.shape, N=self.N, cell=self.cell, z=np.where(self.valid, self.z, 0.0).ravel(),
                   zf=np.where(self.valid, self.filled(), 0.0), slope_pct=np.nan_to_num(self.terrain()[0]).ravel(),
                   acc=self.acc8(), up=g.upstream_max(st), dl=self.cache.get("dl", g.downstream_sum(st)),
                   rec=g.rc[0], step=st, links=links)
        if not links:
            self.warn(tr("Morfometri hanya memuat data dasar karena tidak ada sungai pada ambang yang dipilih."))
        units = []
        idx_all = np.flatnonzero(self.inside.ravel())
        units.append((tr("Seluruh area studi"), "Area studi", idx_all, d.boundary_geom.length(), False, None))
        if self.pour_layer is not None:
            try:
                w = self.ws_data()
                for i, m in enumerate(w["masks"]):
                    gg = w["geoms"][i]
                    per = gg.simplify(self.cell).length() if gg else None
                    units.append((w["names"][i], "DAS titik outlet", np.flatnonzero(m), per, True, None))
            except Exception as e:
                self.warn(tr("DAS titik outlet tidak ikut morfometri: %s") % e)
        if links:
            m2, full = self.subbasin_data()
            flat = m2.ravel()
            ids, cnt = np.unique(flat[flat > 0], return_counts=True)
            for k, c in sorted(zip(ids, cnt), key=lambda t: -t[1])[:150]:
                units.append((tr("Sub-DAS %d (orde %d)") % (k, links[k - 1]["order"]), "Sub-DAS",
                              np.flatnonzero(flat == k), full[int(k)].simplify(self.cell).length(), True, int(k)))
        rows, detail = [], {}
        dom_edge = np.zeros(self.shape, bool)
        dom_edge[0, :] = dom_edge[-1, :] = dom_edge[:, 0] = dom_edge[:, -1] = True
        edge_flat = dom_edge.ravel()
        for name, kind, idx, per, flow, _k in units:
            if idx.size < 4:
                continue
            m = I.basin_morphometry(idx, ctx, per, flow)
            if kind == "Area studi" and "orders_in" in self.cache:
                self.override_stream_in_boundary(m, idx)
            m["nama"], m["jenis"] = name, kind
            m["menyentuh_tepi_DEM"] = bool(edge_flat[idx].any())
            detail[name] = dict(orders=m.pop("_orders", {}), hypso=m.pop("_hypso", []), profile=m.pop("_profile", None))
            rows.append(m)
        o = self.table("basin_morphometry", "morphometry", "Basin Morphometry and Hypsometry", rows,
                       dict(detail=detail))
        edge = [r["nama"] for r in rows if r["menyentuh_tepi_DEM"] and r["jenis"] != "Area studi"]
        if edge:
            self.warn(tr("%d unit DAS menyentuh tepi DEM sehingga luas/panjangnya bisa terpotong (perbesar buffer): %s") %
                      (len(edge), ", ".join(edge[:5])))

    def override_stream_in_boundary(self, m, idx):
        """Untuk area studi: panjang sungai dihitung hanya di dalam batas (bukan seluruh ruas)."""
        sg = self.stream_geoms()
        byo = {}
        for s in sg:
            e = byo.setdefault(s["lk"]["order"], dict(n=0, len=0.0))
            e["n"] += 1
            e["len"] += s["len_in"]
        A_km = idx.size * self.cell ** 2 / 1e6
        L = sum(v["len"] for v in byo.values()) / 1000.0
        N = sum(v["n"] for v in byo.values())
        m["L_sungai_km"], m["N_ruas"] = L, N
        m["Dd_km_km2"] = L / A_km
        m["Fs_per_km2"] = N / A_km
        m["Infiltration_number"] = m["Dd_km_km2"] * m["Fs_per_km2"]
        m["orde_maks"] = max(byo) if byo else 0
        m["_orders"] = {k: byo[k] for k in sorted(byo)}
        ords = sorted(byo)
        rb = [byo[o]["n"] / byo[o + 1]["n"] for o in ords[:-1] if byo.get(o + 1, {}).get("n")]
        wt = [byo[o]["n"] + byo[o + 1]["n"] for o in ords[:-1] if byo.get(o + 1, {}).get("n")]
        m["Rb_rata2"] = float(np.mean(rb)) if rb else float("nan")
        m["Rb_terbobot"] = float(np.average(rb, weights=wt)) if rb else float("nan")
        if m.get("keliling_km"):
            m["Rt_tekstur"] = N / m["keliling_km"]
