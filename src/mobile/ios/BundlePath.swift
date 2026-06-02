import Foundation
import React

@objc(BundlePath)
class BundlePath: NSObject {
  @objc func getBundlePath(_ resolve: RCTPromiseResolveBlock,
                           rejecter reject: RCTPromiseRejectBlock) {
    resolve(Bundle.main.bundlePath)
  }

  @objc static func requiresMainQueueSetup() -> Bool { false }
}
