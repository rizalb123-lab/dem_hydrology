# -*- coding: utf-8 -*-
"""
Peta standar tiap keluaran, mengikuti templat pengguna: latar abu-abu, poligon kawasan putih
dengan garis tepi tebal, batas administrasi bertitik dengan label berhalo putih, panah utara
berlingkaran "U", skala batang hitam-putih, dan blok "Legenda" di kanan atas.
"""
from .i18n import tr
import math

from qgis.core import (QgsProject, QgsVectorLayer, QgsRasterLayer, QgsFeature, QgsGeometry, QgsRectangle,
                       QgsPrintLayout, QgsLayoutItemMap, QgsLayoutItem, QgsLayoutMeasurement, QgsLayoutItemLabel, QgsLayoutItemLegend,
                       QgsLayoutItemScaleBar, QgsLayoutItemShape, QgsLayoutItemPolygon, QgsLayoutPoint,
                       QgsLayoutSize, QgsLayoutExporter, QgsUnitTypes, QgsFillSymbol, QgsLineSymbol,
                       QgsSingleSymbolRenderer, QgsPalLayerSettings, QgsTextFormat, QgsTextBufferSettings,
                       QgsVectorLayerSimpleLabeling, QgsLegendStyle, QgsMapLayerLegendUtils, QgsReadWriteContext,
                       QgsLayerTree, QgsSymbol, QgsMarkerSymbol, QgsCoordinateReferenceSystem, QgsWkbTypes)
from qgis.PyQt.QtCore import Qt, QSizeF, QPointF
from qgis.PyQt.QtGui import QColor, QFont, QPolygonF

from . import qgis_io as Q, styles as S

PAGE_W, PAGE_H = 297.0, 210.0
MAP_X, MAP_Y, MAP_W, MAP_H = 10.0, 20.0, 277.0, 176.0
BG = "#d3d3d3"


def _family():
    import sys
    return "Arial" if sys.platform.startswith("win") else ("Helvetica Neue" if sys.platform == "darwin" else "DejaVu Sans")


def _font(size, bold=False):
    f = QFont(_family(), int(size))
    f.setBold(bold)
    return f


def _fmt(size, bold=False, color="#000000", buffer=False):
    tf = QgsTextFormat()
    tf.setFont(_font(size, bold))
    tf.setSize(size)
    tf.setColor(QColor(color))
    if buffer:
        b = QgsTextBufferSettings()
        b.setEnabled(True)
        b.setSize(1.0)
        b.setColor(QColor("#ffffff"))
        tf.setBuffer(b)
    return tf


def _label(layout, text, x, y, w, h, size=10, bold=False, align=Qt.AlignLeft, color="#000000"):
    lb = QgsLayoutItemLabel(layout)
    lb.setText(text)
    lb.setTextFormat(_fmt(size, bold, color))
    lb.setHAlign(align)
    lb.setVAlign(Qt.AlignVCenter)
    lb.attemptMove(QgsLayoutPoint(x, y))
    lb.attemptResize(QgsLayoutSize(w, h))
    layout.addLayoutItem(lb)
    return lb


# ---------------------------------------------------------------------------
def _mem_polys(geoms, crs, name, attrs=None):
    lyr = QgsVectorLayer(tr("MultiPolygon?crs=%s") % crs.authid(), name, "memory")
    if attrs:
        from qgis.core import QgsField
        from qgis.PyQt.QtCore import QVariant
        lyr.dataProvider().addAttributes([QgsField(n, QVariant.String) for n in attrs[0]])
        lyr.updateFields()
    feats = []
    for i, g in enumerate(geoms):
        f = QgsFeature(lyr.fields())
        f.setGeometry(g)
        if attrs:
            f.setAttributes(attrs[1][i])
        feats.append(f)
    lyr.dataProvider().addFeatures(feats)
    return lyr


def admin_layer(admin, label_field, boundary_geom, crs):
    """Batas administrasi dipotong ke kawasan studi, dengan label."""
    if admin is None:
        return None
    from qgis.core import QgsCoordinateTransform
    xf = QgsCoordinateTransform(admin.crs(), crs, QgsProject.instance()) if admin.crs() != crs else None
    geoms, labs = [], []
    for f in admin.getFeatures():
        g = QgsGeometry(f.geometry())
        if g.isNull():
            continue
        if xf is not None:
            g.transform(xf)
        c = g.intersection(boundary_geom)
        if c is None or c.isEmpty():
            continue
        geoms.append(c)
        v = f[label_field] if label_field and label_field in admin.fields().names() else ""
        labs.append([str(v) if v not in (None, "NULL") else ""])
    lyr = _mem_polys(geoms, crs, tr("Batas Administrasi"), (["label"], labs))
    sym = QgsFillSymbol.createSimple({"style": "no", "outline_color": "#4d4d4d", "outline_style": "dot",
                                      "outline_width": "0.45"})
    lyr.setRenderer(QgsSingleSymbolRenderer(sym))
    s = QgsPalLayerSettings()
    s.fieldName = "label"
    s.setFormat(_fmt(9, True, "#202020", buffer=True))
    s.placement = QgsPalLayerSettings.OverPoint if False else QgsPalLayerSettings.AroundPoint
    s.centroidInside = True
    s.centroidWhole = False
    lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
    lyr.setLabelsEnabled(True)
    return lyr


def study_layers(boundary_geom, crs):
    base = _mem_polys([boundary_geom], crs, tr("Kawasan Studi (dasar)"))
    base.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"color": "#ffffff", "outline_style": "no"})))
    line = _mem_polys([boundary_geom], crs, tr("Batas Kawasan Studi"))
    line.setRenderer(QgsSingleSymbolRenderer(QgsFillSymbol.createSimple(
        {"style": "no", "outline_color": "#111111", "outline_width": "1.1", "joinstyle": "round"})))
    return base, line


def result_layer(out):
    """Layer baru untuk peta (tidak bergantung pada layer di proyek)."""
    if out.kind == "raster":
        lyr = QgsRasterLayer(out.path, out.title)
        Q.style_raster(lyr, out.style, out.stats.get("min"), out.stats.get("max"))
        return lyr
    lyr = QgsVectorLayer(tr("%s|layername=%s") % (out.path, out.key), out.title, "ogr")
    k = out.key
    if k == "stream_lines":
        Q.style_streams(lyr, S.ORDER_COLORS, S.ORDER_WIDTH)
    elif k in ("subbasins", "watersheds"):
        from .pipeline_basin import PASTEL
        Q.style_polygons_by_id(lyr, "id" if k == "subbasins" else "nama", PASTEL, 0.6 if k == "subbasins" else 0.9, 0.55)
        s = QgsPalLayerSettings()
        s.fieldName = "id" if k == "subbasins" else "nama"
        s.setFormat(_fmt(8, True, "#1a1a1a", buffer=True))
        s.placement = QgsPalLayerSettings.AroundPoint
        s.centroidInside = True
        lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
        lyr.setLabelsEnabled(True)
    elif k == "pour_points":
        Q.style_points(lyr)
        s = QgsPalLayerSettings()
        s.fieldName = "nama"
        s.setFormat(_fmt(9, True, "#7f0000", buffer=True))
        s.placement = QgsPalLayerSettings.AroundPoint
        lyr.setLabeling(QgsVectorLayerSimpleLabeling(s))
        lyr.setLabelsEnabled(True)
    else:
        Q.style_single_polygon(lyr, "#ef5350", "#8e0000")
    return lyr


# ---------------------------------------------------------------------------
def _north_arrow(layout, x, y, d=15.0):
    c = QgsLayoutItemShape(layout)
    c.setShapeType(QgsLayoutItemShape.Ellipse)
    c.setSymbol(QgsFillSymbol.createSimple({"color": "#ffffff", "outline_color": "#000000", "outline_width": "0.5"}))
    c.attemptMove(QgsLayoutPoint(x, y + 4.5))
    c.attemptResize(QgsLayoutSize(d, d))
    layout.addLayoutItem(c)
    arrow = QgsLayoutItemPolygon(QPolygonF([QPointF(0, 0)]), layout)
    arrow.setNodes(QPolygonF([QPointF(x + d / 2, y + 4.5 + 1.6), QPointF(x + d / 2 + 3.2, y + 4.5 + d - 2.4),
                              QPointF(x + d / 2, y + 4.5 + d - 4.4), QPointF(x + d / 2 - 3.2, y + 4.5 + d - 2.4)]))
    arrow.setSymbol(QgsFillSymbol.createSimple({"color": "#000000", "outline_color": "#000000", "outline_width": "0.2"}))
    layout.addLayoutItem(arrow)
    _label(layout, tr("U"), x, y - 0.5, d, 5.5, 11, True, Qt.AlignHCenter)


def _scalebar(layout, mp, extent_w_m, x, y):
    step = S.nice_step(extent_w_m / 14.0)
    sb = QgsLayoutItemScaleBar(layout)
    sb.setLinkedMap(mp)
    sb.setStyle("Single Box")
    if step >= 1000:
        sb.setUnits(QgsUnitTypes.DistanceKilometers)
        sb.setUnitsPerSegment(step / 1000.0)
        sb.setUnitLabel("km")
    else:
        sb.setUnits(QgsUnitTypes.DistanceMeters)
        sb.setUnitsPerSegment(step)
        sb.setUnitLabel("m")
    sb.setNumberOfSegmentsLeft(0)
    sb.setNumberOfSegments(4)
    sb.setHeight(2.2)
    sb.setFillColor(QColor("#000000"))
    sb.setFillColor2(QColor("#ffffff"))
    sb.setTextFormat(_fmt(8, False))
    sb.setBackgroundEnabled(True)
    sb.setBackgroundColor(QColor(255, 255, 255, 215))
    sb.attemptMove(QgsLayoutPoint(x, y))
    layout.addLayoutItem(sb)
    return sb


def make_map(out, domain, png_path, title, subtitle, admin=None, label_field=None, dpi=150, footer=None,
             extra_layers=None):
    d = domain
    crs = d.crs
    bg_geom = d.boundary_geom
    res = result_layer(out)
    if not res.isValid():
        raise RuntimeError(tr("Layer hasil tidak valid: %s") % out.path)
    base, line = study_layers(bg_geom, crs)
    adm = admin_layer(admin, label_field, bg_geom, crs) if admin is not None else None
    layers = [line] + ([adm] if adm is not None else []) + [res] + list(extra_layers or []) + [base]
    for l in (base, line, adm):
        if l is not None:
            l.setCrs(crs)
    prj = QgsProject.instance()
    layout = QgsPrintLayout(prj)
    layout.initializeDefaults()
    pc = layout.pageCollection()
    pc.page(0).setPageSize(QgsLayoutSize(PAGE_W, PAGE_H))
    # judul
    _label(layout, title, 10, 5, 277, 8, 15, True, Qt.AlignHCenter)
    _label(layout, subtitle, 10, 12.2, 277, 6, 9.5, False, Qt.AlignHCenter, "#333333")
    # peta
    mp = QgsLayoutItemMap(layout)
    mp.attemptMove(QgsLayoutPoint(MAP_X, MAP_Y))
    mp.attemptResize(QgsLayoutSize(MAP_W, MAP_H))
    mp.setCrs(crs)
    mp.setBackgroundColor(QColor(BG))
    mp.setBackgroundEnabled(True)
    mp.setFrameEnabled(True)
    mp.setFrameStrokeWidth(QgsLayoutMeasurement(0.4))
    mp.setLayers(layers)
    bb = bg_geom.boundingBox()
    ar = MAP_W / MAP_H
    wd = bb.width() / 0.64
    hd = wd / ar
    if bb.height() * 1.22 > hd:
        hd = bb.height() * 1.22
        wd = hd * ar
    cy = bb.center().y()
    ext = QgsRectangle(bb.xMinimum() - 0.04 * wd, cy - hd / 2.0, bb.xMinimum() - 0.04 * wd + wd, cy + hd / 2.0)
    mp.zoomToExtent(ext)
    layout.addLayoutItem(mp)
    _north_arrow(layout, MAP_X + 4, MAP_Y + 4)
    _scalebar(layout, mp, wd, MAP_X + 4, MAP_Y + MAP_H - 9)
    # legenda
    lg = QgsLayoutItemLegend(layout)
    lg.setLinkedMap(mp)
    lg.setAutoUpdateModel(False)
    root = lg.model().rootGroup()
    root.clear()
    n_res = root.addLayer(res)
    res.setName(out.title)
    nodes = lg.model().layerLegendNodes(n_res, False)
    if out.key == "subbasins":
        QgsMapLayerLegendUtils.setLegendNodeOrder(n_res, [])
    elif out.kind == "raster":
        keep = [i for i, nd in enumerate(nodes) if not str(nd.data(Qt.DisplayRole)).startswith("Band")]
        if keep:
            QgsMapLayerLegendUtils.setLegendNodeOrder(n_res, keep)
    lg.model().refreshLayerLegend(n_res)
    for l in (adm, line):
        if l is not None:
            root.addLayer(l)
    lg.setTitle(tr("Legenda"))
    lg.setStyleFont(QgsLegendStyle.Title, _font(11, True))
    lg.setStyleFont(QgsLegendStyle.Subgroup, _font(8.5, True))
    lg.setStyleFont(QgsLegendStyle.SymbolLabel, _font(7.5))
    lg.setBackgroundEnabled(True)
    lg.setBackgroundColor(QColor("#ffffff"))
    lg.setFrameEnabled(True)
    lg.setBoxSpace(2.0)
    lg.setSymbolWidth(7.0)
    lg.setSymbolHeight(3.6)
    lg.setReferencePoint(QgsLayoutItem.UpperRight)
    lg.attemptMove(QgsLayoutPoint(MAP_X + MAP_W - 3, MAP_Y + 3), True)
    layout.addLayoutItem(lg)
    lg.adjustBoxSize()
    # kaki
    _label(layout, footer or (tr("Sumber: DEM masukan pengguna; analisis: plugin Analisis Hidrologi DEM. ")
                             + tr("Koordinat: %s.") % crs.authid()), 10, MAP_Y + MAP_H + 1.5, 277, 5, 7.5, False, Qt.AlignLeft,
           "#444444")
    from osgeo import gdal
    gdal.PushErrorHandler('CPLQuietErrorHandler')
    ex = QgsLayoutExporter(layout)
    st = QgsLayoutExporter.ImageExportSettings()
    st.dpi = dpi
    st.generateWorldFile = False
    try:
        r = ex.exportToImage(png_path, st)
    finally:
        gdal.PopErrorHandler()
    if r != QgsLayoutExporter.Success:
        raise RuntimeError(tr("Gagal mengekspor peta (kode %s)") % r)
    return png_path
