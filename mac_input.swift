import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

// Mouse and keyboard input via CGEvent, used by cubism_gui.mjs (also runnable on its own).
// Coordinates are global screen points (origin top-left of the main display), same space as
// CGWindowList and screencapture -R.
// mods: comma-separated cmd,shift,alt,ctrl. Every event of a gesture (down, drag, up) carries the
// same flags, and modifier keys are pressed first and released last so Java-based apps see them.
//
// Input:
//   move <x> <y>                   sends leftMouseDragged while the left button is held (drag between down and up)
//   click <x> <y> [count] [left|right] [mods]
//   down <x> <y> [mods]            press left button only (must be followed by up)
//   up <x> <y> [mods]
//   drag <x1> <y1> <x2> <y2> [steps] [mods]
//   path "x,y;x,y;..." [mods]      press at the first point, pass through each, release at the last
//   scroll <x> <y> <dy> [dx]       lines; positive = up/left
//   key <combo>                    e.g. cmd+s, return, escape, tab, delete, cmd+shift+z, a, 1, f1, left, space
//   text "<string>"                types via keyboardSetUnicodeString (CJK works, bypasses the IME)
//   paste "<string>"               temporarily puts the string on the clipboard, sends cmd+v, restores all clipboard types
// Queries (JSON output):
//   windows <pid>                  on-screen windows of the process (front to back) + display scale
//   hit <x> <y>                    owner of the topmost window at the point
//   displays                       frames and scale of all displays
//   frontmost                      frontmost app
//   cursor                         cursor position and whether the left button is down
//   find <executable>              running apps by executable name or bundle id (pid, bundle id)
//   activate <pid>                 bring the app to the front
//   setframe <pid> <cur x y w h> <new x y w h>   move/resize via Accessibility API (window closest to cur frame)
//
// Input events and setframe need Accessibility; window titles need Screen Recording (empty otherwise).

setvbuf(stdout, nil, _IONBF, 0)
let args = Array(CommandLine.arguments.dropFirst())
let src = CGEventSource(stateID: .hidSystemState)

func fail(_ msg: String, _ code: Int32 = 2) -> Never {
  FileHandle.standardError.write((msg + "\n").data(using: .utf8)!)
  exit(code)
}
func num(_ s: String?) -> Double {
  guard let s = s, let v = Double(s), v.isFinite else { fail("Not a number: \(s ?? "(missing)")") }
  return v
}
func ms(_ n: Int) { usleep(useconds_t(n * 1000)) }
func printJSON(_ obj: Any) {
  let d = try! JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys])
  print(String(data: d, encoding: .utf8)!)
}

// ── Modifiers ────────────────────────────────────────────

struct Mod { let flag: CGEventFlags; let code: CGKeyCode }
let MODS: [String: Mod] = [
  "cmd": Mod(flag: .maskCommand, code: 55), "command": Mod(flag: .maskCommand, code: 55),
  "shift": Mod(flag: .maskShift, code: 56),
  "alt": Mod(flag: .maskAlternate, code: 58), "opt": Mod(flag: .maskAlternate, code: 58), "option": Mod(flag: .maskAlternate, code: 58),
  "ctrl": Mod(flag: .maskControl, code: 59), "control": Mod(flag: .maskControl, code: 59),
]
func parseMods(_ s: String?) -> [Mod] {
  guard let s = s, !s.isEmpty, s != "-", s != "none" else { return [] }
  var out: [Mod] = []
  for part in s.lowercased().split(whereSeparator: { $0 == "," || $0 == "+" }) {
    guard let m = MODS[String(part)] else { fail("Unknown modifier: \(part) (use cmd,shift,alt,ctrl)") }
    if !out.contains(where: { $0.code == m.code }) { out.append(m) }
  }
  return out
}
func flagsOf(_ mods: [Mod]) -> CGEventFlags { mods.reduce(CGEventFlags()) { $0.union($1.flag) } }

// Press modifiers in order (flags accumulate per key); returns the combined flags
func pressMods(_ mods: [Mod]) -> CGEventFlags {
  var f = CGEventFlags()
  for m in mods {
    f.insert(m.flag)
    let e = CGEvent(keyboardEventSource: src, virtualKey: m.code, keyDown: true)!
    e.flags = f
    e.post(tap: .cghidEventTap)
    ms(25)
  }
  return f
}
func releaseMods(_ mods: [Mod]) {
  var f = flagsOf(mods)
  for m in mods.reversed() {
    f.remove(m.flag)
    let e = CGEvent(keyboardEventSource: src, virtualKey: m.code, keyDown: false)!
    e.flags = f
    e.post(tap: .cghidEventTap)
    ms(25)
  }
}

// ── Mouse ────────────────────────────────────────────────

func mouse(_ type: CGEventType, _ p: CGPoint, _ button: CGMouseButton = .left, flags: CGEventFlags = [], clickState: Int64 = 1) {
  let e = CGEvent(mouseEventSource: src, mouseType: type, mouseCursorPosition: p, mouseButton: button)!
  e.flags = flags
  if type != .mouseMoved { e.setIntegerValueField(.mouseEventClickState, value: clickState) }
  e.post(tap: .cghidEventTap)
}
// While the left button is held (after down, before up), send leftMouseDragged with the held modifiers so apps treat it as a drag
func moveTo(_ p: CGPoint, flags: CGEventFlags = []) {
  if CGEventSource.buttonState(.combinedSessionState, button: .left) {
    let held = CGEventSource.flagsState(.combinedSessionState).intersection([.maskCommand, .maskShift, .maskAlternate, .maskControl])
    mouse(.leftMouseDragged, p, flags: flags.union(held))
  } else {
    mouse(.mouseMoved, p, flags: flags)
  }
}
func pt(_ x: String?, _ y: String?) -> CGPoint { CGPoint(x: num(x), y: num(y)) }

func doClick(_ p: CGPoint, count: Int, right: Bool, mods: [Mod]) {
  let (downT, upT, btn): (CGEventType, CGEventType, CGMouseButton) = right ? (.rightMouseDown, .rightMouseUp, .right) : (.leftMouseDown, .leftMouseUp, .left)
  moveTo(p)
  ms(120)
  let f = pressMods(mods)
  defer { releaseMods(mods) }
  for i in 1...max(1, count) {
    mouse(downT, p, btn, flags: f, clickState: Int64(i))
    ms(60)
    mouse(upT, p, btn, flags: f, clickState: Int64(i))
    ms(i < count ? 90 : 150)
  }
}

// Hold left button through a list of points (steps segments between each pair), leftMouseDragged per step
func doGesture(_ pts: [CGPoint], steps: Int, mods: [Mod]) {
  guard let first = pts.first else { fail("No points") }
  moveTo(first)
  ms(120)
  let f = pressMods(mods)
  defer { releaseMods(mods) }
  mouse(.leftMouseDown, first, flags: f)
  ms(120)
  var cur = first
  for p in pts.dropFirst() {
    let n = max(1, steps)
    for k in 1...n {
      let t = Double(k) / Double(n)
      let q = CGPoint(x: cur.x + (p.x - cur.x) * t, y: cur.y + (p.y - cur.y) * t)
      mouse(.leftMouseDragged, q, flags: f)
      ms(12)
    }
    cur = p
    ms(30)
  }
  // Pause before release so the app processes the final position
  mouse(.leftMouseDragged, cur, flags: f)
  ms(120)
  mouse(.leftMouseUp, cur, flags: f)
  ms(150)
}

func parsePath(_ s: String?) -> [CGPoint] {
  guard let s = s else { fail("Missing point list, e.g. \"100,200;150,220\"") }
  let pts = s.split(separator: ";").map { seg -> CGPoint in
    let xy = seg.split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }
    guard xy.count == 2 else { fail("Point must be x,y: \(seg)") }
    return pt(xy[0], xy[1])
  }
  if pts.count < 2 { fail("At least two points required") }
  return pts
}

// ── Keyboard ─────────────────────────────────────────────

let KEYS: [String: CGKeyCode] = [
  "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9, "b": 11, "q": 12, "w": 13, "e": 14,
  "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20, "4": 21, "6": 22, "5": 23, "=": 24, "equal": 24, "9": 25, "7": 26,
  "-": 27, "minus": 27, "8": 28, "0": 29, "]": 30, "o": 31, "u": 32, "[": 33, "i": 34, "p": 35, "l": 37, "j": 38,
  "'": 39, "quote": 39, "k": 40, ";": 41, "semicolon": 41, "\\": 42, "backslash": 42, ",": 43, "comma": 43, "/": 44, "slash": 44,
  "n": 45, "m": 46, ".": 47, "period": 47, "`": 50, "grave": 50,
  "return": 36, "enter": 36, "kpenter": 76, "tab": 48, "space": 49, "delete": 51, "backspace": 51, "escape": 53, "esc": 53,
  "forwarddelete": 117, "fwddelete": 117, "home": 115, "end": 119, "pageup": 116, "pagedown": 121,
  "left": 123, "right": 124, "down": 125, "up": 126,
  "f1": 122, "f2": 120, "f3": 99, "f4": 118, "f5": 96, "f6": 97, "f7": 98, "f8": 100, "f9": 101, "f10": 109,
  "f11": 103, "f12": 111,
]

func doKey(_ combo: String) {
  let parts = combo.lowercased().split(separator: "+", omittingEmptySubsequences: false).map(String.init)
  guard let keyName = parts.last, !keyName.isEmpty else { fail("Missing key: \(combo)") }
  guard let code = KEYS[keyName] else { fail("Unknown key: \(keyName)") }
  let mods = parseMods(parts.dropLast().joined(separator: ","))
  let f = pressMods(mods)
  defer { releaseMods(mods) }
  let d = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: true)!
  d.flags = f
  d.post(tap: .cghidEventTap)
  ms(40)
  let u = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: false)!
  u.flags = f
  u.post(tap: .cghidEventTap)
  ms(80)
}

func doText(_ s: String) {
  // Send at most 16 UTF-16 units per event (never splitting a character); newlines become return
  var chunk: [Character] = []
  func flush() {
    guard !chunk.isEmpty else { return }
    let u = Array(String(chunk).utf16)
    for down in [true, false] {
      let e = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: down)!
      e.flags = []
      u.withUnsafeBufferPointer { e.keyboardSetUnicodeString(stringLength: u.count, unicodeString: $0.baseAddress) }
      e.post(tap: .cghidEventTap)
      ms(down ? 15 : 30)
    }
    chunk.removeAll()
  }
  for ch in s {
    if ch == "\n" || ch == "\r\n" { flush(); doKey("return"); continue }
    if String(chunk).utf16.count + String(ch).utf16.count > 16 { flush() }
    chunk.append(ch)
  }
  flush()
}

func doPaste(_ s: String) {
  let pb = NSPasteboard.general
  // Save every item and every type on the current clipboard
  let saved: [[NSPasteboard.PasteboardType: Data]] = (pb.pasteboardItems ?? []).map { item in
    var m: [NSPasteboard.PasteboardType: Data] = [:]
    for t in item.types { if let d = item.data(forType: t) { m[t] = d } }
    return m
  }
  pb.clearContents()
  pb.setString(s, forType: .string)
  ms(80)
  doKey("cmd+v")
  ms(450)
  pb.clearContents()
  if !saved.isEmpty {
    let items = saved.map { m -> NSPasteboardItem in
      let it = NSPasteboardItem()
      for (t, d) in m { it.setData(d, forType: t) }
      return it
    }
    pb.writeObjects(items)
  }
}

// ── Windows and displays ─────────────────────────────────

func displays() -> [[String: Any]] {
  var n: UInt32 = 0
  CGGetActiveDisplayList(0, nil, &n)
  var ids = [CGDirectDisplayID](repeating: 0, count: Int(n))
  CGGetActiveDisplayList(n, &ids, &n)
  return ids.map { id in
    let b = CGDisplayBounds(id)
    var scale = 1.0
    if let mode = CGDisplayCopyDisplayMode(id), mode.width > 0 { scale = Double(mode.pixelWidth) / Double(mode.width) }
    return ["id": Int(id), "x": Int(b.origin.x), "y": Int(b.origin.y), "w": Int(b.width), "h": Int(b.height),
            "scale": scale, "main": CGDisplayIsMain(id) != 0]
  }
}

func displayFor(_ r: CGRect, _ ds: [[String: Any]]) -> [String: Any]? {
  var best: [String: Any]? = nil
  var bestArea = -1.0
  for d in ds {
    let dr = CGRect(x: d["x"] as! Int, y: d["y"] as! Int, width: d["w"] as! Int, height: d["h"] as! Int)
    let i = dr.intersection(r)
    let a = i.isNull ? 0 : Double(i.width * i.height)
    if a > bestArea { bestArea = a; best = d }
  }
  return best
}

func cgWindows() -> [[String: Any]] {
  (CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID) as? [[String: Any]]) ?? []
}
func boundsOf(_ w: [String: Any]) -> CGRect {
  let b = w[kCGWindowBounds as String] as? [String: Any] ?? [:]
  func v(_ k: String) -> Double { (b[k] as? NSNumber)?.doubleValue ?? 0 }
  return CGRect(x: v("X"), y: v("Y"), width: v("Width"), height: v("Height"))
}

// Titles via Accessibility API (CGWindowList has no titles without Screen Recording)
func axWindows(_ pid: pid_t) -> [(title: String, frame: CGRect, el: AXUIElement)] {
  let app = AXUIElementCreateApplication(pid)
  var ref: CFTypeRef?
  guard AXUIElementCopyAttributeValue(app, kAXWindowsAttribute as CFString, &ref) == .success, let wins = ref as? [AXUIElement] else { return [] }
  return wins.compactMap { w in
    var t: CFTypeRef?, p: CFTypeRef?, s: CFTypeRef?
    AXUIElementCopyAttributeValue(w, kAXTitleAttribute as CFString, &t)
    AXUIElementCopyAttributeValue(w, kAXPositionAttribute as CFString, &p)
    AXUIElementCopyAttributeValue(w, kAXSizeAttribute as CFString, &s)
    var pos = CGPoint.zero, size = CGSize.zero
    guard let pv = p, let sv = s else { return nil }
    AXValueGetValue(pv as! AXValue, .cgPoint, &pos)
    AXValueGetValue(sv as! AXValue, .cgSize, &size)
    return ((t as? String) ?? "", CGRect(origin: pos, size: size), w)
  }
}

func listWindows(_ pid: pid_t) -> [[String: Any]] {
  let ds = displays()
  let ax = AXIsProcessTrusted() ? axWindows(pid) : []
  var out: [[String: Any]] = []
  for (z, w) in cgWindows().enumerated() {
    guard (w[kCGWindowOwnerPID as String] as? NSNumber)?.int32Value == pid else { continue }
    let r = boundsOf(w)
    let alpha = (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 1
    if r.width < 2 || r.height < 2 || alpha <= 0 { continue }
    var title = (w[kCGWindowName as String] as? String) ?? ""
    if title.isEmpty, let m = ax.first(where: { abs($0.frame.minX - r.minX) < 2 && abs($0.frame.minY - r.minY) < 2 && abs($0.frame.width - r.width) < 2 && abs($0.frame.height - r.height) < 2 }) { title = m.title }
    let d = displayFor(r, ds)
    out.append(["id": (w[kCGWindowNumber as String] as? NSNumber)?.intValue ?? 0, "z": z,
                "layer": (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0, "title": title,
                "x": Int(r.minX.rounded()), "y": Int(r.minY.rounded()), "w": Int(r.width.rounded()), "h": Int(r.height.rounded()),
                "scale": d?["scale"] ?? 1.0, "display": d?["id"] ?? 0])
  }
  return out
}

// Topmost visible window at the point. Skips: fully transparent, 1x1, cursor layer and above (the Window
// Server "Cursor" window follows the pointer and resizes with its shape), and full-display WindowManager
// overlays. Small Stage Manager strip overlays (Gesture Blocking Overlay, App Icon Window) intercept clicks
// and are not skipped.
let CURSOR_LAYER = Int(CGWindowLevelForKey(.cursorWindow))
func coversADisplay(_ r: CGRect, _ ds: [[String: Any]]) -> Bool {
  ds.contains { d in
    let dr = CGRect(x: d["x"] as! Int, y: d["y"] as! Int, width: d["w"] as! Int, height: d["h"] as! Int)
    let i = dr.intersection(r)
    return !i.isNull && i.width * i.height >= 0.9 * dr.width * dr.height
  }
}
func hitTest(_ p: CGPoint) -> [String: Any] {
  let ds = displays()
  for w in cgWindows() {
    let r = boundsOf(w)
    let alpha = (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 1
    let owner = (w[kCGWindowOwnerName as String] as? String) ?? ""
    let layer = (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0
    if alpha <= 0 || r.width < 2 || r.height < 2 || layer >= CURSOR_LAYER { continue }
    if owner == "WindowManager" && coversADisplay(r, ds) { continue }
    if r.contains(p) {
      return ["pid": (w[kCGWindowOwnerPID as String] as? NSNumber)?.intValue ?? 0, "owner": owner,
              "id": (w[kCGWindowNumber as String] as? NSNumber)?.intValue ?? 0,
              "layer": (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0,
              "title": (w[kCGWindowName as String] as? String) ?? ""]
    }
  }
  return ["pid": 0, "owner": ""]
}

func appInfo(_ a: NSRunningApplication?) -> [String: Any] {
  guard let a = a else { return ["pid": 0] }
  return ["pid": Int(a.processIdentifier), "name": a.localizedName ?? "", "bundle": a.bundleIdentifier ?? "",
          "exe": a.executableURL?.lastPathComponent ?? "", "active": a.isActive]
}

// ── Main ─────────────────────────────────────────────────

func needAX() {
  if !AXIsProcessTrusted() {
    fail("Accessibility permission missing: enable the app running this (Terminal or node) in System Settings > Privacy & Security > Accessibility", 3)
  }
}

guard let cmd = args.first else { fail("Usage: see the header comment of mac_input.swift") }
let a = Array(args.dropFirst())
switch cmd {
case "move":
  needAX(); moveTo(pt(a[safe: 0], a[safe: 1])); ms(60)
case "click":
  needAX()
  let count = a.count > 2 ? Int(num(a[2])) : 1
  let right = (a[safe: 3] ?? "left").lowercased() == "right"
  if count < 1 || count > 3 { fail("Count must be 1-3") }
  doClick(pt(a[safe: 0], a[safe: 1]), count: count, right: right, mods: parseMods(a[safe: 4]))
case "down":
  needAX()
  let p = pt(a[safe: 0], a[safe: 1]); let mods = parseMods(a[safe: 2])
  moveTo(p); ms(100)
  let f = pressMods(mods)
  mouse(.leftMouseDown, p, flags: f); ms(80)
case "up":
  needAX()
  let p = pt(a[safe: 0], a[safe: 1]); let mods = parseMods(a[safe: 2])
  mouse(.leftMouseDragged, p, flags: flagsOf(mods)); ms(60)
  mouse(.leftMouseUp, p, flags: flagsOf(mods)); ms(60)
  releaseMods(mods)
case "drag":
  needAX()
  let steps = a.count > 4 ? Int(num(a[4])) : 24
  doGesture([pt(a[safe: 0], a[safe: 1]), pt(a[safe: 2], a[safe: 3])], steps: steps, mods: parseMods(a[safe: 5]))
case "path":
  needAX()
  doGesture(parsePath(a[safe: 0]), steps: 6, mods: parseMods(a[safe: 1]))
case "scroll":
  needAX()
  let p = pt(a[safe: 0], a[safe: 1])
  let dy = Int32(num(a[safe: 2])), dx = a.count > 3 ? Int32(num(a[3])) : 0
  moveTo(p); ms(100)
  let e = CGEvent(scrollWheelEvent2Source: src, units: .line, wheelCount: 2, wheel1: dy, wheel2: dx, wheel3: 0)!
  e.location = p
  e.post(tap: .cghidEventTap); ms(120)
case "key":
  needAX(); doKey(a[safe: 0] ?? "")
case "text":
  needAX(); doText(a[safe: 0] ?? "")
case "paste":
  needAX(); doPaste(a[safe: 0] ?? "")
case "windows":
  printJSON(listWindows(pid_t(num(a[safe: 0]))))
case "hit":
  printJSON(hitTest(pt(a[safe: 0], a[safe: 1])))
case "displays":
  printJSON(displays())
case "frontmost":
  printJSON(appInfo(NSWorkspace.shared.frontmostApplication))
case "cursor":
  let loc = CGEvent(source: nil)?.location ?? .zero
  printJSON(["x": Double(loc.x), "y": Double(loc.y), "left": CGEventSource.buttonState(.combinedSessionState, button: .left)])
case "find":
  let exe = a[safe: 0] ?? ""
  printJSON(NSWorkspace.shared.runningApplications.filter { $0.executableURL?.lastPathComponent == exe || $0.bundleIdentifier == exe }.map { appInfo($0) })
case "activate":
  guard let app = NSRunningApplication(processIdentifier: pid_t(num(a[safe: 0]))) else { fail("No app with this pid") }
  app.unhide()
  app.activate(options: [.activateAllWindows])
  ms(300)
  printJSON(appInfo(NSWorkspace.shared.frontmostApplication))
case "setframe":
  needAX()
  let pid = pid_t(num(a[safe: 0]))
  let cur = CGRect(x: num(a[safe: 1]), y: num(a[safe: 2]), width: num(a[safe: 3]), height: num(a[safe: 4]))
  var origin = CGPoint(x: num(a[safe: 5]), y: num(a[safe: 6]))
  var size = CGSize(width: num(a[safe: 7]), height: num(a[safe: 8]))
  let wins = axWindows(pid)
  func dist(_ r: CGRect) -> Double { abs(r.minX - cur.minX) + abs(r.minY - cur.minY) + abs(r.width - cur.width) + abs(r.height - cur.height) }
  guard let w = wins.min(by: { dist($0.frame) < dist($1.frame) }) else { fail("Accessibility API returned no windows for this app") }
  // Resize, move, then resize again (size may be clamped when changing displays)
  let sv = AXValueCreate(.cgSize, &size)!, pv = AXValueCreate(.cgPoint, &origin)!
  AXUIElementSetAttributeValue(w.el, kAXSizeAttribute as CFString, sv)
  let r1 = AXUIElementSetAttributeValue(w.el, kAXPositionAttribute as CFString, pv)
  let r2 = AXUIElementSetAttributeValue(w.el, kAXSizeAttribute as CFString, sv)
  if r1 != .success || r2 != .success { fail("Setting position/size failed (AXError \(r1.rawValue)/\(r2.rawValue))") }
  ms(300)
default:
  fail("Unknown command: \(cmd)")
}

extension Array {
  subscript(safe i: Int) -> Element? { i >= 0 && i < count ? self[i] : nil }
}
