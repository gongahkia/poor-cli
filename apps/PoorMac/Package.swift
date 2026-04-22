// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "PoorMac",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "PoorMac", targets: ["PoorMac"]),
    ],
    targets: [
        .executableTarget(name: "PoorMac"),
        .testTarget(name: "PoorMacTests", dependencies: ["PoorMac"]),
    ]
)
