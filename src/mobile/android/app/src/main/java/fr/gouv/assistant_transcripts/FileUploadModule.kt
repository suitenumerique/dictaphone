package fr.gouv.assistant_transcripts

import android.content.ClipData
import android.content.Intent
import androidx.core.content.FileProvider
import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.File
import java.io.FileInputStream
import java.io.FileOutputStream
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class FileUploadModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    override fun getName() = "FileUploadModule"

    @ReactMethod
    fun addListener(eventName: String) {
        // Required for NativeEventEmitter.
    }

    @ReactMethod
    fun removeListeners(count: Int) {
        // Required for NativeEventEmitter.
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
                val file = File(filePath)
                val totalBytes = file.length()
                val connection = URL(url).openConnection() as HttpURLConnection

                connection.requestMethod = "PUT"
                connection.setRequestProperty("Content-Type", contentType)
                connection.setRequestProperty("X-amz-acl", "private")
                connection.setRequestProperty("Content-Length", totalBytes.toString())
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(totalBytes) // true streaming

                var lastEmittedProgress = -1
                fun emitProgress(uploadedBytes: Long) {
                    val currentProgress =
                        if (totalBytes > 0) ((uploadedBytes * 100) / totalBytes).toInt() else 0

                    if (currentProgress != lastEmittedProgress || uploadedBytes == totalBytes) {
                        lastEmittedProgress = currentProgress
                        sendProgress(uploadId, uploadedBytes, totalBytes)
                    }
                }

                emitProgress(0)

                file.inputStream().use { input ->
                    connection.outputStream.use { output ->
                        val buffer = ByteArray(DEFAULT_BUFFER_SIZE)
                        var uploadedBytes = 0L
                        var bytesRead = input.read(buffer)

                        while (bytesRead >= 0) {
                            output.write(buffer, 0, bytesRead)
                            uploadedBytes += bytesRead
                            emitProgress(uploadedBytes)
                            bytesRead = input.read(buffer)
                        }
                    }
                }

                val status = connection.responseCode
                if (status == 200) promise.resolve(null)
                else promise.reject("UPLOAD_FAILED", "Status: $status")

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

    private fun sendProgress(uploadId: String, uploadedBytes: Long, totalBytes: Long) {
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

    private fun normalizePath(path: String): String {
        val prefix = "file://"
        return if (path.startsWith(prefix)) path.removePrefix(prefix) else path
    }
}
