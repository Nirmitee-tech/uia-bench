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
// Usage: skyshot act "App" click <x> <y>
//        skyshot act "App" type "<text>"
//        skyshot act "App" key <keycode>
// Coordinates are global screen points (the center of a control, computed by the
// caller from the bounds this tool reports). This is the real executor: CGEvent
// posts synthetic input, the same mechanism Codex's service uses.
func activate(_ appName: String) {
    if let app = NSWorkspace.shared.runningApplications.first(where: {
        $0.localizedName == appName }) {
        app.activate()
        usleep(150_000)
    }
}

func doClick(_ x: Double, _ y: Double) {
    let p = CGPoint(x: x, y: y)
    let src = CGEventSource(stateID: .combinedSessionState)
    CGEvent(mouseEventSource: src, mouseType: .mouseMoved, mouseCursorPosition: p,
            mouseButton: .left)?.post(tap: .cghidEventTap)
    usleep(30_000)
    CGEvent(mouseEventSource: src, mouseType: .leftMouseDown, mouseCursorPosition: p,
            mouseButton: .left)?.post(tap: .cghidEventTap)
    usleep(30_000)
    CGEvent(mouseEventSource: src, mouseType: .leftMouseUp, mouseCursorPosition: p,
            mouseButton: .left)?.post(tap: .cghidEventTap)
}

func doType(_ text: String) {
    let src = CGEventSource(stateID: .combinedSessionState)
    for scalar in text.unicodeScalars {
        var u = UniChar(scalar.value)
        guard let down = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: true),
              let up = CGEvent(keyboardEventSource: src, virtualKey: 0, keyDown: false)
        else { continue }
        down.keyboardSetUnicodeString(stringLength: 1, unicodeString: &u)
        up.keyboardSetUnicodeString(stringLength: 1, unicodeString: &u)
        down.post(tap: .cghidEventTap)
        up.post(tap: .cghidEventTap)
        usleep(8_000)
    }
}

func doKey(_ code: CGKeyCode) {
    let src = CGEventSource(stateID: .combinedSessionState)
    CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: true)?.post(tap: .cghidEventTap)
    usleep(20_000)
    CGEvent(keyboardEventSource: src, virtualKey: code, keyDown: false)?.post(tap: .cghidEventTap)
}

if CommandLine.arguments.count >= 3 && CommandLine.arguments[1] == "act" {
    let app = CommandLine.arguments[2]
    activate(app)
    let verb = CommandLine.arguments.count > 3 ? CommandLine.arguments[3] : ""
    switch verb {
    case "click" where CommandLine.arguments.count >= 6:
        doClick(Double(CommandLine.arguments[4]) ?? 0, Double(CommandLine.arguments[5]) ?? 0)
    case "type" where CommandLine.arguments.count >= 5:
        doType(CommandLine.arguments[4])
    case "key" where CommandLine.arguments.count >= 5:
        doKey(CGKeyCode(UInt16(CommandLine.arguments[4]) ?? 36))  // 36 = Return
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
