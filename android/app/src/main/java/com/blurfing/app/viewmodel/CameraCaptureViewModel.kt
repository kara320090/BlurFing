package com.blurfing.app.viewmodel

import android.app.Application
import android.content.ActivityNotFoundException
import android.content.Context
import android.net.Uri
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.SavedStateHandle
import com.blurfing.app.utils.CameraCaptureFiles
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow

/** Only the pending output URI is restored; image pixels never go into a saved-state Bundle. */
class CameraCaptureViewModel @JvmOverloads constructor(
    application: Application,
    private val savedState: SavedStateHandle,
    private val createOutput: (Context) -> Uri = { CameraCaptureFiles.create(it) }
) : AndroidViewModel(application) {
    private val context get() = getApplication<Application>()
    val pendingUri = savedState.getStateFlow<String?>(PENDING_URI, null)
    private val _error = MutableStateFlow<String?>(null)
    val error = _error.asStateFlow()

    init {
        CameraCaptureFiles.removeExpired(context, pendingUri.value?.let(Uri::parse))
    }

    fun beginCapture(): Uri? {
        if (pendingUri.value != null) return null
        _error.value = null
        return try {
            createOutput(context).also { savedState[PENDING_URI] = it.toString() }
        } catch (_: Exception) {
            _error.value = "촬영을 준비하지 못했습니다. 저장 공간을 확인하고 다시 시도해 주세요."
            null
        }
    }

    fun completeCapture(success: Boolean): Uri? {
        val uri = takePending() ?: return null
        if (!success) {
            CameraCaptureFiles.discard(context, uri)
            return null
        }
        if (!CameraCaptureFiles.hasOutput(context, uri)) {
            CameraCaptureFiles.discard(context, uri)
            _error.value = "촬영된 사진을 찾을 수 없습니다. 다시 촬영해 주세요."
            return null
        }
        CameraCaptureFiles.revoke(context, uri)
        // The importer now owns cleanup, after it has read and normalized the image.
        return uri
    }

    fun launchFailed(cause: Exception) {
        takePending()?.let { CameraCaptureFiles.discard(context, it) }
        _error.value = if (cause is ActivityNotFoundException)
            "사용할 수 있는 카메라 앱이 없습니다. 갤러리에서 사진을 선택해 주세요."
        else "카메라를 열지 못했습니다. 다시 시도하거나 갤러리에서 사진을 선택해 주세요."
    }

    fun clearError() { _error.value = null }

    private fun takePending(): Uri? {
        val value = pendingUri.value ?: return null
        savedState[PENDING_URI] = null
        return Uri.parse(value)
    }

    override fun onCleared() {
        takePending()?.let { CameraCaptureFiles.discard(context, it) }
        super.onCleared()
    }

    companion object {
        private const val PENDING_URI = "pending_camera_uri"
    }
}
