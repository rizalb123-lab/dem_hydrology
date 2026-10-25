# -*- coding: utf-8 -*-
def classFactory(iface):
    from .plugin import HidrologiDemPlugin
    return HidrologiDemPlugin(iface)
