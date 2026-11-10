EEU GIS to DIgSILENT PowerFactory - QGIS plugin prototype

GitHub: https://github.com/kenbon231/EEU-GIS-to-PowerFactory

The plugin exports selected QGIS vector layers to CSV staging tables, a manifest,
and a QA report. It is a GIS extraction and preparation tool, not yet a native
DGS writer or automatic PowerFactory model builder.

Install locally by copying this folder into the QGIS profile's python/plugins
directory, restarting QGIS, and enabling the plugin in Plugin Manager.

Review all electrical parameters and topology before using exported data in
PowerFactory. Missing R/X, transformer impedance/losses, voltage, ratings,
switch state and load parameters are not invented by this plugin.
