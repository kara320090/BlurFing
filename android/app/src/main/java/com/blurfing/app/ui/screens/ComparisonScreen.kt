package com.blurfing.app.ui.screens

import android.graphics.Bitmap
import androidx.compose.foundation.Canvas
import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.IntOffset
import androidx.compose.ui.unit.IntSize
import androidx.compose.ui.unit.dp
import com.blurfing.app.model.EvaluationPresentation
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.model.ExportFormat
import com.blurfing.app.model.ProcessingTiming
import com.blurfing.app.utils.ComparisonCrop
import java.util.Locale
import kotlin.math.min
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ComparisonScreen(
    originalBitmap: Bitmap,
    protectedBitmap: Bitmap,
    response: ProtectionResponse?,
    onSaveProtectedImage: () -> Unit,
    onBack: () -> Unit,
    isSaving: Boolean = false,
    isAwaitingSavePermission: Boolean = false,
    saveError: String? = null,
    modifier: Modifier = Modifier,
    regions: List<NormalizedRegion> = response?.appliedRegions.orEmpty(),
    settings: ProcessingSettings = ProcessingSettings(),
    onSettingsChanged: (ProcessingSettings) -> Unit = {},
    onShare: () -> Unit = {},
    isSharing: Boolean = false,
    shareError: String? = null,
    processingTiming: ProcessingTiming? = null,
    onExportDiagnostics: () -> Unit = {},
    isDiagnosticPending: Boolean = false
) {
    var showProtectedOnly by rememberSaveable(response?.requestId) { mutableStateOf(true) }
    var sideBySide by rememberSaveable(response?.requestId) { mutableStateOf(false) }
    var selectedRegion by rememberSaveable(response?.requestId) { mutableIntStateOf(-1) }
    var zoom by rememberSaveable(response?.requestId) { mutableFloatStateOf(1f) }
    val crop = remember(originalBitmap, regions, selectedRegion, zoom) {
        ComparisonCrop.calculate(originalBitmap.width, originalBitmap.height, regions.getOrNull(selectedRegion), zoom)
    }
    val evaluation = remember(response) { EvaluationPresentation.from(response) }

    Scaffold(topBar = {
        TopAppBar(title = { Text("전후 비교 및 저장") }, navigationIcon = {
            IconButton(onClick = onBack) { Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "뒤로가기") }
        })
    }, modifier = modifier.fillMaxSize()) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = !sideBySide, onClick = { sideBySide = false }, label = { Text("한 장씩") })
                FilterChip(selected = sideBySide, onClick = { sideBySide = true }, label = { Text("나란히 비교") })
            }
            if (!sideBySide) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                    Text(if (showProtectedOnly) "처리본 표시 중" else "원본 표시 중")
                    TextButton(onClick = { showProtectedOnly = !showProtectedOnly }) {
                        Text(if (showProtectedOnly) "원본 보기" else "보호본 보기")
                    }
                }
            }
            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),
                horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                FilterChip(selected = selectedRegion == -1, onClick = { selectedRegion = -1; zoom = 1f }, label = { Text("전체") })
                regions.forEachIndexed { index, _ ->
                    FilterChip(selected = selectedRegion == index, onClick = { selectedRegion = index; zoom = 1f },
                        label = { Text("영역 ${index + 1}") })
                }
            }
            if (sideBySide) {
                Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    Column(Modifier.weight(1f)) {
                        Text("원본")
                        CroppedPhoto(originalBitmap, crop, "원본 이미지", Modifier.fillMaxWidth().height(300.dp))
                    }
                    Column(Modifier.weight(1f)) {
                        Text("처리본")
                        CroppedPhoto(protectedBitmap, crop, "보호본 이미지", Modifier.fillMaxWidth().height(300.dp))
                    }
                }
            } else {
                CroppedPhoto(if (showProtectedOnly) protectedBitmap else originalBitmap, crop,
                    if (showProtectedOnly) "보호본 이미지" else "원본 이미지", Modifier.fillMaxWidth().height(300.dp))
            }
            Text("${if (selectedRegion < 0) "전체 사진" else "영역 ${selectedRegion + 1}"} · 추가 확대 ${String.format(Locale.ROOT, "%.1f", zoom)}배")
            Slider(value = zoom, onValueChange = { zoom = it }, valueRange = 1f..4f,
                modifier = Modifier.semantics { contentDescription = "비교 확대 배율" })
            Text("양쪽 사진에 같은 영역과 배율을 적용합니다. 저장되는 사본의 크기는 바뀌지 않습니다.",
                style = MaterialTheme.typography.bodySmall)
            if (response?.resultKind == "mock") {
                Text("[Mock 결과] UI 확인용 프리뷰이며 실제 AI 보호 성능을 나타내지 않습니다.",
                    style = MaterialTheme.typography.bodySmall)
            } else if (response?.resultKind == "real") {
                Text("서버 처리 이미지 · 보호 성능은 아래 측정 자료와 별도로 확인하세요.", style = MaterialTheme.typography.bodySmall)
            }
            response?.processingMs?.takeIf { it >= 0 }?.let {
                Text(if (response.resultKind == "mock") "Mock 보고 지연 시간: ${it}ms" else "서버 보고 처리 시간: ${it}ms",
                    style = MaterialTheme.typography.bodySmall)
            }
            processingTiming?.let {
                Text("앱 측정 전체 시간: ${it.totalMs}ms\n사진 변환 ${it.encodeMs}ms · 요청/대기 ${it.requestMs}ms · 결과 표시 준비 ${it.decodeMs}ms",
                    style = MaterialTheme.typography.bodySmall)
                Text("통신과 앱 처리가 포함된 경과 시간이며 지문 보호 성능 점수가 아닙니다.", style = MaterialTheme.typography.bodySmall)
            }
            HorizontalDivider()
            Text("지문 평가", style = MaterialTheme.typography.titleMedium)
            Text(evaluation.message, style = MaterialTheme.typography.bodySmall)
            evaluation.verifiedReport?.let {
                Text("원본 점수: ${it.originalScore}  /  처리본 점수: ${it.protectedScore}")
                Text("단위: ${it.scoreUnit}\n엔진: ${it.engine} ${it.engineVersion}\n측정 시각: ${it.measuredAt}\n조건: ${it.conditions}\n자료: ${it.sampleId} / 참조: ${it.referenceId}",
                    style = MaterialTheme.typography.bodySmall)
            }
            saveError?.let { Text(it, color = MaterialTheme.colorScheme.error, style = MaterialTheme.typography.bodySmall) }
            Text("사본 파일 형식",style=MaterialTheme.typography.titleMedium)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                ExportFormat.entries.forEach { format ->
                    FilterChip(selected=settings.exportFormat==format,
                        enabled=!isSaving && !isSharing && !isAwaitingSavePermission,
                        onClick={ onSettingsChanged(settings.copy(exportFormat=format)) },
                        label={ Text(if(format==ExportFormat.PNG) "PNG (손실 없음)" else "JPEG (용량 절약)") })
                }
            }
            if(settings.exportFormat==ExportFormat.JPEG) {
                Text("JPEG 품질 ${settings.jpegQuality} · 저장 후 보호 효과가 달라질 수 있습니다.",style=MaterialTheme.typography.bodySmall)
                Slider(value=settings.jpegQuality.toFloat(),onValueChange={ onSettingsChanged(settings.copy(jpegQuality=it.roundToInt())) },
                    enabled=!isSaving && !isSharing && !isAwaitingSavePermission,valueRange=80f..100f,steps=19,
                    modifier=Modifier.semantics { contentDescription="JPEG 저장 품질" })
            }
            Button(onClick = onSaveProtectedImage, enabled = !isSaving && !isSharing && !isAwaitingSavePermission,
                modifier = Modifier.fillMaxWidth(), contentPadding = PaddingValues(vertical = 14.dp)) {
                Text(when {
                    isAwaitingSavePermission -> "저장 권한 확인 중…"
                    isSaving -> "저장 중…"
                    saveError != null -> "사본 저장 다시 시도"
                    else -> "보호 사본 저장 (원본 보존)"
                })
            }
            shareError?.let { Text(it, color = MaterialTheme.colorScheme.error) }
            OutlinedButton(onClick = onShare, enabled = !isSharing && !isSaving && !isAwaitingSavePermission,
                modifier = Modifier.fillMaxWidth()) {
                Text(if (isSharing) "공유 사본 준비 중…" else if (response?.resultKind == "mock") "Mock 프리뷰 공유" else "처리 사본 공유")
            }
            OutlinedButton(onClick = onExportDiagnostics, enabled = !isDiagnosticPending && !isSharing && !isSaving,
                modifier = Modifier.fillMaxWidth()) { Text("진단 기록 저장 (사진 제외)") }
            Text("사진·서버 주소·지문 점수는 제외하고 처리 설정과 앱 측정 시간만 JSON으로 저장합니다.",
                style = MaterialTheme.typography.bodySmall)
        }
    }
}

@Composable
private fun CroppedPhoto(bitmap: Bitmap, crop: ComparisonCrop, description: String, modifier: Modifier) {
    val image = remember(bitmap) { bitmap.asImageBitmap() }
    val background = MaterialTheme.colorScheme.surfaceVariant
    Canvas(modifier.background(background).semantics { contentDescription = description }) {
        val scale = min(size.width / crop.width, size.height / crop.height)
        val width = (crop.width * scale).roundToInt().coerceAtLeast(1)
        val height = (crop.height * scale).roundToInt().coerceAtLeast(1)
        drawImage(image, srcOffset = IntOffset(crop.left, crop.top), srcSize = IntSize(crop.width, crop.height),
            dstOffset = IntOffset(((size.width - width) / 2).roundToInt(), ((size.height - height) / 2).roundToInt()),
            dstSize = IntSize(width, height))
    }
}
