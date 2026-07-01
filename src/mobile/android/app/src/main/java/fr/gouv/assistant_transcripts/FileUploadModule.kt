package fr.gouv.assistant_transcripts

import android.content.ClipData
import android.content.Intent
import android.media.MediaExtractor
import android.media.MediaFormat
import android.media.MediaMetadataRetriever
import android.os.SystemClock
import android.util.Base64
import androidx.core.content.FileProvider
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import java.nio.ByteBuffer
import java.nio.file.Files
import java.nio.file.attribute.BasicFileAttributes
import java.util.concurrent.atomic.AtomicInteger
import kotlin.concurrent.thread

class FileUploadModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {
    private val listenerCount = AtomicInteger(0)

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
        uploadId: String,
        promise: Promise
    ) {
        thread {
            try {
                val file = File(normalizePath(filePath))
                val totalBytes = file.length()
                val connection = URL(url).openConnection() as HttpURLConnection

                connection.requestMethod = "PUT"
                connection.setRequestProperty("Content-Type", contentType)
                connection.setRequestProperty("X-amz-acl", "private")
                connection.setRequestProperty("Content-Length", totalBytes.toString())
                connection.doOutput = true
                connection.connectTimeout = HTTP_CONNECT_TIMEOUT_MS
                connection.setFixedLengthStreamingMode(totalBytes) // true streaming

                var lastEmittedProgress = -1
                var lastReportedBytes = 0L
                var lastReportedAtMs = 0L
                fun emitProgress(uploadedBytes: Long, force: Boolean = false) {
                    if (!force) {
                        val now = SystemClock.elapsedRealtime()
                        val sentEnoughBytes =
                            (uploadedBytes - lastReportedBytes) >= PROGRESS_BYTES_STEP
                        val waitedEnoughTime = (now - lastReportedAtMs) >= PROGRESS_MIN_INTERVAL_MS
                        if (!sentEnoughBytes && !waitedEnoughTime) {
                            return
                        }
                    }

                    val currentProgress =
                        if (totalBytes > 0) ((uploadedBytes * 100) / totalBytes).toInt() else 0

                    if (currentProgress != lastEmittedProgress || uploadedBytes == totalBytes) {
                        lastEmittedProgress = currentProgress
                        lastReportedBytes = uploadedBytes
                        lastReportedAtMs = SystemClock.elapsedRealtime()
                        sendProgress(uploadId, uploadedBytes, totalBytes)
                    }
                }

                emitProgress(0, force = true)

                BufferedInputStream(file.inputStream(), UPLOAD_BUFFER_SIZE).use { input ->
                    BufferedOutputStream(connection.outputStream, UPLOAD_BUFFER_SIZE).use { output ->
                        val buffer = ByteArray(UPLOAD_BUFFER_SIZE)
                        var uploadedBytes = 0L
                        var bytesRead = input.read(buffer)

                        while (bytesRead >= 0) {
                            output.write(buffer, 0, bytesRead)
                            uploadedBytes += bytesRead
                            emitProgress(uploadedBytes)
                            bytesRead = input.read(buffer)
                        }
                        output.flush()
                    }
                }

                val status = connection.responseCode
                if (status == 200) {
                    emitProgress(totalBytes, force = true)
                    promise.resolve(null)
                } else {
                    promise.reject("UPLOAD_FAILED", "Status: $status")
                }

            } catch (e: Exception) {
                promise.reject("UPLOAD_ERROR", e.message)
            }
        }
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

    private fun sendProgress(uploadId: String, uploadedBytes: Long, totalBytes: Long) {
        if (listenerCount.get() <= 0) {
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

    companion object {
        private const val UPLOAD_PROGRESS_EVENT = "FileUploadProgress"
        private const val DEFAULT_BUFFER_SIZE = 8192
        private const val UPLOAD_BUFFER_SIZE = 256 * 1024
        private const val PROGRESS_BYTES_STEP = 512 * 1024L
        private const val PROGRESS_MIN_INTERVAL_MS = 200L
        private const val HTTP_CONNECT_TIMEOUT_MS = 30_000
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

    private fun collectM4AFiles(root: File): List<File> {
        val output = mutableListOf<File>()
        val stack = ArrayDeque<File>()
        stack.add(root)

        while (stack.isNotEmpty()) {
            val current = stack.removeLast()
            val children = current.listFiles() ?: continue
            children.forEach { child ->
                if (child.isDirectory) {
                    stack.add(child)
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
