package fr.gouv.assistant_transcripts

import android.content.ClipData
import android.content.Context
import android.content.Intent
import android.net.Uri
import android.provider.OpenableColumns
import android.app.NotificationManager
import android.app.PendingIntent
import android.os.Build
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.util.Base64
import androidx.core.content.FileProvider
import androidx.core.app.NotificationCompat
import androidx.work.BackoffPolicy
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

class FileUploadModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {
    private val listenerCount = AtomicInteger(0)
    private val uploadStateStore = UploadStateStore(reactContext)
    private val waiters = mutableMapOf<String, MutableList<Promise>>()

    init {
        instance = this
    }

    override fun invalidate() {
        super.invalidate()
        instance = null
    }

    override fun getName() = "FileUploadModule"

    @ReactMethod
    fun addListener(eventName: String) {
        // Required for NativeEventEmitter.
        listenerCount.incrementAndGet()
    }

    @ReactMethod
    fun removeListeners(count: Int) {
        // Required for NativeEventEmitter.
        listenerCount.updateAndGet { current -> (current - count).coerceAtLeast(0) }
    }

    @ReactMethod
    fun uploadFile(
        filePath: String,
        url: String,
        contentType: String,
        acl: String?,
        uploadId: String,
        wifiOnly: Boolean,
        notificationStrings: ReadableMap,
        promise: Promise
    ) {
        val file = File(normalizePath(filePath))
        if (!file.exists() || !file.isFile) {
            promise.reject("FILE_NOT_FOUND", "Upload file does not exist")
            return
        }

        val totalBytes = file.length()
        uploadStateStore.put(
            NativeUploadState(
                uploadId = uploadId,
                filePath = file.absolutePath,
                url = url,
                contentType = contentType,
                acl = acl,
                totalBytes = totalBytes,
                uploadedBytes = 0,
                wifiOnly = wifiOnly,
                status = FileUploadWorker.UPLOADING,
                notificationStrings = parseNotificationStrings(notificationStrings),
            )
        )
        synchronized(waiters) {
            waiters.getOrPut(uploadId) { mutableListOf() }.add(promise)
        }

        enqueueUpload(uploadId, wifiOnly)
    }

    @ReactMethod
    fun getUploadStatuses(promise: Promise) {
        val result = Arguments.createArray()
        uploadStateStore.all().forEach { state ->
            result.pushMap(
                Arguments.createMap().apply {
                    putString("uploadId", state.uploadId)
                    putString("status", state.status)
                    putDouble("uploadedBytes", state.uploadedBytes.toDouble())
                    putDouble("totalBytes", state.totalBytes.toDouble())
                    state.error?.let { putString("error", it) }
                }
            )
        }
        promise.resolve(result)
    }

    @ReactMethod
    fun resumeUpload(
        uploadId: String,
        notificationStrings: ReadableMap,
        wifiOnly: Boolean,
        promise: Promise,
    ) {
        val state = uploadStateStore.get(uploadId)
        when {
            state == null -> promise.reject("UPLOAD_NOT_FOUND", "Upload does not exist")
            state.status != FileUploadWorker.UPLOADING -> promise.resolve(null)
            else -> {
                val networkPolicyChanged = state.wifiOnly != wifiOnly
                uploadStateStore.put(
                    state.copy(
                        notificationStrings = parseNotificationStrings(notificationStrings),
                        wifiOnly = wifiOnly,
                    )
                )
                enqueueUpload(uploadId, wifiOnly, replaceExisting = networkPolicyChanged)
                promise.resolve(null)
            }
        }
    }

    @ReactMethod
    fun waitForUpload(uploadId: String, promise: Promise) {
        val state = uploadStateStore.get(uploadId)
        when (state?.status) {
            FileUploadWorker.UPLOADED_AWAITING_FINALIZE -> promise.resolve(null)
            FileUploadWorker.FAILED -> promise.reject("UPLOAD_ERROR", state.error)
            null -> promise.reject("UPLOAD_NOT_FOUND", "Upload does not exist")
            else -> synchronized(waiters) {
                waiters.getOrPut(uploadId) { mutableListOf() }.add(promise)
            }
        }
    }

    @ReactMethod
    fun markUploadFinalized(uploadId: String, promise: Promise) {
        resolveWaiters(uploadId)
        uploadStateStore.remove(uploadId)
        WorkManager.getInstance(reactApplicationContext).cancelUniqueWork(workName(uploadId))
        cancelNotification(uploadId)
        promise.resolve(null)
    }

    @ReactMethod
    fun clearUpload(uploadId: String, promise: Promise) {
        rejectWaiters(uploadId, "Upload was cleared")
        uploadStateStore.remove(uploadId)
        WorkManager.getInstance(reactApplicationContext).cancelUniqueWork(workName(uploadId))
        cancelNotification(uploadId)
        promise.resolve(null)
    }

    @ReactMethod
    fun setAppActive(active: Boolean) {
        uploadStateStore.setAppActive(active)
    }

    @ReactMethod
    fun requestNotificationPermission(promise: Promise) {
        // Android notification permission is requested by PermissionsAndroid in JS.
        promise.resolve(true)
    }

    @ReactMethod
    fun copyExternalFile(sourceUri: String, fileName: String, maxSize: Double, promise: Promise) {
        thread {
            try {
                val source = Uri.parse(sourceUri)
                val input = if (source.scheme == "file") {
                    FileInputStream(
                        File(source.path ?: throw IllegalArgumentException("Invalid file URI"))
                    )
                } else {
                    reactApplicationContext.contentResolver.openInputStream(source)
                        ?: throw IllegalArgumentException("Unable to open shared file")
                }

                val importedDirectory = File(
                    reactApplicationContext.filesDir,
                    "Assistant Transcripts/Imported",
                )
                if (!importedDirectory.exists() && !importedDirectory.mkdirs()) {
                    throw IllegalStateException("Unable to create imported files directory")
                }

                val resolvedName = fileName.trim().ifEmpty {
                    queryDisplayName(source).orEmpty()
                }
                val safeName = sanitizeImportedFileName(
                    resolvedName.ifEmpty {
                        "audio-file${extensionForMimeType(reactApplicationContext.contentResolver.getType(source))}"
                    },
                )
                val dest = File(
                    importedDirectory,
                    "${System.currentTimeMillis()}-$safeName",
                )

                val maxSizeBytes = maxSize.toLong()
                var bytesCopied = 0L
                input.use { inputStream ->
                    dest.outputStream().use { outputStream ->
                        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                        var bytesRead = inputStream.read(buffer)
                        while (bytesRead >= 0) {
                            bytesCopied += bytesRead
                            if (maxSizeBytes > 0 && bytesCopied > maxSizeBytes) {
                                if (dest.exists()) {
                                    dest.delete()
                                }
                                promise.reject("FILE_TOO_LARGE", "File exceeds maximum size limit")
                                return@thread
                            }
                            outputStream.write(buffer, 0, bytesRead)
                            bytesRead = inputStream.read(buffer)
                        }
                        outputStream.flush()
                    }
                }

                promise.resolve(
                    Arguments.createMap().apply {
                        putString("path", dest.absolutePath)
                        putString("name", safeName)
                        putDouble("size", dest.length().toDouble())
                    },
                )
            } catch (error: Exception) {
                promise.reject("FILE_COPY_ERROR", "Unable to copy shared file", error)
            }
        }
    }

    @ReactMethod
    fun getPendingSharedFile(promise: Promise) {
        val result = Arguments.createArray()
        while (true) {
            val file = takePendingSharedFile() ?: break
            result.pushMap(file)
        }
        promise.resolve(result)
    }

    @ReactMethod
    fun shareAudioFile(filePath: String, fileName: String, promise: Promise) {
        thread {
            try {
                val sourceFile = File(normalizePath(filePath))
                if (!sourceFile.exists() || !sourceFile.isFile) {
                    promise.reject("FILE_NOT_FOUND", "Recording file does not exist")
                    return@thread
                }

                val safeName = sanitizeFileName(fileName)
                val sharedDir = File(reactApplicationContext.cacheDir, "shared_audio")
                if (!sharedDir.exists()) {
                    sharedDir.mkdirs()
                }
                val sharedFile = File(sharedDir, "${System.currentTimeMillis()}-$safeName")
                copyFile(sourceFile, sharedFile)

                val authority = "${reactApplicationContext.packageName}.fileprovider"
                val contentUri =
                    FileProvider.getUriForFile(reactApplicationContext, authority, sharedFile)
                val shareIntent =
                    Intent(Intent.ACTION_SEND).apply {
                        type = "audio/mp4"
                        putExtra(Intent.EXTRA_STREAM, contentUri)
                        clipData =
                            ClipData.newUri(
                                reactApplicationContext.contentResolver,
                                sharedFile.name,
                                contentUri
                            )
                        addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION)
                    }
                val chooser = Intent.createChooser(shareIntent, null).apply {
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
                }

                reactApplicationContext.startActivity(chooser)
                promise.resolve(null)
            } catch (e: Exception) {
                promise.reject("SHARE_ERROR", e.message, e)
            }
        }
    }

    @ReactMethod
    fun deleteLocalFile(filePath: String, promise: Promise) {
        thread {
            try {
                val file = File(normalizePath(filePath))
                if (!file.exists()) {
                    promise.resolve(null)
                    return@thread
                }

                if (file.delete()) {
                    promise.resolve(null)
                } else {
                    promise.reject("DELETE_ERROR", "Unable to delete local file")
                }
            } catch (e: Exception) {
                promise.reject("DELETE_ERROR", e.message, e)
            }
        }
    }

    @ReactMethod
    fun localFileExists(filePath: String, promise: Promise) {
        thread {
            try {
                val file = File(normalizePath(filePath))
                promise.resolve(file.exists() && file.isFile)
            } catch (e: Exception) {
                promise.reject("FILE_EXISTS_ERROR", e.message, e)
            }
        }
    }

    @ReactMethod
    fun listDocumentM4AFiles(promise: Promise) {
        thread {
            try {
                // react-native-audio-api maps FileDirectory.Document to filesDir on Android
                val documentsDir = reactApplicationContext.filesDir
                if (!documentsDir.exists() || !documentsDir.isDirectory) {
                    promise.resolve(Arguments.createArray())
                    return@thread
                }

                val output = Arguments.createArray()
                collectM4AFiles(documentsDir).forEach { file ->
                    val fileMap =
                        Arguments.createMap().apply {
                            putString("path", file.absolutePath)
                            putString("name", file.name)
                            putDouble("createdAtMs", getCreatedAtMs(file).toDouble())
                            putDouble("durationSeconds", getDurationSeconds(file))
                            putDouble("fileSizeBytes", file.length().toDouble())
                        }
                    output.pushMap(fileMap)
                }
                promise.resolve(output)
            } catch (e: Exception) {
                promise.reject("LIST_DOCUMENT_FILES_ERROR", e.message, e)
            }
        }
    }

    @ReactMethod
    fun readBundledFileAsBase64(fileName: String, promise: Promise) {
        thread {
            try {
                val normalizedName = fileName.trim()
                if (normalizedName.isEmpty()) {
                    promise.reject("BUNDLE_FILE_READ_ERROR", "File name cannot be empty")
                    return@thread
                }

                val baseName = normalizedName.substringBeforeLast('.')
                val resourceName = if (baseName.isNotEmpty()) baseName else normalizedName
                val resources = reactApplicationContext.resources
                val packageName = reactApplicationContext.packageName
                val resourceId = resources.getIdentifier(resourceName, "raw", packageName)

                val bytes =
                    if (resourceId != 0) {
                        resources.openRawResource(resourceId).use { it.readBytes() }
                    } else {
                        reactApplicationContext.assets.open(normalizedName).use { it.readBytes() }
                    }

                promise.resolve(Base64.encodeToString(bytes, Base64.NO_WRAP))
            } catch (e: Exception) {
                promise.reject("BUNDLE_FILE_READ_ERROR", e.message, e)
            }
        }
    }

    private fun onUploadSucceeded(uploadId: String) {
        val state = uploadStateStore.get(uploadId) ?: return
        uploadStateStore.put(
            state.copy(
                uploadedBytes = state.totalBytes,
                status = FileUploadWorker.UPLOADED_AWAITING_FINALIZE,
                error = null,
            )
        )
        sendProgress(uploadId, state.totalBytes, state.totalBytes)
        resolveWaiters(uploadId)
        if (!uploadStateStore.isAppActive()) {
            showUploadNotification(
                state.uploadId,
                state.notificationStrings,
                state.notificationStrings.completeTitle,
                state.notificationStrings.completeBody,
                ongoing = false,
            )
        } else {
            cancelNotification(uploadId)
        }
    }

    private fun onUploadFailed(uploadId: String, message: String) {
        val state = uploadStateStore.get(uploadId) ?: return
        uploadStateStore.put(state.copy(status = FileUploadWorker.FAILED, error = message))
        rejectWaiters(uploadId, message)
        if (!uploadStateStore.isAppActive()) {
            showUploadNotification(
                state.uploadId,
                state.notificationStrings,
                state.notificationStrings.failedTitle,
                state.notificationStrings.failedBody,
                ongoing = false,
            )
        }
    }

    private fun resolveWaiters(uploadId: String) {
        val uploadWaiters = synchronized(waiters) { waiters.remove(uploadId).orEmpty() }
        uploadWaiters.forEach { it.resolve(null) }
    }

    private fun rejectWaiters(uploadId: String, message: String) {
        val uploadWaiters = synchronized(waiters) { waiters.remove(uploadId).orEmpty() }
        uploadWaiters.forEach { it.reject("UPLOAD_ERROR", message) }
    }

    private fun showUploadNotification(
        uploadId: String,
        notificationStrings: UploadNotificationStrings,
        title: String,
        text: String,
        ongoing: Boolean,
    ) {
        val manager = reactApplicationContext.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            manager.createNotificationChannel(
                android.app.NotificationChannel(
                    FileUploadWorker.CHANNEL_ID,
                    notificationStrings.channelName,
                    NotificationManager.IMPORTANCE_LOW,
                )
            )
        }
        val launchIntent = reactApplicationContext.packageManager
            .getLaunchIntentForPackage(reactApplicationContext.packageName)
        val pendingIntent = launchIntent?.let {
            PendingIntent.getActivity(
                reactApplicationContext,
                FileUploadWorker.notificationId(uploadId),
                it,
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
            )
        }
        val notification = NotificationCompat.Builder(
            reactApplicationContext,
            FileUploadWorker.CHANNEL_ID,
        )
            .setSmallIcon(android.R.drawable.stat_sys_upload_done)
            .setContentTitle(title)
            .setContentText(text)
            .setAutoCancel(!ongoing)
            .setOngoing(ongoing)
            .apply { pendingIntent?.let { setContentIntent(it) } }
            .build()
        manager.notify(FileUploadWorker.notificationId(uploadId), notification)
    }

    private fun cancelNotification(uploadId: String) {
        reactApplicationContext
            .getSystemService(NotificationManager::class.java)
            .cancel(FileUploadWorker.notificationId(uploadId))
    }

    private fun enqueueUpload(
        uploadId: String,
        wifiOnly: Boolean,
        replaceExisting: Boolean = false,
    ) {
        val request = OneTimeWorkRequestBuilder<FileUploadWorker>()
            .setInputData(
                androidx.work.Data.Builder()
                    .putString(FileUploadWorker.KEY_UPLOAD_ID, uploadId)
                    .build()
            )
            .setConstraints(FileUploadWorker.requestConstraints(wifiOnly))
            // Network failures should become manually retriable quickly. Linear backoff avoids
            // the long exponential tail while still giving transient failures a second chance.
            .setBackoffCriteria(BackoffPolicy.LINEAR, 10, TimeUnit.SECONDS)
            .build()
        WorkManager.getInstance(reactApplicationContext).enqueueUniqueWork(
            workName(uploadId),
            if (replaceExisting) ExistingWorkPolicy.REPLACE else ExistingWorkPolicy.KEEP,
            request,
        )
    }

    private fun parseNotificationStrings(map: ReadableMap): UploadNotificationStrings =
        UploadNotificationStrings(
            channelName = mapString(map, "channelName", UploadNotificationStrings().channelName),
            uploadingTitle = mapString(map, "uploadingTitle", UploadNotificationStrings().uploadingTitle),
            uploadingIndeterminate = mapString(
                map,
                "uploadingIndeterminate",
                UploadNotificationStrings().uploadingIndeterminate,
            ),
            completeTitle = mapString(map, "completeTitle", UploadNotificationStrings().completeTitle),
            completeBody = mapString(map, "completeBody", UploadNotificationStrings().completeBody),
            failedTitle = mapString(map, "failedTitle", UploadNotificationStrings().failedTitle),
            failedBody = mapString(map, "failedBody", UploadNotificationStrings().failedBody),
        )

    private fun mapString(map: ReadableMap, key: String, fallback: String): String =
        if (map.hasKey(key) && !map.isNull(key)) map.getString(key) ?: fallback else fallback

    private fun sendProgress(uploadId: String, uploadedBytes: Long, totalBytes: Long) {
        if (listenerCount.get() <= 0 || !reactApplicationContext.hasActiveReactInstance()) {
            return
        }

        val params = Arguments.createMap().apply {
            putString("uploadId", uploadId)
            putDouble("uploadedBytes", uploadedBytes.toDouble())
            putDouble("totalBytes", totalBytes.toDouble())
            putDouble(
                "progress",
                if (totalBytes > 0) uploadedBytes.toDouble() / totalBytes.toDouble() else 0.0
            )
        }

        reactApplicationContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(UPLOAD_PROGRESS_EVENT, params)
    }

    private fun emitIncomingSharedFile(file: WritableMap) {
        reactApplicationContext
            .getJSModule(DeviceEventManagerModule.RCTDeviceEventEmitter::class.java)
            .emit(INCOMING_SHARED_FILE_EVENT, file)
    }

    companion object {
        @Volatile
        private var instance: FileUploadModule? = null
        private const val UPLOAD_PROGRESS_EVENT = "FileUploadProgress"
        private const val INCOMING_SHARED_FILE_EVENT = "IncomingSharedFile"
        private const val DEFAULT_BUFFER_SIZE = 8192
        private val pendingSharedFiles = mutableListOf<WritableMap>()

        fun handleIncomingIntent(intent: Intent?) {
            if (intent?.action != Intent.ACTION_SEND) {
                return
            }

            val uri = intent.getParcelableExtra<Uri>(Intent.EXTRA_STREAM) ?: return
            val map = Arguments.createMap().apply {
                putString("uri", uri.toString())
                putString("name", intent.getStringExtra(Intent.EXTRA_TITLE))
                putString("type", intent.type)
            }
            synchronized(pendingSharedFiles) {
                pendingSharedFiles.add(map)
            }
            instance?.emitIncomingSharedFile(map)
        }

        private fun takePendingSharedFile(): WritableMap? {
            synchronized(pendingSharedFiles) {
                return if (pendingSharedFiles.isNotEmpty()) {
                    pendingSharedFiles.removeAt(0)
                } else {
                    null
                }
            }
        }

        fun emitProgressFromWorker(uploadId: String, uploadedBytes: Long, totalBytes: Long) {
            instance?.sendProgress(uploadId, uploadedBytes, totalBytes)
        }

        fun onWorkerUploadSucceeded(context: Context, uploadId: String) {
            instance?.onUploadSucceeded(uploadId) ?: run {
                val store = UploadStateStore(context)
                val state = store.get(uploadId) ?: return
                store.put(
                    state.copy(
                        uploadedBytes = state.totalBytes,
                        status = FileUploadWorker.UPLOADED_AWAITING_FINALIZE,
                        error = null,
                    )
                )
                if (!store.isAppActive()) {
                    showStaticNotification(
                        context,
                        state,
                        state.notificationStrings.completeTitle,
                        state.notificationStrings.completeBody,
                    )
                }
            }
        }

        fun onWorkerUploadFailed(context: Context, uploadId: String, message: String) {
            instance?.onUploadFailed(uploadId, message) ?: run {
                val store = UploadStateStore(context)
                val state = store.get(uploadId) ?: return
                store.put(state.copy(status = FileUploadWorker.FAILED, error = message))
                if (!store.isAppActive()) {
                    showStaticNotification(
                        context,
                        state,
                        state.notificationStrings.failedTitle,
                        state.notificationStrings.failedBody,
                    )
                }
            }
        }

        private fun workName(uploadId: String) = "file-upload-$uploadId"

        private fun showStaticNotification(
            context: Context,
            state: NativeUploadState,
            title: String,
            text: String,
        ) {
            val manager = context.getSystemService(NotificationManager::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                manager.createNotificationChannel(
                    android.app.NotificationChannel(
                        FileUploadWorker.CHANNEL_ID,
                        state.notificationStrings.channelName,
                        NotificationManager.IMPORTANCE_LOW,
                    )
                )
            }
            val launchIntent = context.packageManager.getLaunchIntentForPackage(context.packageName)
            val pendingIntent = launchIntent?.let {
                PendingIntent.getActivity(
                    context,
                    FileUploadWorker.notificationId(state.uploadId),
                    it,
                    PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
                )
            }
            val notification = NotificationCompat.Builder(context, FileUploadWorker.CHANNEL_ID)
                .setSmallIcon(android.R.drawable.stat_sys_upload_done)
                .setContentTitle(title)
                .setContentText(text)
                .setAutoCancel(true)
                .apply { pendingIntent?.let { setContentIntent(it) } }
                .build()
            manager.notify(FileUploadWorker.notificationId(state.uploadId), notification)
        }
    }

    private fun copyFile(source: File, destination: File) {
        FileInputStream(source).use { input ->
            FileOutputStream(destination).use { output ->
                val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                var bytesRead = input.read(buffer)
                while (bytesRead >= 0) {
                    output.write(buffer, 0, bytesRead)
                    bytesRead = input.read(buffer)
                }
                output.flush()
            }
        }
    }

    private fun sanitizeFileName(fileName: String): String {
        val trimmed = fileName.trim().ifEmpty { "recording.m4a" }
        val withExtension = if (trimmed.lowercase().endsWith(".m4a")) trimmed else "$trimmed.m4a"
        return withExtension.replace(Regex("""[\\/:*?"<>|]"""), "_")
    }

    private fun sanitizeImportedFileName(fileName: String): String {
        val trimmed = fileName.trim()
        val fallback = if (trimmed.isEmpty()) "audio-file" else trimmed
        return fallback.replace(Regex("""[\\/:*?"<>|]"""), "_")
    }

    private fun queryDisplayName(uri: Uri): String? {
        if (uri.scheme != "content") {
            return null
        }
        return reactApplicationContext.contentResolver.query(
            uri,
            arrayOf(OpenableColumns.DISPLAY_NAME),
            null,
            null,
            null,
        )?.use { cursor ->
            if (cursor.moveToFirst()) {
                val nameIndex = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME)
                if (nameIndex >= 0) cursor.getString(nameIndex) else null
            } else {
                null
            }
        }
    }

    private fun extensionForMimeType(mimeType: String?): String = when (mimeType) {
        "audio/mp4", "video/mp4" -> ".m4a"
        "audio/mpeg" -> ".mp3"
        "audio/wav", "audio/x-wav" -> ".wav"
        "audio/ogg", "application/ogg" -> ".ogg"
        "audio/opus" -> ".opus"
        "audio/flac" -> ".flac"
        "audio/aac" -> ".aac"
        "audio/webm" -> ".webm"
        else -> ".m4a"
    }

    private fun collectM4AFiles(root: File): List<File> {
        val output = mutableListOf<File>()
        val stack = ArrayDeque<File>()
        stack.add(root)

        while (stack.isNotEmpty()) {
            val current = stack.removeLast()
            val children = current.listFiles() ?: continue
            children.forEach { child ->
                if (child.isDirectory) {
                    if (child.name != "Imported") {
                        stack.add(child)
                    }
                } else if (child.isFile && child.name.lowercase().endsWith(".m4a")) {
                    output.add(child)
                }
            }
        }

        return output
    }

    private fun getCreatedAtMs(file: File): Long =
        try {
            val attrs = Files.readAttributes(file.toPath(), BasicFileAttributes::class.java)
            attrs.creationTime().toMillis()
        } catch (_: Exception) {
            file.lastModified()
        }

    private fun getDurationSeconds(file: File): Double {
        // Some flushed m4a files may miss container duration metadata.
        // Use layered fallbacks to keep recovery robust.
        val durationFromRetrieverMs = getDurationMsFromMetadataRetriever(file)
        if (durationFromRetrieverMs > 0) {
            return durationFromRetrieverMs / 1000.0
        }

        val durationFromExtractorTrackMs = getDurationMsFromExtractorTrackMetadata(file)
        if (durationFromExtractorTrackMs > 0) {
            return durationFromExtractorTrackMs / 1000.0
        }

        val durationFromExtractorSamplesMs = getDurationMsFromExtractorSamples(file)
        return if (durationFromExtractorSamplesMs > 0) {
            durationFromExtractorSamplesMs / 1000.0
        } else {
            0.0
        }
    }

    private fun getDurationMsFromMetadataRetriever(file: File): Long {
        val retriever = MediaMetadataRetriever()
        return try {
            retriever.setDataSource(file.absolutePath)
            retriever.extractMetadata(MediaMetadataRetriever.METADATA_KEY_DURATION)
                ?.toLongOrNull()
                ?: 0L
        } catch (_: Exception) {
            0L
        } finally {
            try {
                retriever.release()
            } catch (_: Exception) {}
        }
    }

    private fun getDurationMsFromExtractorTrackMetadata(file: File): Long {
        val extractor = MediaExtractor()
        return try {
            extractor.setDataSource(file.absolutePath)
            var maxDurationUs = 0L
            for (trackIndex in 0 until extractor.trackCount) {
                val format = extractor.getTrackFormat(trackIndex)
                if (format.containsKey(MediaFormat.KEY_DURATION)) {
                    val durationUs = format.getLong(MediaFormat.KEY_DURATION)
                    if (durationUs > maxDurationUs) {
                        maxDurationUs = durationUs
                    }
                }
            }
            maxDurationUs / 1000L
        } catch (_: Exception) {
            0L
        } finally {
            try {
                extractor.release()
            } catch (_: Exception) {}
        }
    }

    private fun getDurationMsFromExtractorSamples(file: File): Long {
        val extractor = MediaExtractor()
        return try {
            extractor.setDataSource(file.absolutePath)
            var maxSampleTimeUs = 0L

            for (trackIndex in 0 until extractor.trackCount) {
                extractor.selectTrack(trackIndex)
                val buffer = ByteBuffer.allocate(64 * 1024)

                while (true) {
                    val bytesRead = extractor.readSampleData(buffer, 0)
                    if (bytesRead < 0) {
                        break
                    }

                    val sampleTimeUs = extractor.sampleTime
                    if (sampleTimeUs > maxSampleTimeUs) {
                        maxSampleTimeUs = sampleTimeUs
                    }
                    if (!extractor.advance()) {
                        break
                    }
                }

                extractor.unselectTrack(trackIndex)
                extractor.seekTo(0, MediaExtractor.SEEK_TO_CLOSEST_SYNC)
            }

            maxSampleTimeUs / 1000L
        } catch (_: Exception) {
            0L
        } finally {
            try {
                extractor.release()
            } catch (_: Exception) {}
        }
    }

    private fun normalizePath(path: String): String {
        val prefix = "file://"
        return if (path.startsWith(prefix)) path.removePrefix(prefix) else path
    }
}
