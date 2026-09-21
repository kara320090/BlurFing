package com.blurfing.app

import android.os.Bundle
import android.widget.Toast
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import com.blurfing.app.ui.screens.ComparisonScreen
import com.blurfing.app.ui.screens.ImagePickerScreen
import com.blurfing.app.ui.screens.ProcessingScreen
import com.blurfing.app.ui.screens.RegionEditorScreen
import com.blurfing.app.ui.theme.BlurFingTheme
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState

class MainActivity : ComponentActivity() {

    private val viewModel: BlurFingViewModel by viewModels()

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            BlurFingTheme {
                Surface(
                    modifier = Modifier.fillMaxSize(),
                    color = MaterialTheme.colorScheme.background
                ) {
                    val uiState by viewModel.uiState.collectAsState()
                    val context = LocalContext.current

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
                                        onImageSelected = { uri -> viewModel.onImageSelected(uri, context) },
                                        onProceedToRegionEdit = { viewModel.navigateToStep(ScreenStep.REGION_EDITOR) },
                                        onReset = { viewModel.resetToIdle() }
                                    )
                                }
                                ScreenStep.REGION_EDITOR -> {
                                    RegionEditorScreen(
                                        bitmap = state.originalBitmap,
                                        regions = state.regions,
                                        onAddRegion = { viewModel.addRegion() },
                                        onDeleteRegion = { index -> viewModel.deleteRegion(index) },
                                        onUpdateRegion = { index, region -> viewModel.updateRegion(index, region) },
                                        onProceedToSettings = { viewModel.navigateToStep(ScreenStep.PROCESSING) },
                                        onBack = { viewModel.resetToIdle() }
                                    )
                                }
                                ScreenStep.PROCESSING -> {
                                    ProcessingScreen(
                                        isProcessing = state.isProcessing,
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
                                        onSaveProtectedImage = { viewModel.saveProtectedImage(context) },
                                        onBack = { viewModel.navigateToStep(ScreenStep.REGION_EDITOR) }
                                    )
                                }
                            }
                        }
                        else -> {
                            ImagePickerScreen(
                                uiState = state,
                                onImageSelected = { uri -> viewModel.onImageSelected(uri, context) },
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
