# -*- coding: utf-8 -*-
"""Penghubung ke QGIS/GDAL: membaca DEM ke grid persegi, topeng batas, menulis keluaran, simbologi."""
from .i18n import tr
import math
import os

import numpy as np
from osgeo import gdal, ogr, osr
from qgis.core import (QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsProject, QgsGeometry,
                       QgsRasterLayer, QgsVectorLayer, QgsFeature, QgsFields, QgsField, QgsWkbTypes,
                       QgsVectorFileWriter, QgsCoordinateTransformContext, QgsPointXY,
                       QgsSingleBandPseudoColorRenderer, QgsRasterShader, QgsColorRampShader,
                       QgsPalettedRasterRenderer, QgsSingleBandGrayRenderer, QgsContrastEnhancement,
                       QgsCategorizedSymbolRenderer, QgsRendererCategory, QgsSymbol, QgsSingleSymbolRenderer,
                       QgsFillSymbol, QgsLineSymbol, QgsMarkerSymbol)
from qgis.PyQt.QtCore import QVariant
from qgis.PyQt.QtGui import QColor

gdal.UseExceptions()
NODATA = -9999.0


class Domain:
    """Grid analisis: persegi, baris 0 = utara, dalam CRS terproyeksi (meter)."""
    pass


def layer_source_path(layer):
    s = layer.source()
    return s.split("|")[0] if "|" in s else s


def utm_crs_for(lon, lat):
    zone = int((lon + 180) // 6) + 1
    epsg = (32600 if lat >= 0 else 32700) + zone
    return QgsCoordinateReferenceSystem(tr("EPSG:%d") % epsg)


def pick_working_crs(dem_layer, boundary_layer):
    """CRS kerja harus terproyeksi (meter). Urutan: CRS batas, CRS DEM, lalu UTM dari pusat batas."""
    for lyr in (boundary_layer, dem_layer):
        crs = lyr.crs()
        if crs.isValid() and not crs.isGeographic():
            return crs
    ctr = boundary_layer.extent().center()
    xf = QgsCoordinateTransform(boundary_layer.crs(), QgsCoordinateReferenceSystem("EPSG:4326"), QgsProject.instance())
    p = xf.transform(ctr)
    return utm_crs_for(p.x(), p.y())


def collect_boundary(layer, crs, only_selected=True):
    """Gabungan seluruh poligon batas dalam CRS kerja."""
    feats = layer.selectedFeatures() if (only_selected and layer.selectedFeatureCount() > 0) else layer.getFeatures()
    xf = None
    if layer.crs() != crs:
        xf = QgsCoordinateTransform(layer.crs(), crs, QgsProject.instance())
    geoms = []
    for f in feats:
        g = QgsGeometry(f.geometry())
        if g.isNull() or g.isEmpty():
            continue
        if xf is not None:
            g.transform(xf)
        geoms.append(g)
    if not geoms:
        raise ValueError("Layer batas studi tidak memiliki poligon.")
    u = QgsGeometry.unaryUnion(geoms)
    return u.makeValid() if not u.isGeosValid() else u


def native_cell_m(dem_layer, crs):
    px = dem_layer.rasterUnitsPerPixelX()
    if dem_layer.crs().isGeographic():
        c = dem_layer.extent().center()
        return px * 111320.0 * math.cos(math.radians(c.y()))
    return px


def build_domain(dem_layer, boundary_layer, buffer_m=1000.0, max_cells_million=4.0, only_selected=True,
                 cell_override=None, log=None):
    log = log or (lambda m: None)
    d = Domain()
    crs = pick_working_crs(dem_layer, boundary_layer)
    d.crs = crs
    d.wkt = crs.toWkt()
    bnd = collect_boundary(boundary_layer, crs, only_selected)
    d.boundary_geom = bnd
    bb = bnd.boundingBox()
    cell = float(cell_override) if cell_override else native_cell_m(dem_layer, crs)
    cell = max(cell, 0.01)
    xmin, xmax = bb.xMinimum() - buffer_m, bb.xMaximum() + buffer_m
    ymin, ymax = bb.yMinimum() - buffer_m, bb.yMaximum() + buffer_m
    nx, ny = int(math.ceil((xmax - xmin) / cell)), int(math.ceil((ymax - ymin) / cell))
    limit = max_cells_million * 1e6
    if nx * ny > limit:
        f = math.sqrt(nx * ny / limit)
        cell *= f
        nx, ny = int(math.ceil((xmax - xmin) / cell)), int(math.ceil((ymax - ymin) / cell))
        log(tr("Grid terlalu rapat: ukuran sel analisis dibesarkan menjadi %.2f m (batas %.1f juta sel).") % (cell, max_cells_million))
    d.cell = cell
    d.shape = (ny, nx)
    d.x0, d.y0 = xmin, ymin + ny * cell                      # pojok kiri-atas
    d.gt = (d.x0, cell, 0.0, d.y0, 0.0, -cell)
    src = gdal.Open(layer_source_path(dem_layer))
    if src is None:
        raise ValueError("DEM tidak dapat dibuka oleh GDAL.")
    native = native_cell_m(dem_layer, crs)
    alg = "average" if cell > 1.5 * native else "bilinear"
    sb = src.GetRasterBand(1)
    snd = sb.GetNoDataValue()
    ds = gdal.Warp("", src, format="MEM", outputBounds=(d.x0, d.y0 - ny * cell, d.x0 + nx * cell, d.y0),
                   width=nx, height=ny, dstSRS=d.wkt, resampleAlg=alg, srcNodata=snd, dstNodata=-99999.0,
                   outputType=gdal.GDT_Float32)
    z = ds.GetRasterBand(1).ReadAsArray().astype(np.float64)
    ds = None
    bad = (z <= -99998.0) | ~np.isfinite(z) | (np.abs(z) > 1e6) | (z < -1000.0)
    z[bad] = np.nan
    d.valid = np.isfinite(z)
    d.z = z
    d.inside = rasterize_geom(bnd, d) & d.valid
    d.inside_all = rasterize_geom(bnd, d)
    if not d.inside_all.any():
        raise ValueError("Batas studi lebih kecil dari satu sel DEM atau berada di luar DEM.")
    frac = d.inside.sum() / max(d.inside_all.sum(), 1)
    if frac < 0.5:
        raise ValueError(tr("Kurang dari 50 %% batas studi tertutup DEM (%.0f %%). Periksa DEM dan batas.") % (100 * frac))
    rr, cc = np.where(d.inside_all)
    d.win = (int(rr.min()), int(rr.max()) + 1, int(cc.min()), int(cc.max()) + 1)
    d.src_native = native
    d.resampled = alg
    return d


def rasterize_geom(geom, d):
    """Topeng (True di dalam poligon, aturan titik pusat sel)."""
    drv = ogr.GetDriverByName("Memory")
    ods = drv.CreateDataSource("m")
    srs = osr.SpatialReference()
    srs.ImportFromWkt(d.wkt)
    lyr = ods.CreateLayer("b", srs=srs)
    f = ogr.Feature(lyr.GetLayerDefn())
    f.SetGeometry(ogr.CreateGeometryFromWkb(bytes(geom.asWkb())))
    lyr.CreateFeature(f)
    mem = gdal.GetDriverByName("MEM").Create("", d.shape[1], d.shape[0], 1, gdal.GDT_Byte)
    mem.SetGeoTransform(d.gt)
    mem.SetProjection(d.wkt)
    gdal.RasterizeLayer(mem, [1], lyr, burn_values=[1])
    return mem.GetRasterBand(1).ReadAsArray().astype(bool)


def xy(d, flat_idx):
    """Koordinat peta (x, y) pusat sel dari indeks datar."""
    r, c = np.divmod(np.asarray(flat_idx), d.shape[1])
    return d.x0 + (c + 0.5) * d.cell, d.y0 - (r + 0.5) * d.cell


def cell_of(d, x, y):
    return int((d.y0 - y) // d.cell), int((x - d.x0) // d.cell)


# ---------------------------------------------------------------------------
# Raster
# ---------------------------------------------------------------------------
def write_raster(path, arr, d, nodata=NODATA, dtype="float32", clip_to_boundary=True):
    """Tulis pada jendela batas studi; sel di luar batas = nodata."""
    r0, r1, c0, c1 = d.win
    a = np.array(arr[r0:r1, c0:c1], dtype=np.float64)
    if clip_to_boundary:
        a = np.where(d.inside_all[r0:r1, c0:c1], a, np.nan)
    gt = (d.x0 + c0 * d.cell, d.cell, 0.0, d.y0 - r0 * d.cell, 0.0, -d.cell)
    gdt = {"float32": gdal.GDT_Float32, "int16": gdal.GDT_Int16, "int32": gdal.GDT_Int32, "byte": gdal.GDT_Byte}[dtype]
    out = np.where(np.isfinite(a), a, nodata)
    ds = gdal.GetDriverByName("GTiff").Create(path, a.shape[1], a.shape[0], 1, gdt, ["COMPRESS=DEFLATE", "TILED=YES"])
    ds.SetGeoTransform(gt)
    ds.SetProjection(d.wkt)
    b = ds.GetRasterBand(1)
    b.SetNoDataValue(float(nodata))
    b.WriteArray(out.astype({"float32": np.float32, "int16": np.int16, "int32": np.int32, "byte": np.uint8}[dtype]))
    b.FlushCache()
    ds = None
    return path


def polygonize(labels, d, min_label=1, window=None):
    """Poligon per label (int); window=(r0,r1,c0,c1) membatasi pemrosesan. Mengembalikan
    {label: QgsGeometry multipart}."""
    gt = d.gt
    if window is not None:
        r0, r1, c0, c1 = window
        labels = labels[r0:r1, c0:c1]
        gt = (d.x0 + c0 * d.cell, d.cell, 0.0, d.y0 - r0 * d.cell, 0.0, -d.cell)
    ny, nx = labels.shape
    mem = gdal.GetDriverByName("MEM").Create("", nx, ny, 1, gdal.GDT_Int32)
    mem.SetGeoTransform(gt)
    mem.SetProjection(d.wkt)
    lab = np.where(labels >= min_label, labels, 0).astype(np.int32)
    mem.GetRasterBand(1).WriteArray(lab)
    mem.GetRasterBand(1).SetNoDataValue(0)
    ods = ogr.GetDriverByName("Memory").CreateDataSource("p")
    lyr = ods.CreateLayer("p", srs=None)
    lyr.CreateField(ogr.FieldDefn("v", ogr.OFTInteger))
    gdal.Polygonize(mem.GetRasterBand(1), mem.GetRasterBand(1), lyr, 0, ["8CONNECTED=8"])
    parts = {}
    for f in lyr:
        v = f.GetField("v")
        if v <= 0:
            continue
        parts.setdefault(v, []).append(QgsGeometry.fromWkt(f.GetGeometryRef().ExportToWkt()))
    out = {}
    for v, gl in parts.items():
        g = QgsGeometry.unaryUnion(gl) if len(gl) > 1 else gl[0]
        out[v] = g
    return out


def clip_geoms(geoms, d):
    """Pangkas poligon hasil ke batas studi."""
    out = {}
    for k, g in geoms.items():
        c = g.intersection(d.boundary_geom)
        if c is not None and not c.isEmpty():
            out[k] = c
    return out


# ---------------------------------------------------------------------------
# Vektor
# ---------------------------------------------------------------------------
def normalize_geom(g, wkb):
    """Samakan geometri dengan tipe layer: ambil bagian bertipe sama dari koleksi, lalu multi bila perlu."""
    if g is None or g.isNull() or g.isEmpty():
        return None
    want = QgsWkbTypes.geometryType(wkb)
    if QgsWkbTypes.geometryType(g.wkbType()) != want or g.wkbType() in (
            QgsWkbTypes.GeometryCollection, QgsWkbTypes.GeometryCollectionZ):
        parts = [x for x in g.asGeometryCollection() if QgsWkbTypes.geometryType(x.wkbType()) == want]
        if not parts:
            return None
        g = QgsGeometry.collectGeometry(parts)
    if QgsWkbTypes.isMultiType(wkb) and not g.isMultipart():
        g.convertToMultiType()
    return g


def write_vector(path, layer_name, wkb, crs, fields, rows):
    """fields: [(nama, 'int'|'double'|'string')]; rows: [(QgsGeometry, [nilai...])]."""
    flds = QgsFields()
    tmap = {"int": QVariant.Int, "double": QVariant.Double, "string": QVariant.String, "ll": QVariant.LongLong}
    for n, t in fields:
        flds.append(QgsField(n, tmap[t]))
    mem = QgsVectorLayer(tr("%s?crs=%s") % (QgsWkbTypes.displayString(wkb), crs.authid() or "EPSG:4326"), layer_name, "memory")
    mem.dataProvider().addAttributes(list(flds))
    mem.updateFields()
    feats = []
    for g, vals in rows:
        g = normalize_geom(g, wkb)
        if g is None:
            continue
        f = QgsFeature(mem.fields())
        f.setGeometry(g)
        f.setAttributes([v.item() if hasattr(v, "item") else v for v in vals])
        feats.append(f)
    ok, _added = mem.dataProvider().addFeatures(feats)
    if not ok or mem.featureCount() != len(feats):
        raise RuntimeError(tr("Hanya %d dari %d objek diterima saat menulis %s") % (mem.featureCount(), len(feats), layer_name))
    if not feats:
        raise RuntimeError(tr("Tidak ada objek untuk ditulis: %s") % layer_name)
    opt = QgsVectorFileWriter.SaveVectorOptions()
    opt.driverName = "GPKG"
    opt.layerName = layer_name
    opt.fileEncoding = "UTF-8"
    err = QgsVectorFileWriter.writeAsVectorFormatV3(mem, path, QgsCoordinateTransformContext(), opt)
    if err[0] != QgsVectorFileWriter.NoError:
        raise RuntimeError(tr("Gagal menulis %s: %s") % (path, err[1]))
    return len(feats)


# ---------------------------------------------------------------------------
# Simbologi
# ---------------------------------------------------------------------------
def qcolor(h):
    return QColor(h)


def style_raster(layer, spec, vmin=None, vmax=None):
    prov = layer.dataProvider()
    t = spec["type"]
    if t == "paletted":
        cls = [QgsPalettedRasterRenderer.Class(it["value"], qcolor(it["color"]), it["label"]) for it in spec["items"]]
        layer.setRenderer(QgsPalettedRasterRenderer(prov, 1, cls))
    elif t == "gray":
        r = QgsSingleBandGrayRenderer(prov, 1)
        ce = QgsContrastEnhancement(prov.dataType(1))
        ce.setMinimumValue(spec.get("vmin", 0))
        ce.setMaximumValue(spec.get("vmax", 255))
        ce.setContrastEnhancementAlgorithm(QgsContrastEnhancement.StretchToMinimumMaximum)
        r.setContrastEnhancement(ce)
        layer.setRenderer(r)
    else:
        items = []
        for it in spec["items"]:
            up = it["upper"] if it["upper"] < 1e29 else float("inf")
            items.append(QgsColorRampShader.ColorRampItem(up, qcolor(it["color"]), it["label"]))
        fn = QgsColorRampShader()
        fn.setColorRampType(QgsColorRampShader.Discrete)
        fn.setColorRampItemList(items)
        fn.setClassificationMode(QgsColorRampShader.Continuous)
        sh = QgsRasterShader()
        sh.setRasterShaderFunction(fn)
        r = QgsSingleBandPseudoColorRenderer(prov, 1, sh)
        if vmin is not None and vmax is not None:
            r.setClassificationMin(vmin)
            r.setClassificationMax(vmax)
        layer.setRenderer(r)
    layer.triggerRepaint()


def _fill(color, outline="#333333", width=0.3, alpha=1.0):
    s = QgsFillSymbol.createSimple({"color": color, "outline_color": outline, "outline_width": str(width),
                                    "style": "solid"})
    s.setOpacity(alpha)
    return s


def style_polygons_by_id(layer, field, colors, width=0.5, alpha=0.55):
    cats = []
    vals = sorted(layer.uniqueValues(layer.fields().indexOf(field)))
    for i, v in enumerate(vals):
        sym = _fill(colors[i % len(colors)], "#222222", width, alpha)
        cats.append(QgsRendererCategory(v, sym, str(v)))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, cats))
    layer.triggerRepaint()


def style_single_polygon(layer, color="#e57373", outline="#b71c1c", width=0.3, alpha=0.7):
    layer.setRenderer(QgsSingleSymbolRenderer(_fill(color, outline, width, alpha)))
    layer.triggerRepaint()


def style_streams(layer, order_colors, order_widths, field="strahler"):
    cats = []
    vals = sorted(layer.uniqueValues(layer.fields().indexOf(field)))
    for v in vals:
        i = min(int(v) - 1, len(order_colors) - 1)
        sym = QgsLineSymbol.createSimple({"line_color": order_colors[i], "line_width": str(order_widths[i]),
                                          "capstyle": "round", "joinstyle": "round"})
        cats.append(QgsRendererCategory(v, sym, tr("Orde %d") % int(v)))
    layer.setRenderer(QgsCategorizedSymbolRenderer(field, cats))
    layer.triggerRepaint()


def style_points(layer, color="#d50000"):
    sym = QgsMarkerSymbol.createSimple({"name": "triangle", "color": color, "outline_color": "#ffffff",
                                        "size": "3.2"})
    layer.setRenderer(QgsSingleSymbolRenderer(sym))
    layer.triggerRepaint()


def add_to_project(layer, group_name=None):
    group_name = group_name or tr("Analisis Hidrologi DEM")
    prj = QgsProject.instance()
    root = prj.layerTreeRoot()
    grp = root.findGroup(group_name) or root.insertGroup(0, group_name)
    prj.addMapLayer(layer, False)
    grp.insertLayer(0, layer)
    return layer
