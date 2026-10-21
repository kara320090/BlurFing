package com.blurfing.app.ui.screens

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CameraAlt
import androidx.compose.material.icons.filled.Fingerprint
import androidx.compose.material.icons.filled.PhotoLibrary
import androidx.compose.material.icons.filled.Warning
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.blurfing.app.ui.components.BrandTopBar
import com.blurfing.app.ui.components.InfoBanner
import com.blurfing.app.ui.components.SectionCard
import com.blurfing.app.ui.components.WorkflowSteps
import com.blurfing.app.viewmodel.UiState

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
    val picker = rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia(), onImageSelected)
    val choose = { picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly)) }
    Scaffold(topBar = { BrandTopBar() }, modifier = modifier.fillMaxSize(),
        containerColor = MaterialTheme.colorScheme.background) { padding ->
        Box(Modifier.fillMaxSize().padding(padding).padding(horizontal = 20.dp), contentAlignment = Alignment.TopCenter) {
            when (uiState) {
                is UiState.Idle -> Column(
                    Modifier.widthIn(max = 600.dp).fillMaxWidth().verticalScroll(rememberScrollState()).padding(bottom = 24.dp),
                    verticalArrangement = Arrangement.spacedBy(18.dp)
                ) {
                    WorkflowSteps(0)
                    Surface(shape = RoundedCornerShape(26.dp), color = MaterialTheme.colorScheme.primaryContainer) {
                        Column(Modifier.padding(22.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
                            Text("사진 속 손끝을 위한 작은 변화", style = MaterialTheme.typography.labelMedium,
                                color = MaterialTheme.colorScheme.onPrimaryContainer)
                            Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
                                Text("공유하기 전,\n손끝을 한 번 더.", modifier = Modifier.weight(1f),
                                    style = MaterialTheme.typography.headlineMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                                Icon(Icons.Default.Fingerprint, null, Modifier.size(66.dp),
                                    tint = MaterialTheme.colorScheme.primary)
                            }
                            Text("사진의 손끝 영역을 확인하고, 처리 전후를 비교해 보세요.",
                                style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onPrimaryContainer)
                        }
                    }
                    onExperimentalPhoto?.let { open ->
                        Button(onClick = open, enabled = !isCameraPending,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 56.dp).testTag("open_automatic_photo"),
                            shape = RoundedCornerShape(16.dp), contentPadding = PaddingValues(16.dp)) {
                            Icon(Icons.Default.Fingerprint, null, Modifier.size(21.dp)); Spacer(Modifier.width(10.dp))
                            Text("자동 처리 시작")
                        }
                        InfoBanner("자동 처리는 실험 기능입니다. 미검출·거절 영역에는 원본 지문이 남을 수 있어요.", caution = true)
                    }
                    SectionCard(title = if (onExperimentalPhoto != null) "직접 영역을 지정하려면" else "사진을 가져오세요") {
                        Text("촬영하거나 갤러리에서 사진을 골라 손끝 영역을 확인하세요.",
                            style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        OutlinedButton(onClick = onTakePhoto, enabled = !isCameraPending,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp), shape = RoundedCornerShape(14.dp)) {
                            Icon(Icons.Default.CameraAlt, null, Modifier.size(20.dp)); Spacer(Modifier.width(10.dp))
                            Text(if (isCameraPending) "촬영 결과를 기다리는 중…" else "카메라로 사진 촬영")
                        }
                        OutlinedButton(onClick = choose, enabled = !isCameraPending,
                            modifier = Modifier.fillMaxWidth().heightIn(min = 50.dp), shape = RoundedCornerShape(14.dp)) {
                            Icon(Icons.Default.PhotoLibrary, null, Modifier.size(20.dp)); Spacer(Modifier.width(10.dp))
                            Text("갤러리에서 사진 선택")
                        }
                        cameraError?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                    }
                    Text("15MB · 2,000만 화소 이하  /  원본과 별도 사본 저장",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.fillMaxWidth(), textAlign = TextAlign.Center)
                }
                is UiState.Loading -> Column(Modifier.fillMaxSize(), horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center) {
                    CircularProgressIndicator(); Spacer(Modifier.height(20.dp))
                    Text(uiState.message, style = MaterialTheme.typography.bodyLarge)
                }
                is UiState.Ready -> Column(Modifier.fillMaxSize().padding(bottom = 20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp)) {
                    WorkflowSteps(0)
                    Text("사진이 준비됐어요", style = MaterialTheme.typography.headlineSmall)
                    Card(shape = RoundedCornerShape(22.dp), colors = CardDefaults.cardColors(containerColor = MaterialTheme.colorScheme.surface),
                        modifier = Modifier.fillMaxWidth().weight(1f)) {
                        Image(uiState.originalBitmap.asImageBitmap(), "선택된 사진 미리보기", Modifier.fillMaxSize().padding(10.dp))
                    }
                    Text("이미지 크기: " + uiState.originalBitmap.width + " × " + uiState.originalBitmap.height + " px",
                        style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    onExperimentalPhoto?.let { open ->
                        TextButton(onClick = open, enabled = !isCameraPending) { Text("자동 처리로 열기") }
                    }
                    Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                        OutlinedButton(onClick = onReset, modifier = Modifier.weight(1f).heightIn(min = 50.dp)) { Text("다시 선택") }
                        Button(onClick = onProceedToRegionEdit, modifier = Modifier.weight(1f).heightIn(min = 50.dp)) { Text("영역 확인") }
                    }
                }
                is UiState.Error -> Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(top = 30.dp),
                    verticalArrangement = Arrangement.spacedBy(18.dp), horizontalAlignment = Alignment.CenterHorizontally) {
                    Icon(Icons.Default.Warning, "오류 아이콘", Modifier.size(50.dp), tint = MaterialTheme.colorScheme.error)
                    Text("사진을 불러오지 못했어요", style = MaterialTheme.typography.titleLarge)
                    Text(uiState.message, color = MaterialTheme.colorScheme.onSurfaceVariant, textAlign = TextAlign.Center)
                    Button(onClick = { onReset(); choose() }, enabled = !isCameraPending,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("갤러리에서 다시 선택") }
                    OutlinedButton(onClick = onTakePhoto, enabled = !isCameraPending,
                        modifier = Modifier.fillMaxWidth().heightIn(min = 52.dp)) { Text("카메라로 다시 촬영") }
                    cameraError?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
                }
            }
        }
    }
}
