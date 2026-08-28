import Foundation
import AVFoundation
import React
import UIKit
import UserNotifications

@objc(FileUploadModule)
class FileUploadModule: RCTEventEmitter, URLSessionTaskDelegate, URLSessionDelegate {

  private struct UploadState: Codable {
    let uploadId: String
    let filePath: String
    let url: String
    let contentType: String
    let acl: String?
    var wifiOnly: Bool
    var uploadedBytes: Int64
    let totalBytes: Int64
    var status: String
    var error: String?
    var retryCount: Int
    var notificationStrings: NotificationStrings?

    private enum CodingKeys: String, CodingKey {
      case uploadId
      case filePath
      case url
      case contentType
      case acl
      case wifiOnly
      case uploadedBytes
      case totalBytes
      case status
      case error
      case retryCount
      case notificationStrings
    }

    init(
      uploadId: String,
      filePath: String,
      url: String,
      contentType: String,
      acl: String?,
      wifiOnly: Bool,
      uploadedBytes: Int64,
      totalBytes: Int64,
      status: String,
      error: String?,
      retryCount: Int = 0,
      notificationStrings: NotificationStrings?
    ) {
      self.uploadId = uploadId
      self.filePath = filePath
      self.url = url
      self.contentType = contentType
      self.acl = acl
      self.wifiOnly = wifiOnly
      self.uploadedBytes = uploadedBytes
      self.totalBytes = totalBytes
      self.status = status
      self.error = error
      self.retryCount = retryCount
      self.notificationStrings = notificationStrings
    }

    init(from decoder: Decoder) throws {
      let container = try decoder.container(keyedBy: CodingKeys.self)
      uploadId = try container.decode(String.self, forKey: .uploadId)
      filePath = try container.decode(String.self, forKey: .filePath)
      url = try container.decode(String.self, forKey: .url)
      contentType = try container.decode(String.self, forKey: .contentType)
      // Uploads persisted before ACLs became configurable were signed with private ACL.
      acl = container.contains(.acl)
        ? try container.decodeIfPresent(String.self, forKey: .acl)
        : "private"
      wifiOnly = try container.decode(Bool.self, forKey: .wifiOnly)
      uploadedBytes = try container.decode(Int64.self, forKey: .uploadedBytes)
      totalBytes = try container.decode(Int64.self, forKey: .totalBytes)
      status = try container.decode(String.self, forKey: .status)
      error = try container.decodeIfPresent(String.self, forKey: .error)
      retryCount = try container.decodeIfPresent(Int.self, forKey: .retryCount) ?? 0
      notificationStrings = try container.decodeIfPresent(
        NotificationStrings.self,
        forKey: .notificationStrings
      )
    }
  }

  private struct NotificationStrings: Codable {
    let channelName: String
    let uploadingTitle: String
    let uploadingIndeterminate: String
    let completeTitle: String
    let completeBody: String
    let failedTitle: String
    let failedBody: String

    init(_ values: [String: String] = [:]) {
      channelName = values["channelName"] ?? "Recording uploads"
      uploadingTitle = values["uploadingTitle"] ?? "Uploading recording"
      uploadingIndeterminate = values["uploadingIndeterminate"] ?? "Uploading…"
      completeTitle = values["completeTitle"] ?? "Upload complete"
      completeBody = values["completeBody"] ?? "Open the app to finish processing the recording"
      failedTitle = values["failedTitle"] ?? "Upload failed"
      failedBody = values["failedBody"] ?? "Open the app to retry the recording upload"
    }
  }

  private typealias PromiseHandlers = (
    resolver: RCTPromiseResolveBlock,
    rejecter: RCTPromiseRejectBlock
  )

  private var uploadIdsByTaskId: [Int: String] = [:]
  private var promiseHandlersByTaskId: [Int: PromiseHandlers] = [:]
  private var lastEmittedProgressByTaskId: [Int: Int] = [:]
  private var waitersByUploadId: [String: [(RCTPromiseResolveBlock, RCTPromiseRejectBlock)]] = [:]
  private var replacedTaskIds = Set<Int>()
  private var hasListeners = false
  private let stateQueue = DispatchQueue(label: "fr.gouv.assistant_transcripts.FileUploadModule")
  private let defaults = UserDefaults.standard
  private lazy var session: URLSession = {
    URLSession(
      configuration: Self.backgroundSessionConfiguration,
      delegate: self,
      delegateQueue: nil
    )
  }()

  deinit {
    session.invalidateAndCancel()
  }

  private static let stateKey = "FileUploadStates"
  private static let appActiveKey = "FileUploadAppActive"
  private static let maxUploadRetries = 2
  static let backgroundSessionIdentifier = "fr.gouv.assistant_transcripts.uploads"
  private static var backgroundCompletionHandler: (() -> Void)?
  private static let incomingSharedFileEvent = "IncomingSharedFile"

  private static var backgroundSessionConfiguration: URLSessionConfiguration = {
    let configuration = URLSessionConfiguration.background(
      withIdentifier: backgroundSessionIdentifier
    )
    configuration.sessionSendsLaunchEvents = true
    configuration.waitsForConnectivity = true
    configuration.isDiscretionary = false
    return configuration
  }()

  @objc func uploadFile(_ filePath: String,
                        url: String,
                        contentType: String,
                        acl: String?,
                        uploadId: String,
                        wifiOnly: Bool,
                        notificationStrings: [String: String],
                        resolver: @escaping RCTPromiseResolveBlock,
                        rejecter: @escaping RCTPromiseRejectBlock) {

    let normalizedPath = normalizePath(filePath)
    let fileUrl = URL(fileURLWithPath: normalizedPath)
    guard FileManager.default.fileExists(atPath: fileUrl.path),
          let requestUrl = URL(string: url) else {
      rejecter("INVALID_URL", "Invalid file or request URL", nil)
      return
    }

    let totalBytes: Int64
    do {
      let attributes = try FileManager.default.attributesOfItem(atPath: fileUrl.path)
      totalBytes = (attributes[.size] as? NSNumber)?.int64Value ?? 0
    } catch {
      rejecter("FILE_READ_ERROR", "Unable to read upload file", error)
      return
    }

    var request = URLRequest(url: requestUrl)
    request.httpMethod = "PUT"
    request.allowsCellularAccess = !wifiOnly
    request.setValue(contentType, forHTTPHeaderField: "Content-Type")
    if let acl {
      request.setValue(acl, forHTTPHeaderField: "X-amz-acl")
    }

    let task = session.uploadTask(with: request, fromFile: fileUrl)
    task.taskDescription = uploadId
    let uploadState = UploadState(
      uploadId: uploadId,
      filePath: normalizedPath,
      url: url,
      contentType: contentType,
      acl: acl,
      wifiOnly: wifiOnly,
      uploadedBytes: 0,
      totalBytes: totalBytes,
      status: "uploading",
      error: nil,
      notificationStrings: NotificationStrings(notificationStrings)
    )
    stateQueue.sync {
      uploadIdsByTaskId[task.taskIdentifier] = uploadId
      promiseHandlersByTaskId[task.taskIdentifier] = (resolver, rejecter)
      lastEmittedProgressByTaskId[task.taskIdentifier] = -1
    }
    saveState(uploadState)
    task.resume()
  }

  @objc func getUploadStatuses(_ resolver: @escaping RCTPromiseResolveBlock,
                               rejecter: @escaping RCTPromiseRejectBlock) {
    resolver(allStates().map { state in
      var result: [String: Any] = [
        "uploadId": state.uploadId,
        "status": state.status,
        "uploadedBytes": state.uploadedBytes,
        "totalBytes": state.totalBytes
      ]
      if let error = state.error {
        result["error"] = error
      }
      return result
    })
  }

  @objc func resumeUpload(_ uploadId: String,
                          notificationStrings: [String: String],
                          wifiOnly: Bool,
                          resolver: @escaping RCTPromiseResolveBlock,
                          rejecter: @escaping RCTPromiseRejectBlock) {
    guard var state = state(for: uploadId) else {
      rejecter("UPLOAD_NOT_FOUND", "Upload does not exist", nil)
      return
    }

    guard state.status == "uploading" else {
      resolver(nil)
      return
    }

    let networkPolicyChanged = state.wifiOnly != wifiOnly
    state.notificationStrings = NotificationStrings(notificationStrings)
    state.wifiOnly = wifiOnly
    saveState(state)

    let fileUrl = URL(fileURLWithPath: state.filePath)
    guard FileManager.default.fileExists(atPath: fileUrl.path) else {
      markFailed(uploadId, "Upload file does not exist")
      resolver(nil)
      return
    }

    session.getAllTasks { tasks in
      if let task = tasks.first(where: { $0.taskDescription == uploadId }) {
        if networkPolicyChanged {
          let handlers = self.stateQueue.sync {
            self.replacedTaskIds.insert(task.taskIdentifier)
            self.uploadIdsByTaskId.removeValue(forKey: task.taskIdentifier)
            self.lastEmittedProgressByTaskId.removeValue(forKey: task.taskIdentifier)
            return self.promiseHandlersByTaskId.removeValue(forKey: task.taskIdentifier)
          }
          task.cancel()

          var restartedState = state
          restartedState.uploadedBytes = 0
          restartedState.status = "uploading"
          restartedState.error = nil
          restartedState.retryCount = 0

          guard let replacementTask = self.makeUploadTask(from: restartedState) else {
            self.markFailed(uploadId, "Invalid upload URL")
            handlers?.rejecter("UPLOAD_ERROR", "Invalid upload URL", nil)
            resolver(nil)
            return
          }

          self.saveState(restartedState)
          self.stateQueue.sync {
            self.uploadIdsByTaskId[replacementTask.taskIdentifier] = uploadId
            if let handlers {
              self.promiseHandlersByTaskId[replacementTask.taskIdentifier] = handlers
            }
            self.lastEmittedProgressByTaskId[replacementTask.taskIdentifier] = -1
          }
          replacementTask.resume()
          resolver(nil)
          return
        }

        self.stateQueue.sync {
          self.uploadIdsByTaskId[task.taskIdentifier] = uploadId
          self.lastEmittedProgressByTaskId[task.taskIdentifier] = -1
        }
        task.resume()
        resolver(nil)
        return
      }

      var restartedState = state
      restartedState.uploadedBytes = 0
      restartedState.status = "uploading"
      restartedState.error = nil
      restartedState.retryCount = 0

      guard let task = self.makeUploadTask(from: restartedState) else {
        self.markFailed(uploadId, "Invalid upload URL")
        resolver(nil)
        return
      }

      self.saveState(restartedState)
      self.stateQueue.sync {
        self.uploadIdsByTaskId[task.taskIdentifier] = uploadId
        self.lastEmittedProgressByTaskId[task.taskIdentifier] = -1
      }
      task.resume()
      resolver(nil)
    }
  }

  @objc func waitForUpload(_ uploadId: String,
                           resolver: @escaping RCTPromiseResolveBlock,
                           rejecter: @escaping RCTPromiseRejectBlock) {
    guard let state = state(for: uploadId) else {
      rejecter("UPLOAD_NOT_FOUND", "Upload does not exist", nil)
      return
    }
    if state.status == "uploadedAwaitingFinalize" {
      resolver(nil)
    } else if state.status == "failed" {
      rejecter("UPLOAD_ERROR", state.error ?? "Upload failed", nil)
    } else {
      stateQueue.sync {
        waitersByUploadId[uploadId, default: []].append((resolver, rejecter))
      }
    }
  }

  @objc func markUploadFinalized(_ uploadId: String,
                                 resolver: @escaping RCTPromiseResolveBlock,
                                 rejecter: @escaping RCTPromiseRejectBlock) {
    resolveWaiters(uploadId)
    removeState(uploadId)
    UNUserNotificationCenter.current().removePendingNotificationRequests(withIdentifiers: [uploadId])
    UNUserNotificationCenter.current().removeDeliveredNotifications(withIdentifiers: [uploadId])
    resolver(nil)
  }

  @objc func clearUpload(_ uploadId: String,
                         resolver: @escaping RCTPromiseResolveBlock,
                         rejecter: @escaping RCTPromiseRejectBlock) {
    session.getAllTasks { tasks in
      tasks.filter { $0.taskDescription == uploadId }.forEach { $0.cancel() }
      self.rejectWaiters(uploadId, message: "Upload was cleared")
      self.removeState(uploadId)
      resolver(nil)
    }
  }

  @objc func setAppActive(_ active: Bool) {
    defaults.set(active, forKey: Self.appActiveKey)
  }

  @objc func requestNotificationPermission(_ resolver: @escaping RCTPromiseResolveBlock,
                                           rejecter: @escaping RCTPromiseRejectBlock) {
    UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound]) { granted, error in
      if let error {
        rejecter("NOTIFICATION_PERMISSION_ERROR", error.localizedDescription, error)
      } else {
        resolver(granted)
      }
    }
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

  @objc func listDocumentM4AFiles(_ resolver: @escaping RCTPromiseResolveBlock,
                                  rejecter: @escaping RCTPromiseRejectBlock) {
    DispatchQueue.global(qos: .userInitiated).async {
      do {
        let fileManager = FileManager.default
        guard let documentsDirectory = fileManager.urls(for: .documentDirectory, in: .userDomainMask).first else {
          resolver([])
          return
        }

        let resourceKeys: Set<URLResourceKey> = [.isDirectoryKey, .creationDateKey, .nameKey, .fileSizeKey]
        guard let enumerator = fileManager.enumerator(
          at: documentsDirectory,
          includingPropertiesForKeys: Array(resourceKeys),
          options: [.skipsHiddenFiles]
        ) else {
          resolver([])
          return
        }

        var output: [[String: Any]] = []
        for case let fileUrl as URL in enumerator {
          if fileUrl.pathComponents.contains("Imported") {
            continue
          }
          let values = try fileUrl.resourceValues(forKeys: resourceKeys)
          if values.isDirectory == true {
            continue
          }

          let fileName = values.name ?? fileUrl.lastPathComponent
          if !fileName.lowercased().hasSuffix(".m4a") {
            continue
          }

          let createdAtMs = values.creationDate?.timeIntervalSince1970 ?? 0
          output.append([
            "path": fileUrl.path,
            "name": fileName,
            "createdAtMs": Int(createdAtMs * 1000),
            "durationSeconds": self.getDurationSeconds(fileUrl),
            "fileSizeBytes": values.fileSize ?? 0
          ])
        }

        resolver(output)
      } catch {
        rejecter("LIST_DOCUMENT_FILES_ERROR", "Unable to list document flac files", error)
      }
    }
  }

  @objc func readBundledFileAsBase64(_ fileName: String,
                                     resolver: @escaping RCTPromiseResolveBlock,
                                     rejecter: @escaping RCTPromiseRejectBlock) {
    let normalizedName = fileName.trimmingCharacters(in: .whitespacesAndNewlines)
    guard !normalizedName.isEmpty else {
      rejecter("BUNDLE_FILE_READ_ERROR", "File name cannot be empty", nil)
      return
    }

    DispatchQueue.global(qos: .userInitiated).async {
      do {
        let nsName = normalizedName as NSString
        let resource = nsName.deletingPathExtension
        let ext = nsName.pathExtension.isEmpty ? nil : nsName.pathExtension
        let bundleUrl = Bundle.main.url(forResource: resource, withExtension: ext)
          ?? Bundle.main.url(forResource: normalizedName, withExtension: nil)

        guard let fileUrl = bundleUrl else {
          rejecter("BUNDLE_FILE_NOT_FOUND", "Bundled file not found: \(normalizedName)", nil)
          return
        }

        let data = try Data(contentsOf: fileUrl, options: [.mappedIfSafe])
        resolver(data.base64EncodedString())
      } catch {
        rejecter("BUNDLE_FILE_READ_ERROR", "Unable to read bundled file: \(normalizedName)", error)
      }
    }
  }

  @objc func copyExternalFile(_ sourceUri: String,
                              fileName: String,
                              maxSize: Double,
                              resolver: @escaping RCTPromiseResolveBlock,
                              rejecter: @escaping RCTPromiseRejectBlock) {
    DispatchQueue.global(qos: .userInitiated).async {
      let sourceUrl: URL
      if let parsedUrl = URL(string: sourceUri), parsedUrl.scheme != nil {
        sourceUrl = parsedUrl
      } else {
        sourceUrl = URL(fileURLWithPath: self.normalizePath(sourceUri))
      }

      let didStartAccessing = sourceUrl.startAccessingSecurityScopedResource()
      defer {
        if didStartAccessing {
          sourceUrl.stopAccessingSecurityScopedResource()
        }
      }

      var destination: URL? = nil
      do {
        let fileManager = FileManager.default
        guard fileManager.fileExists(atPath: sourceUrl.path) else {
          rejecter("FILE_NOT_FOUND", "Shared file does not exist", nil)
          return
        }

        guard let documentsDirectory = fileManager.urls(
          for: .documentDirectory,
          in: .userDomainMask
        ).first else {
          rejecter("FILE_COPY_ERROR", "Unable to access app documents", nil)
          return
        }

        let importedDirectory = documentsDirectory
          .appendingPathComponent("Assistant Transcripts", isDirectory: true)
          .appendingPathComponent("Imported", isDirectory: true)
        try fileManager.createDirectory(
          at: importedDirectory,
          withIntermediateDirectories: true,
          attributes: nil
        )

        let resolvedName = fileName.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
          ? (sourceUrl.lastPathComponent.isEmpty ? "audio-file" : sourceUrl.lastPathComponent)
          : fileName
        let safeName = self.sanitizeImportedFileName(resolvedName)
        let dest = importedDirectory.appendingPathComponent(
          "\(UUID().uuidString)-\(safeName)"
        )
        destination = dest

        let maxSizeBytes = Int64(maxSize)
        let inputStream = InputStream(url: sourceUrl)
        let outputStream = OutputStream(url: dest, append: false)

        guard let input = inputStream, let output = outputStream else {
          rejecter("FILE_COPY_ERROR", "Unable to open file streams", nil)
          return
        }

        input.open()
        output.open()
        defer {
          input.close()
          output.close()
        }

        let bufferSize = 8192
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer {
          buffer.deallocate()
        }

        var bytesCopied: Int64 = 0
        while input.hasBytesAvailable {
          let bytesRead = input.read(buffer, maxLength: bufferSize)
          if bytesRead < 0 {
            throw input.streamError ?? NSError(
              domain: "FileUploadModule",
              code: -1,
              userInfo: [NSLocalizedDescriptionKey: "Read error"]
            )
          }
          if bytesRead == 0 {
            break
          }

          bytesCopied += Int64(bytesRead)
          if maxSizeBytes > 0 && bytesCopied > maxSizeBytes {
            if fileManager.fileExists(atPath: dest.path) {
              try? fileManager.removeItem(at: dest)
            }
            rejecter("FILE_TOO_LARGE", "File exceeds maximum size limit", nil)
            return
          }

          var bytesWritten = 0
          while bytesWritten < bytesRead {
            let written = output.write(buffer.advanced(by: bytesWritten), maxLength: bytesRead - bytesWritten)
            if written < 0 {
              throw output.streamError ?? NSError(
                domain: "FileUploadModule",
                code: -1,
                userInfo: [NSLocalizedDescriptionKey: "Write error"]
              )
            }
            bytesWritten += written
          }
        }

        let attributes = try fileManager.attributesOfItem(atPath: dest.path)
        let size = (attributes[.size] as? NSNumber)?.intValue ?? 0
        resolver(["path": dest.path, "name": safeName, "size": size])
      } catch {
        if let dest = destination, FileManager.default.fileExists(atPath: dest.path) {
          try? FileManager.default.removeItem(at: dest)
        }
        rejecter("FILE_COPY_ERROR", "Unable to copy shared file", error)
      }
    }
  }

  override func supportedEvents() -> [String]! {
    [FileUploadModule.uploadProgressEvent, FileUploadModule.incomingSharedFileEvent]
  }

  override func startObserving() {
    hasListeners = true
  }

  override func stopObserving() {
    hasListeners = false
  }

  @objc static func storeBackgroundCompletionHandler(_ handler: @escaping () -> Void) {
    backgroundCompletionHandler = handler
  }

  func urlSession(_ session: URLSession,
                  task: URLSessionTask,
                  didSendBodyData bytesSent: Int64,
                  totalBytesSent: Int64,
                  totalBytesExpectedToSend: Int64) {
    let uploadId = stateQueue.sync { () -> String? in
      let resolvedUploadId = uploadIdsByTaskId[task.taskIdentifier] ?? task.taskDescription
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
      return resolvedUploadId
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
    let wasReplaced = stateQueue.sync {
      replacedTaskIds.remove(task.taskIdentifier) != nil
    }
    if wasReplaced {
      return
    }

    let uploadId = task.taskDescription ?? stateQueue.sync {
      uploadIdsByTaskId[task.taskIdentifier]
    }
    let taskState = stateQueue.sync {
      (
        uploadId: uploadIdsByTaskId.removeValue(forKey: task.taskIdentifier) ?? uploadId,
        handlers: promiseHandlersByTaskId.removeValue(forKey: task.taskIdentifier)
      )
    }
    stateQueue.sync {
      lastEmittedProgressByTaskId.removeValue(forKey: task.taskIdentifier)
    }

    if let error = error {
      if let uploadId = taskState.uploadId {
        if retryUpload(uploadId, handlers: taskState.handlers) {
          return
        }
        markFailed(uploadId, error.localizedDescription)
      }
      taskState.handlers?.rejecter("UPLOAD_ERROR", error.localizedDescription, error)
      return
    }

    let status = (task.response as? HTTPURLResponse)?.statusCode ?? 0
    if status == 200 {
      if let uploadId = taskState.uploadId {
        let totalBytes = task.countOfBytesExpectedToSend
        sendProgress(uploadId: uploadId, uploadedBytes: totalBytes, totalBytes: totalBytes)
        markSucceeded(uploadId, totalBytes: totalBytes)
      }
      taskState.handlers?.resolver(nil)
    } else {
      let message = "Status: \(status)"
      if let uploadId = taskState.uploadId {
        if isTransientHTTPStatus(status),
           retryUpload(uploadId, handlers: taskState.handlers) {
          return
        }
        markFailed(uploadId, message)
      }
      taskState.handlers?.rejecter("UPLOAD_FAILED", message, nil)
    }
  }

  func urlSessionDidFinishEvents(forBackgroundURLSession session: URLSession) {
    DispatchQueue.main.async {
      Self.backgroundCompletionHandler?()
      Self.backgroundCompletionHandler = nil
    }
  }

  private func sendProgress(uploadId: String, uploadedBytes: Int64, totalBytes: Int64) {
    if var state = state(for: uploadId) {
      state.uploadedBytes = uploadedBytes
      saveState(state)
    }
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

  private func makeUploadTask(from state: UploadState) -> URLSessionUploadTask? {
    guard let requestUrl = URL(string: state.url) else {
      return nil
    }

    var request = URLRequest(url: requestUrl)
    request.httpMethod = "PUT"
    request.allowsCellularAccess = !state.wifiOnly
    request.setValue(state.contentType, forHTTPHeaderField: "Content-Type")
    if let acl = state.acl {
      request.setValue(acl, forHTTPHeaderField: "X-amz-acl")
    }

    let task = session.uploadTask(
      with: request,
      fromFile: URL(fileURLWithPath: state.filePath)
    )
    task.taskDescription = state.uploadId
    return task
  }

  private func retryUpload(_ uploadId: String, handlers: PromiseHandlers?) -> Bool {
    guard var state = state(for: uploadId),
          state.status == "uploading",
          state.retryCount < Self.maxUploadRetries,
          let task = makeUploadTask(from: state) else {
      return false
    }

    state.retryCount += 1
    state.uploadedBytes = 0
    state.error = nil
    saveState(state)
    stateQueue.sync {
      uploadIdsByTaskId[task.taskIdentifier] = uploadId
      if let handlers {
        promiseHandlersByTaskId[task.taskIdentifier] = handlers
      }
      lastEmittedProgressByTaskId[task.taskIdentifier] = -1
    }
    task.resume()
    return true
  }

  private func isTransientHTTPStatus(_ status: Int) -> Bool {
    status == 408 || status == 429 || status >= 500
  }

  @objc override static func requiresMainQueueSetup() -> Bool { false }

  private static let uploadProgressEvent = "FileUploadProgress"

  private func allStates() -> [UploadState] {
    return stateQueue.sync {
      guard let data = defaults.data(forKey: Self.stateKey),
            let states = try? JSONDecoder().decode([UploadState].self, from: data) else {
        return []
      }
      return states
    }
  }

  private func state(for uploadId: String) -> UploadState? {
    return stateQueue.sync {
      guard let data = defaults.data(forKey: Self.stateKey),
            let states = try? JSONDecoder().decode([UploadState].self, from: data) else {
        return nil
      }
      return states.first { $0.uploadId == uploadId }
    }
  }

  private func saveState(_ state: UploadState) {
    stateQueue.sync {
      var states: [UploadState]
      if let data = defaults.data(forKey: Self.stateKey),
         let decoded = try? JSONDecoder().decode([UploadState].self, from: data) {
        states = decoded.filter { $0.uploadId != state.uploadId }
      } else {
        states = []
      }
      states.append(state)
      if let data = try? JSONEncoder().encode(states) {
        defaults.set(data, forKey: Self.stateKey)
      }
    }
  }

  private func removeState(_ uploadId: String) {
    stateQueue.sync {
      var states: [UploadState] = []
      if let data = defaults.data(forKey: Self.stateKey),
         let decoded = try? JSONDecoder().decode([UploadState].self, from: data) {
        states = decoded.filter { $0.uploadId != uploadId }
      }
      if let data = try? JSONEncoder().encode(states) {
        defaults.set(data, forKey: Self.stateKey)
      }
    }
  }

  private func isAppActive() -> Bool {
    return (defaults.object(forKey: Self.appActiveKey) as? Bool) ?? true
  }

  private func markSucceeded(_ uploadId: String, totalBytes: Int64) {
    guard var state = state(for: uploadId) else { return }
    let notificationStrings = state.notificationStrings ?? NotificationStrings()
    state.uploadedBytes = totalBytes
    state.status = "uploadedAwaitingFinalize"
    state.error = nil
    saveState(state)
    resolveWaiters(uploadId)
    if !isAppActive() {
      scheduleCompletionNotification(uploadId, notificationStrings: notificationStrings)
    }
  }

  private func markFailed(_ uploadId: String, _ message: String) {
    guard var state = state(for: uploadId) else { return }
    let notificationStrings = state.notificationStrings ?? NotificationStrings()
    state.status = "failed"
    state.error = message
    saveState(state)
    rejectWaiters(uploadId, message: message)
    if !isAppActive() {
      scheduleFailureNotification(uploadId, notificationStrings: notificationStrings)
    }
  }

  private func resolveWaiters(_ uploadId: String) {
    let waiters = stateQueue.sync { waitersByUploadId.removeValue(forKey: uploadId) ?? [] }
    waiters.forEach { $0.0(nil) }
  }

  private func rejectWaiters(_ uploadId: String, message: String) {
    let waiters = stateQueue.sync { waitersByUploadId.removeValue(forKey: uploadId) ?? [] }
    waiters.forEach { $0.1("UPLOAD_ERROR", message, nil) }
  }

  private func scheduleCompletionNotification(
    _ uploadId: String,
    notificationStrings: NotificationStrings
  ) {
    scheduleNotification(
      uploadId,
      title: notificationStrings.completeTitle,
      body: notificationStrings.completeBody
    )
  }

  private func scheduleFailureNotification(
    _ uploadId: String,
    notificationStrings: NotificationStrings
  ) {
    scheduleNotification(
      uploadId,
      title: notificationStrings.failedTitle,
      body: notificationStrings.failedBody
    )
  }

  private func scheduleNotification(_ identifier: String, title: String, body: String) {
    let content = UNMutableNotificationContent()
    content.title = title
    content.body = body
    content.sound = .default
    UNUserNotificationCenter.current().add(
      UNNotificationRequest(identifier: identifier, content: content, trigger: nil)
    )
  }

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

  private func sanitizeImportedFileName(_ fileName: String) -> String {
    let trimmed = fileName.trimmingCharacters(in: .whitespacesAndNewlines)
    let fallback = trimmed.isEmpty ? "audio-file" : trimmed
    let invalidCharacters = CharacterSet(charactersIn: "\\/:*?\"<>|")
    return fallback.components(separatedBy: invalidCharacters).joined(separator: "_")
  }

  private func getDurationSeconds(_ fileURL: URL) -> Double {
    let asset = AVURLAsset(url: fileURL)
    let duration = CMTimeGetSeconds(asset.duration)
    guard duration.isFinite, duration >= 0 else {
      return 0
    }
    return duration
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
