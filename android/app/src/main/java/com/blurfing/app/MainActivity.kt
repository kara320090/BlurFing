package com.blurfing.app

import android.Manifest
import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.core.app.ActivityCompat
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory
import com.blurfing.app.model.ProcessingSettingsStore
import com.blurfing.app.utils.DraftSession
import com.blurfing.app.ui.screens.ComparisonScreen
import com.blurfing.app.ui.screens.ImagePickerScreen
import com.blurfing.app.ui.screens.ProcessingScreen
import com.blurfing.app.ui.screens.RegionEditorScreen
import com.blurfing.app.ui.theme.BlurFingTheme
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.CameraCaptureViewModel
import com.blurfing.app.utils.CameraCaptureContract
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState

class MainActivity : ComponentActivity() {

    private val viewModel: BlurFingViewModel by viewModels {
        viewModelFactory {
            initializer {
                BlurFingViewModel(draftSession = DraftSession(application, createSavedStateHandle()),
                    settingsStore = ProcessingSettingsStore(application))
            }
        }
    }
    private val cameraViewModel: CameraCaptureViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            BlurFingTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val uiState by viewModel.uiState.collectAsState()
                    val processingSettings by viewModel.settings.collectAsState()
                    val context = LocalContext.current
                    val pendingCameraUri by cameraViewModel.pendingUri.collectAsState()
                    val cameraError by cameraViewModel.error.collectAsState()
                    // Register independently of the current screen so a restored camera result is delivered.
                    val cameraLauncher = rememberLauncherForActivityResult(CameraCaptureContract()) { success ->
                        cameraViewModel.completeCapture(success)?.let { uri ->
                            viewModel.onCameraImageCaptured(uri, context)
                        }
                    }
                    val takePhoto: () -> Unit = {
                        cameraViewModel.beginCapture()?.let { uri ->
                            viewModel.clearError()
                            try {
                                cameraLauncher.launch(uri)
                            } catch (error: Exception) {
                                cameraViewModel.launchFailed(error)
                            }
                        }
                    }
                    // Keep the launched request ID across Activity recreation; never apply an old grant to a new photo.
                    var savePermissionRequestId by rememberSaveable { mutableStateOf<String?>(null) }
                    var showPermissionRationale by rememberSaveable { mutableStateOf(false) }
                    val completeSavePermission: (Boolean) -> Unit = { granted ->
                        val requestId = savePermissionRequestId
                        savePermissionRequestId = null
                        showPermissionRationale = false
                        requestId?.let { viewModel.onSavePermissionResult(context, it, granted) }
                    }
                    val savePermissionLauncher = rememberLauncherForActivityResult(
                        ActivityResultContracts.RequestPermission()
                    ) { granted -> completeSavePermission(granted) }
                    val launchSavePermission = {
                        showPermissionRationale = false
                        try {
                            savePermissionLauncher.launch(Manifest.permission.WRITE_EXTERNAL_STORAGE)
                        } catch (_: IllegalStateException) {
                            completeSavePermission(false)
                        }
                    }

                    if (showPermissionRationale) {
                        AlertDialog(
                            onDismissRequest = { completeSavePermission(false) },
                            title = { Text("보호 사본 저장 권한") },
                            text = { Text("보호 사본을 갤러리에 저장하려면 저장 공간 접근 권한이 필요합니다. 허용하지 않아도 사진 편집과 비교는 계속 이용할 수 있습니다.") },
                            confirmButton = { TextButton(onClick = launchSavePermission) { Text("계속") } },
                            dismissButton = { TextButton(onClick = { completeSavePermission(false) }) { Text("취소") } }
                        )
                    }

                    when (val state = uiState) {
                        is UiState.Ready -> {
                            LaunchedEffect(state.saveMessage) {
                                state.saveMessage?.let { msg ->
                                    Toast.makeText(context, msg, Toast.LENGTH_LONG).show()
                                }
                            }

                            when (state.step) {
                                ScreenStep.IMAGE_PICKER -> {
                                    ImagePickerScreen(
                                        uiState = state,
                                        onImageSelected = { uri ->
                                            cameraViewModel.clearError()
                                            viewModel.onImageSelected(uri, context)
                                        },
                                        onTakePhoto = takePhoto,
                                        isCameraPending = pendingCameraUri != null,
                                        cameraError = cameraError,
                                        onProceedToRegionEdit = { viewModel.navigateToStep(ScreenStep.REGION_EDITOR) },
                                        onReset = { viewModel.resetToIdle() }
                                    )
                                }
                                ScreenStep.REGION_EDITOR -> {
                                    RegionEditorScreen(
                                        bitmap = state.originalBitmap,
                                        regions = state.regions,
                                        sessionNotice = state.sessionNotice,
                                        onAddRegion = { viewModel.addRegion() },
                                        onDeleteRegion = { index -> viewModel.deleteRegion(index) },
                                        onUpdateRegion = { index, region -> viewModel.updateRegion(index, region) },
                                        canUndo = state.canUndoRegions,
                                        canRedo = state.canRedoRegions,
                                        onUndo = viewModel::undoRegions,
                                        onRedo = viewModel::redoRegions,
                                        onClearRegions = viewModel::clearRegions,
                                        onProceedToSettings = { viewModel.navigateToStep(ScreenStep.PROCESSING) },
                                        onBack = { viewModel.resetToIdle() }
                                    )
                                }
                                ScreenStep.PROCESSING -> {
                                    ProcessingScreen(
                                        isProcessing = state.isProcessing,
                                        settings = processingSettings,
                                        onSettingsChanged = viewModel::updateSettings,
                                        onStartProcessing = { method, strength, serverUrl ->
                                            viewModel.startProtection(method, strength, serverUrl)
                                        },
                                        processingError = state.processingError,
                                        onCancelProcessing = { viewModel.cancelProtection() },
                                        onBack = { viewModel.navigateToStep(ScreenStep.REGION_EDITOR) }
                                    )
                                }
                                ScreenStep.COMPARISON -> {
                                    ComparisonScreen(
                                        originalBitmap = state.originalBitmap,
                                        protectedBitmap = state.protectedBitmap ?: state.originalBitmap,
                                        response = state.protectionResponse,
                                        regions = state.protectionResponse?.appliedRegions ?: state.regions,
                                        isSaving = state.isSaving,
                                        isAwaitingSavePermission = state.savePermissionRequestId != null,
                                        saveError = state.saveError,
                                        onSaveProtectedImage = {
                                            if (savePermissionRequestId == null) {
                                                viewModel.saveProtectedImage(context)?.let { requestId ->
                                                    savePermissionRequestId = requestId
                                                    if (ActivityCompat.shouldShowRequestPermissionRationale(
                                                            this@MainActivity, Manifest.permission.WRITE_EXTERNAL_STORAGE)) {
                                                        showPermissionRationale = true
                                                    } else {
                                                        launchSavePermission()
                                                    }
                                                }
                                            }
                                        },
                                        onBack = { viewModel.navigateToStep(ScreenStep.REGION_EDITOR) }
                                    )
                                }
                            }
                        }
                        else -> {
                            ImagePickerScreen(
                                uiState = state,
                                onImageSelected = { uri ->
                                    cameraViewModel.clearError()
                                    viewModel.onImageSelected(uri, context)
                                },
                                onTakePhoto = takePhoto,
                                isCameraPending = pendingCameraUri != null,
                                cameraError = cameraError,
                                onProceedToRegionEdit = { viewModel.navigateToStep(ScreenStep.REGION_EDITOR) },
                                onReset = { viewModel.resetToIdle() }
                            )
                        }
                    }
                }
            }
        }
    }
}
