package fr.gouv.assistant_transcripts

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject

data class UploadNotificationStrings(
    val channelName: String = "Recording uploads",
    val uploadingTitle: String = "Uploading recording",
    val uploadingIndeterminate: String = "Uploading…",
    val completeTitle: String = "Upload complete",
    val completeBody: String = "Open the app to finish processing the recording",
    val failedTitle: String = "Upload failed",
    val failedBody: String = "Open the app to retry the recording upload",
)

data class NativeUploadState(
    val uploadId: String,
    val filePath: String,
    val url: String,
    val contentType: String,
    val acl: String?,
    val totalBytes: Long,
    val uploadedBytes: Long,
    val wifiOnly: Boolean,
    val status: String,
    val error: String? = null,
    val notificationStrings: UploadNotificationStrings = UploadNotificationStrings(),
)

class UploadStateStore(context: Context) {
    private val preferences = context.getSharedPreferences(PREFERENCES_NAME, Context.MODE_PRIVATE)

    @Synchronized
    fun get(uploadId: String): NativeUploadState? = all().firstOrNull { it.uploadId == uploadId }

    @Synchronized
    fun all(): List<NativeUploadState> {
        val raw = preferences.getString(UPLOADS_KEY, "[]") ?: "[]"
        val json = try {
            JSONArray(raw)
        } catch (_: Exception) {
            JSONArray()
        }

        return buildList {
            for (index in 0 until json.length()) {
                val item = json.optJSONObject(index) ?: continue
                val uploadId = item.optString("uploadId")
                if (uploadId.isEmpty()) continue
                add(
                    NativeUploadState(
                        uploadId = uploadId,
                        filePath = item.optString("filePath"),
                        url = item.optString("url"),
                        contentType = item.optString("contentType"),
                        acl = when {
                            !item.has("acl") -> "private"
                            item.isNull("acl") -> null
                            else -> item.optString("acl")
                        },
                        totalBytes = item.optLong("totalBytes"),
                        uploadedBytes = item.optLong("uploadedBytes"),
                        wifiOnly = item.optBoolean("wifiOnly"),
                        status = item.optString("status"),
                        error = item.optString("error").takeIf { it.isNotEmpty() },
                        notificationStrings = notificationStringsFrom(item),
                    )
                )
            }
        }
    }

    @Synchronized
    fun put(state: NativeUploadState) {
        val states = all().filterNot { it.uploadId == state.uploadId } + state
        val json = JSONArray()
        states.forEach { item ->
            json.put(stateToJson(item))
        }
        preferences.edit().putString(UPLOADS_KEY, json.toString()).apply()
    }

    /**
     * Persists transfer progress without clobbering fields a concurrent caller may have
     * refreshed (notification strings, wifiOnly…). Cheap enough to call periodically.
     */
    @Synchronized
    fun updateProgress(uploadId: String, uploadedBytes: Long, status: String) {
        val state = get(uploadId) ?: return
        put(state.copy(uploadedBytes = uploadedBytes, status = status))
    }

    @Synchronized
    fun remove(uploadId: String) {
        val states = all().filterNot { it.uploadId == uploadId }
        val json = JSONArray()
        states.forEach { item ->
            json.put(stateToJson(item))
        }
        preferences.edit().putString(UPLOADS_KEY, json.toString()).apply()
    }

    private fun stateToJson(item: NativeUploadState): JSONObject {
        return JSONObject().apply {
            put("uploadId", item.uploadId)
            put("filePath", item.filePath)
            put("url", item.url)
            put("contentType", item.contentType)
            put("acl", item.acl ?: JSONObject.NULL)
            put("totalBytes", item.totalBytes)
            put("uploadedBytes", item.uploadedBytes)
            put("wifiOnly", item.wifiOnly)
            put("status", item.status)
            put("error", item.error ?: "")
            put("notificationStrings", JSONObject().apply {
                put("channelName", item.notificationStrings.channelName)
                put("uploadingTitle", item.notificationStrings.uploadingTitle)
                put("uploadingIndeterminate", item.notificationStrings.uploadingIndeterminate)
                put("completeTitle", item.notificationStrings.completeTitle)
                put("completeBody", item.notificationStrings.completeBody)
                put("failedTitle", item.notificationStrings.failedTitle)
                put("failedBody", item.notificationStrings.failedBody)
            })
        }
    }

    private fun notificationStringsFrom(item: JSONObject): UploadNotificationStrings {
        val json = item.optJSONObject("notificationStrings")
        val defaults = UploadNotificationStrings()
        return UploadNotificationStrings(
            channelName = json?.optString("channelName")?.takeIf { it.isNotEmpty() }
                ?: defaults.channelName,
            uploadingTitle = json?.optString("uploadingTitle")?.takeIf { it.isNotEmpty() }
                ?: defaults.uploadingTitle,
            uploadingIndeterminate = json?.optString("uploadingIndeterminate")
                ?.takeIf { it.isNotEmpty() } ?: defaults.uploadingIndeterminate,
            completeTitle = json?.optString("completeTitle")?.takeIf { it.isNotEmpty() }
                ?: defaults.completeTitle,
            completeBody = json?.optString("completeBody")?.takeIf { it.isNotEmpty() }
                ?: defaults.completeBody,
            failedTitle = json?.optString("failedTitle")?.takeIf { it.isNotEmpty() }
                ?: defaults.failedTitle,
            failedBody = json?.optString("failedBody")?.takeIf { it.isNotEmpty() }
                ?: defaults.failedBody,
        )
    }

    fun isAppActive(): Boolean = preferences.getBoolean(APP_ACTIVE_KEY, true)

    fun setAppActive(active: Boolean) {
        preferences.edit().putBoolean(APP_ACTIVE_KEY, active).apply()
    }

    companion object {
        private const val PREFERENCES_NAME = "background_uploads"
        private const val UPLOADS_KEY = "uploads"
        private const val APP_ACTIVE_KEY = "app_active"
    }
}
