package com.blurfing.app.viewmodel

import android.content.Context
import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import kotlinx.coroutines.withContext
import java.io.InputStream

/**
 * UI State for BlurFing application workflow.
 */
sealed interface UiState {
    object Idle : UiState
    data class Loading(val message: String) : UiState
    data class ImageLoaded(
        val uri: Uri,
        val bitmap: Bitmap,
        val width: Int,
        val height: Int
    ) : UiState
    data class Error(
        val message: String,
        val cause: Throwable? = null,
        val retryable: Boolean = true
    ) : UiState
}

open class BlurFingViewModel : ViewModel() {

    private val _uiState = MutableStateFlow<UiState>(UiState.Idle)
    val uiState: StateFlow<UiState> = _uiState.asStateFlow()

    /**
     * Handles image selection from gallery / photo picker (BF-01).
     * Handles read errors, cancellation, and bitmap decoding safely.
     */
    fun onImageSelected(uri: Uri?, context: Context) {
        if (uri == null) {
            // User cancelled photo picker
            return
        }

        _uiState.value = UiState.Loading("사진을 불러오는 중...")

        viewModelScope.launch {
            try {
                val bitmap = withContext(Dispatchers.IO) {
                    val inputStream: InputStream? = context.contentResolver.openInputStream(uri)
                    requireNotNull(inputStream) { "이미지 파일을 열 수 없습니다: $uri" }
                    inputStream.use { stream ->
                        BitmapFactory.decodeStream(stream)
                    } ?: throw IllegalStateException("유효한 이미지 형식이 아닙니다.")
                }

                _uiState.value = UiState.ImageLoaded(
                    uri = uri,
                    bitmap = bitmap,
                    width = bitmap.width,
                    height = bitmap.height
                )
            } catch (e: Exception) {
                _uiState.value = UiState.Error(
                    message = "사진을 불러오지 못했습니다: ${e.localizedMessage ?: "알 수 없는 오류"}",
                    cause = e,
                    retryable = true
                )
            }
        }
    }

    fun resetToIdle() {
        _uiState.value = UiState.Idle
    }

    fun clearError() {
        if (_uiState.value is UiState.Error) {
            _uiState.value = UiState.Idle
        }
    }
}
