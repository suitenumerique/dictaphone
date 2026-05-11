package fr.gouv.assistant_transcripts

import com.facebook.react.bridge.*
import com.facebook.react.modules.core.DeviceEventManagerModule
import java.io.File
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
}
