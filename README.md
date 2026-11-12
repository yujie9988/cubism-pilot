# cubism-pilot

English | [繁體中文](README.zh-TW.md)

Layered PSD → Cubism-ready PSD → (rig in Cubism Editor) → runtime files → web `model.js`, plus a GUI-control CLI for Cubism Editor on macOS.

| File | Role |
|---|---|
| `make_psd.py` | layered PSD → Cubism-ready PSD (reshape, mouth scale, back-hair fill, groups) |
| `finalize_export.py` | Cubism moc3 export folder → add physics3.json, EyeBlink/LipSync groups, moc3 version check |
| `pack.py` | moc3 export folder → single `model.js` (all files as data URLs) |
| `cubism_gui.mjs` | Cubism Editor GUI control CLI (macOS): window screenshots, mouse, keyboard |
| `mac_input.swift` | CGEvent input binary used by `cubism_gui.mjs` (compiled on demand) |
| `_psd.py` | PSD read/write helpers used by `make_psd.py` |
| `_vendor/` | bundled `psd-tools` 1.26.1 |
| `examples/mythbreaker.json` | full config example (3584×4800 canvas) |
| `requirements.txt` | Python dependencies |
| `AI_GUIDE.md` | optional: operating notes and known pitfalls for AI agents driving Cubism Editor with `cubism_gui.mjs` |

## Requirements

| | Needed for |
|---|---|
| Python ≥ 3.11 + `requirements.txt` | `make_psd.py`, `finalize_export.py`, `pack.py` |
| `psd-tools` ≥ 1.26 | installed copy used if present (`pip install psd-tools`); else bundled `_vendor/` (native RLE on macOS arm64 only, pure-Python elsewhere) |
| Live2D Cubism Editor 5.x (FREE or PRO) | rigging, moc3 export |
| macOS, Node.js ≥ 18, Xcode Command Line Tools (`swiftc`) | `cubism_gui.mjs` only |

| Tool | Platform |
|---|---|
| `make_psd.py`, `finalize_export.py`, `pack.py` | any OS with Python (no OS-specific calls; tested on macOS) |
| `cubism_gui.mjs` | macOS only (CGEvent, `screencapture`, System Events) |

`cubism_gui.mjs` is a CLI, not an MCP server. It moves the real cursor and sends real key events:
Cubism must be frontmost and uncovered, and the mouse/keyboard must not be used while it runs.

## Installation

```
git clone https://github.com/yujie9988/cubism-pilot.git cubism-pilot
cd cubism-pilot
python3 -m pip install -r requirements.txt
```

ZIP download: GitHub → **Code → Download ZIP**, unzip, then run the `pip install` line in this folder.

`cubism_gui.mjs` only:

```
xcode-select --install            # skip if swiftc is already available
node cubism_gui.mjs build         # compiles mac_input into ./.bin
```

System Settings → Privacy & Security → enable the app that runs the command (Terminal, iTerm, …) under **Accessibility** and **Screen Recording**.

Check:

```
python3 make_psd.py -h
node cubism_gui.mjs windows       # Cubism Editor running → JSON list of its windows
```

## Tutorial

### 1. Source PSD

One pixel layer per Live2D part (groups optional, ignored on input). Layer names are used as Cubism ArtMesh names/IDs.

| Typical layers | |
|---|---|
| face, neck, body | skin and clothing |
| hair_front, hair_side_L/R, hair_back, hair_ahoge | hair split by depth |
| eye_white_L/R, iris_L/R, lash_upper_L/R, lash_lower_L/R, eye_close_L/R | open eye set + closed-eye line |
| mouth_close, mouth_upper, mouth_lower, mouth_teeth, mouth_tongue, mouth_inner | closed line + open set |
| brow_L/R, nose, accessories | |

### 2. Config

```
cp examples/mythbreaker.json my_model.json
```

Edit layer names in `groups`, `mouth.layers`, `back_fill`, `reshape.skip`; set pixel values for your canvas; delete steps you don't need (`reshape`, `mouth`, `back_fill`).

### 3. Build the Cubism PSD

```
python3 make_psd.py my_model.json source.psd model.psd --preview preview.png
```

Check `preview.png` (not the Finder/Quick Look thumbnail of the PSD).

### 4. Rig in Cubism Editor

| Step | Menu / setting |
|---|---|
| Import | open `model.psd` → *Create model from PSD (5.2 blend mode or earlier)* |
| Mesh | select all ArtMeshes → *Automatic Mesh Generator* → preset *Standard* |
| Rig | deformers, parameters, keyforms |
| Export | *File → Export For Runtime → Export as moc3 file*; **Export version: SDK 5.0** |

### 5. Finalize the export

```
python3 finalize_export.py my_model.json export_folder/
```

Adds `*.physics3.json` and the EyeBlink/LipSync groups; exits with an error if the moc3 version is newer than 5.

### 6. Web model (optional)

```
python3 pack.py export_folder/ my_model --frame 1.25,0.5,0.44 --out-dir web/models
```

`web/models/my_model/model.js` → load after the Cubism Core / PixiJS / pixi-live2d-display scripts; read `window.L2D_MODELS["my_model"]` and `window.L2D_FRAMES["my_model"]`.

### 7. GUI control (optional)

```
node cubism_gui.mjs shot screen.png --grid    # window screenshot with a coordinate grid
node cubism_gui.mjs click 1200 700            # window-relative point
node cubism_gui.mjs key cmd+s
node cubism_gui.mjs text "model name" --paste
```

## Reference

### make_psd.py

```
python3 make_psd.py CONFIG.json INPUT.psd OUTPUT.psd [--preview PNG] [--overwrite]
```

| Arg | |
|---|---|
| `CONFIG.json` | see schema below |
| `INPUT.psd` | flat or grouped PSD; layer names are stripped, a trailing `.png` is removed |
| `OUTPUT.psd` | 8-bit RGB, one pixel layer per input layer, cropped to alpha, no masks, all visible |
| `--preview PNG` | alpha-correct composite (layers in `preview_hide` omitted) |
| `--overwrite` | replace `OUTPUT.psd` |

Steps run in order; omit a key to skip the step.

#### `reshape`

One warp field for every layer not in `skip`, single bilinear sample, premultiplied alpha.

| Key | Type | |
|---|---|---|
| `center_x` | px | face midline |
| `hair_top` | px | hair top row (without ahoge); `cut` is measured here |
| `cut` | px | vertical shift of `hair_top` (crown squash) |
| `crown_bottom` | px | rows ≥ this are not moved vertically |
| `crown_blend` | px | band above `crown_bottom` where the squash eases in |
| `crown_narrow` | 0–1 | horizontal narrowing at the hair top, eases to 0 at `crown_bottom` |
| `face_narrow` | 0–1 | horizontal narrowing of the whole head |
| `face_fade` | [y0, y1] px | `face_narrow` eases from full (y0) to 0 (y1) |
| `side_narrow` | 0–1 | narrowing of content farther than `side_blend[1]` from `center_x` |
| `side_blend` | [d0, d1] px | distance from `center_x` where `side_narrow` eases in |
| `skip` | [names] | layers left untouched |

#### `mouth`

| Key | Type | |
|---|---|---|
| `layers` | [names] | layers to scale (Lanczos) |
| `center` | [x, y] px | fixed point |
| `scale` | float | |

#### `back_fill`

Fills `layer` with its interior median colour where `cover` layers are opaque.

| Key | Type | Default | |
|---|---|---|---|
| `layer` | name | | back-hair layer |
| `cover` | [names] | | layers drawn in front of it |
| `inset` | px | 6 | erosion of the cover mask |
| `interior` | px | 25 | erosion of `layer`'s opaque area used to sample the colour |

#### `groups`

Bottom → top. A group becomes a Cubism part. Each layer must appear exactly once.

```json
[["group", ["layer", "layer", ["subgroup", ["layer"]]]], ...]
```

Missing key: one group `all` in input order.

#### `preview_hide`

`[names]` omitted from `--preview`.

### finalize_export.py

```
python3 finalize_export.py CONFIG.json EXPORT_DIR [--max-moc N]
```

| | |
|---|---|
| `EXPORT_DIR` | folder from Cubism *File → Export For Runtime → Export as moc3*; exactly one `*.model3.json` |
| `--max-moc` | max moc3 version byte (default 5 = SDK 5.0); exit 1 if exceeded |

Writes `<model>.physics3.json`, sets `FileReferences.Physics`, sets `Groups` `EyeBlink` / `LipSync`.

| Config key | Type | |
|---|---|---|
| `physics` | [entry] | one 2-vertex pendulum per entry |
| `eye_blink` | [param ids] | `EyeBlink` group |
| `lip_sync` | [param ids] | `LipSync` group |

Physics entry:

| Key | Default | |
|---|---|---|
| `output` | | parameter id driven by the pendulum tip angle |
| `scale` | | output scale |
| `name` | `output` | dictionary name |
| `length` | 3 | pendulum length (vertex 2 Y and radius) |
| `delay` | 0.9 | |
| `mobility` | 0.95 | |
| `acceleration` | 1.5 | |
| `angle_range` | 10 | angle normalization ±range |

Inputs (fixed): `ParamAngleX` X 60 %, `ParamAngleZ` angle 60 %, `ParamBodyAngleX` X 40 %, `ParamBodyAngleZ` angle 40 %.

### pack.py

```
python3 pack.py MODEL_DIR NAME --out-dir DIR [--frame ZOOM,FX,FY]
```

| Arg | Default | |
|---|---|---|
| `MODEL_DIR` | | moc3 export folder; exactly one `*.model3.json` |
| `NAME` | | `[a-z][a-z0-9_-]{1,30}` |
| `--frame` | `3,0.5,0.2` | ZOOM = model width / canvas width; FX, FY = model point (width/height fraction) at frame center |
| `--out-dir` | required | output `<out-dir>/<NAME>/model.js` |

Output: `window.L2D_MODELS[NAME]` (model3.json, files as data URLs), `window.L2D_FRAMES[NAME]` (`{zoom, fx, fy}`).
Exit 1 if a `NEED` parameter id is missing from the cdi3.json.

### cubism_gui.mjs

```
node cubism_gui.mjs <command>
```

| Command | |
|---|---|
| `windows` | JSON list of Cubism windows: index, id, title, global frame, layer, display scale |
| `activate` | bring Cubism to the front |
| `resize <x> <y> <w> <h>` | set the main window frame (global points) |
| `shot <out.png> [--win i] [--rect x,y,w,h] [--grid] [--no-activate]` | window screenshot, 1 px = 1 pt; `--rect` crops (JSON returns the origin offset); `--grid` overlays labelled 50/100 pt lines |
| `click <x> <y> [--count 1-3] [--button left\|right] [--mods ...] [--win i]` | |
| `dclick \| rclick <x> <y> [--mods ...] [--win i]` | |
| `move <x> <y> [--win i]` | sends drag events while the left button is down |
| `down \| up <x> <y> [--mods ...] [--win i]` | refused `up` releases at the current cursor |
| `drag <x1> <y1> <x2> <y2> [--steps n] [--mods ...] [--win i]` | |
| `path "<x,y;x,y;...>" [--mods ...] [--win i]` | press at first point, release at last |
| `scroll <x> <y> <dy> [dx] [--win i]` | lines; positive = up / left |
| `key <combo>` | `cmd+s`, `return`, `escape`, `tab`, `delete`, `cmd+shift+z`, `a`–`z`, `0`–`9`, `f1`–`f12`, arrows, `space` (US layout) |
| `text <string> [--paste]` | type into the focused field; `--paste` via clipboard (restored) |
| `build` | compile `mac_input` |

| Option | |
|---|---|
| `--win i` | `windows` index, `#<window id>`, or title substring; default = largest window |
| `--mods` | comma list of `cmd`, `shift`, `alt`, `ctrl` |

Coordinates: window-relative points of the selected window.
Refusals (exit 1): any point outside every Cubism window, a point covered by another app's window, Cubism not frontmost for `key` / `text`.
Output: one JSON line per command (`build`: binary path).

| Env | Default | |
|---|---|---|
| `CUBISM_GUI_BIN_DIR` | `./.bin` | where `mac_input` is built |

macOS permissions for the launching app: Accessibility (input, resize), Screen Recording (screenshots, window titles).
Menu bar items are outside the window and are not reachable through this tool.
