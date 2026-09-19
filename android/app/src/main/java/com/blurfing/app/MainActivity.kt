package com.blurfing.app

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.viewModels
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Modifier
import com.blurfing.app.ui.screens.ImagePickerScreen
import com.blurfing.app.ui.theme.BlurFingTheme
import com.blurfing.app.viewmodel.BlurFingViewModel

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
                    ImagePickerScreen(
                        uiState = uiState,
                        onImageSelected = { uri -> viewModel.onImageSelected(uri, this) },
                        onProceedToRegionEdit = { /* Will connect in BF-03 */ },
                        onReset = { viewModel.resetToIdle() }
                    )
                }
            }
        }
    }
}
