# -*- coding: utf-8 -*-
"""Antarmuka plugin (dibangun dari registri; tanpa berkas .ui)."""
from .i18n import tr
import html
import json
import os
import traceback

from qgis.PyQt.QtCore import Qt, QSettings, QUrl
from qgis.PyQt.QtGui import QDesktopServices, QFont
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QTabWidget, QWidget, QLabel, QLineEdit,
                                 QPushButton, QTreeWidget, QTreeWidgetItem, QTextBrowser, QSplitter, QScrollArea,
                                 QGroupBox, QFormLayout, QDoubleSpinBox, QSpinBox, QCheckBox, QComboBox,
                                 QPlainTextEdit, QProgressBar, QApplication, QMessageBox, QGridLayout, QSizePolicy)
from qgis.core import QgsMapLayerProxyModel, QgsProject
from qgis.gui import QgsMapLayerComboBox, QgsFieldComboBox, QgsFileWidget

from . import registry as R, runner as RN, i18n
from .qgis_io import add_to_project  # noqa: F401  (memastikan modul termuat)

SET = "DEMHydrology/"
AUTHOR = "Rizal Brilliant Nugraha"
EMAIL = "rizalb123@gmail.com"
SUPPORT_URL = "https://sociabuzz.com/rizalb123"
_PLUGIN_DIR = os.path.dirname(__file__)


def plugin_version():
    try:
        with open(os.path.join(_PLUGIN_DIR, "metadata.txt"), encoding="utf-8") as f:
            for ln in f:
                if ln.startswith("version="):
                    return ln.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def initial_language():
    """Saved choice, else the QGIS interface language, else English."""
    try:
        v = QSettings().value(SET + "lang", "") or ""
        if v:
            return v
        st = QSettings()
        loc = st.value("locale/userLocale", "") if st.value("locale/overrideFlag", False, type=bool) else ""
        if not loc:
            from qgis.PyQt.QtCore import QLocale
            loc = QLocale().name()
        return i18n.guess_language(loc)
    except Exception:
        return "en"


def esc(s):
    return html.escape(str(s))


class ParamForm(QGroupBox):
    """Satu kelompok parameter, dibangun dari definisi registri."""

    def __init__(self, title, params, parent=None):
        super().__init__(title, parent)
        self.params = params
        self.w = {}
        lay = QFormLayout(self)
        lay.setLabelAlignment(Qt.AlignLeft)
        lay.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        lay.setVerticalSpacing(10)
        for p in params:
            w = self._make(p)
            self.w[p["key"]] = w
            lab = QLabel(p["label"] + (" (%s)" % p["unit"] if p["unit"] else ""))
            lab.setWordWrap(True)
            lab.setMinimumWidth(320)
            lab.setMinimumHeight(34)
            if p.get("help"):
                lab.setToolTip(p["help"])
                w.setToolTip(p["help"])
            lay.addRow(lab, w)

    def _make(self, p):
        t = p["type"]
        if t == "float":
            w = QDoubleSpinBox()
            st = p["step"] or 0.1
            w.setDecimals(4 if st < 0.01 else 3 if st < 0.1 else 2 if st < 1 else 1)
            w.setRange(p["min"] if p["min"] is not None else -1e9, p["max"] if p["max"] is not None else 1e9)
            w.setSingleStep(st)
            w.setValue(float(p["default"]))
            w.setMinimumWidth(110)
            return w
        if t == "int":
            w = QSpinBox()
            w.setRange(int(p["min"]), int(p["max"]))
            w.setValue(int(p["default"]))
            return w
        if t == "bool":
            w = QCheckBox()
            w.setChecked(bool(p["default"]))
            return w
        if t == "choice":
            w = QComboBox()
            for k, lab in p["choices"]:
                w.addItem(lab, k)
            w.setCurrentIndex(max(0, w.findData(p["default"])))
            return w
        w = QLineEdit(str(p["default"]))
        return w

    def values(self):
        out = {}
        for p in self.params:
            w = self.w[p["key"]]
            t = p["type"]
            out[p["key"]] = (w.value() if t in ("float", "int") else w.isChecked() if t == "bool"
                             else w.currentData() if t == "choice" else w.text().strip())
        return out

    def set_values(self, d):
        for p in self.params:
            if p["key"] not in d:
                continue
            w, v, t = self.w[p["key"]], d[p["key"]], p["type"]
            try:
                if t in ("float", "int"):
                    w.setValue(float(v) if t == "float" else int(v))
                elif t == "bool":
                    w.setChecked(bool(v))
                elif t == "choice":
                    w.setCurrentIndex(max(0, w.findData(v)))
                else:
                    w.setText(str(v))
            except (ValueError, TypeError):
                pass

    def reset(self):
        self.set_values({p["key"]: p["default"] for p in self.params})


class HidrologiDialog(QDialog):
    show_popup = True  # tests switch this off

    def __init__(self, iface=None, parent=None):
        super().__init__(parent)
        self.iface = iface
        self.resize(1180, 780)
        self.cancel = False
        self.running = False
        self.last = None
        self.last_popup_text = ""
        self._log_text = ""
        self._tab_index = 0
        i18n.reload()
        i18n.set_language(initial_language())
        self.root = QVBoxLayout(self)
        self._head()
        self.body = None
        self.build()

    # ------------------------------------------------------------ language bar
    def _head(self):
        self.head = QHBoxLayout()
        self.lbl_lang = QLabel("")
        self.cb_lang = QComboBox()
        self.btn_langdir = QPushButton("")
        self.btn_langtpl = QPushButton("")
        self.btn_about = QPushButton("")
        self.btn_support = QPushButton("")
        self.btn_support.setStyleSheet("font-weight:bold; color:#b03060;")
        for w in (self.lbl_lang, self.cb_lang, self.btn_langdir, self.btn_langtpl):
            self.head.addWidget(w)
        self.head.addStretch(1)
        self.head.addWidget(self.btn_support)
        self.head.addWidget(self.btn_about)
        self.root.addLayout(self.head)
        self.cb_lang.currentIndexChanged.connect(self._lang_changed)
        self.btn_langdir.clicked.connect(self.open_lang_folder)
        self.btn_langtpl.clicked.connect(self.export_template)
        self.btn_about.clicked.connect(self.show_about)
        self.btn_support.clicked.connect(lambda: self._open_url(SUPPORT_URL))
        self._fill_lang()

    def _fill_lang(self):
        self.cb_lang.blockSignals(True)
        self.cb_lang.clear()
        for code, name in i18n.languages():
            self.cb_lang.addItem(name, code)
        self.cb_lang.setCurrentIndex(max(0, self.cb_lang.findData(i18n.language())))
        self.cb_lang.blockSignals(False)
        self.lbl_lang.setText(tr("Bahasa:"))
        self.btn_langdir.setText(tr("Folder bahasa"))
        self.btn_langdir.setToolTip(tr("Buka folder tempat berkas bahasa buatan Anda disimpan (.json)."))
        self.btn_langtpl.setText(tr("Ekspor templat terjemahan"))
        self.btn_langtpl.setToolTip(tr("Membuat berkas terjemahan kosong di folder bahasa untuk Anda isi dengan bahasa baru."))
        self.btn_about.setText(tr("Tentang"))
        self.btn_support.setText(tr("Dukung pembuat"))

    def _lang_changed(self, _i):
        code = self.cb_lang.currentData()
        if not code or code == i18n.language():
            return
        snap = self.snapshot()
        i18n.set_language(code)
        try:
            QSettings().setValue(SET + "lang", code)
        except Exception:
            pass
        self._fill_lang()
        self.build(snap)

    def open_lang_folder(self):
        d = i18n.user_dir()
        os.makedirs(d, exist_ok=True)
        self._open(d)

    def export_template(self):
        d = i18n.user_dir()
        os.makedirs(d, exist_ok=True)
        path, n = os.path.join(d, "my_language.json"), 1
        while os.path.exists(path):
            n += 1
            path = os.path.join(d, "my_language_%d.json" % n)
        i18n.export_template(path)
        QMessageBox.information(
            self, tr("Templat terjemahan"),
            tr("Templat dibuat:\n%s\n\nIsi nilai terjemahannya, ubah \"name\" pada \"_meta\" menjadi nama bahasa, "
               "ganti nama berkas dengan kode bahasa (mis. de.json), lalu buka kembali plugin atau pilih bahasa baru "
               "dari daftar.") % path)
        i18n.reload()
        self._fill_lang()
        self._open(d)

    def show_about(self):
        t = ("<h3>%s %s</h3><p>%s</p><p><b>%s:</b> %s<br><b>Email:</b> <a href='mailto:%s'>%s</a><br>"
             "<b>%s:</b> <a href='%s'>%s</a></p><p>%s</p>") % (
            esc(tr("Analisis Hidrologi DEM")), esc(plugin_version()),
            esc(tr("Seluruh analisis hidrologi yang dapat diturunkan dari DEM, lengkap dengan simbologi, peta standar, "
                   "rekap Excel dan laporan PDF.")),
            esc(tr("Pembuat")), AUTHOR, EMAIL, EMAIL, esc(tr("Dukung pengembangan")), SUPPORT_URL, SUPPORT_URL,
            esc(tr("Lisensi: GNU GPL v2 atau lebih baru.")))
        m = QMessageBox(self)
        m.setWindowTitle(tr("Tentang"))
        m.setTextFormat(Qt.RichText)
        m.setText(t)
        m.setTextInteractionFlags(Qt.TextBrowserInteraction)
        m.exec_()

    @staticmethod
    def _open_url(url):
        QDesktopServices.openUrl(QUrl(url))

    # ------------------------------------------------------------ build / rebuild
    def snapshot(self):
        if getattr(self, "body", None) is None:
            return {}
        lid = lambda cb: (cb.currentLayer().id() if cb.currentLayer() is not None else None)
        return dict(
            dem=lid(self.cb_dem), bnd=lid(self.cb_bnd), adm=lid(self.cb_adm), admf=self.cb_admf.currentField(),
            pour=lid(self.cb_pour), pourf=self.cb_pourf.currentField(), outdir=self.fw_out.filePath(),
            title=self.ed_title.text(), area=self.ed_area.text(), selected=self.selected(),
            params={k: f.values() for k, f in self.param_forms.items()}, dpi=self.sp_dpi.value(),
            sel_only=self.ck_sel.isChecked(),
            outs=[c.isChecked() for c in (self.ck_layers, self.ck_maps, self.ck_xlsx, self.ck_pdf)],
            tab=self.tabs.currentIndex(), log=self.log_view.toPlainText(), default_title=self._default_title)

    def restore(self, sn):
        prj = QgsProject.instance()
        for cb, key in ((self.cb_dem, "dem"), (self.cb_bnd, "bnd"), (self.cb_adm, "adm"), (self.cb_pour, "pour")):
            lyr = prj.mapLayer(sn.get(key)) if sn.get(key) else None
            if lyr is not None:
                cb.setLayer(lyr)
        if sn.get("admf"):
            self.cb_admf.setField(sn["admf"])
        if sn.get("pourf"):
            self.cb_pourf.setField(sn["pourf"])
        self.fw_out.setFilePath(sn.get("outdir", ""))
        t = sn.get("title", "")
        self.ed_title.setText(self._default_title if (not t or t == sn.get("default_title")) else t)
        self.ed_area.setText(sn.get("area", ""))
        self.set_checked(sn.get("selected", []))
        for k, v in sn.get("params", {}).items():
            if k in self.param_forms:
                self.param_forms[k].set_values(v)
        self.sp_dpi.setValue(sn.get("dpi", 120))
        self.ck_sel.setChecked(sn.get("sel_only", True))
        for c, v in zip((self.ck_layers, self.ck_maps, self.ck_xlsx, self.ck_pdf), sn.get("outs", [True] * 4)):
            c.setChecked(v)
        self.log_view.setPlainText(sn.get("log", ""))
        self.tabs.setCurrentIndex(sn.get("tab", 0))

    def build(self, snap=None):
        if self.body is not None:
            self.root.removeWidget(self.body)
            self.body.setParent(None)
            self.body.deleteLater()
        self.setWindowTitle(tr("Analisis Hidrologi DEM") + "  -  " + AUTHOR)
        self._default_title = tr("Analisis Hidrologi DEM")
        self.body = QWidget()
        root = QVBoxLayout(self.body)
        root.setContentsMargins(0, 0, 0, 0)
        self.root.addWidget(self.body, 1)
        self.tabs = QTabWidget()
        root.addWidget(self.tabs, 1)
        self._tab_data()
        self._tab_analyses()
        self._tab_params()
        self._tab_output()
        self._tab_run()
        bar = QHBoxLayout()
        self.pb = QProgressBar()
        self.pb.setRange(0, 1000)
        self.lbl = QLabel(tr("Siap."))
        self.btn_run = QPushButton(tr("Jalankan analisis"))
        self.btn_run.setStyleSheet("font-weight:bold; padding:6px 18px;")
        self.btn_cancel = QPushButton(tr("Batal"))
        self.btn_cancel.setEnabled(False)
        self.btn_close = QPushButton(tr("Tutup"))
        bar.addWidget(self.lbl, 1)
        bar.addWidget(self.pb, 2)
        bar.addWidget(self.btn_run)
        bar.addWidget(self.btn_cancel)
        bar.addWidget(self.btn_close)
        root.addLayout(bar)
        self.btn_run.clicked.connect(self.on_run)
        self.btn_cancel.clicked.connect(self.on_cancel)
        self.btn_close.clicked.connect(self.close)
        if snap:
            self.restore(snap)
        else:
            self.load_settings()
        self.show_detail(None)

    # ------------------------------------------------------------------ tab Data
    def _tab_data(self):
        w = QWidget()
        g = QGridLayout(w)
        g.setColumnStretch(1, 1)
        r = 0

        def row(label, widget, help_=None):
            nonlocal r
            lb = QLabel(label)
            lb.setWordWrap(True)
            g.addWidget(lb, r, 0)
            g.addWidget(widget, r, 1)
            if help_:
                widget.setToolTip(help_)
            r += 1

        self.cb_dem = QgsMapLayerComboBox()
        self.cb_dem.setFilters(QgsMapLayerProxyModel.RasterLayer)
        row(tr("DEM (raster ketinggian, satuan meter)"), self.cb_dem,
            tr("DEM ber-CRS geografis akan diproyeksikan otomatis ke UTM. Nilai elevasi harus dalam meter."))
        self.cb_bnd = QgsMapLayerComboBox()
        self.cb_bnd.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        row(tr("Batas kawasan studi (poligon)"), self.cb_bnd)
        self.ck_sel = QCheckBox(tr("Pakai hanya fitur terpilih bila ada"))
        self.ck_sel.setChecked(True)
        row("", self.ck_sel)
        self.cb_adm = QgsMapLayerComboBox()
        self.cb_adm.setFilters(QgsMapLayerProxyModel.PolygonLayer)
        self.cb_adm.setAllowEmptyLayer(True)
        self.cb_adm.setCurrentIndex(0)
        row(tr("Batas administrasi (opsional, untuk garis dan label di peta)"), self.cb_adm)
        self.cb_admf = QgsFieldComboBox()
        self.cb_admf.setLayer(None)
        row(tr("Kolom label administrasi"), self.cb_admf, tr("Mis. nama desa/kelurahan."))
        self.cb_adm.layerChanged.connect(self._adm_changed)
        self.cb_pour = QgsMapLayerComboBox()
        self.cb_pour.setFilters(QgsMapLayerProxyModel.PointLayer)
        self.cb_pour.setAllowEmptyLayer(True)
        self.cb_pour.setCurrentIndex(0)
        row(tr("Titik outlet / pour point (opsional, untuk DAS titik)"), self.cb_pour)
        self.cb_pourf = QgsFieldComboBox()
        row(tr("Kolom nama titik outlet"), self.cb_pourf)
        self.cb_pour.layerChanged.connect(lambda l: self.cb_pourf.setLayer(l))
        self.fw_out = QgsFileWidget()
        self.fw_out.setStorageMode(QgsFileWidget.GetDirectory)
        row(tr("Folder keluaran"), self.fw_out)
        self.ed_title = QLineEdit(self._default_title)
        row(tr("Judul laporan"), self.ed_title)
        self.ed_area = QLineEdit()
        self.ed_area.setPlaceholderText(tr("Mis. Kecamatan Ngoro, Kabupaten Mojokerto"))
        row(tr("Nama kawasan (tampil pada subjudul peta)"), self.ed_area)
        g.setRowStretch(r, 1)
        note = QLabel(tr("Catatan: seluruh analisis memakai DEM saja. DEM berupa DSM (memuat tajuk dan bangunan) "
                         "dapat membelokkan aliran; DTM lebih tepat untuk hidrologi."))
        note.setWordWrap(True)
        note.setStyleSheet("color:#555;")
        g.addWidget(note, r + 1, 0, 1, 2)
        self.tabs.addTab(w, tr("1. Data"))

    def _adm_changed(self, lyr):
        self.cb_admf.setLayer(lyr)
        if lyr is not None:
            for n in ("nama", "NAMOBJ", "name", "NAME", "DESA", "desa", "WADMKD", "namobj"):
                if n in lyr.fields().names():
                    self.cb_admf.setField(n)
                    break

    # ---------------------------------------------------------------- tab Analisis
    def _tab_analyses(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        for txt, fn in [(tr("Pilih semua"), lambda: self.set_checked(list(R.L()["ANALYSES"]))),
                        (tr("Kosongkan"), lambda: self.set_checked([]))]:
            b = QPushButton(txt)
            b.clicked.connect(fn)
            top.addWidget(b)
        top.addWidget(QLabel(tr("Paket:")))
        self.cb_preset = QComboBox()
        self.cb_preset.addItem(tr("(pilih paket)"))
        for n in R.L()["PRESETS"]:
            self.cb_preset.addItem(n)
        self.cb_preset.currentIndexChanged.connect(self._preset)
        top.addWidget(self.cb_preset)
        top.addStretch(1)
        self.lbl_count = QLabel("")
        top.addWidget(self.lbl_count)
        lay.addLayout(top)
        sp = QSplitter(Qt.Horizontal)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.items = {}
        for grp in R.L()["GROUPS"]:
            gi = QTreeWidgetItem([grp])
            gi.setFlags(gi.flags() | Qt.ItemIsUserCheckable | Qt.ItemIsAutoTristate)
            gi.setCheckState(0, Qt.Unchecked)
            f = gi.font(0)
            f.setBold(True)
            gi.setFont(0, f)
            self.tree.addTopLevelItem(gi)
            for k, a in R.L()["ANALYSES"].items():
                if a["group"] != grp:
                    continue
                it = QTreeWidgetItem([a["name"]])
                it.setFlags(it.flags() | Qt.ItemIsUserCheckable)
                it.setCheckState(0, Qt.Unchecked)
                it.setData(0, Qt.UserRole, k)
                gi.addChild(it)
                self.items[k] = it
            gi.setExpanded(True)
        self.tree.itemChanged.connect(lambda *_: self._count())
        self.tree.currentItemChanged.connect(lambda cur, _p: self.show_detail(cur.data(0, Qt.UserRole) if cur else None))
        sp.addWidget(self.tree)
        self.detail = QTextBrowser()
        self.detail.setOpenExternalLinks(False)
        sp.addWidget(self.detail)
        sp.setSizes([520, 620])
        lay.addWidget(sp, 1)
        self.tabs.addTab(w, tr("2. Analisis"))

    def _preset(self, i):
        if i <= 0:
            return
        name = self.cb_preset.itemText(i)
        self.set_checked(R.L()["PRESETS"][name])
        self.cb_preset.blockSignals(True)
        self.cb_preset.setCurrentIndex(0)
        self.cb_preset.blockSignals(False)

    def set_checked(self, keys):
        self.tree.blockSignals(True)
        for k, it in self.items.items():
            it.setCheckState(0, Qt.Checked if k in keys else Qt.Unchecked)
        self.tree.blockSignals(False)
        for gi in [self.tree.topLevelItem(i) for i in range(self.tree.topLevelItemCount())]:
            n = sum(1 for j in range(gi.childCount()) if gi.child(j).checkState(0) == Qt.Checked)
            gi.setCheckState(0, Qt.Checked if n == gi.childCount() else Qt.PartiallyChecked if n else Qt.Unchecked)
        self._count()

    def selected(self):
        return [k for k, it in self.items.items() if it.checkState(0) == Qt.Checked]

    def _count(self):
        n = len(self.selected())
        self.lbl_count.setText(tr("%d dari %d analisis dipilih") % (n, len(R.L()["ANALYSES"])))
        if hasattr(self, "param_forms"):
            for k, f in self.param_forms.items():
                f.setVisible(k == "core" or k in self.selected())

    def show_detail(self, key):
        if not key or key not in R.L()["ANALYSES"]:
            self.detail.setHtml("<p style='color:#555'>" + esc(tr("Pilih sebuah analisis di sebelah kiri untuk melihat dasar ilmiah, "
                                "rumus, keluaran, dan batasannya. Beri tanda centang untuk menjalankannya. "
                                "Analisis turunan (indeks komposit, HAND flood, dsb.) otomatis menghitung prasyaratnya.")) + "</p>")
            return
        a = R.L()["ANALYSES"][key]
        h = ["<h3>%s</h3><p>%s</p>" % (esc(a["name"]), esc(a["desc"]))]
        h.append("<p><b>" + esc(tr("Keluaran")) + ":</b><br>" + "<br>".join("&bull; " + esc(t) for _, t, _k in a["outputs"]) + "</p>")
        if R.DEPENDS.get(key):
            h.append(tr("<p><b>Memakai hasil:</b> %s</p>") % esc(", ".join(R.L()["ANALYSES"][x]["name"] for x in R.DEPENDS[key])))
        if a["formula"]:
            h.append(tr("<p><b>Rumus / prosedur:</b> %s</p>") % esc(a["formula"]))
        if a["limits"]:
            h.append(tr("<p><b>Batasan:</b> %s</p>") % esc(a["limits"]))
        if a["params"]:
            h.append("<p><b>" + esc(tr("Parameter (tab 3)")) + ":</b> " + esc("; ".join(p["label"] for p in a["params"])) + "</p>")
        refs = R.refs_for(a["refs"])
        if refs:
            h.append("<p><b>" + esc(tr("Dasar ilmiah")) + ":</b></p><ul>" + "".join(tr("<li><small>%s</small></li>") % esc(t) for _k, t in refs) + "</ul>")
        self.detail.setHtml("".join(h))

    # ---------------------------------------------------------------- tab Parameter
    def _tab_params(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        top = QHBoxLayout()
        b = QPushButton(tr("Kembalikan semua ke nilai bawaan"))
        b.clicked.connect(lambda: [f.reset() for f in self.param_forms.values()])
        top.addWidget(b)
        top.addStretch(1)
        top.addWidget(QLabel(tr("Hanya analisis yang dicentang pada tab 2 yang tampil.")))
        lay.addLayout(top)
        sc = QScrollArea()
        sc.setWidgetResizable(True)
        inner = QWidget()
        il = QVBoxLayout(inner)
        self.param_forms = {}
        f = ParamForm(tr("Umum (berlaku untuk seluruh analisis)"), R.L()["CORE_PARAMS"])
        self.param_forms["core"] = f
        il.addWidget(f)
        for k, a in R.L()["ANALYSES"].items():
            if a["params"]:
                f = ParamForm(a["name"], a["params"])
                self.param_forms[k] = f
                il.addWidget(f)
        il.addStretch(1)
        sc.setWidget(inner)
        lay.addWidget(sc, 1)
        self.tabs.addTab(w, tr("3. Parameter"))

    # ---------------------------------------------------------------- tab Keluaran
    def _tab_output(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        g = QGroupBox(tr("Hasil yang dibuat"))
        gl = QVBoxLayout(g)
        self.ck_layers = QCheckBox(tr("Muat hasil ke proyek QGIS (sudah bersimbologi)"))
        self.ck_layers.setChecked(True)
        self.ck_maps = QCheckBox(tr("Peta standar (PNG) untuk setiap keluaran"))
        self.ck_maps.setChecked(True)
        self.ck_xlsx = QCheckBox(tr("Rekapitulasi Excel (.xlsx)"))
        self.ck_xlsx.setChecked(True)
        self.ck_pdf = QCheckBox(tr("Laporan PDF (peta, tabel, morfometri, metode, pustaka)"))
        self.ck_pdf.setChecked(True)
        for c in (self.ck_layers, self.ck_maps, self.ck_xlsx, self.ck_pdf):
            gl.addWidget(c)
        lay.addWidget(g)
        g2 = QGroupBox(tr("Peta"))
        f = QFormLayout(g2)
        self.sp_dpi = QSpinBox()
        self.sp_dpi.setRange(72, 300)
        self.sp_dpi.setValue(120)
        f.addRow(tr("Resolusi peta (dpi)"), self.sp_dpi)
        lay.addWidget(g2)
        t = QLabel(tr("Berkas disimpan pada folder keluaran: subfolder <b>results</b> (GeoTIFF dan GeoPackage), "
                   "<b>maps</b> (PNG), serta berkas Excel dan PDF."))
        t.setWordWrap(True)
        lay.addWidget(t)
        lay.addStretch(1)
        self.tabs.addTab(w, tr("4. Keluaran"))

    # ---------------------------------------------------------------- tab Proses
    def _tab_run(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        self.log_view = QPlainTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setFont(QFont("Consolas", 9))
        lay.addWidget(self.log_view, 1)
        row = QHBoxLayout()
        self.btn_folder = QPushButton(tr("Buka folder keluaran"))
        self.btn_pdf = QPushButton(tr("Buka PDF"))
        self.btn_xlsx = QPushButton(tr("Buka Excel"))
        for b in (self.btn_folder, self.btn_pdf, self.btn_xlsx):
            b.setEnabled(False)
            row.addWidget(b)
        row.addStretch(1)
        lay.addLayout(row)
        self.btn_folder.clicked.connect(lambda: self._open(self.fw_out.filePath()))
        self.btn_pdf.clicked.connect(lambda: self._open(self.last["files"].get("pdf")))
        self.btn_xlsx.clicked.connect(lambda: self._open(self.last["files"].get("excel")))
        self.tabs.addTab(w, tr("5. Proses"))

    def _open(self, path):
        if path:
            QDesktopServices.openUrl(QUrl.fromLocalFile(path))

    # ---------------------------------------------------------------- jalan
    def log(self, m):
        self.log_view.appendPlainText(m)
        QApplication.processEvents()
        if self.cancel:
            raise InterruptedError(tr("Dibatalkan pengguna"))

    def progress(self, f, m):
        if f is not None:
            self.pb.setValue(int(f * 1000))
        if m:
            self.lbl.setText(m)
        QApplication.processEvents()
        if self.cancel:
            raise InterruptedError(tr("Dibatalkan pengguna"))

    def collect(self):
        par = {k: f.values() for k, f in self.param_forms.items()}
        return RN.Settings(
            dem=self.cb_dem.currentLayer(), boundary=self.cb_bnd.currentLayer(), admin=self.cb_adm.currentLayer(),
            admin_field=self.cb_admf.currentField() or None, pour=self.cb_pour.currentLayer(),
            pour_field=self.cb_pourf.currentField() or None, outdir=self.fw_out.filePath(), selected=self.selected(),
            params=par, title=self.ed_title.text().strip() or self._default_title, area_name=self.ed_area.text().strip(),
            make_maps=self.ck_maps.isChecked(), make_excel=self.ck_xlsx.isChecked(), make_pdf=self.ck_pdf.isChecked(),
            load_layers=self.ck_layers.isChecked(), only_selected_features=self.ck_sel.isChecked(), dpi=self.sp_dpi.value())

    def on_cancel(self):
        self.cancel = True
        self.lbl.setText(tr("Membatalkan..."))

    def on_run(self):
        if self.running:
            return
        s = self.collect()
        errs = RN.validate(s)
        if errs:
            QMessageBox.warning(self, tr("Lengkapi dulu"), "\n".join("- " + e for e in errs))
            return
        self.save_settings()
        self.running, self.cancel = True, False
        for b in (self.btn_run,):
            b.setEnabled(False)
        self.btn_cancel.setEnabled(True)
        self.tabs.setCurrentIndex(4)
        self.log_view.clear()
        self.pb.setValue(0)
        for b in (self.btn_folder, self.btn_pdf, self.btn_xlsx):
            b.setEnabled(False)
        try:
            self.last = RN.run(s, self.log, self.progress)
            pl = self.last["pipeline"]
            self.log(tr("\n=== SELESAI (%.0f detik) ===") % self.last["seconds"])
            fails = [k for k, v in pl.status.items() if v != "ok"]
            for k in fails:
                self.log(tr("Gagal: %s -> %s") % (R.L()["ANALYSES"][k]["name"], pl.status[k]))
            for wmsg in pl.warnings:
                self.log(tr("Perhatian: ") + wmsg)
            for k, v in self.last["files"].items():
                if isinstance(v, str):
                    self.log("%s: %s" % (k, v))
            self.btn_folder.setEnabled(True)
            self.btn_pdf.setEnabled("pdf" in self.last["files"])
            self.btn_xlsx.setEnabled("excel" in self.last["files"])
            self.lbl.setText(tr("Selesai."))
            self.pb.setValue(1000)
            ok_n = sum(1 for v in pl.status.values() if v == "ok")
            if ok_n:
                self.success_popup(s, ok_n, len(pl.status))
            if self.iface is not None:
                try:
                    self.iface.mapCanvas().refresh()
                    self.iface.messageBar().pushSuccess(tr("Analisis Hidrologi DEM"), tr("Selesai. Hasil ada di %s") % s.outdir)
                except Exception:
                    pass
        except InterruptedError:
            self.log(tr("\nDibatalkan."))
            self.lbl.setText(tr("Dibatalkan."))
        except Exception as ex:
            self.log(tr("\nKESALAHAN: %s\n%s") % (ex, traceback.format_exc()))
            self.lbl.setText(tr("Gagal."))
            QMessageBox.critical(self, tr("Gagal"), str(ex))
        finally:
            self.running = False
            self.btn_run.setEnabled(True)
            self.btn_cancel.setEnabled(False)

    # ---------------------------------------------------------------- pop-up sukses
    def success_popup(self, s, ok_n, total):
        """Shown after every successful run: summary + link to support the author."""
        pl = self.last["pipeline"]
        txt = tr("%d dari %d analisis berhasil dalam %.0f detik.") % (ok_n, total, self.last["seconds"])
        if ok_n < total:
            txt += " " + tr("%d analisis gagal; rinciannya ada di tab Proses.") % (total - ok_n)
        txt += "\n\n" + tr("Hasil tersimpan di:") + "\n" + s.outdir
        thanks = tr("Plugin ini gratis dan dikembangkan secara mandiri. Jika bermanfaat, dukung pembuatnya agar "
                    "pengembangan terus berlanjut:")
        self.last_popup_text = txt + "\n\n" + thanks + "\n" + SUPPORT_URL
        if not self.show_popup:
            return
        m = QMessageBox(self)
        m.setIcon(QMessageBox.Information)
        m.setWindowTitle(tr("Analisis selesai"))
        m.setTextFormat(Qt.RichText)
        m.setText("<b>%s</b>" % esc(tr("Analisis berhasil!")))
        m.setInformativeText(
            esc(txt).replace("\n", "<br>") + "<br><br>" + esc(thanks) + "<br><a href='%s'>%s</a>" % (SUPPORT_URL, SUPPORT_URL))
        m.setTextInteractionFlags(Qt.TextBrowserInteraction)
        b_sup = m.addButton(tr("Dukung pembuat (SociaBuzz)"), QMessageBox.ActionRole)
        b_fold = m.addButton(tr("Buka folder keluaran"), QMessageBox.ActionRole)
        b_pdf = None
        if "pdf" in self.last["files"]:
            b_pdf = m.addButton(tr("Buka PDF"), QMessageBox.ActionRole)
        m.addButton(tr("Tutup"), QMessageBox.RejectRole)
        m.exec_()
        c = m.clickedButton()
        if c is b_sup:
            self._open_url(SUPPORT_URL)
        elif c is b_fold:
            self._open(s.outdir)
        elif b_pdf is not None and c is b_pdf:
            self._open(self.last["files"]["pdf"])

    # ---------------------------------------------------------------- simpan
    def save_settings(self):
        try:
            s = QSettings()
            s.setValue(SET + "outdir", self.fw_out.filePath())
            s.setValue(SET + "title", "" if self.ed_title.text() == self._default_title else self.ed_title.text())
            s.setValue(SET + "area", self.ed_area.text())
            s.setValue(SET + "selected", json.dumps(self.selected()))
            s.setValue(SET + "params", json.dumps({k: f.values() for k, f in self.param_forms.items()}))
            s.setValue(SET + "dpi", self.sp_dpi.value())
            s.setValue(SET + "lang", i18n.language())
        except Exception:
            pass

    def load_settings(self):
        try:
            s = QSettings()
            self.fw_out.setFilePath(s.value(SET + "outdir", "") or "")
            t = s.value(SET + "title", "") or ""
            self.ed_title.setText(self._default_title if t in ("", "Analisis Hidrologi DEM", "DEM Hydrology Toolkit") else t)
            self.ed_area.setText(s.value(SET + "area", "") or "")
            sel = json.loads(s.value(SET + "selected", "[]") or "[]")
            self.set_checked([k for k in sel if k in R.L()["ANALYSES"]] or R.L()["PRESETS"][R.L()["DEFAULT_PRESET"]])
            pv = json.loads(s.value(SET + "params", "{}") or "{}")
            for k, v in pv.items():
                if k in self.param_forms:
                    self.param_forms[k].set_values(v)
            self.sp_dpi.setValue(int(s.value(SET + "dpi", 120) or 120))
        except Exception:
            self.set_checked(R.L()["PRESETS"][R.L()["DEFAULT_PRESET"]])
        self._count()

    def closeEvent(self, ev):
        if self.running:
            ev.ignore()
            QMessageBox.information(self, tr("Sedang berjalan"), tr("Klik Batal dulu bila ingin menghentikan proses."))
            return
        self.save_settings()
        ev.accept()
