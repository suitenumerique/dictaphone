import Foundation
import React

@objc(FileUploadModule)
class FileUploadModule: RCTEventEmitter, URLSessionTaskDelegate {

  private typealias PromiseHandlers = (
    resolver: RCTPromiseResolveBlock,
    rejecter: RCTPromiseRejectBlock
  )

  private var uploadIdsByTaskId: [Int: String] = [:]
  private var promiseHandlersByTaskId: [Int: PromiseHandlers] = [:]
  private var lastEmittedProgressByTaskId: [Int: Int] = [:]
  private var hasListeners = false
  private let stateQueue = DispatchQueue(label: "fr.gouv.assistant_transcripts.FileUploadModule")
  private lazy var session = URLSession(
    configuration: .default,
    delegate: self,
    delegateQueue: nil
  )

  @objc func uploadFile(_ filePath: String,
                        url: String,
                        contentType: String,
                        uploadId: String,
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
    let task = session.uploadTask(with: request, fromFile: fileUrl)
    stateQueue.sync {
      uploadIdsByTaskId[task.taskIdentifier] = uploadId
      promiseHandlersByTaskId[task.taskIdentifier] = (resolver, rejecter)
      lastEmittedProgressByTaskId[task.taskIdentifier] = -1
    }
    task.resume()
  }

  override func supportedEvents() -> [String]! {
    [FileUploadModule.uploadProgressEvent]
  }

  override func startObserving() {
    hasListeners = true
  }

  override func stopObserving() {
    hasListeners = false
  }

  func urlSession(_ session: URLSession,
                  task: URLSessionTask,
                  didSendBodyData bytesSent: Int64,
                  totalBytesSent: Int64,
                  totalBytesExpectedToSend: Int64) {
    let uploadId = stateQueue.sync { () -> String? in
      let currentProgress: Int
      if totalBytesExpectedToSend > 0 {
        currentProgress = Int((totalBytesSent * 100) / totalBytesExpectedToSend)
      } else {
        currentProgress = 0
      }

      guard currentProgress != lastEmittedProgressByTaskId[task.taskIdentifier] ||
            totalBytesSent == totalBytesExpectedToSend else {
        return nil
      }

      lastEmittedProgressByTaskId[task.taskIdentifier] = currentProgress
      return uploadIdsByTaskId[task.taskIdentifier]
    }

    guard let uploadId else {
      return
    }

    sendProgress(
      uploadId: uploadId,
      uploadedBytes: totalBytesSent,
      totalBytes: totalBytesExpectedToSend
    )
  }

  func urlSession(_ session: URLSession,
                  task: URLSessionTask,
                  didCompleteWithError error: Error?) {
    let taskState = stateQueue.sync {
      (
        uploadId: uploadIdsByTaskId.removeValue(forKey: task.taskIdentifier),
        handlers: promiseHandlersByTaskId.removeValue(forKey: task.taskIdentifier)
      )
    }
    stateQueue.sync {
      lastEmittedProgressByTaskId.removeValue(forKey: task.taskIdentifier)
    }

    guard let handlers = taskState.handlers else {
      return
    }

    if let error = error {
      handlers.rejecter("UPLOAD_ERROR", error.localizedDescription, error)
      return
    }

    let status = (task.response as? HTTPURLResponse)?.statusCode ?? 0
    if status == 200 {
      if let uploadId = taskState.uploadId {
        let totalBytes = task.countOfBytesExpectedToSend
        sendProgress(uploadId: uploadId, uploadedBytes: totalBytes, totalBytes: totalBytes)
      }
      handlers.resolver(nil)
    } else {
      handlers.rejecter("UPLOAD_FAILED", "Status: \(status)", nil)
    }
  }

  private func sendProgress(uploadId: String, uploadedBytes: Int64, totalBytes: Int64) {
    guard hasListeners else {
      return
    }

    sendEvent(withName: FileUploadModule.uploadProgressEvent, body: [
      "uploadId": uploadId,
      "uploadedBytes": max(uploadedBytes, 0),
      "totalBytes": max(totalBytes, 0),
      "progress": totalBytes > 0 ? Double(uploadedBytes) / Double(totalBytes) : 0
    ])
  }

  @objc override static func requiresMainQueueSetup() -> Bool { false }

  private static let uploadProgressEvent = "FileUploadProgress"
}
