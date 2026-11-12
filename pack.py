"""Pack a Cubism moc3 export folder into one JS file (moc3, textures, physics, cdi3 as data URLs).

  python3 pack.py MODEL_DIR NAME --out-dir DIR [--frame ZOOM,FX,FY]

  MODEL_DIR  Cubism moc3 export; exactly one *.model3.json
  NAME       [a-z][a-z0-9_-]{1,30}; output <out-dir>/<NAME>/model.js
  --frame    ZOOM: model width / canvas width; FX, FY: model point (width/height fraction) at frame center
             default 3,0.5,0.2
  --out-dir  output root (required)

Output defines window.L2D_MODELS[NAME] (model3.json with data URLs) and window.L2D_FRAMES[NAME] ({zoom, fx, fy}).
Exit 1 if a NEED parameter id is missing from the cdi3.json; missing NICE ids are listed as warnings.
"""
import base64
import glob
import json
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
NAME_RE = re.compile(r"^[a-z][a-z0-9_-]{1,30}$")
# Parameter ids checked against the cdi3.json: NEED missing -> exit 1, NICE missing -> warning
NEED = ["ParamAngleX", "ParamAngleY", "ParamAngleZ", "ParamEyeLOpen", "ParamEyeROpen", "ParamMouthOpenY"]
NICE = ["ParamMouthForm", "ParamEyeBallX", "ParamEyeBallY", "ParamEyeLSmile", "ParamEyeRSmile", "ParamBrowLY", "ParamBrowRY",
        "ParamBrowLAngle", "ParamBrowRAngle", "ParamBrowLForm", "ParamBrowRForm", "ParamCheek", "ParamBodyAngleX",
        "ParamBodyAngleY", "ParamBodyAngleZ", "ParamBreath"]
MIME = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".json": "application/json",
        ".moc3": "application/octet-stream"}


def data_url(base, rel):
    path = os.path.normpath(os.path.join(base, rel))
    if not path.startswith(os.path.normpath(base) + os.sep):
        sys.exit(f"Model file path escapes the model folder: {rel}")
    if not os.path.isfile(path):
        sys.exit(f"Model file not found: {rel}")
    mime = MIME.get(os.path.splitext(path)[1].lower(), "application/octet-stream")
    with open(path, "rb") as f:
        return f"data:{mime};base64," + base64.b64encode(f.read()).decode()


def main():
    args = sys.argv[1:]
    if "-h" in args or "--help" in args:
        print(__doc__)
        return
    frame = {"zoom": 3, "fx": 0.5, "fy": 0.2}
    if "--frame" in args:
        i = args.index("--frame")
        try:
            z, fx, fy = (float(v) for v in args[i + 1].split(","))
        except (IndexError, ValueError):
            sys.exit("--frame must be zoom,fx,fy, e.g. 3.4,0.5,0.165")
        frame = {"zoom": z, "fx": fx, "fy": fy}
        del args[i:i + 2]
    out_dir = None
    if "--out-dir" in args:
        i = args.index("--out-dir")
        if i + 1 >= len(args):
            sys.exit("--out-dir needs a directory")
        out_dir = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    if out_dir is None:
        sys.exit("--out-dir DIR is required")
    if len(args) != 2:
        sys.exit(__doc__)
    src, name = args
    if not NAME_RE.match(name):
        sys.exit("Name must start with a lowercase letter and use only a-z, 0-9, - and _")
    found = glob.glob(os.path.join(src, "*.model3.json"))
    if len(found) != 1:
        sys.exit(f"{src} must contain exactly one *.model3.json (found {len(found)})")
    with open(found[0], encoding="utf-8") as f:
        m = json.load(f)
    fr = m.get("FileReferences") or {}
    if not fr.get("Moc") or not fr.get("Textures"):
        sys.exit("model3.json is missing Moc or Textures")

    # Parameter check: needs the parameter list from DisplayInfo (*.cdi3.json)
    if fr.get("DisplayInfo"):
        with open(os.path.join(src, fr["DisplayInfo"]), encoding="utf-8") as f:
            ids = {p["Id"] for p in json.load(f).get("Parameters", [])}
        miss = [p for p in NEED if p not in ids]
        if miss:
            sys.exit(f"Model lacks required avatar parameters: {', '.join(miss)} (use Cubism standard parameter ids)")
        nice = [p for p in NICE if p not in ids]
        if nice:
            print(f"⚠ Model lacks these parameters; the matching expressions/motions will not appear: {', '.join(nice)}")
    else:
        print("⚠ No DisplayInfo (*.cdi3.json); parameter ids not checked")

    fr["Moc"] = data_url(src, fr["Moc"])
    fr["Textures"] = [data_url(src, t) for t in fr["Textures"]]
    for k in ("Physics", "Pose", "UserData", "DisplayInfo"):
        if fr.get(k):
            fr[k] = data_url(src, fr[k])
    # Motions and expressions are driven by code; drop the model's own
    for k in ("Motions", "Expressions"):
        fr.pop(k, None)
    m["url"] = f"{name}/"

    out = os.path.join(out_dir, name)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, "model.js")
    with open(path + ".tmp", "w", encoding="utf-8") as f:
        f.write(f"// Packed by cubism-pilot pack.py from {os.path.basename(found[0])} (textures, moc3 as data URLs)\n")
        f.write("window.L2D_MODELS = window.L2D_MODELS || {};\n")
        f.write(f"window.L2D_MODELS[{json.dumps(name)}] = {json.dumps(m, ensure_ascii=False)};\n")
        f.write("// Framing: zoom = model width as a multiple of canvas width; fx, fy = model point (width/height fractions) at frame center\n")
        f.write("window.L2D_FRAMES = window.L2D_FRAMES || {};\n")
        f.write(f"window.L2D_FRAMES[{json.dumps(name)}] = {json.dumps(frame)};\n")
    os.replace(path + ".tmp", path)
    shown = os.path.relpath(path, ROOT) if path.startswith(ROOT + os.sep) else path
    print(f"✓ {shown} ({os.path.getsize(path) // 1024} KB)")


if __name__ == "__main__":
    main()
