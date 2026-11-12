# cubism-pilot

[English](README.md) | 繁體中文

分層 PSD → Cubism 用 PSD →（在 Cubism Editor 綁定）→ 執行檔 → 網頁用 `model.js`，另附 macOS 上操作 Cubism Editor 的 GUI 控制指令。

| 檔案 | 功能 |
|---|---|
| `make_psd.py` | 分層 PSD → Cubism 用 PSD（頭型調整、嘴巴縮放、後髮補滿、分組） |
| `finalize_export.py` | Cubism moc3 匯出資料夾 → 加 physics3.json、EyeBlink/LipSync 分組、檢查 moc3 版本 |
| `pack.py` | moc3 匯出資料夾 → 單一 `model.js`（所有檔案轉成 data URL） |
| `cubism_gui.mjs` | Cubism Editor GUI 控制指令（macOS）：視窗截圖、滑鼠、鍵盤 |
| `mac_input.swift` | `cubism_gui.mjs` 用的 CGEvent 輸入程式（需要時自動編譯） |
| `_psd.py` | `make_psd.py` 用的 PSD 讀寫函式 |
| `_vendor/` | 內附 `psd-tools` 1.26.1 |
| `examples/mythbreaker.json` | 完整設定檔範例（3584×4800 畫布） |
| `requirements.txt` | Python 相依套件 |
| `AI_GUIDE.md` | 選用：給用 `cubism_gui.mjs` 操作 Cubism Editor 的 AI 參考的操作方法與已知問題（英文） |

## 需求

| | 用途 |
|---|---|
| Python ≥ 3.11 + `requirements.txt` | `make_psd.py`、`finalize_export.py`、`pack.py` |
| `psd-tools` ≥ 1.26 | 有安裝就用安裝的版本（`pip install psd-tools`）；沒有就用內附的 `_vendor/`（只有 macOS arm64 是原生加速，其他系統用純 Python，較慢） |
| Live2D Cubism Editor 5.x（FREE 或 PRO） | 綁定、匯出 moc3 |
| macOS、Node.js ≥ 18、Xcode Command Line Tools（`swiftc`） | 僅 `cubism_gui.mjs` |

| 工具 | 平台 |
|---|---|
| `make_psd.py`、`finalize_export.py`、`pack.py` | 有 Python 的系統皆可（沒有作業系統專屬呼叫；已在 macOS 測試） |
| `cubism_gui.mjs` | 僅 macOS（CGEvent、`screencapture`、System Events） |

`cubism_gui.mjs` 是指令列工具，不是 MCP server。它移動真的游標、送出真的按鍵：
Cubism 必須在前景且沒被遮住，執行期間不能使用滑鼠和鍵盤。

## 下載與安裝

```
git clone https://github.com/yujie9988/cubism-pilot.git cubism-pilot
cd cubism-pilot
python3 -m pip install -r requirements.txt
```

ZIP 下載：GitHub →「**Code → Download ZIP**」，解壓縮後在這個資料夾執行上面的 `pip install`。

僅 `cubism_gui.mjs` 需要：

```
xcode-select --install            # 已有 swiftc 可略過
node cubism_gui.mjs build         # 把 mac_input 編譯到 ./.bin
```

系統設定 → 隱私權與安全性 → 在「**輔助使用**」和「**螢幕錄製**」打開執行指令的 App（終端機、iTerm 等）。

確認：

```
python3 make_psd.py -h
node cubism_gui.mjs windows       # Cubism Editor 開著 → 輸出它的視窗清單（JSON）
```

## 使用教學

### 1. 原始 PSD

每個 Live2D 部件一個像素圖層（群組可有可無，讀取時忽略）。圖層名稱會成為 Cubism 圖形網格（ArtMesh）的名稱與 ID。

| 常見圖層 | |
|---|---|
| face, neck, body | 皮膚、衣服 |
| hair_front, hair_side_L/R, hair_back, hair_ahoge | 依前後分層的頭髮 |
| eye_white_L/R, iris_L/R, lash_upper_L/R, lash_lower_L/R, eye_close_L/R | 睜眼組＋閉眼線 |
| mouth_close, mouth_upper, mouth_lower, mouth_teeth, mouth_tongue, mouth_inner | 閉嘴線＋張嘴組 |
| brow_L/R, nose, 配件 | |

### 2. 設定檔

```
cp examples/mythbreaker.json my_model.json
```

修改 `groups`、`mouth.layers`、`back_fill`、`reshape.skip` 裡的圖層名稱；依自己的畫布設定像素數值；不需要的步驟（`reshape`、`mouth`、`back_fill`）整段刪除。

### 3. 產生 Cubism 用 PSD

```
python3 make_psd.py my_model.json source.psd model.psd --preview preview.png
```

用 `preview.png` 檢查結果（不要看 Finder／快速查看的 PSD 縮圖）。

### 4. 在 Cubism Editor 綁定

| 步驟 | 選單／設定（English／简体中文介面） |
|---|---|
| 匯入 | 開啟 `model.psd` → *Create model from PSD (5.2 blend mode or earlier)*／「从PSD文件创建模型(5.2版本之前的混合模式)」 |
| 網格 | 選取全部圖形網格 → *Automatic Mesh Generator*／「自动网格生成」→ 預設 *Standard*／「标准」 |
| 綁定 | 變形器、參數、關鍵點 |
| 匯出 | *File → Export For Runtime → Export as moc3 file*／「文件 → 导出运行时文件 → 导出为moc3文件」；**輸出版本：SDK 5.0** |

### 5. 補完匯出檔

```
python3 finalize_export.py my_model.json export_folder/
```

加上 `*.physics3.json` 與 EyeBlink／LipSync 分組；moc3 版本大於 5 時報錯結束。

### 6. 網頁模型（選用）

```
python3 pack.py export_folder/ my_model --frame 1.25,0.5,0.44 --out-dir web/models
```

`web/models/my_model/model.js` → 在 Cubism Core／PixiJS／pixi-live2d-display 之後載入；讀取 `window.L2D_MODELS["my_model"]` 與 `window.L2D_FRAMES["my_model"]`。

### 7. GUI 控制（選用）

```
node cubism_gui.mjs shot screen.png --grid    # 視窗截圖＋座標格線
node cubism_gui.mjs click 1200 700            # 視窗內座標
node cubism_gui.mjs key cmd+s
node cubism_gui.mjs text "model name" --paste
```

## 參考

### make_psd.py

```
python3 make_psd.py CONFIG.json INPUT.psd OUTPUT.psd [--preview PNG] [--overwrite]
```

| 參數 | |
|---|---|
| `CONFIG.json` | 格式見下方 |
| `INPUT.psd` | 平鋪或有群組的 PSD；圖層名稱去掉前後空白與結尾的 `.png` |
| `OUTPUT.psd` | 8-bit RGB，每個輸入圖層一個像素圖層，裁到透明範圍，無遮色片，全部顯示 |
| `--preview PNG` | 依透明度正確疊合的預覽圖（`preview_hide` 裡的圖層不畫） |
| `--overwrite` | 覆蓋 `OUTPUT.psd` |

步驟依序執行；省略某個 key 就跳過該步驟。

#### `reshape`

`skip` 以外的圖層共用同一個變形場，雙線性取樣一次，預乘透明度。

| Key | 型別 | |
|---|---|---|
| `center_x` | px | 臉的中線 |
| `hair_top` | px | 頭髮頂端（不含呆毛）；`cut` 以這裡計算 |
| `cut` | px | `hair_top` 往下移的距離（壓頭頂） |
| `crown_bottom` | px | 這一行以下不做垂直移動 |
| `crown_blend` | px | `crown_bottom` 上方、垂直壓縮漸入的範圍 |
| `crown_narrow` | 0–1 | 頭髮頂端的水平收窄，到 `crown_bottom` 漸減為 0 |
| `face_narrow` | 0–1 | 整個頭部的水平收窄 |
| `face_fade` | [y0, y1] px | `face_narrow` 從 y0（全量）漸減到 y1（0） |
| `side_narrow` | 0–1 | 離 `center_x` 超過 `side_blend[1]` 的部分的收窄 |
| `side_blend` | [d0, d1] px | `side_narrow` 漸入的距離範圍（離 `center_x`） |
| `skip` | [名稱] | 不變形的圖層 |

#### `mouth`

| Key | 型別 | |
|---|---|---|
| `layers` | [名稱] | 要縮放的圖層（Lanczos） |
| `center` | [x, y] px | 縮放中心 |
| `scale` | 浮點數 | |

#### `back_fill`

在 `cover` 圖層不透明的範圍內，用 `layer` 內部的中位數顏色補滿 `layer`。

| Key | 型別 | 預設 | |
|---|---|---|---|
| `layer` | 名稱 | | 後髮圖層 |
| `cover` | [名稱] | | 畫在它前面的圖層 |
| `inset` | px | 6 | 遮罩往內縮 |
| `interior` | px | 25 | 取色時 `layer` 不透明範圍往內縮 |

#### `groups`

由下到上。一個群組會成為一個 Cubism 部件。每個圖層必須剛好出現一次。

```json
[["group", ["layer", "layer", ["subgroup", ["layer"]]]], ...]
```

省略時：一個名為 `all` 的群組，照輸入順序。

#### `preview_hide`

`[名稱]`：`--preview` 不畫的圖層。

### finalize_export.py

```
python3 finalize_export.py CONFIG.json EXPORT_DIR [--max-moc N]
```

| | |
|---|---|
| `EXPORT_DIR` | Cubism「Export as moc3」的輸出資料夾；剛好一個 `*.model3.json` |
| `--max-moc` | moc3 版本上限（預設 5 = SDK 5.0）；超過則 exit 1 |

寫入 `<model>.physics3.json`，設定 `FileReferences.Physics`，設定 `Groups` 的 `EyeBlink`／`LipSync`。

| 設定 key | 型別 | |
|---|---|---|
| `physics` | [項目] | 每個項目一組兩節擺錘 |
| `eye_blink` | [參數 ID] | `EyeBlink` 分組 |
| `lip_sync` | [參數 ID] | `LipSync` 分組 |

物理項目：

| Key | 預設 | |
|---|---|---|
| `output` | | 由擺錘末端角度驅動的參數 ID |
| `scale` | | 輸出倍率 |
| `name` | `output` | 名稱 |
| `length` | 3 | 擺錘長度（第 2 個頂點的 Y 與半徑） |
| `delay` | 0.9 | |
| `mobility` | 0.95 | |
| `acceleration` | 1.5 | |
| `angle_range` | 10 | 角度正規化 ±範圍 |

輸入（固定）：`ParamAngleX` X 60%、`ParamAngleZ` 角度 60%、`ParamBodyAngleX` X 40%、`ParamBodyAngleZ` 角度 40%。

### pack.py

```
python3 pack.py MODEL_DIR NAME --out-dir DIR [--frame ZOOM,FX,FY]
```

| 參數 | 預設 | |
|---|---|---|
| `MODEL_DIR` | | moc3 匯出資料夾；剛好一個 `*.model3.json` |
| `NAME` | | `[a-z][a-z0-9_-]{1,30}` |
| `--frame` | `3,0.5,0.2` | ZOOM = 模型寬度 / 畫布寬度；FX, FY = 對到畫面中心的模型位置（寬、高比例） |
| `--out-dir` | 必填 | 輸出 `<out-dir>/<NAME>/model.js` |

輸出：`window.L2D_MODELS[NAME]`（model3.json，檔案轉成 data URL）、`window.L2D_FRAMES[NAME]`（`{zoom, fx, fy}`）。
cdi3.json 缺少 `NEED` 參數 ID 時 exit 1。

### cubism_gui.mjs

```
node cubism_gui.mjs <command>
```

| 指令 | |
|---|---|
| `windows` | Cubism 視窗清單（JSON）：index、id、標題、全域位置大小、layer、螢幕縮放 |
| `activate` | 把 Cubism 切到前景 |
| `resize <x> <y> <w> <h>` | 設定主視窗位置大小（全域座標） |
| `shot <out.png> [--win i] [--rect x,y,w,h] [--grid] [--no-activate]` | 視窗截圖，1 像素 = 1 點；`--rect` 裁切（JSON 回傳原點偏移）；`--grid` 疊上每 50／100 點的格線與座標 |
| `click <x> <y> [--count 1-3] [--button left\|right] [--mods ...] [--win i]` | |
| `dclick \| rclick <x> <y> [--mods ...] [--win i]` | |
| `move <x> <y> [--win i]` | 左鍵按住時送出拖曳事件 |
| `down \| up <x> <y> [--mods ...] [--win i]` | `up` 被拒絕時在游標目前位置放開 |
| `drag <x1> <y1> <x2> <y2> [--steps n] [--mods ...] [--win i]` | |
| `path "<x,y;x,y;...>" [--mods ...] [--win i]` | 在第一點按下、最後一點放開 |
| `scroll <x> <y> <dy> [dx] [--win i]` | 行數；正數 = 往上／往左 |
| `key <combo>` | `cmd+s`、`return`、`escape`、`tab`、`delete`、`cmd+shift+z`、`a`–`z`、`0`–`9`、`f1`–`f12`、方向鍵、`space`（美式鍵盤配置） |
| `text <string> [--paste]` | 輸入到目前焦點欄位；`--paste` 經由剪貼簿（之後還原） |
| `build` | 編譯 `mac_input` |

| 選項 | |
|---|---|
| `--win i` | `windows` 的 index、`#<視窗 id>` 或標題片段；預設 = 最大的視窗 |
| `--mods` | 逗號分隔的 `cmd`、`shift`、`alt`、`ctrl` |

座標：所選視窗內的點座標。
拒絕（exit 1）：任何一點不在 Cubism 視窗內、該點被其他 App 的視窗蓋住、`key`／`text` 時 Cubism 不在前景。
輸出：每個指令一行 JSON（`build`：執行檔路徑）。

| 環境變數 | 預設 | |
|---|---|---|
| `CUBISM_GUI_BIN_DIR` | `./.bin` | `mac_input` 的編譯位置 |

啟動指令的 App 需要的 macOS 權限：輔助使用（輸入、調整視窗）、螢幕錄製（截圖、視窗標題）。
選單列在視窗外，無法用這個工具點擊。
