import AppKit

guard CommandLine.arguments.count == 2 else {
    fputs("Usage: GenerateAppIcon output.png\n", stderr)
    exit(2)
}

let outputURL = URL(fileURLWithPath: CommandLine.arguments[1])
let size = NSSize(width: 1024, height: 1024)
let image = NSImage(size: size)

image.lockFocus()

let outerRect = NSRect(x: 52, y: 52, width: 920, height: 920)
let outerPath = NSBezierPath(roundedRect: outerRect, xRadius: 210, yRadius: 210)
NSColor(calibratedWhite: 0.035, alpha: 1).setFill()
outerPath.fill()

let glowRect = NSRect(x: 108, y: 108, width: 808, height: 808)
let glowPath = NSBezierPath(roundedRect: glowRect, xRadius: 152, yRadius: 152)
NSColor(calibratedRed: 0.83, green: 0.68, blue: 0.22, alpha: 0.13).setFill()
glowPath.fill()

let frameRect = NSRect(x: 208, y: 214, width: 608, height: 608)
let framePath = NSBezierPath(roundedRect: frameRect, xRadius: 74, yRadius: 74)
framePath.lineWidth = 28
NSColor(calibratedRed: 0.88, green: 0.71, blue: 0.23, alpha: 1).setStroke()
framePath.stroke()

let headPath = NSBezierPath(ovalIn: NSRect(x: 377, y: 500, width: 270, height: 270))
NSColor(calibratedRed: 0.92, green: 0.77, blue: 0.34, alpha: 1).setFill()
headPath.fill()

let shoulders = NSBezierPath()
shoulders.move(to: NSPoint(x: 295, y: 292))
shoulders.curve(
    to: NSPoint(x: 729, y: 292),
    controlPoint1: NSPoint(x: 328, y: 445),
    controlPoint2: NSPoint(x: 696, y: 445)
)
shoulders.line(to: NSPoint(x: 729, y: 260))
shoulders.line(to: NSPoint(x: 295, y: 260))
shoulders.close()
shoulders.fill()

let highlight = NSBezierPath()
highlight.move(to: NSPoint(x: 258, y: 760))
highlight.line(to: NSPoint(x: 258, y: 806))
highlight.line(to: NSPoint(x: 304, y: 806))
highlight.lineWidth = 18
highlight.lineCapStyle = .round
highlight.lineJoinStyle = .round
NSColor(calibratedRed: 0.99, green: 0.9, blue: 0.6, alpha: 0.9).setStroke()
highlight.stroke()

image.unlockFocus()

guard
    let tiffData = image.tiffRepresentation,
    let bitmap = NSBitmapImageRep(data: tiffData),
    let pngData = bitmap.representation(using: .png, properties: [:])
else {
    fputs("Could not render icon\n", stderr)
    exit(1)
}

try pngData.write(to: outputURL)
