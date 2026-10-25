# -*- coding: utf-8 -*-
from .i18n import tr
import os

from qgis.PyQt.QtGui import QIcon
from qgis.PyQt.QtWidgets import QAction


class HidrologiDemPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dlg = None
        self.dir = os.path.dirname(__file__)

    def initGui(self):
        self.action = QAction(QIcon(os.path.join(self.dir, "icon.svg")), "DEM Hydrology Toolkit", self.iface.mainWindow())
        self.action.setToolTip("All DEM-based hydrology analyses with auto symbology, standard maps, Excel and PDF reports")
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&DEM Hydrology Toolkit", self.action)

    def unload(self):
        if self.action is not None:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&DEM Hydrology Toolkit", self.action)
        if self.dlg is not None:
            self.dlg.close()
            self.dlg = None

    def run(self):
        from .dialog import HidrologiDialog
        if self.dlg is None:
            self.dlg = HidrologiDialog(self.iface, self.iface.mainWindow())
        self.dlg.show()
        self.dlg.raise_()
        self.dlg.activateWindow()
