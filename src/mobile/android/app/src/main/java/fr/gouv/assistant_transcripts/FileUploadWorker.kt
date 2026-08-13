package fr.gouv.assistant_transcripts

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.content.Context
import android.content.pm.ServiceInfo
import android.os.Build
import android.os.SystemClock
import androidx.core.app.NotificationCompat
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.Data
import androidx.work.ForegroundInfo
import androidx.work.NetworkType
import androidx.work.WorkerParameters
import java.io.BufferedInputStream
import java.io.BufferedOutputStream
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL

class FileUploadWorker(
    appContext: Context,
    workerParams: WorkerParameters,
) : CoroutineWorker(appContext, workerParams) {
    override suspend fun doWork(): Result {
        val uploadId = inputData.getString(KEY_UPLOAD_ID) ?: return Result.failure()
        val store = UploadStateStore(applicationContext)
        val state = store.get(uploadId) ?: return Result.success()

        if (state.status == UPLOADED_AWAITING_FINALIZE) {
            return Result.success()
        }

        val file = File(state.filePath)
        if (!file.exists() || !file.isFile) {
            return fail(uploadId, "Upload file does not exist")
        }

        setForeground(createForegroundInfo(uploadId, 0, state.totalBytes, state.notificationStrings))

        return try {
            upload(uploadId, state, file, store)
            FileUploadModule.onWorkerUploadSucceeded(applicationContext, uploadId)
            Result.success()
        } catch (error: IOException) {
            if (runAttemptCount < MAX_RETRIES) {
                Result.retry()
            } else {
                fail(uploadId, error.message ?: "Upload failed")
            }
        } catch (error: Exception) {
            fail(uploadId, error.message ?: "Upload failed")
        }
    }

    private suspend fun upload(
        uploadId: String,
        state: NativeUploadState,
        file: File,
        store: UploadStateStore,
    ) {
        val connection = URL(state.url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "PUT"
            connection.setRequestProperty("Content-Type", state.contentType)
            connection.setRequestProperty("X-amz-acl", "private")
            connection.setRequestProperty("Content-Length", state.totalBytes.toString())
            connection.doOutput = true
            connection.connectTimeout = HTTP_CONNECT_TIMEOUT_MS
            connection.readTimeout = HTTP_READ_TIMEOUT_MS
            connection.setFixedLengthStreamingMode(state.totalBytes)

            var uploadedBytes = 0L
            var lastReportedBytes = 0L
            var lastReportedAtMs = 0L
            suspend fun report(force: Boolean = false) {
                val now = SystemClock.elapsedRealtime()
                if (!force &&
                    (uploadedBytes - lastReportedBytes < PROGRESS_BYTES_STEP ||
                    now - lastReportedAtMs < PROGRESS_MIN_INTERVAL_MS)
                ) {
                    return
                }
                lastReportedBytes = uploadedBytes
                lastReportedAtMs = now
                store.put(state.copy(uploadedBytes = uploadedBytes, status = UPLOADING))
                FileUploadModule.emitProgressFromWorker(
                    uploadId,
                    uploadedBytes,
                    state.totalBytes,
                )
                setForeground(
                    createForegroundInfo(
                        uploadId,
                        uploadedBytes,
                        state.totalBytes,
                        state.notificationStrings,
                    )
                )
            }

            report(force = true)
            BufferedInputStream(file.inputStream(), BUFFER_SIZE).use { input ->
                BufferedOutputStream(connection.outputStream, BUFFER_SIZE).use { output ->
                    val buffer = ByteArray(BUFFER_SIZE)
                    var read = input.read(buffer)
                    while (read >= 0) {
                        if (isStopped) throw IOException("Upload was stopped")
                        output.write(buffer, 0, read)
                        uploadedBytes += read
                        report()
                        read = input.read(buffer)
                    }
                    output.flush()
                }
            }

            val responseCode = connection.responseCode
            if (responseCode != HttpURLConnection.HTTP_OK) {
                if (responseCode == 408 || responseCode == 429 || responseCode >= 500) {
                    throw IOException("Upload returned HTTP $responseCode")
                }
                throw IllegalStateException("Upload returned HTTP $responseCode")
            }
            report(force = true)
        } finally {
            connection.disconnect()
        }
    }

    private fun fail(uploadId: String, message: String): Result {
        FileUploadModule.onWorkerUploadFailed(applicationContext, uploadId, message)
        return Result.failure(
            Data.Builder().putString(KEY_ERROR, message).build()
        )
    }

    private fun createForegroundInfo(
        uploadId: String,
        uploadedBytes: Long,
        totalBytes: Long,
        notificationStrings: UploadNotificationStrings,
    ): ForegroundInfo {
        createNotificationChannel(applicationContext, notificationStrings.channelName)
        val notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.stat_sys_upload)
            .setContentTitle(notificationStrings.uploadingTitle)
            .setContentText(
                if (totalBytes > 0) {
                    "${(uploadedBytes * 100 / totalBytes).toInt()}%"
                } else {
                    notificationStrings.uploadingIndeterminate
                }
            )
            .setProgress(
                if (totalBytes > 0) totalBytes.coerceAtMost(Int.MAX_VALUE.toLong()).toInt() else 0,
                if (totalBytes > 0) uploadedBytes.coerceAtMost(Int.MAX_VALUE.toLong()).toInt() else 0,
                totalBytes <= 0,
            )
            .setOngoing(true)
            .setCategory(Notification.CATEGORY_PROGRESS)
            .build()

        return if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q) {
            ForegroundInfo(
                notificationId(uploadId),
                notification,
                ServiceInfo.FOREGROUND_SERVICE_TYPE_DATA_SYNC,
            )
        } else {
            ForegroundInfo(notificationId(uploadId), notification)
        }
    }

    private fun createNotificationChannel(context: Context, channelName: String) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = context.getSystemService(NotificationManager::class.java)
        manager.createNotificationChannel(
            NotificationChannel(
                CHANNEL_ID,
                channelName,
                NotificationManager.IMPORTANCE_LOW,
            )
        )
    }

    companion object {
        const val KEY_UPLOAD_ID = "upload_id"
        const val KEY_ERROR = "error"
        const val UPLOADING = "uploading"
        const val UPLOADED_AWAITING_FINALIZE = "uploadedAwaitingFinalize"
        const val FAILED = "failed"
        const val CHANNEL_ID = "recording_uploads"
        const val MAX_RETRIES = 3
        const val BUFFER_SIZE = 256 * 1024
        const val PROGRESS_BYTES_STEP = 512 * 1024L
        const val PROGRESS_MIN_INTERVAL_MS = 200L
        const val HTTP_CONNECT_TIMEOUT_MS = 30_000
        const val HTTP_READ_TIMEOUT_MS = 60_000

        fun requestConstraints(wifiOnly: Boolean): Constraints = Constraints.Builder()
            .setRequiredNetworkType(
                if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
            )
            .build()

        fun notificationId(uploadId: String): Int =
            (uploadId.hashCode() and 0x7fffffff).coerceAtLeast(1)
    }
}
