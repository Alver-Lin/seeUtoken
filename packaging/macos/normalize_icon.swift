// Fit illustrated artwork to the installed macOS app-icon silhouette.
// Only the reference's alpha is used; its artwork is never copied.
// Usage: swift normalize_icon.swift artwork.png output.png x y width height
//        [system-reference.icns] [diagnostic-alpha.pgm]
import AppKit
import ImageIO
import UniformTypeIdentifiers

func fail(_ message: String) -> Never {
    fputs("\(message)\n", stderr)
    exit(1)
}

func load(_ path: String) -> CGImage {
    guard let image = NSImage(contentsOfFile: path) else {
        fail("Cannot load \(path)")
    }
    var proposed = CGRect(x: 0, y: 0, width: 1024, height: 1024)
    guard let bitmap = image.cgImage(forProposedRect: &proposed, context: nil, hints: nil) else {
        fail("Cannot decode \(path)")
    }
    return bitmap
}

let args = CommandLine.arguments
guard args.count >= 7 else { fail("Expected artwork, output and the backplate's x/y/width/height") }
let values = args[3...6].compactMap(Double.init)
guard values.count == 4, values[2] > 0, values[3] > 0 else { fail("Invalid backplate frame") }
let crop = CGRect(x: values[0], y: values[1], width: values[2], height: values[3])
let reference = args.count > 7 ? args[7] : "/System/Applications/Notes.app/Contents/Resources/AppIcon.icns"
let size = 1024
let canvas = CGRect(x: 0, y: 0, width: size, height: size)
let colorSpace = CGColorSpace(name: CGColorSpace.sRGB)!
let bitmapInfo = CGBitmapInfo.byteOrder32Big.rawValue | CGImageAlphaInfo.premultipliedLast.rawValue

func context() -> CGContext {
    guard let result = CGContext(data: nil, width: size, height: size, bitsPerComponent: 8,
                                 bytesPerRow: size * 4, space: colorSpace, bitmapInfo: bitmapInfo) else {
        fail("Cannot create icon canvas")
    }
    result.interpolationQuality = .high
    return result
}

let maskContext = context()
maskContext.draw(load(reference), in: canvas)
guard let mask = maskContext.makeImage(), let data = maskContext.data else { fail("Cannot read system mask") }
let pixels = data.assumingMemoryBound(to: UInt8.self)
var left = size, top = size, right = 0, bottom = 0
var alpha = Data(capacity: size * size)
for y in 0..<size {
    for x in 0..<size {
        let value = pixels[(y * size + x) * 4 + 3]
        alpha.append(value)
        if value >= 128 {
            left = min(left, x)
            top = min(top, y)
            right = max(right, x + 1)
            bottom = max(bottom, y + 1)
        }
    }
}
guard right > left, bottom > top else { fail("System mask is empty") }
let frame = CGRect(x: left, y: top, width: right - left, height: bottom - top)
guard let artwork = load(args[1]).cropping(to: crop) else { fail("Artwork frame is outside the source") }
let outputContext = context()
outputContext.draw(artwork, in: frame)
outputContext.setBlendMode(.destinationIn)
outputContext.draw(mask, in: canvas)
guard let output = outputContext.makeImage() else { fail("Cannot render icon") }
let url = URL(fileURLWithPath: args[2])
guard let destination = CGImageDestinationCreateWithURL(url as CFURL, UTType.png.identifier as CFString, 1, nil) else {
    fail("Cannot create \(args[2])")
}
CGImageDestinationAddImage(destination, output, nil)
guard CGImageDestinationFinalize(destination) else { fail("Cannot save icon") }
if args.count > 8 {
    var diagnostic = Data("P5\n\(size) \(size)\n255\n".utf8)
    diagnostic.append(alpha)
    try diagnostic.write(to: URL(fileURLWithPath: args[8]))
}
print("Native icon silhouette: \(frame), reference: \(reference)")
print("Saved \(url.path)")
