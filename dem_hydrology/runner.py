# -*- coding: utf-8 -*-
"""Orkestrasi: domain -> pipeline -> peta -> Excel -> PDF."""
from .i18n import tr
import os
import time
import traceback

from . import qgis_io as Q, registry as R, report_common as C


class Settings:
    def __init__(self, **kw):
        self.dem = None
        self.boundary = None
        self.admin = None
        self.admin_field = None
        self.pour = None
        self.pour_field = None
        self.outdir = ""
        self.selected = []
        self.params = {}
        self.title = tr("Analisis Hidrologi DEM")
        self.area_name = ""
        self.make_maps = True
        self.make_excel = True
        self.make_pdf = True
        self.load_layers = True
        self.only_selected_features = True
        self.dpi = 120
        self.__dict__.update(kw)


def validate(s):
    errs = []
    if s.dem is None or not s.dem.isValid():
        errs.append(tr("Pilih layer DEM yang valid."))
    if s.boundary is None or not s.boundary.isValid():
        errs.append(tr("Pilih layer batas studi (poligon)."))
    if not s.outdir:
        errs.append(tr("Tentukan folder keluaran."))
    if not s.selected:
        errs.append(tr("Pilih minimal satu analisis."))
    if "watershed_points" in s.selected and s.pour is None:
        errs.append(tr("Analisis 'Watershed from Pour Points' memerlukan layer titik outlet."))
    return errs


def run(s, log=None, progress=None):
    """Mengembalikan dict hasil: pipeline, domain, files, maps."""
    log = log or (lambda m: None)
    prog = progress or (lambda f, m: None)
    t0 = time.time()
    os.makedirs(s.outdir, exist_ok=True)
    core = s.params.get("core", {})
    prog(0.0, "Membaca DEM dan batas studi")
    d = Q.build_domain(s.dem, s.boundary, core.get("buffer_m", 1000.0), core.get("max_cells", 4.0),
                       s.only_selected_features, log=log)
    log(tr("Grid analisis %d x %d sel, ukuran sel %.2f m, CRS %s") % (d.shape[0], d.shape[1], d.cell, d.crs.authid()))
    from .pipeline import Pipeline
    pl = Pipeline(d, s.params, s.selected, os.path.join(s.outdir, "results"), s.pour, s.pour_field, log=log,
                  progress=lambda f, m: prog(0.05 + 0.5 * (f or 0.0), m) if f is not None else prog(None, m),
                  load_layers=s.load_layers)
    pl.run()
    files = dict(rasters=[o.path for o in pl.outs if o.kind == "raster"],
                 vectors=[o.path for o in pl.outs if o.kind == "vector"])
    maps = []
    if s.make_maps or s.make_pdf:
        from . import mapmaker as M
        md = os.path.join(s.outdir, "maps")
        os.makedirs(md, exist_ok=True)
        todo = [o for o in pl.outs if o.kind in ("raster", "vector") and o.key != "hillshade_x"]
        for i, o in enumerate(todo):
            prog(0.55 + 0.25 * i / max(len(todo), 1), tr("Peta: %s") % o.title)
            png = os.path.join(md, tr("%s.png") % o.key)
            try:
                foot = C.dominant_text(o)
                foot = (foot + "  " if foot else "") + tr("Sumber: DEM masukan pengguna; analisis: plugin Analisis Hidrologi DEM. CRS: %s.") % d.crs.authid()
                M.make_map(o, d, png, tr("PETA %s") % o.title.upper(), s.area_name or s.title,
                           admin=s.admin, label_field=s.admin_field, dpi=s.dpi, footer=foot)
                maps.append((o, png))
            except InterruptedError:
                raise
            except Exception as ex:
                log(tr("Peta '%s' gagal: %s\n%s") % (o.title, ex, traceback.format_exc()))
                pl.warnings.append(tr("Peta '%s' gagal dibuat: %s") % (o.title, ex))
    files["maps"] = [p for _, p in maps]
    if s.make_excel:
        prog(0.82, tr("Menulis Excel"))
        try:
            from .excel_report import build_excel
            files["excel"] = build_excel(os.path.join(s.outdir, "DEM_Hydrology_Summary.xlsx"), pl, d, s.title)
        except ImportError:
            pl.warnings.append(tr("Excel tidak dibuat karena pustaka openpyxl belum terpasang. Buka OSGeo4W Shell lalu "
                               "jalankan: python -m pip install openpyxl, kemudian jalankan ulang."))
            log(pl.warnings[-1])
    if s.make_pdf:
        prog(0.9, tr("Menulis PDF"))
        from .pdf_report import build_pdf
        files["pdf"] = build_pdf(os.path.join(s.outdir, "DEM_Hydrology_Report.pdf"), pl, d, maps,
                                 os.path.join(s.outdir, "maps"), s.title, s.area_name)
    prog(1.0, tr("Selesai dalam %.0f detik") % (time.time() - t0))
    return dict(pipeline=pl, domain=d, files=files, maps=maps, seconds=time.time() - t0)
