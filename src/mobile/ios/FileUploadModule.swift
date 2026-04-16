import Foundation
import React

@objc(FileUploadModule)
class FileUploadModule: NSObject {

  @objc func uploadFile(_ filePath: String,
                        url: String,
                        contentType: String,
                        resolver: @escaping RCTPromiseResolveBlock,
                        rejecter: @escaping RCTPromiseRejectBlock) {

    guard let fileUrl = URL(string: "file://\(filePath)"),
          let requestUrl = URL(string: url) else {
      rejecter("INVALID_URL", "Invalid file or request URL", nil)
      return
    }

    var request = URLRequest(url: requestUrl)
    request.httpMethod = "PUT"
    request.setValue(contentType, forHTTPHeaderField: "Content-Type")
    request.setValue("private", forHTTPHeaderField: "X-amz-acl")

    // uploadTask streams directly from disk — no memory buffering
    let task = URLSession.shared.uploadTask(with: request, fromFile: fileUrl) { _, response, error in
      if let error = error {
        rejecter("UPLOAD_ERROR", error.localizedDescription, error)
        return
      }
      let status = (response as? HTTPURLResponse)?.statusCode ?? 0
      if status == 200 {
        resolver(nil)
      } else {
        rejecter("UPLOAD_FAILED", "Status: \(status)", nil)
      }
    }
    task.resume()
  }

  @objc static func requiresMainQueueSetup() -> Bool { false }
}
