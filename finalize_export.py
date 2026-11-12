#!/usr/bin/env python3
"""Post-process a Cubism "Export For Runtime" (moc3) folder.

  - writes <model>.physics3.json from the config's "physics" list
    (2-vertex pendulum per entry, inputs: ParamAngleX/Z 60%, ParamBodyAngleX/Z 40%)
  - sets FileReferences.Physics in <model>.model3.json
  - fills the EyeBlink / LipSync groups from "eye_blink" / "lip_sync"
  - checks the moc3 version byte (<= --max-moc 5 by default)

Usage:
  python3 finalize_export.py CONFIG.json EXPORT_DIR [--max-moc N]

Config keys:
  physics   [{name, output, scale, length=3, delay=0.9, mobility=0.95, acceleration=1.5, angle_range=10}]
  eye_blink [parameter ids]
  lip_sync  [parameter ids]
"""
import argparse
import glob
import json
import os
import sys

INPUTS = [("ParamAngleX", 60, "X"), ("ParamAngleZ", 60, "Angle"),
          ("ParamBodyAngleX", 40, "X"), ("ParamBodyAngleZ", 40, "Angle")]


def setting(i, p):
    L = p.get("length", 3)
    R = p.get("angle_range", 10)
    return {
        "Id": f"PhysicsSetting{i}",
        "Input": [{"Source": {"Target": "Parameter", "Id": pid}, "Weight": w, "Type": t, "Reflect": False}
                  for pid, w, t in INPUTS],
        "Output": [{"Destination": {"Target": "Parameter", "Id": p["output"]}, "VertexIndex": 1,
                    "Scale": p["scale"], "Weight": 100, "Type": "Angle", "Reflect": False}],
        "Vertices": [
            {"Position": {"X": 0, "Y": 0}, "Mobility": 1, "Delay": 1, "Acceleration": 1, "Radius": 0},
            {"Position": {"X": 0, "Y": L}, "Mobility": p.get("mobility", 0.95), "Delay": p.get("delay", 0.9),
             "Acceleration": p.get("acceleration", 1.5), "Radius": L},
        ],
        "Normalization": {"Position": {"Minimum": -10, "Default": 0, "Maximum": 10},
                          "Angle": {"Minimum": -R, "Default": 0, "Maximum": R}},
    }


def physics(entries):
    s = [setting(i, p) for i, p in enumerate(entries, 1)]
    return {
        "Version": 3,
        "Meta": {
            "PhysicsSettingCount": len(s),
            "TotalInputCount": sum(len(x["Input"]) for x in s),
            "TotalOutputCount": sum(len(x["Output"]) for x in s),
            "VertexCount": sum(len(x["Vertices"]) for x in s),
            "EffectiveForces": {"Gravity": {"X": 0, "Y": -1}, "Wind": {"X": 0, "Y": 0}},
            "PhysicsDictionary": [{"Id": x["Id"], "Name": p.get("name", p["output"])} for x, p in zip(s, entries)],
        },
        "PhysicsSettings": s,
    }


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("config")
    ap.add_argument("export_dir")
    ap.add_argument("--max-moc", type=int, default=5)
    a = ap.parse_args()
    cfg = json.load(open(a.config, encoding="utf-8"))

    found = glob.glob(os.path.join(a.export_dir, "*.model3.json"))
    if len(found) != 1:
        sys.exit(f"expected exactly one *.model3.json in {a.export_dir}, found {len(found)}")
    m3 = found[0]
    base = os.path.basename(m3)[:-len(".model3.json")]
    m = json.load(open(m3, encoding="utf-8"))
    fr = m.setdefault("FileReferences", {})

    moc = os.path.join(a.export_dir, fr.get("Moc", ""))
    ver = open(moc, "rb").read()[4]
    print(f"moc3 version {ver}")
    if ver > a.max_moc:
        sys.exit(f"moc3 version {ver} > {a.max_moc}: re-export with an older 'Export version' (e.g. SDK 5.0)")

    if cfg.get("physics"):
        name = f"{base}.physics3.json"
        with open(os.path.join(a.export_dir, name), "w", encoding="utf-8") as f:
            json.dump(physics(cfg["physics"]), f, ensure_ascii=False, indent="\t")
        fr["Physics"] = name
        print(f"physics: {len(cfg['physics'])} settings -> {name}")

    groups = {g["Name"]: g for g in m.setdefault("Groups", [])}
    for key, gname in (("eye_blink", "EyeBlink"), ("lip_sync", "LipSync")):
        if key in cfg:
            if gname not in groups:
                groups[gname] = {"Target": "Parameter", "Name": gname, "Ids": []}
                m["Groups"].append(groups[gname])
            groups[gname]["Ids"] = list(cfg[key])
            print(f"{gname}: {cfg[key]}")

    with open(m3, "w", encoding="utf-8") as f:
        json.dump(m, f, ensure_ascii=False, indent="\t")
    print(f"updated {os.path.basename(m3)}")


if __name__ == "__main__":
    main()
