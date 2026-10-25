# -*- coding: utf-8 -*-
"""Laporan PDF (QTextDocument + QPdfWriter): ringkasan, peta, tabel, morfometri, metode, pustaka."""
from .i18n import tr
import datetime
import html
import math
import os

from qgis.PyQt.QtCore import QMarginsF, QSizeF, Qt, QRectF, QPointF
from qgis.PyQt.QtGui import (QPdfWriter, QPageLayout, QPageSize, QTextDocument, QImage, QPainter, QColor, QPen, QFont,
                             QPolygonF)

from . import registry as R, styles as S, report_common as C
from .mapmaker import _family

CSS = """
body { font-family: Arial, 'DejaVu Sans', sans-serif; font-size: 9pt; color: #222; }
h1 { font-size: 20pt; color: #1F4E79; margin-bottom: 2pt; }
h2 { font-size: 13pt; color: #1F4E79; border-bottom: 1px solid #1F4E79; margin-top: 10pt; }
h3 { font-size: 10.5pt; color: #333; margin-bottom: 2pt; }
table { border-collapse: collapse; }
th { background-color: #1F4E79; color: #ffffff; padding: 3px; font-size: 8pt; }
td { border: 1px solid #bbbbbb; padding: 3px; font-size: 8pt; }
.note { color: #555; font-size: 8pt; }
.warn { color: #9c2a00; }
"""


def e(s):
    return html.escape(str(s))


def fnum(v, nd=None):
    if v is None or (isinstance(v, float) and not math.isfinite(v)):
        return "-"
    return S.fmtnum(float(v), nd) if isinstance(v, (int, float)) else e(v)


def table(heads, rows, widths=None, align=None):
    h = "<table width='100%' cellspacing='0' cellpadding='2'><tr>" + "".join("<th>%s</th>" % e(tr(x)) for x in heads) + "</tr>"
    for r in rows:
        h += "<tr>" + "".join("<td%s>%s</td>" % (" align='right'" if isinstance(v, (int, float)) else "",
                                                 fnum(v) if isinstance(v, (int, float)) else ("-" if v is None else e(v)))
                              for v in r) + "</tr>"
    return h + "</table>"


# ---------------------------------------------------------------------------
# Grafik sederhana dengan QPainter (tanpa matplotlib)
# ---------------------------------------------------------------------------
def line_chart(path, series, title, xlabel, ylabel, w=1100, h=620, ymax=None, xmax=None, bars=False):
    """series: [(nama, [x], [y])]."""
    img = QImage(w, h, QImage.Format_RGB32)
    img.fill(QColor("white"))
    p = QPainter(img)
    p.setRenderHint(QPainter.Antialiasing)
    ml, mr, mt, mb = 90, 30, 60, 80
    pw, ph = w - ml - mr, h - mt - mb
    xs = [x for _, X, _Y in series for x in X]
    ys = [y for _, _X, Y in series for y in Y]
    if not xs:
        p.end()
        return None
    x0, x1 = min(xs), (xmax if xmax else max(xs))
    y0, y1 = min(0.0, min(ys)), (ymax if ymax else max(ys))
    if x1 <= x0:
        x1 = x0 + 1
    if y1 <= y0:
        y1 = y0 + 1
    xt, yt = S.nice_step((x1 - x0) / 6), S.nice_step((y1 - y0) / 6)
    f = QFont(_family(), 10)
    p.setFont(f)
    px = lambda x: ml + (x - x0) / (x1 - x0) * pw
    py = lambda y: mt + ph - (y - y0) / (y1 - y0) * ph
    p.setPen(QPen(QColor("#dddddd"), 1))
    v = math.ceil(x0 / xt) * xt
    while v <= x1 + 1e-9:
        p.drawLine(QPointF(px(v), mt), QPointF(px(v), mt + ph))
        p.setPen(QPen(QColor("#333")))
        p.drawText(QRectF(px(v) - 40, mt + ph + 4, 80, 20), Qt.AlignHCenter, S.fmtnum(v))
        p.setPen(QPen(QColor("#dddddd"), 1))
        v += xt
    v = math.ceil(y0 / yt) * yt
    while v <= y1 + 1e-9:
        p.drawLine(QPointF(ml, py(v)), QPointF(ml + pw, py(v)))
        p.setPen(QPen(QColor("#333")))
        p.drawText(QRectF(0, py(v) - 10, ml - 6, 20), Qt.AlignRight | Qt.AlignVCenter, S.fmtnum(v))
        p.setPen(QPen(QColor("#dddddd"), 1))
        v += yt
    p.setPen(QPen(QColor("#333"), 2))
    p.drawRect(QRectF(ml, mt, pw, ph))
    cols = ["#1f78b4", "#e31a1c", "#33a02c", "#ff7f00", "#6a3d9a", "#b15928", "#00897b", "#555555"]
    for i, (nm, X, Y) in enumerate(series):
        col = QColor(cols[i % len(cols)])
        if bars:
            bw = pw / max(len(X), 1) * 0.7
            p.setBrush(col)
            p.setPen(Qt.NoPen)
            for a, b in zip(X, Y):
                p.drawRect(QRectF(px(a) - bw / 2, py(b), bw, py(0) - py(b)))
        else:
            p.setPen(QPen(col, 3))
            poly = QPolygonF([QPointF(px(a), py(b)) for a, b in zip(X, Y)])
            p.drawPolyline(poly)
    f2 = QFont(_family(), 12)
    f2.setBold(True)
    p.setFont(f2)
    p.setPen(QPen(QColor("#1F4E79")))
    p.drawText(QRectF(0, 8, w, 36), Qt.AlignHCenter, title)
    p.setFont(f)
    p.setPen(QPen(QColor("#333")))
    p.drawText(QRectF(ml, h - 34, pw, 24), Qt.AlignHCenter, xlabel)
    p.save()
    p.translate(22, mt + ph / 2)
    p.rotate(-90)
    p.drawText(QRectF(-ph / 2, -12, ph, 24), Qt.AlignHCenter, ylabel)
    p.restore()
    if len(series) > 1:
        yy = mt + 8
        for i, (nm, _X, _Y) in enumerate(series[:8]):
            p.setPen(QPen(QColor(cols[i % len(cols)]), 4))
            p.drawLine(QPointF(ml + pw - 230, yy + 8), QPointF(ml + pw - 200, yy + 8))
            p.setPen(QPen(QColor("#222")))
            p.drawText(QRectF(ml + pw - 192, yy - 2, 190, 20), Qt.AlignLeft, nm[:26])
            yy += 22
    p.end()
    img.save(path)
    return path


# ---------------------------------------------------------------------------
def build_pdf(path, pl, d, maps, workdir, project_title="Analisis Hidrologi DEM", area_name=""):
    """maps: [(out, png_path)] sudah dibuat. Mengembalikan path PDF."""
    os.makedirs(workdir, exist_ok=True)
    wr = QPdfWriter(path)
    wr.setPageSize(QPageSize(QPageSize.A4))
    wr.setPageOrientation(QPageLayout.Landscape)
    wr.setPageMargins(QMarginsF(12, 12, 12, 12), QPageLayout.Millimeter)
    wr.setResolution(150)
    wr.setTitle(project_title)
    wr.setCreator(tr("Plugin Analisis Hidrologi DEM"))
    W, H = wr.width(), wr.height()
    h = [tr("<html><head><style>%s</style></head><body>") % CSS]
    now = datetime.datetime.now().strftime("%d %B %Y")
    h.append(tr("<h1>%s</h1><p><b>%s</b></p><p class='note'>Disusun %s</p>") % (e(project_title), e(area_name), now))
    h.append("<h2>1. " + e(tr("Data dan pengaturan")) + "</h2>")
    h.append(table(["Keterangan", "Nilai"], C.dem_summary(d, pl)))
    h.append("<h3>" + e(tr("Analisis yang dijalankan")) + "</h3>")
    h.append(table(["Analisis", "Status", "Waktu (detik)"],
                   [(R.L()["ANALYSES"][k]["name"], tr(pl.status.get(k, "-")), round(pl.timing.get("run_" + k, 0), 1)) for k in pl.sel]))
    if pl.warnings:
        h.append("<h3>" + e(tr("Peringatan")) + "</h3><ul>" + "".join(tr("<li class='warn'>%s</li>") % e(w) for w in pl.warnings) + "</ul>")
    h.append("<h3>" + e(tr("Catatan penggunaan")) + "</h3><ul>" + "".join("<li>%s</li>" % e(t) for t in C.method_note()) + "</ul>")
    h.append("<h2>2. " + e(tr("Parameter")) + "</h2>")
    h.append(table(["Analisis", "Parameter", "Nilai", "Satuan"], C.params_rows(pl.par, pl.sel)))

    # ---- peta
    sc = 96.0 / wr.logicalDpiX()
    mw = int(min(W, (H - 4) * 297.0 / 210.0 * 0.985) * sc)
    h.append("<p class='note'>" + e(tr("Peta tiap keluaran dimuat pada halaman-halaman berikutnya, satu halaman per peta.")) + "</p>")
    for o, png in maps:
        h.append(tr("<p style='page-break-before:always' align='center'><img src='%s' width='%d'></p>") % (e(png), mw))

    # ---- statistik
    h.append("<h2 style='page-break-before:always'>3. " + e(tr("Statistik dan luas kelas")) + "</h2>")
    rows = []
    for o in pl.outs:
        if o.kind == "raster" and o.stats:
            s = o.stats
            rows.append((o.title, o.unit, s["min"], s["p5"], s["median"], s["p95"], s["max"], s["mean"], s["std"]))
    if rows:
        h.append(table(["Keluaran", "Satuan", "Min", "P5", "Median", "P95", "Maks", "Rata-rata", "Std"], rows))
    for o in pl.outs:
        if o.classes:
            h.append("<h3>%s</h3>" % e(o.title))
            h.append(table(["Kelas", "Luas (ha)", "Persen (%)"], [(c["kelas"], c["luas_ha"], c["persen"]) for c in o.classes]))
            t = C.dominant_text(o)
            if t:
                h.append(tr("<p class='note'>%s</p>") % e(t))

    # ---- sungai
    so = next((o for o in pl.outs if o.key == "stream_lines"), None)
    if so is not None:
        h.append("<h2 style='page-break-before:always'>4. " + e(tr("Jaringan sungai")) + "</h2>")
        sm = so.extra["summary"]
        h.append(tr("<p>Ambang luas tangkapan %s ha; %d ruas; panjang total %s km; Dd %s km/km2.</p>") %
                 (fnum(sm["ambang_ha"]), sm["jumlah_ruas"], fnum(sm["panjang_total_km"]), fnum(sm["Dd_km_km2"])))
        h.append(table(["Orde", "Jumlah ruas", "Panjang total (km)", "Panjang rata-rata (km)", "Rb"],
                       [(r["orde"], r["jumlah_ruas"], r["panjang_total_km"], r["panjang_rata2_km"], r["Rb"])
                        for r in so.extra["orders"]]))

    # ---- morfometri
    mo = next((o for o in pl.outs if o.key == "morphometry"), None)
    if mo is not None and mo.extra["rows"]:
        rows = mo.extra["rows"]
        h.append("<h2 style='page-break-before:always'>5. " + e(tr("Morfometri DAS")) + "</h2>")
        show = rows[:7]
        if len(rows) > len(show):
            h.append(tr("<p class='note'>Tabel menampilkan %d unit terbesar dari %d. Seluruh unit ada pada berkas Excel.</p>") %
                     (len(show), len(rows)))
        heads = [tr("Parameter"), tr("Satuan")] + [r["nama"] for r in show]
        body = []
        for k, lab, u, f_, ref in C.morph_meta():
            body.append([lab, u] + [r.get(k) for r in show])
        body.append([tr("Bentuk DAS (Re)"), ""] + [C.interp_re(r.get("Re_elongasi")) for r in show])
        body.append([tr("Tahap lahan (HI)"), ""] + [C.interp_hi(r.get("HI")) for r in show])
        h.append(table(heads, body))
        h.append("<h3>" + e(tr("Rumus dan dasar")) + "</h3>" + table(["Parameter", "Rumus", "Pustaka"],
                 [(lab, f_, R.REFS.get(ref, "")) for k, lab, u, f_, ref in C.morph_meta() if f_]))
        det = mo.extra["detail"]
        names = [r["nama"] for r in show]
        hs = [(nm, [p["a_rel"] for p in det[nm]["hypso"]], [p["h_rel"] for p in det[nm]["hypso"]])
              for nm in names if det.get(nm, {}).get("hypso")]
        if hs:
            png = line_chart(os.path.join(workdir, "c_hypso.png"), hs, tr("Kurva hipsometrik"), "a/A", "h/H", ymax=1.0, xmax=1.0)
            h.append(tr("<p align='center'><img src='%s' width='%d'></p>") % (e(png), int(W * 0.6 * sc)))
        pr = [(nm, [x / 1000.0 for x in [det[nm]["profile"]["dist"][i] for i in range(len(det[nm]["profile"]["dist"]))]],
               det[nm]["profile"]["z"]) for nm in names if det.get(nm, {}).get("profile")]
        if pr:
            png = line_chart(os.path.join(workdir, "c_prof.png"), pr[:4], tr("Profil memanjang alur terpanjang"), tr("Jarak dari hulu (km)"), tr("Elevasi (m)"))
            h.append(tr("<p align='center'><img src='%s' width='%d'></p>") % (e(png), int(W * 0.6 * sc)))

    # ---- time-area
    to = next((o for o in pl.outs if o.key == "travel_time"), None)
    if to is not None and to.extra.get("time_area"):
        h.append("<h2 style='page-break-before:always'>6. " + e(tr("Waktu tempuh dan fungsi luas-waktu")) + "</h2>")
        sr = [(nm, [r["t1"] for r in rows], [r["cum_pct"] for r in rows]) for nm, rows in to.extra["time_area"].items() if rows]
        if sr:
            png = line_chart(os.path.join(workdir, "c_ta.png"), sr[:6], tr("Kumulatif luas terhadap waktu tempuh"), tr("Waktu (menit)"), tr("Luas kumulatif (%)"), ymax=100)
            h.append(tr("<p align='center'><img src='%s' width='%d'></p>") % (e(png), int(W * 0.6 * sc)))
            first = next(iter(to.extra["time_area"].items()))
            rr = first[1]
            step = max(1, len(rr) // 15)
            h.append("<h3>%s</h3>" % e(first[0]))
            h.append(table(["Dari (menit)", "Sampai (menit)", "Luas (ha)", "Kumulatif (ha)", "Kumulatif (%)"],
                           [(r["t0"], r["t1"], r["area_ha"], r["cum_ha"], r["cum_pct"]) for r in rr[::step]]))

    # ---- skenario genangan
    ho = next((o for o in pl.outs if o.key == "hand_flood"), None)
    if ho is not None and ho.extra.get("stage_table"):
        h.append("<h3>" + e(tr("Skenario genangan HAND")) + "</h3>" + table(
            ["Muka air (m)", "Luas (ha)", "Persen (%)", "Kedalaman rata-rata (m)", "Volume (m3)"],
            [(r["muka_air_m"], r["luas_ha"], r["persen"], r["kedalaman_rata2_m"], r["volume_m3"]) for r in ho.extra["stage_table"]]))

    # ---- metode
    h.append("<h2 style='page-break-before:always'>7. " + e(tr("Dasar ilmiah dan pustaka")) + "</h2>")
    for k in pl.sel:
        a = R.L()["ANALYSES"][k]
        h.append("<h3>%s</h3><p>%s</p>" % (e(a["name"]), e(a["desc"])))
        if a["formula"]:
            h.append(tr("<p><b>Rumus/prosedur:</b> %s</p>") % e(a["formula"]))
        if a["limits"]:
            h.append(tr("<p><b>Batasan:</b> %s</p>") % e(a["limits"]))
        refs = R.refs_for(a["refs"])
        if refs:
            h.append("<p class='note'>" + "<br>".join(e(t) for _, t in refs) + "</p>")
    h.append("</body></html>")
    doc = QTextDocument()
    doc.documentLayout().setPaintDevice(wr)
    doc.setPageSize(QSizeF(W, H))
    doc.setDocumentMargin(0)
    doc.setHtml("".join(h))
    doc.print_(wr)
    return path
