// skyshot — dump the accessibility tree of the frontmost window as JSON.
//
// This is the real-machine source for the Codex-style "skyshot": it walks
// AXUIElement and emits the same shape the fixture adapter produces, so the
// seven test classes run unchanged against a live app. A later revision adds a
// ScreenCaptureKit frame and its SHA-256; this first cut proves AX extraction,
// which is the part that decides whether element-targeted clicking is even
// possible on a given app.
//
// Build:   swiftc -O native/skyshot/Skyshot.swift -o native/skyshot/skyshot
// Run:     ./native/skyshot/skyshot "App Name"
// Needs:   System Settings > Privacy > Accessibility permission for the caller.
//
// Output (stdout): one JSON object matching tests/gold/*.json, with
// "ax_available": false when the app exposes no usable tree (the vision-only
// case the POC must measure).

import ApplicationServices
import AppKit
import Foundation

func attr(_ el: AXUIElement, _ key: String) -> CFTypeRef? {
    var value: CFTypeRef?
    let err = AXUIElementCopyAttributeValue(el, key as CFString, &value)
    return err == .success ? value : nil
}

func str(_ el: AXUIElement, _ key: String) -> String? {
    attr(el, key) as? String
}

func frame(_ el: AXUIElement) -> [Double] {
    guard let v = attr(el, kAXPositionAttribute as String),
          let s = attr(el, kAXSizeAttribute as String) else { return [0, 0, 0, 0] }
    var p = CGPoint.zero; var sz = CGSize.zero
    AXValueGetValue(v as! AXValue, .cgPoint, &p)
    AXValueGetValue(s as! AXValue, .cgSize, &sz)
    return [Double(p.x), Double(p.y), Double(sz.width), Double(sz.height)]
}

// roles worth exposing as actionable or readable controls
let keepRoles: Set<String> = [
    "AXButton", "AXTextField", "AXStaticText", "AXCheckBox", "AXRadioButton",
    "AXPopUpButton", "AXMenuItem", "AXLink", "AXTextArea", "AXCell",
]

func walk(_ el: AXUIElement, _ out: inout [[String: Any]], _ depth: Int) {
    if depth > 40 { return }
    if let role = str(el, kAXRoleAttribute as String), keepRoles.contains(role) {
        let label = str(el, kAXTitleAttribute as String)
            ?? str(el, kAXDescriptionAttribute as String)
            ?? str(el, kAXValueAttribute as String) ?? ""
        if !label.isEmpty {
            var entry: [String: Any] = ["role": role, "label": label,
                                        "bounds": frame(el), "enabled": true]
            if let value = str(el, kAXValueAttribute as String) { entry["value"] = value }
            out.append(entry)
        }
    }
    if let kids = attr(el, kAXChildrenAttribute as String) as? [AXUIElement] {
        for k in kids { walk(k, &out, depth + 1) }
    }
}

// --- act: perform one input event -------------------------------------------
// Usage: skyshot act "App" [--bg] <verb> ...
//   move  <x> <y>                 | click      <x> <y>
//   rclick <x> <y>                | dclick     <x> <y>
//   drag  <x1> <y1> <x2> <y2>     | scroll     <x> <y> <dy> [dx]
//   type  "<text>"                | key        <name>[+<mod>...]   e.g. a+cmd, Return
//
// Default delivery is the shared HID stream (`--global`-equivalent): it drives
// whatever is frontmost, like a person. Pass --bg to deliver events to the
// target app's process instead (CGEventPostToPid), which does not move the
// hardware cursor and lets the app receive input without stealing your focus.
// --bg is the "do not disturb my workflow" path; see the isolation note in the
// README for its limits and the full-isolation options (separate session / VM).
func pidFor(_ appName: String) -> pid_t? {
    NSWorkspace.shared.runningApplications.first(where: {
        $0.localizedName == appName })?.processIdentifier
}

func activate(_ appName: String) {
    NSWorkspace.shared.runningApplications.first(where: {
        $0.localizedName == appName })?.activate()
    usleep(150_000)
}

// a small, explicit keymap: enough for app control, extend as needed
let keymap: [String: CGKeyCode] = [
    "a":0,"s":1,"d":2,"f":3,"h":4,"g":5,"z":6,"x":7,"c":8,"v":9,"b":11,"q":12,
    "w":13,"e":14,"r":15,"y":16,"t":17,"1":18,"2":19,"3":20,"4":21,"6":22,"5":23,
    "9":25,"7":26,"8":28,"0":29,"o":31,"u":32,"i":34,"p":35,"l":37,"j":38,"k":40,
    "n":45,"m":46,"Return":36,"Tab":48,"space":49,"Delete":51,"Escape":53,
    "Left":123,"Right":124,"Down":125,"Up":126,"Home":115,"End":119,
    "PageUp":116,"PageDown":121,"ForwardDelete":117,
]
let modmap: [String: CGEventFlags] = [
    "cmd":.maskCommand,"shift":.maskShift,"ctrl":.maskControl,"alt":.maskAlternate,
    "control":.maskControl,"option":.maskAlternate,"command":.maskCommand,
]

func deliver(_ e: CGEvent, _ pid: pid_t?) {
    if let pid = pid { e.postToPid(pid) } else { e.post(tap: .cghidEventTap) }
}

func mouse(_ type: CGEventType, _ x: Double, _ y: Double, _ btn: CGMouseButton,
           _ pid: pid_t?, clicks: Int64 = 1) {
    let src = CGEventSource(stateID: .combinedSessionState)
    let e = CGEvent(mouseEventSource: src, mouseType: type,
                    mouseCursorPosition: CGPoint(x: x, y: y), mouseButton: btn)
    if clicks > 1 { e?.setIntegerValueField(.mouseEventClickState, value: clicks) }
    if let e = e { deliver(e, pid) }
}

func doClick(_ x: Double, _ y: Double, _ pid: pid_t?, right: Bool = false, clicks: Int64 = 1) {
    let btn: CGMouseButton = right ? .right : .left
    let down: CGEventType = right ? .rightMouseDown : .leftMouseDown
    let up: CGEventType = right ? .rightMouseUp : .leftMouseUp
    if pid == nil { mouse(.mouseMoved, x, y, btn, pid); usleep(20_000) }
    for c in 1...max(1, Int(clicks)) {
        mouse(down, x, y, btn, pid, clicks: Int64(c)); usleep(25_000)
        mouse(up, x, y, btn, pid, clicks: Int64(c)); usleep(25_000)
    }
}

func doDrag(_ x1: Double, _ y1: Double, _ x2: Double, _ y2: Double, _ pid: pid_t?) {
    mouse(.leftMouseDown, x1, y1, .left, pid); usleep(40_000)
    mouse(.leftMouseDragged, x2, y2, .left, pid); usleep(40_000)
    mouse(.leftMouseUp, x2, y2, .left, pid)
}

func doScroll(_ x: Double, _ y: Double, _ dy: Int32, _ dx: Int32, _ pid: pid_t?) {
    let src = CGEventSource(stateID: .combinedSessionState)
    if pid == nil { mouse(.mouseMoved, x, y, .left, pid); usleep(20_000) }
    if let e = CGEvent(scrollWheelEvent2Source: src, units: .pixel,
                       wheelCount: 2, wheel1: dy, wheel2: dx, wheel3: 0) {
        deliver(e, pid)
    }
}

func doType(_ text: String, _ pid: pid_t?) {
    let src = CGEventSource(stateID: .combinedSessionState)
    for scalar in text.unicodeScalars {
        var u = UniChar(scalar.value)
        guard let down = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: true),
              let up = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: false)
        else { continue }
        down.keyboardSetUnicodeString(stringLength: 1, unicodeString: &u)
        up.keyboardSetUnicodeString(stringLength: 1, unicodeString: &u)
        deliver(down, pid); deliver(up, pid)
        usleep(8_000)
    }
}

func doKey(_ spec: String, _ pid: pid_t?) {
    let parts = spec.split(separator: "+").map(String.init)
    var flags: CGEventFlags = []
    var code: CGKeyCode? = nil
    for p in parts {
        if let m = modmap[p.lowercased()] { flags.insert(m) }
        else if let c = keymap[p] ?? keymap[p.lowercased()] { code = c }
    }
    guard let code = code else {
        FileHandle.standardError.write("unknown key: \(spec)\n".data(using: .utf8)!)
        exit(2)
    }
    let src = CGEventSource(stateID: .combinedSessionState)
    let down = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: true)
    down?.flags = flags
    let up = CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: false)
    up?.flags = flags
    if let down = down { deliver(down, pid) }; usleep(20_000)
    if let up = up { deliver(up, pid) }
}

if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "act" {
    let app = CommandLine.arguments[2]
    var args = Array(CommandLine.arguments.dropFirst(3))
    var pid: pid_t? = nil
    if args.first == "--bg" {            // background: deliver to the app's pid
        pid = pidFor(app)
        args.removeFirst()
    } else {
        activate(app)                     // foreground: drive what the user sees
    }
    func d(_ i: Int) -> Double { i < args.count ? (Double(args[i]) ?? 0) : 0 }
    let verb = args.first ?? ""
    switch verb {
    case "move":   mouse(.mouseMoved, d(1), d(2), .left, pid)
    case "click":  doClick(d(1), d(2), pid)
    case "rclick": doClick(d(1), d(2), pid, right: true)
    case "dclick": doClick(d(1), d(2), pid, clicks: 2)
    case "drag":   doDrag(d(1), d(2), d(3), d(4), pid)
    case "scroll": doScroll(d(1), d(2), Int32(d(3)), Int32(args.count > 4 ? d(4) : 0), pid)
    case "type" where args.count >= 2:  doType(args[1], pid)
    case "key"  where args.count >= 2:  doKey(args[1], pid)
    default:
        FileHandle.standardError.write("bad act command\n".data(using: .utf8)!)
        exit(2)
    }
    print("{\"ok\":true}")
    exit(0)
}

let appName = CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ""
guard let app = NSWorkspace.shared.runningApplications.first(where: {
    $0.localizedName == appName
}) else {
    FileHandle.standardError.write("app not found: \(appName)\n".data(using: .utf8)!)
    exit(2)
}

let axApp = AXUIElementCreateApplication(app.processIdentifier)
var windowRef = attr(axApp, kAXFocusedWindowAttribute as String)
if windowRef == nil, let wins = attr(axApp, kAXWindowsAttribute as String) as? [AXUIElement] {
    windowRef = wins.first
}

var elements: [[String: Any]] = []
var title = ""
var winBounds: [Double] = [0, 0, 0, 0]
if let win = windowRef {
    title = str(win as! AXUIElement, kAXTitleAttribute as String) ?? ""
    winBounds = frame(win as! AXUIElement)
    walk(win as! AXUIElement, &elements, 0)
}

let payload: [String: Any] = [
    "app": appName,
    "window_title": title,
    "ax_available": !elements.isEmpty,
    "window_bounds": winBounds,
    "elements": elements,
]
let data = try JSONSerialization.data(withJSONObject: payload, options: [.sortedKeys])
FileHandle.standardOutput.write(data)
