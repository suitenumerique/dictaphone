package com.dictaphone

import com.facebook.react.bridge.*
import java.io.File
import java.net.HttpURLConnection
import java.net.URL
import kotlin.concurrent.thread

class FileUploadModule(reactContext: ReactApplicationContext) :
    ReactContextBaseJavaModule(reactContext) {

    override fun getName() = "FileUploadModule"

    @ReactMethod
    fun uploadFile(filePath: String, url: String, contentType: String, promise: Promise) {
        thread {
            try {
                val file = File(filePath)
                val connection = URL(url).openConnection() as HttpURLConnection

                connection.requestMethod = "PUT"
                connection.setRequestProperty("Content-Type", contentType)
                connection.setRequestProperty("X-amz-acl", "private")
                connection.setRequestProperty("Content-Length", file.length().toString())
                connection.doOutput = true
                connection.setFixedLengthStreamingMode(file.length()) // true streaming

                file.inputStream().use { input ->
                    connection.outputStream.use { output ->
                        input.copyTo(output, bufferSize = 8192)
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
}
