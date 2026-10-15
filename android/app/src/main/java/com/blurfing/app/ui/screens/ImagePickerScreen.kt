package com.blurfing.app.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AddPhotoAlternate
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.blurfing.app.viewmodel.UiState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ImagePickerScreen(
    uiState: UiState,
    onImageSelected: (Uri?) -> Unit,
    onProceedToRegionEdit: () -> Unit,
    onReset: () -> Unit,
    onTakePhoto: () -> Unit,
    isCameraPending: Boolean = false,
    cameraError: String? = null,
    modifier: Modifier = Modifier,
    onExperimentalPhoto: (() -> Unit)? = null
) {
    val photoPickerLauncher = rememberLauncherForActivityResult(
        contract = ActivityResultContracts.PickVisualMedia()
    ) { uri: Uri? ->
        onImageSelected(uri)
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("BlurFing - 사진 선택") },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                )
            )
        },
        modifier = modifier.fillMaxSize()
    ) { paddingValues ->
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            contentAlignment = Alignment.Center
        ) {
            when (uiState) {
                is UiState.Idle -> {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                        modifier = Modifier.padding(24.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.AddPhotoAlternate,
                            contentDescription = "사진 선택 아이콘",
                            modifier = Modifier.size(80.dp),
                            tint = MaterialTheme.colorScheme.primary
                        )
                        Text(
                            text = "SNS 공유 전 손끝 지문을 보호하세요",
                            style = MaterialTheme.typography.headlineSmall,
                            fontWeight = FontWeight.Bold,
                            textAlign = TextAlign.Center
                        )
                        Text(
                            text = "사진을 촬영하거나 갤러리에서 선택하고\n직접 손끝 영역을 확인한 뒤 처리하세요.\n15MB · 2,000만 화소 이하 사진을 지원합니다.",
                            style = MaterialTheme.typography.bodyMedium,
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Spacer(modifier = Modifier.height(8.dp))
                        Button(
                            onClick = onTakePhoto,
                            enabled = !isCameraPending,
                            shape = RoundedCornerShape(12.dp),
                            contentPadding = PaddingValues(horizontal = 24.dp, vertical = 14.dp)
                        ) {
                            Text(if (isCameraPending) "촬영 결과를 기다리는 중…" else "카메라로 사진 촬영")
                        }
                        if (cameraError != null) {
                            Text(cameraError, color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
                        }
                        Button(
                            onClick = {
                                photoPickerLauncher.launch(
                                    PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                                )
                            },
                            enabled = !isCameraPending,
                            shape = RoundedCornerShape(12.dp),
                            contentPadding = PaddingValues(horizontal = 24.dp, vertical = 14.dp)
                        ) {
                            Text("갤러리에서 사진 선택")
                        }
                        onExperimentalPhoto?.let { open -> OutlinedButton(onClick=open,enabled=!isCameraPending) { Text("사진 AI 보호 실험 (미승인)") } }
                    }
                }

                is UiState.Loading -> {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp)
                    ) {
                        CircularProgressIndicator()
                        Text(
                            text = uiState.message,
                            style = MaterialTheme.typography.bodyLarge
                        )
                    }
                }

                is UiState.Ready -> {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                        modifier = Modifier.fillMaxWidth()
                    ) {
                        Card(
                            shape = RoundedCornerShape(12.dp),
                            elevation = CardDefaults.cardElevation(defaultElevation = 4.dp),
                            modifier = Modifier
                                .fillMaxWidth()
                                .weight(1f)
                        ) {
                            Box(
                                modifier = Modifier.fillMaxSize(),
                                contentAlignment = Alignment.Center
                            ) {
                                Image(
                                    bitmap = uiState.originalBitmap.asImageBitmap(),
                                    contentDescription = "선택된 사진 미리보기",
                                    modifier = Modifier.fillMaxSize()
                                )
                            }
                        }

                        Text(
                            text = "이미지 크기: ${uiState.originalBitmap.width} x ${uiState.originalBitmap.height} px",
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        onExperimentalPhoto?.let { open -> OutlinedButton(onClick=open,enabled=!isCameraPending) { Text("별도 사진 AI 보호 실험 (미승인)") } }

                        Row(
                            horizontalArrangement = Arrangement.spacedBy(12.dp),
                            modifier = Modifier.fillMaxWidth()
                        ) {
                            OutlinedButton(
                                onClick = onReset,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("다시 선택")
                            }
                            Button(
                                onClick = onProceedToRegionEdit,
                                modifier = Modifier.weight(1f)
                            ) {
                                Text("영역 확인 (BF-03)")
                            }
                        }
                    }
                }

                is UiState.Error -> {
                    Column(
                        horizontalAlignment = Alignment.CenterHorizontally,
                        verticalArrangement = Arrangement.spacedBy(16.dp),
                        modifier = Modifier.padding(24.dp)
                    ) {
                        Icon(
                            imageVector = Icons.Default.Warning,
                            contentDescription = "오류 아이콘",
                            tint = MaterialTheme.colorScheme.error,
                            modifier = Modifier.size(64.dp)
                        )
                        Text(
                            text = "오류가 발생했습니다",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.Bold,
                            color = MaterialTheme.colorScheme.error
                        )
                        Text(
                            text = uiState.message,
                            style = MaterialTheme.typography.bodyMedium,
                            textAlign = TextAlign.Center,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )
                        Button(
                            onClick = {
                                onReset()
                                photoPickerLauncher.launch(
                                    PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)
                                )
                            },
                            enabled = !isCameraPending,
                            colors = ButtonDefaults.buttonColors(containerColor = MaterialTheme.colorScheme.error)
                        ) {
                            Text("갤러리에서 다시 선택")
                        }
                        OutlinedButton(onClick = onTakePhoto, enabled = !isCameraPending) {
                            Text("카메라로 다시 촬영")
                        }
                        if (cameraError != null) {
                            Text(cameraError, color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodySmall, textAlign = TextAlign.Center)
                        }
                    }
                }
            }
        }
    }
}
