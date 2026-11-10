# -*- coding: utf-8 -*-
"""
EEU GIS to DIgSILENT PowerFactory - QGIS 3.34 plugin
Exports selected EEU distribution GIS layers to clean CSV tables for PowerFactory
model preparation. It does not invent missing electrical parameters.
"""
import os, csv, json, traceback
from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtWidgets import ( QAction, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QComboBox, QPushButton, QFileDialog, QMessageBox, QLineEdit,
    QFormLayout, QCheckBox )
from qgis.core import ( QgsProject, QgsVectorLayer, QgsWkbTypes,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform, QgsFeatureRequest, QgsGeometry )

PLUGIN_NAME = "EEU GIS to PowerFactory"

# Candidate names are suggestions only; the user can choose actual project layers.
LAYER_ROLES = {
    "substation": ["Substation", "PowerSubstation", "SS"],
    "mv_overhead": ["MV_Overhead", "MVOverhead", "OverheadLine"],
    "mv_underground": ["MV_Underground", "MVUnderground", "UndergroundCable"],
    "transformer": ["PowerDistributionTransformer", "Transformer", "DistributionTransformer"],
    "switch": ["MV_Switch", "MVSwitch", "Switch"],
    "pole": ["MV_Pole", "MVPole", "Pole"],
    "load": ["Load", "CustomerLoad", "DistributionLoad"],
}

def _safe_name(s):
    return "".join(c if c.isalnum() or c in "_-" else "_" for c in s)

def _value(feature, names):
    """Return first non-null attribute matching candidate names (case-insensitive)."""
    fields = {f.name().lower(): f.name() for f in feature.fields()}
    for n in names:
        actual = fields.get(n.lower())
        if actual:
            v = feature[actual]
            if v is not None and str(v).strip() not in ("", "NULL", "None"):
                return v
    return None

def _as_float(v):
    if v is None:
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except Exception:
        return None

def _feature_record(layer, feature, role, target_crs):
    geom = feature.geometry()
    x = y = None
    if geom and not geom.isEmpty():
        g = QgsGeometry(geom)
        if layer.crs().isValid() and target_crs.isValid() and layer.crs() != target_crs:
            tr = QgsCoordinateTransform(layer.crs(), target_crs, QgsProject.instance())
            g.transform(tr)
        p = g.pointOnSurface().asPoint() if QgsWkbTypes.geometryType(g.wkbType()) == QgsWkbTypes.PolygonGeometry else g.centroid().asPoint()
        x, y = p.x(), p.y()
    attrs = {f.name(): feature[f.name()] for f in layer.fields()}
    rec = {
        "source_layer": layer.name(),
        "source_fid": feature.id(),
        "element_role": role,
        "element_id": str(_value(feature, ["Asset_ID","AssetID","Equipment_ID","EquipmentID","Transformer_ID","TransformerID","Line_ID","Pole_ID","ID","Name"]) or feature.id()),
        "name": str(_value(feature, ["Name","name","Asset_Name","Transformer_Name","Line_Name","Substation_Name","Feeder_Name"]) or ""),
        "feeder": str(_value(feature, ["Feeder_Name","FeederName","Feeder","FEEDER"]) or ""),
        "substation": str(_value(feature, ["Substation_Name","SubstationName","Substation","SS_Name","SSName"]) or ""),
        "from_node": str(_value(feature, ["From_Node","FromNode","FromPole","StartNode","From_ID"]) or ""),
        "to_node": str(_value(feature, ["To_Node","ToNode","ToPole","EndNode","To_ID"]) or ""),
        "voltage_kv": _as_float(_value(feature, ["Voltage_kV","VoltageKV","NominalVoltage","RatedVoltage","kV"])),
        "length_m": _as_float(_value(feature, ["Length_m","Shape_Length","Shape_Leng","Length"])),
        "rated_power_kva": _as_float(_value(feature, ["RatedCapacity_kVA","Capacity_kVA","Rated_kVA","KVA","Capacity"])),
        "load_mw": _as_float(_value(feature, ["ExistingLoad_MW","ExistingLoad","Load_MW","P_MW","MW"])),
        "r_ohm_per_km": _as_float(_value(feature, ["R_ohm_km","R_Ohm_per_km","Resistance"])),
        "x_ohm_per_km": _as_float(_value(feature, ["X_ohm_km","X_Ohm_per_km","Reactance"])),
        "x_m": x, "y_m": y,
        "geometry_wkt": geom.asWkt() if geom and not geom.isEmpty() else ""
    }
    # Preserve all source attributes as a JSON column for traceability.
    rec["source_attributes_json"] = json.dumps(attrs, default=str, ensure_ascii=False)
    return rec

class EEU_GIS_to_PowerFactory:
    def __init__(self, iface):
        self.iface = iface
        self.action = None

    def initGui(self):
        self.action = QAction("EEU GIS → PowerFactory", self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("&EEU GIS Tools", self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("&EEU GIS Tools", self.action)

    def run(self):
        dlg = QDialog(self.iface.mainWindow())
        dlg.setWindowTitle("EEU GIS to DIgSILENT PowerFactory")
        dlg.resize(560, 520)
        layout = QVBoxLayout(dlg)
        layout.addWidget(QLabel(
            "Select the GIS layers for one substation. The exporter creates "
            "equipment CSV tables, a QA report and a manifest. Missing electrical "
            "parameters are left blank and reported."
        ))
        form = QFormLayout()
        combos = {}
        project_layers = [l for l in QgsProject.instance().mapLayers().values()
                          if isinstance(l, QgsVectorLayer) and l.isValid()]
        for role in LAYER_ROLES:
            cb = QComboBox()
            cb.addItem("(not selected)", "")
            for lyr in project_layers:
                cb.addItem(lyr.name(), lyr.id())
            # choose first name match if present
            candidates = [x.lower() for x in LAYER_ROLES[role]]
            for i in range(1, cb.count()):
                if cb.itemText(i).lower() in candidates:
                    cb.setCurrentIndex(i); break
            combos[role] = cb
            form.addRow(role.replace("_"," ").title(), cb)
        layout.addLayout(form)
        out_row = QHBoxLayout()
        out_edit = QLineEdit(os.path.join(os.path.expanduser("~"), "EEU_PowerFactory_Export"))
        browse = QPushButton("Browse…")
        def choose():
            p = QFileDialog.getExistingDirectory(dlg, "Choose output folder", out_edit.text())
            if p: out_edit.setText(p)
        browse.clicked.connect(choose)
        out_row.addWidget(out_edit); out_row.addWidget(browse)
        layout.addWidget(QLabel("Output folder"))
        layout.addLayout(out_row)
        epsg = QLineEdit("EPSG:32637")
        layout.addWidget(QLabel("Coordinate system for exported X/Y (use a suitable projected CRS)"))
        layout.addWidget(epsg)
        layout.addWidget(QLabel("Tip: EPSG:32637 is only a default example. Confirm the correct UTM zone for your project."))
        buttons = QHBoxLayout()
        run_btn, cancel_btn = QPushButton("Export"), QPushButton("Cancel")
        buttons.addWidget(run_btn); buttons.addWidget(cancel_btn); layout.addLayout(buttons)
        cancel_btn.clicked.connect(dlg.reject)
        def do_export():
            try:
                output = out_edit.text().strip()
                if not output:
                    raise Exception("Choose an output folder.")
                os.makedirs(output, exist_ok=True)
                target_crs = QgsCoordinateReferenceSystem(epsg.text().strip())
                if not target_crs.isValid():
                    raise Exception("Invalid output CRS. Use an EPSG code such as EPSG:32637.")
                selected = {}
                for role, cb in combos.items():
                    lid = cb.currentData()
                    if lid:
                        lyr = QgsProject.instance().mapLayer(lid)
                        if lyr: selected[role] = lyr
                if not selected:
                    raise Exception("Select at least one GIS layer.")
                manifest = {
                    "tool": PLUGIN_NAME, "qgis_project": QgsProject.instance().fileName(),
                    "output_crs": target_crs.authid(), "selected_layers": {},
                    "warnings": ["CSV outputs are staging tables, not a guaranteed native DGS import file.",
                                 "Review field mappings and PowerFactory type parameters before import."]
                }
                qa = []
                for role, lyr in selected.items():
                    manifest["selected_layers"][role] = {"name": lyr.name(), "feature_count": lyr.featureCount(),
                        "crs": lyr.crs().authid()}
                    path = os.path.join(output, role + ".csv")
                    count = 0
                    with open(path, "w", newline="", encoding="utf-8-sig") as f:
                        writer = None
                        for feat in lyr.getFeatures():
                            rec = _feature_record(lyr, feat, role, target_crs)
                            if writer is None:
                                writer = csv.DictWriter(f, fieldnames=list(rec.keys()))
                                writer.writeheader()
                            writer.writerow(rec); count += 1
                            if role in ("mv_overhead","mv_underground","transformer"):
                                missing = []
                                if rec["voltage_kv"] is None: missing.append("voltage_kv")
                                if role == "transformer" and rec["rated_power_kva"] is None: missing.append("rated_power_kva")
                                if role in ("mv_overhead","mv_underground") and rec["length_m"] is None: missing.append("length_m")
                                if missing:
                                    qa.append({"role":role,"layer":lyr.name(),"fid":feat.id(),
                                               "element_id":rec["element_id"],"issue":"Missing "+", ".join(missing)})
                        if writer is None:
                            writer = csv.DictWriter(f, fieldnames=["source_layer","source_fid","element_role"])
                            writer.writeheader()
                    manifest["selected_layers"][role]["exported_count"] = count
                qa_path = os.path.join(output, "qa_issues.csv")
                with open(qa_path, "w", newline="", encoding="utf-8-sig") as f:
                    cols = ["role","layer","fid","element_id","issue"]
                    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(qa)
                with open(os.path.join(output, "manifest.json"), "w", encoding="utf-8") as f:
                    json.dump(manifest, f, indent=2, ensure_ascii=False)
                with open(os.path.join(output, "README_IMPORT.txt"), "w", encoding="utf-8") as f:
                    f.write("EEU GIS to PowerFactory export\\n\\n")
                    f.write("CSV files are staging tables. Map them to PowerFactory classes/types and validate before load flow.\\n")
                    f.write("Do not treat GIS line length as electrical impedance. Obtain R/X and equipment type data from approved EEU records.\\n")
                    f.write("Check coordinate reference system, voltage levels, node connectivity, transformer vector group, uk%, copper losses, and load power factor.\\n")
                QMessageBox.information(dlg, "Export complete",
                    "Exported %d layer(s). QA issues: %d\\nOutput: %s" % (len(selected), len(qa), output))
                dlg.accept()
            except Exception as e:
                QMessageBox.critical(dlg, "Export failed", str(e) + "\\n\\n" + traceback.format_exc())
        run_btn.clicked.connect(do_export)
        dlg.exec_()

def classFactory(iface):
    return EEU_GIS_to_PowerFactory(iface)
