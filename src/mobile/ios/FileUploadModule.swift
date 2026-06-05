import Foundation
import React
import UIKit

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

  @objc func shareAudioFile(_ filePath: String,
                            fileName: String,
                            resolver: @escaping RCTPromiseResolveBlock,
                            rejecter: @escaping RCTPromiseRejectBlock) {
    let normalizedPath = normalizePath(filePath)
    let sourceUrl = URL(fileURLWithPath: normalizedPath)

    guard FileManager.default.fileExists(atPath: sourceUrl.path) else {
      rejecter("FILE_NOT_FOUND", "Recording file does not exist", nil)
      return
    }

    let safeName = sanitizeFileName(fileName)
    let sharedDirectory = FileManager.default.temporaryDirectory.appendingPathComponent("shared_audio", isDirectory: true)

    do {
      try FileManager.default.createDirectory(
        at: sharedDirectory,
        withIntermediateDirectories: true,
        attributes: nil
      )
      let destination = sharedDirectory.appendingPathComponent("\(UUID().uuidString)-\(safeName)")
      if FileManager.default.fileExists(atPath: destination.path) {
        try FileManager.default.removeItem(at: destination)
      }
      try FileManager.default.copyItem(at: sourceUrl, to: destination)

      DispatchQueue.main.async {
        guard let presenter = self.topViewController() else {
          rejecter("NO_UI", "No view controller available to present share sheet", nil)
          return
        }

        let activityViewController = UIActivityViewController(
          activityItems: [destination],
          applicationActivities: nil
        )

        if let popover = activityViewController.popoverPresentationController {
          popover.sourceView = presenter.view
          popover.sourceRect = CGRect(
            x: presenter.view.bounds.midX,
            y: presenter.view.bounds.midY,
            width: 0,
            height: 0
          )
          popover.permittedArrowDirections = []
        }

        presenter.present(activityViewController, animated: true) {
          resolver(nil)
        }
      }
    } catch {
      rejecter("SHARE_ERROR", "Unable to prepare file for sharing", error)
    }
  }

  @objc func deleteLocalFile(_ filePath: String,
                             resolver: @escaping RCTPromiseResolveBlock,
                             rejecter: @escaping RCTPromiseRejectBlock) {
    let normalizedPath = normalizePath(filePath)
    let fileManager = FileManager.default

    guard fileManager.fileExists(atPath: normalizedPath) else {
      resolver(nil)
      return
    }

    do {
      try fileManager.removeItem(atPath: normalizedPath)
      resolver(nil)
    } catch {
      rejecter("DELETE_ERROR", "Unable to delete local file", error)
    }
  }

  @objc func localFileExists(_ filePath: String,
                             resolver: @escaping RCTPromiseResolveBlock,
                             rejecter: @escaping RCTPromiseRejectBlock) {
    let normalizedPath = normalizePath(filePath)
    let fileExists = FileManager.default.fileExists(atPath: normalizedPath)
    resolver(fileExists)
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

  private func normalizePath(_ path: String) -> String {
    path.hasPrefix("file://") ? String(path.dropFirst("file://".count)) : path
  }

  private func sanitizeFileName(_ fileName: String) -> String {
    let trimmed = fileName.trimmingCharacters(in: .whitespacesAndNewlines)
    let fallback = trimmed.isEmpty ? "recording.m4a" : trimmed
    let withExtension = fallback.lowercased().hasSuffix(".m4a") ? fallback : "\(fallback).m4a"
    let invalidCharacters = CharacterSet(charactersIn: "\\/:*?\"<>|")
    return withExtension.components(separatedBy: invalidCharacters).joined(separator: "_")
  }

  private func topViewController() -> UIViewController? {
    let rootController = UIApplication.shared.connectedScenes
      .compactMap { $0 as? UIWindowScene }
      .flatMap { $0.windows }
      .first { $0.isKeyWindow }?
      .rootViewController

    var current = rootController
    while let presented = current?.presentedViewController {
      current = presented
    }
    return current
  }
}
