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
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.cancelAndJoin
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.util.concurrent.atomic.AtomicLong

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

        // Created once: this is a binder call, and it never changes during a transfer.
        createNotificationChannel(state.notificationStrings.channelName)
        // Promoting the worker to foreground is also a round trip through WorkManager and
        // ActivityManager, so it happens once here. Later progress updates go straight to
        // NotificationManager with the same id, which updates the same notification in place.
        setForeground(createForegroundInfo(uploadId, 0, state.totalBytes, state.notificationStrings))

        return try {
            upload(uploadId, state, file, store)
            FileUploadModule.onWorkerUploadSucceeded(applicationContext, uploadId)
            Result.success()
        } catch (error: CancellationException) {
            // A replacement or explicit cancellation is not an upload failure. In particular,
            // changing from Wi-Fi-only to any network replaces the waiting work request.
            throw error
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

    /**
     * Runs the transfer on [Dispatchers.IO] with a sibling coroutine sampling progress, so that
     * nothing on the reporting path (preferences, JS bridge, notifications) can stall the socket
     * writes. The writer only ever touches the streams and [progress].
     */
    private suspend fun upload(
        uploadId: String,
        state: NativeUploadState,
        file: File,
        store: UploadStateStore,
    ) = coroutineScope {
        val progress = AtomicLong(0)
        val reporter = launch(Dispatchers.IO) { reportProgress(uploadId, state, store, progress) }
        try {
            withContext(Dispatchers.IO) { transfer(state, file, progress) }
        } finally {
            reporter.cancelAndJoin()
        }
        // The success path (FileUploadModule.onWorkerUploadSucceeded) persists the final
        // byte count and emits the terminal progress event, so no last report is needed here.
    }

    /**
     * Blocking writer. Deliberately free of suspension points and IPC: the only work between two
     * socket writes is a file read and an atomic add.
     */
    private fun transfer(state: NativeUploadState, file: File, progress: AtomicLong) {
        val connection = URL(state.url).openConnection() as HttpURLConnection
        try {
            connection.requestMethod = "PUT"
            connection.setRequestProperty("Content-Type", state.contentType)
            state.acl?.let { connection.setRequestProperty("X-amz-acl", it) }
            connection.setRequestProperty("Content-Length", state.totalBytes.toString())
            connection.doOutput = true
            connection.connectTimeout = HTTP_CONNECT_TIMEOUT_MS
            connection.readTimeout = HTTP_READ_TIMEOUT_MS
            connection.setFixedLengthStreamingMode(state.totalBytes)

            // No Buffered* wrappers: chunks are already large enough that they bypass the
            // buffer and would only add a copy.
            file.inputStream().use { input ->
                connection.outputStream.use { output ->
                    val buffer = ByteArray(UPLOAD_CHUNK_SIZE)
                    while (true) {
                        if (isStopped) throw IOException("Upload was stopped")
                        val read = input.read(buffer)
                        if (read < 0) break
                        output.write(buffer, 0, read)
                        progress.addAndGet(read.toLong())
                    }
                    output.flush()
                }
            }

            val responseCode = connection.responseCode
            if (responseCode != HttpURLConnection.HTTP_OK) {
                val responseBody = runCatching {
                    connection.errorStream?.bufferedReader()?.use { it.readText() }
                }.getOrNull()

                val responseDetails =
                    if (!responseBody.isNullOrBlank()) ": $responseBody" else ""

                if (responseCode == 408 || responseCode == 429 || responseCode >= 500) {
                    throw IOException("Upload returned HTTP $responseCode - $responseDetails")
                }
                throw IllegalStateException("Upload returned HTTP $responseCode - $responseDetails")
            }
        } finally {
            connection.disconnect()
        }
    }

    /** Samples [progress] until cancelled. Never touched by the writer. */
    private suspend fun reportProgress(
        uploadId: String,
        state: NativeUploadState,
        store: UploadStateStore,
        progress: AtomicLong,
    ) {
        var lastReportedBytes = -1L
        var lastNotifiedPercent = -1
        var lastPersistedAtMs = SystemClock.elapsedRealtime()

        while (true) {
            delay(PROGRESS_TICK_MS)

            val uploadedBytes = progress.get()
            if (uploadedBytes == lastReportedBytes) continue
            lastReportedBytes = uploadedBytes

            FileUploadModule.emitProgressFromWorker(uploadId, uploadedBytes, state.totalBytes)

            val percent = percentOf(uploadedBytes, state.totalBytes)
            if (percent != lastNotifiedPercent) {
                lastNotifiedPercent = percent
                notifyProgress(uploadId, uploadedBytes, state.totalBytes, state.notificationStrings)
            }

            // Only needed so a killed process can report progress on restart, so it is kept
            // well away from the per-tick path.
            val now = SystemClock.elapsedRealtime()
            if (now - lastPersistedAtMs >= PERSIST_INTERVAL_MS) {
                lastPersistedAtMs = now
                store.updateProgress(uploadId, uploadedBytes, UPLOADING)
            }
        }
    }

    private fun fail(uploadId: String, message: String): Result {
        FileUploadModule.onWorkerUploadFailed(applicationContext, uploadId, message)
        return Result.failure(
            Data.Builder().putString(KEY_ERROR, message).build()
        )
    }

    /** Updates the foreground notification in place, without going through WorkManager. */
    private fun notifyProgress(
        uploadId: String,
        uploadedBytes: Long,
        totalBytes: Long,
        notificationStrings: UploadNotificationStrings,
    ) {
        applicationContext
            .getSystemService(NotificationManager::class.java)
            .notify(
                notificationId(uploadId),
                buildProgressNotification(uploadedBytes, totalBytes, notificationStrings),
            )
    }

    private fun createForegroundInfo(
        uploadId: String,
        uploadedBytes: Long,
        totalBytes: Long,
        notificationStrings: UploadNotificationStrings,
    ): ForegroundInfo {
        val notification = buildProgressNotification(uploadedBytes, totalBytes, notificationStrings)

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

    private fun buildProgressNotification(
        uploadedBytes: Long,
        totalBytes: Long,
        notificationStrings: UploadNotificationStrings,
    ): Notification = NotificationCompat.Builder(applicationContext, CHANNEL_ID)
        .setSmallIcon(android.R.drawable.stat_sys_upload)
        .setContentTitle(notificationStrings.uploadingTitle)
        .setContentText(
            if (totalBytes > 0) {
                "${percentOf(uploadedBytes, totalBytes)}%"
            } else {
                notificationStrings.uploadingIndeterminate
            }
        )
        .setProgress(
            if (totalBytes > 0) 100 else 0,
            if (totalBytes > 0) percentOf(uploadedBytes, totalBytes) else 0,
            totalBytes <= 0,
        )
        .setOngoing(true)
        .setOnlyAlertOnce(true)
        .setCategory(Notification.CATEGORY_PROGRESS)
        .build()

    private fun createNotificationChannel(channelName: String) {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        applicationContext.getSystemService(NotificationManager::class.java)
            .createNotificationChannel(
                NotificationChannel(
                    CHANNEL_ID,
                    channelName,
                    NotificationManager.IMPORTANCE_LOW,
                )
            )
    }

    companion object {
        private const val TAG = "FileUploadWorker"
        const val KEY_UPLOAD_ID = "upload_id"
        const val KEY_ERROR = "error"
        const val UPLOADING = "uploading"
        const val UPLOADED_AWAITING_FINALIZE = "uploadedAwaitingFinalize"
        const val FAILED = "failed"
        const val CHANNEL_ID = "recording_uploads"
        const val MAX_RETRIES = 2

        /**
         * Small enough that a single write on a slow mobile link cannot freeze progress for
         * seconds, large enough to keep syscall overhead irrelevant.
         */
        const val UPLOAD_CHUNK_SIZE = 64 * 1024
        const val PROGRESS_TICK_MS = 150L
        const val PERSIST_INTERVAL_MS = 2_500L
        const val HTTP_CONNECT_TIMEOUT_MS = 30_000
        const val HTTP_READ_TIMEOUT_MS = 60_000

        fun requestConstraints(wifiOnly: Boolean): Constraints = Constraints.Builder()
            .setRequiredNetworkType(
                if (wifiOnly) NetworkType.UNMETERED else NetworkType.CONNECTED
            )
            .build()

        fun notificationId(uploadId: String): Int =
            (uploadId.hashCode() and 0x7fffffff).coerceAtLeast(1)

        private fun percentOf(uploadedBytes: Long, totalBytes: Long): Int =
            if (totalBytes > 0) (uploadedBytes * 100 / totalBytes).toInt() else 0
    }
}
