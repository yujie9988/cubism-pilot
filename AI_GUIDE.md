# cubism-pilot — AI_GUIDE.md

Optional reference for an AI agent that drives Live2D Cubism Editor 5.x on macOS through `cubism_gui.mjs`.
Written from a real session (Cubism Editor 5.3, Simplified-Chinese UI, PRO trial). Menu names are given as
English / 简体中文 because the UI language varies.

---

## 1. Control loop

1. `node cubism_gui.mjs windows` — get the window list. Index 0 is usually the main window; dialogs and popups
   appear as extra windows (often with an empty title).
2. `node cubism_gui.mjs shot out.png [--win <title>] [--rect x,y,w,h] [--grid]` — look before every action.
   Coordinates in the image are window-relative points; pass them straight to `click`/`drag`.
   For precise work crop with `--rect` and upscale the PNG yourself (image px = window pt + rect origin).
3. Act: `click`, `dclick`, `drag`, `scroll`, `key`, `text --paste`.
4. Shot again and verify. Never chain many blind actions; list contents and dialog positions change.

Prefer `--win <title substring>` over `--win <index>`: tooltips and transient popups get inserted into the
window list and shift indices.

## 2. Things outside the window

| Need | How |
|---|---|
| Menu bar (File, Modeling, …) | `osascript -e 'tell application "System Events" to tell process "CubismEditor" to click menu item "<item>" of menu 1 of menu bar item "<menu>" of menu bar 1'`; nested: `menu item "<sub>" of menu 1 of menu item "<item>" of menu 1 of menu bar item "<menu>" of menu bar 1` |
| List menu items | `... to get name of every menu item of menu 1 of menu bar item "<menu>" of menu bar 1` |
| Dialog hidden behind the main window | `... perform action "AXRaise" of (first window whose name is "<title>")`, then shot/click it |
| Read a dialog's text without a screenshot | `... get value of every static text of (first window whose name is "<title>")` |
| Window minimized / in Stage Manager strip (tiny frame, negative x) | `node cubism_gui.mjs activate` or `open -a "<Cubism app path>"` |

Java buttons are often not addressable by name through AppleScript; raise the dialog and click by coordinates.

## 3. Pitfalls

| Symptom | Cause | Fix |
|---|---|---|
| Every click refused: "covered by another window (截圖 / Screenshot)" | a full-screen transparent window left by macOS screencaptureui after the user took a screenshot | ask the user to press Esc / finish the screenshot; if it persists, with the user's consent `kill` the screencaptureui process (it relaunches on demand) |
| Click refused only near the cursor | (fixed) the cursor's own window was treated as an obstacle | — |
| macOS dialog "… wants to access files in your Desktop folder" | TCC privacy prompt | a system permission; the user must answer it |
| Dropdown popup item picked one row off | popup position/row pitch varies per dropdown and current value | shot the popup window (`windows` shows it as an untitled window) before clicking an item |
| Parameter slider row moved | the Parameters panel scrolled slightly | re-shot the panel before every value edit; locate rows by label |
| Scroll direction | natural scrolling: positive `dy` scrolled lists down in this setup | test once, then reuse |
| Typed value not applied | field not focused / value rejected | `dclick` the field, `key cmd+a`, `text`, then `key return` or `key tab`; re-shot |
| Shell loop passed one argument instead of three | zsh does not word-split `$var` | run loops in `bash -c` or use arrays |
| Save cancelled silently | the "unused source images, delete?" dialog grows wider with more file names, so a fixed click hit Cancel | compute the button from the dialog width; buttons are `Cancel / No / Yes` (取消 / 否 / 是) from left to right |
| moc3 does not load in the web runtime ("moc3 ver is [6]") | exported with SDK 5.3 | export with **Export version: SDK 5.0** (支持SDK 5.0 / Cubism5.0) |
| Physics / EyeBlink / LipSync missing after export | the export overwrote model3.json | run `finalize_export.py` after every export that overwrites model3.json |
| ArtMesh ID is `nose2`, `face2` | a part (PSD group) has the same name | use the real ID shown in the Inspector when typing clipping IDs |
| Faint ghost of the big open mouth / eyelid when the parameter is near its closed key | key 0 had opacity 0 but the full-size shape | give the closed key the same squashed shape as the next key (e.g. 0 = 0.1 shape), not only opacity 0 |
| Iris still visible when eyes closed | a clipping mask with opacity 0 still masks | squash the eye-white mask flat at the closed key |
| Background shows behind the face when turning | back hair transparent where the face covered it | `make_psd.py` `back_fill` |
| Parts cut off after `make_psd.py` reshape | (fixed) output box did not grow with moved content | — |

## 4. Rigging recipe (parameters use Cubism standard IDs)

### Import
`cmd+o` → file dialog (Swing): click the file-name field, `text "<absolute path>" --paste`, `key return`.
Model Settings / 模型设置 → *Create model from PSD (5.2 blend mode or earlier)* / 从PSD文件创建模型(5.2版本之前的混合模式).
Re-importing an edited PSD into the same model: pick `<model> (model)` in the same dialog → *Replace [old.psd]* / 替换.

### Mesh
Click empty canvas → `key cmd+a` → toolbar *Automatic Mesh Generator* / 自动网格生成 → preset *Standard* / 标准 →
click any numeric field → `key return` (applies to all selected) → close.
Regenerating meshes after keyforms exist kept the keyforms in 5.3 (they were transferred to the new mesh); verify.

### Clipping
Select the clipped mesh (e.g. iris) → Inspector *Clipping ID* / 剪贴ID field → type the mask mesh ID → return.

### Face motion (AngleX/Y)
Requires one PSD group per feature (face, eye_L/R, eyeball_L/R, brow_L/R, mouth, nose) and no parent deformers yet.
Parameters panel menu (☰) → *Auto generation of facial motion* / 自动生成面部动作 → *Generate face deformer* / 生成面部变形器:
assign parts per row (leave ears empty) → OK → *Generate facial motion* / 生成面部动作 → *Angle X…*, *Angle Y…*, then *Four corners* / 四角.
The adjustment dialog is modeless: drag the AngleX/Y sliders to preview before OK.

### Keyforms on a parameter
Select objects first, then click the parameter row, then panel buttons: *Add 2 keys* / 新增2个键, *Add 3 keys* / 新增3个键,
*Manual key edit* / 手动调整键 (add arbitrary values, e.g. 0.2). Set the parameter by double-clicking its value field.
Edit at a key value only. Move a mesh: drag the centre handle of its bounding box. Squash: drag an edge handle.
Combined X×Y keys: panel menu → *Four-corner shape synthesis* / 四角形状合成.

| Parameter | Recipe used |
|---|---|
| ParamEyeL/ROpen | keys 0, 0.2, 1; 1 = original, closed line opacity 0; 0.2 = upper lash moved down, eye white squashed from top, closed line 0; 0 = open set opacity 0 and squashed, closed line 100 |
| ParamEyeBallX/Y | iris meshes, 3 keys each, move ~¼ of eye-white width / less vertically, then four-corner synthesis |
| ParamMouthOpenY | keys 0, 0.1, 1; 1 = original open set, closed line 0; 0.1 = open set squashed to ~30 % height and ~70 % width, closed line 0; 0 = same shape as 0.1 with opacity 0, closed line 100 |
| ParamAngleZ | rotation deformer around all head deformers; Cmd+drag the pivot to the chin/neck joint; ±30 → ±10° (positive = head top toward screen right) |
| ParamBodyAngleX / Z | warp deformer over body + neck + head rotation (±10 → small shift); rotation deformer around that, pivot at the body bottom, ±10 → ±4° |
| ParamBreath | warp deformer over body + front collar; key 1 = top edge up a few px |

### Hair follow + sway
Per hair layer: warp deformer `…摇动` (sway) as parent of the meshes, warp deformer `…XY` as its parent
(toolbar *Create Warp Deformer* / 创建弯曲变形器 → *Set as parent of selected objects* / 设为所选对象的父级).
Head-turn follow: panel menu → *Apply 3D rotation expression* / 应用3D旋转表现 → register the `…XY` deformers (+) →
rotation centre at the head centre, Z offset front hair +350 / side +250 / back −100, perspective 40,
angle range X 20 / Y 12 (30 / 100 made the crown stretch) → *Update keyforms*; answer Yes to "add 3 keys".
Sway: panel menu → *Auto generation of sway motion* / 自动生成摇摆运动 → register the `…摇动` deformers →
**change the target parameter first** (it defaults to Angle X) to ParamHairFront / ParamHairSide / ParamHairBack →
fulcrum Top → *Update keyforms*. Side hair needed horizontal ~9, vertical ~2.5 to read as swaying.
Physics is not authored in Cubism here; `finalize_export.py` writes physics3.json.

### Texture atlas and export
Toolbar *Edit Texture Atlas* / 编辑纹理集 → new texture 2048×2048 (FREE limit) → *Auto layout* / 自动排版 → OK.
Menu *File → Export For Runtime → Export as moc3 file* / 文件 → 导出运行时文件 → 导出为moc3文件 → Export version SDK 5.0 →
OK → save dialog: paste the absolute path, return → "overwrite?" Yes → "overwrite model3.json?" Yes if textures changed
(then run `finalize_export.py`), No to replace only the moc3.

## 5. Verify outside Cubism

- Render poses in a browser page with pixi-live2d-display (set parameter values directly, no physics) and inspect:
  front, AngleX ±25, AngleY ±20, AngleZ +20, eyes 0 / 0.6, mouth 0.3 / 0.8, eyeballs, diagonal.
- Check the in-between values that the runtime will actually use (eyes 0.05–0.3, mouth 0.02–0.3), not only keys.
- Judge PSDs by an alpha-correct composite (`make_psd.py --preview`), never by the Finder thumbnail.
