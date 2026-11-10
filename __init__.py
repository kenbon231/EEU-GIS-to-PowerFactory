def classFactory(iface):
    from .eeu_gis_to_pf import classFactory as factory
    return factory(iface)
