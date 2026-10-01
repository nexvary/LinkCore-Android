// swift-tools-version: 5.9
import PackageDescription

let package = Package(
    name: "FGLinkCore",
    platforms: [.iOS(.v16), .macOS(.v13)],
    products: [.library(name: "FGLinkCore", targets: ["FGLinkCore"])],
    targets: [
        .target(name: "FGLinkCore"),
        .testTarget(name: "FGLinkCoreTests", dependencies: ["FGLinkCore"])
    ]
)
