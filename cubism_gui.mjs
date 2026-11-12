#!/usr/bin/env node
// Drive Live2D Cubism Editor through the GUI: window screenshots plus mouse/keyboard input.
// All x, y are window-relative points; origin is the top-left of the selected Cubism window.
// shot images are 1 px = 1 pt, so positions read off an image can be passed to click directly.
// Safety: pointer actions re-read window frames first and refuse any point that is outside every
// Cubism window or covered by another app's window. Keyboard actions bring Cubism to the front
// and verify it first; they refuse if that fails. No input is ever sent to other apps.
//
// Usage (node cubism_gui.mjs <command> ...):
//   windows                                   list Cubism windows (index, title, global frame, display scale)
//   activate                                  bring Cubism to the front
//   resize <x> <y> <w> <h>                    set the main window's global frame
//   shot <out.png> [--win i] [--rect x,y,w,h] [--grid] [--no-activate]
//   click <x> <y> [--count 1-3] [--button left|right] [--mods cmd,shift,alt,ctrl] [--win i]
//   dclick|rclick <x> <y> [--mods cmd,shift,alt,ctrl] [--win i]
//   move <x> <y> [--win i]                    between down and up, sends drag events
//   down|up <x> <y> [--mods ...] [--win i]    separate left press/release (always up after down; a refused up releases at the current cursor)
//   drag <x1> <y1> <x2> <y2> [--steps n] [--mods ...] [--win i]
//   path "<x,y;x,y;...>" [--mods ...] [--win i]
//   scroll <x> <y> <dy> [dx] [--win i]        lines; positive = up/left
//   key <combo>                               e.g. cmd+s, return, escape, tab, delete, cmd+shift+z, a, f1, left, space
//   text <string> [--paste]                   type into the focused field; --paste goes through the clipboard (restored afterwards)
//   build                                     compile mac_input only
// --win i: index from windows, #<window id>, or a title substring. Default: the largest window (main).
//
// Env: CUBISM_GUI_BIN_DIR overrides where the mac_input binary is built
// (default <repo>/dashboard/cache/bin inside the host project, else <script dir>/.bin).
// Requires Accessibility (input, resize) and Screen Recording (screenshots, window titles) permissions
// for the app that launches this script (Terminal, or the node used by the dashboard).
import { execFile } from 'node:child_process';
import { existsSync, mkdirSync, statSync, rmSync } from 'node:fs';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const HERE = path.dirname(fileURLToPath(import.meta.url));
const ROOT = path.resolve(HERE, '..', '..');
const INPUT_SRC = path.join(HERE, 'mac_input.swift');
const PROJECT_BIN = path.join(ROOT, 'dashboard', 'cache', 'bin');
const BIN_DIR = process.env.CUBISM_GUI_BIN_DIR ? path.resolve(process.env.CUBISM_GUI_BIN_DIR)
  : existsSync(path.join(ROOT, 'dashboard')) ? PROJECT_BIN : path.join(HERE, '.bin');
const INPUT_BIN = path.join(BIN_DIR, 'mac_input');
const EXE = 'CubismEditor';
const BUNDLE = 'com.live2d.cubism.CECubismEditorApp';

const run = (cmd, args, { input, timeout = 30000 } = {}) => new Promise((resolve, reject) => {
  const p = execFile(cmd, args, { timeout, maxBuffer: 64 * 1024 * 1024 }, (err, stdout, stderr) => {
    if (err) return reject(Object.assign(new Error(String(stderr || err.message).trim().split('\n').pop()), { code: err.code }));
    resolve(String(stdout).trim());
  });
  if (input !== undefined) { p.stdin.end(input); }
});
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

// Patterns also match localized (zh) system messages.
function permHint(e) {
  const m = String(e?.message || e);
  if (/-1719|-25211|not allowed assistive|輔助|assistive access|accessibility permission/i.test(m)) return `${m} (enable the app running this script in System Settings > Privacy & Security > Accessibility)`;
  if (/could not create image|screen ?record|螢幕錄製/i.test(m)) return `${m} (enable the app running this script in System Settings > Privacy & Security > Screen Recording)`;
  return m;
}

async function inputBin() {
  const fresh = existsSync(INPUT_BIN) && statSync(INPUT_BIN).mtimeMs >= statSync(INPUT_SRC).mtimeMs;
  if (!fresh) {
    mkdirSync(BIN_DIR, { recursive: true });
    await run('swiftc', ['-O', INPUT_SRC, '-o', INPUT_BIN], { timeout: 300000 });
  }
  return INPUT_BIN;
}
const mi = async (...args) => run(await inputBin(), args.map(String));
const miJSON = async (...args) => JSON.parse(await mi(...args));

// ── Cubism process and windows ───────────────────────────

async function cubismPid() {
  const apps = await miJSON('find', EXE);
  if (!apps.length) throw new Error('Cubism Editor is not running');
  return apps[0].pid;
}

// Index is by window id (creation order), so it stays stable when focus or z-order changes.
export async function listWindows() {
  const pid = await cubismPid();
  const ws = (await miJSON('windows', pid)).sort((a, b) => a.id - b.id);
  let main = -1;
  ws.forEach((w, i) => { w.index = i; if (w.layer === 0 && (main < 0 || w.w * w.h > ws[main].w * ws[main].h)) main = i; });
  if (main >= 0) ws[main].main = true;
  return { pid, windows: ws.map(({ index, id, title, x, y, w, h, layer, z, scale, display, main: m }) => ({ index, id, title, x, y, w, h, layer, z, scale, display, main: !!m })) };
}

async function pickWindow(sel) {
  const { pid, windows } = await listWindows();
  if (!windows.length) throw new Error('Cubism has no visible windows (minimized to the Dock?)');
  let w;
  if (sel === undefined || sel === null || sel === true) w = windows.find((x) => x.main) || windows[0];
  else if (/^\d+$/.test(String(sel))) w = windows[Number(sel)];
  else if (/^#\d+$/.test(String(sel))) w = windows.find((x) => x.id === Number(String(sel).slice(1)));
  else w = windows.find((x) => x.title.includes(String(sel)));
  if (!w) throw new Error(`Window not found: ${sel}; run windows to list them`);
  return { pid, win: w, windows };
}

async function frontmostPid() {
  return (await miJSON('frontmost')).pid;
}

export async function activate() {
  const pid = await cubismPid();
  if (await frontmostPid() === pid) return { frontmost: true, pid };
  await mi('activate', pid).catch(() => {});
  for (let i = 0; i < 10; i++) {
    if (await frontmostPid() === pid) return { frontmost: true, pid };
    if (i === 2) await run('osascript', ['-e', `tell application id "${BUNDLE}" to activate`]).catch(() => {});
    await sleep(200);
  }
  const f = await miJSON('frontmost');
  return { frontmost: false, pid, actual: f };
}

async function needFront() {
  const a = await activate();
  if (!a.frontmost) throw new Error(`Cannot bring Cubism to the front (frontmost is ${a.actual?.name || 'unknown'}); refusing keyboard/mouse input`);
  await sleep(150);
  return a;
}

// Window-relative -> global. Every point must be inside some Cubism window, and the topmost window there must be Cubism's.
async function toGlobal(points, sel) {
  const { pid, win, windows } = await pickWindow(sel);
  const out = [];
  for (const [x, y] of points) {
    if (![x, y].every(Number.isFinite)) throw new Error(`Coordinates are not numbers: ${x}, ${y}`);
    const gx = Math.round(win.x + x), gy = Math.round(win.y + y);
    const inside = windows.some((w) => gx >= w.x && gx < w.x + w.w && gy >= w.y && gy < w.y + w.h);
    if (!inside) throw new Error(`Refused: (${x}, ${y}) maps to screen (${gx}, ${gy}), outside every Cubism window (selected window ${win.w}x${win.h})`);
    const hit = await miJSON('hit', gx, gy);
    if (hit.pid !== pid) throw new Error(`Refused: (${x}, ${y}) is covered by another window (${hit.owner || 'system'}${hit.title ? ` "${hit.title}"` : ''})`);
    out.push([gx, gy]);
  }
  return { win, pts: out };
}

const winInfo = (w) => ({ index: w.index, id: w.id, title: w.title, x: w.x, y: w.y, w: w.w, h: w.h, scale: w.scale });

// ── Screenshot ───────────────────────────────────────────

const GRID_PY = String.raw`
import sys
from PIL import Image, ImageDraw, ImageFont
f, ox, oy = sys.argv[1], int(sys.argv[2]), int(sys.argv[3])
im = Image.open(f).convert('RGBA')
W, H = im.size
lay = Image.new('RGBA', im.size, (0, 0, 0, 0))
d = ImageDraw.Draw(lay)
try:
    font = ImageFont.truetype('/System/Library/Fonts/Menlo.ttc', 10)
except Exception:
    font = ImageFont.load_default()
def lab(x, y, t):
    b = d.textbbox((x, y), t, font=font)
    d.rectangle((b[0] - 1, b[1] - 1, b[2] + 1, b[3] + 1), fill=(255, 255, 255, 140))
    d.text((x, y), t, fill=(200, 0, 90, 230), font=font)
for gx in range((ox // 50 + 1) * 50, ox + W, 50):
    x = gx - ox
    major = gx % 100 == 0
    d.line((x, 0, x, H), fill=(255, 0, 120, 110 if major else 45), width=1)
for gy in range((oy // 50 + 1) * 50, oy + H, 50):
    y = gy - oy
    major = gy % 100 == 0
    d.line((0, y, W, y), fill=(255, 0, 120, 110 if major else 45), width=1)
for gx in range((ox // 100 + 1) * 100, ox + W, 100):
    for gy in range((oy // 100 + 1) * 100, oy + H, 100):
        if gx % 200 == 0 and gy % 200 == 0:
            lab(gx - ox + 2, gy - oy + 1, '%d,%d' % (gx, gy))
    lab(gx - ox + 2, 1, str(gx))
for gy in range((oy // 100 + 1) * 100, oy + H, 100):
    lab(1, gy - oy + 1, str(gy))
Image.alpha_composite(im, lay).convert('RGB').save(f)
`;

async function drawGrid(file, ox, oy) {
  try {
    await run('python3', ['-I', '-c', 'import PIL'], { timeout: 15000 });
  } catch {
    return 'python3 PIL not available; grid skipped (pip install pillow)';
  }
  await run('python3', ['-I', '-c', GRID_PY, file, String(ox), String(oy)], { timeout: 60000 });
  return null;
}

export async function shot(out, { win: sel, rect, grid = false, activateFirst = true } = {}) {
  if (activateFirst) await needFront();
  const { win } = await pickWindow(sel);
  let [rx, ry, rw, rh] = [0, 0, win.w, win.h];
  if (rect) {
    [rx, ry, rw, rh] = String(rect).split(',').map((v) => Math.round(Number(v)));
    if (![rx, ry, rw, rh].every(Number.isFinite) || rw <= 0 || rh <= 0) throw new Error('--rect must be x,y,w,h');
    // Clamp to the window.
    const x2 = Math.min(win.w, rx + rw), y2 = Math.min(win.h, ry + rh);
    rx = Math.max(0, rx); ry = Math.max(0, ry); rw = x2 - rx; rh = y2 - ry;
    if (rw <= 0 || rh <= 0) throw new Error('--rect is outside the window');
  }
  const tmp = path.join(tmpdir(), `cubism-${process.pid}-${Date.now()}.png`);
  let warning = null;
  try {
    await run('screencapture', ['-x', '-R', `${win.x + rx},${win.y + ry},${rw},${rh}`, tmp]);
    if (!existsSync(tmp)) throw new Error('Screenshot failed (Screen Recording permission?)');
    await run('sips', ['-z', String(rh), String(rw), tmp, '--out', out]);
  } finally {
    rmSync(tmp, { force: true });
  }
  if (grid) warning = await drawGrid(out, rx, ry);
  const r = { path: out, win: winInfo(win), origin: { x: rx, y: ry }, size: { w: rw, h: rh }, scale: win.scale };
  if (rx || ry) r.note = `image (px, py) = window (px+${rx}, py+${ry})`;
  if (warning) r.warning = warning;
  return r;
}

// ── Actions ──────────────────────────────────────────────

function modsArg(m) {
  if (!m) return '-';
  const ok = String(m).toLowerCase().split(/[,+]/).filter(Boolean);
  for (const k of ok) if (!['cmd', 'command', 'shift', 'alt', 'opt', 'option', 'ctrl', 'control'].includes(k)) throw new Error(`Unknown modifier: ${k}`);
  return ok.join(',') || '-';
}

async function pointer(points, sel) {
  await needFront();
  return toGlobal(points, sel);
}

export async function click(x, y, { count = 1, button = 'left', mods, win } = {}) {
  const m = modsArg(mods);
  const { win: w, pts: [[gx, gy]] } = await pointer([[x, y]], win);
  await mi('click', gx, gy, count, button, m);
  return { ok: 'click', x, y, count, button, mods: mods || null, global: [gx, gy], win: w.index };
}

export async function move(x, y, { win } = {}) {
  const { win: w, pts: [[gx, gy]] } = await pointer([[x, y]], win);
  await mi('move', gx, gy);
  return { ok: 'move', x, y, global: [gx, gy], win: w.index };
}

// If up is refused (outside, covered, Cubism not frontmost), still release the left button and modifiers
// at the current cursor so nothing stays held.
export async function press(kind, x, y, { mods, win } = {}) {
  if (kind !== 'down' && kind !== 'up') throw new Error(`press accepts only down/up: ${kind}`);
  const m = modsArg(mods);
  try {
    const { win: w, pts: [[gx, gy]] } = await pointer([[x, y]], win);
    await mi(kind, gx, gy, m);
    return { ok: kind, x, y, global: [gx, gy], win: w.index };
  } catch (e) {
    if (kind !== 'up') throw e;
    let note;
    try {
      const c = await miJSON('cursor');
      await mi('up', c.x, c.y, m);
      note = `released left button${m !== '-' ? ' and modifiers' : ''} at current cursor (${Math.round(c.x)}, ${Math.round(c.y)})`;
    } catch (e2) {
      note = `releasing left button also failed: ${e2.message}`;
    }
    throw Object.assign(new Error(`${e.message}; ${note}`), { code: e.code });
  }
}

export async function drag(x1, y1, x2, y2, { steps = 24, mods, win } = {}) {
  const m = modsArg(mods);
  const { win: w, pts } = await pointer([[x1, y1], [x2, y2]], win);
  await mi('drag', ...pts[0], ...pts[1], Math.max(1, Math.round(steps)), m);
  return { ok: 'drag', from: [x1, y1], to: [x2, y2], global: pts, win: w.index };
}

export async function gesturePath(spec, { mods, win } = {}) {
  const points = String(spec).split(';').filter((s) => s.trim()).map((s) => s.split(',').map(Number));
  if (points.length < 2 || points.some((p) => p.length !== 2)) throw new Error('Path must be "x,y;x,y;..." with at least two points');
  const m = modsArg(mods);
  const { win: w, pts } = await pointer(points, win);
  await mi('path', pts.map((p) => p.join(',')).join(';'), m);
  return { ok: 'path', points, win: w.index };
}

export async function scroll(x, y, dy, dx = 0, { win } = {}) {
  const { win: w, pts: [[gx, gy]] } = await pointer([[x, y]], win);
  await mi('scroll', gx, gy, Math.round(dy), Math.round(dx));
  return { ok: 'scroll', x, y, dy, dx, win: w.index };
}

export async function key(combo) {
  if (!combo) throw new Error('Missing key');
  await needFront();
  await mi('key', combo);
  return { ok: 'key', combo };
}

export async function text(s, { paste = false } = {}) {
  if (typeof s !== 'string' || !s.length) throw new Error('Missing text');
  await needFront();
  await mi(paste ? 'paste' : 'text', s);
  return { ok: paste ? 'paste' : 'text', length: [...s].length };
}

export async function resize(x, y, w, h) {
  const nums = [x, y, w, h].map(Number);
  if (!nums.every(Number.isFinite) || nums[2] < 200 || nums[3] < 150) throw new Error('resize needs x y w h, width >= 200, height >= 150');
  const { pid, win } = await pickWindow();
  await mi('setframe', pid, win.x, win.y, win.w, win.h, ...nums);
  await sleep(300);
  const after = (await pickWindow()).win;
  return { ok: 'resize', before: winInfo(win), after: winInfo(after) };
}

// ── CLI ──────────────────────────────────────────────────

function parseArgs(argv) {
  const pos = [], opt = {};
  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--grid' || a === '--paste' || a === '--no-activate') opt[a.slice(2)] = true;
    else if (/^--(win|rect|mods|steps|count|button)$/.test(a)) {
      if (i + 1 >= argv.length) throw new Error(`${a} needs a value`);
      opt[a.slice(2)] = argv[++i];
    } else if (/^--(win|rect|mods|steps|count|button)=/.test(a)) {
      const [k, ...v] = a.slice(2).split('=');
      opt[k] = v.join('=');
    } else pos.push(a);
  }
  return { pos, opt };
}

const USAGE = `Usage: node cubism_gui.mjs <command>
  windows
  activate
  resize <x> <y> <w> <h>
  shot <out.png> [--win i] [--rect x,y,w,h] [--grid] [--no-activate]
  click <x> <y> [--count 1-3] [--button left|right] [--mods cmd,shift,alt,ctrl] [--win i]
  dclick|rclick <x> <y> [--mods cmd,shift,alt,ctrl] [--win i]
  move <x> <y> [--win i]
  down|up <x> <y> [--mods ...] [--win i]
  drag <x1> <y1> <x2> <y2> [--steps n] [--mods ...] [--win i]
  path "<x,y;x,y;...>" [--mods ...] [--win i]
  scroll <x> <y> <dy> [dx] [--win i]
  key <combo>
  text <string> [--paste]
  build
--win: index from windows, #<window id>, or a title substring; default is the main window. x, y are window-relative points.`;

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const main = async () => {
    const [cmd, ...rest] = process.argv.slice(2);
    const { pos: a, opt } = parseArgs(rest);
    const n = (i) => {
      const v = Number(a[i]);
      if (a[i] === undefined || !Number.isFinite(v)) throw new Error(`Argument ${i + 1} must be a number\n${USAGE}`);
      return v;
    };
    for (const k of ['button', 'count']) if (opt[k] !== undefined && cmd !== 'click') throw new Error(`--${k} is only valid with click\n${USAGE}`);
    const o = { win: opt.win, mods: opt.mods };
    let r;
    switch (cmd) {
      case 'windows': r = await listWindows(); break;
      case 'activate': r = await activate(); if (!r.frontmost) process.exitCode = 1; break;
      case 'resize': r = await resize(n(0), n(1), n(2), n(3)); break;
      case 'shot':
        if (!a[0]) throw new Error(USAGE);
        r = await shot(path.resolve(a[0]), { win: opt.win, rect: opt.rect, grid: !!opt.grid, activateFirst: !opt['no-activate'] });
        break;
      case 'click': {
        const button = opt.button === undefined ? 'left' : String(opt.button).toLowerCase();
        if (button !== 'left' && button !== 'right') throw new Error('--button must be left or right');
        r = await click(n(0), n(1), { ...o, count: Number(opt.count) || 1, button });
        break;
      }
      case 'dclick': r = await click(n(0), n(1), { ...o, count: 2 }); break;
      case 'rclick': r = await click(n(0), n(1), { ...o, button: 'right' }); break;
      case 'move': r = await move(n(0), n(1), o); break;
      case 'down': case 'up': r = await press(cmd, n(0), n(1), o); break;
      case 'drag': r = await drag(n(0), n(1), n(2), n(3), { ...o, steps: Number(opt.steps) || 24 }); break;
      case 'path': if (!a[0]) throw new Error(USAGE); r = await gesturePath(a[0], o); break;
      case 'scroll': r = await scroll(n(0), n(1), n(2), a[3] !== undefined ? n(3) : 0, o); break;
      case 'key': r = await key(a[0]); break;
      case 'text': r = await text(a.join(' '), { paste: !!opt.paste }); break;
      case 'build': return console.log(await inputBin());
      default:
        console.error(USAGE);
        process.exitCode = 2;
        return;
    }
    console.log(JSON.stringify(r));
  };
  main().catch((e) => { console.error(permHint(e)); process.exitCode = process.exitCode || 1; });
}
