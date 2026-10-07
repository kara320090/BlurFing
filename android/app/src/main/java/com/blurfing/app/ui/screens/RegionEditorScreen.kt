package com.blurfing.app.ui.screens

import android.graphics.Bitmap
import android.graphics.RectF
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Delete
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.onGloballyPositioned
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.contentDescription
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.ui.components.FingertipOverlayCanvas
import com.blurfing.app.utils.CoordinateTransformer

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun RegionEditorScreen(
    bitmap: Bitmap,
    regions: List<NormalizedRegion>,
    onAddRegion: () -> Unit,
    onDeleteRegion: (Int) -> Unit,
    onUpdateRegion: (Int, NormalizedRegion) -> Unit,
    onProceedToSettings: () -> Unit,
    onBack: () -> Unit,
    sessionNotice: String? = null,
    modifier: Modifier = Modifier,
    canUndo: Boolean = false,
    canRedo: Boolean = false,
    onUndo: () -> Unit = {},
    onRedo: () -> Unit = {},
    onClearRegions: () -> Unit = {}
) {
    var selectedIndex by remember { mutableStateOf<Int?>(if (regions.isNotEmpty()) 0 else null) }
    var viewWidth by remember { mutableStateOf(0f) }
    var viewHeight by remember { mutableStateOf(0f) }
    LaunchedEffect(regions.size) {
        if (selectedIndex == null || selectedIndex !in regions.indices) selectedIndex = regions.indices.firstOrNull()
    }

    val imageBounds = remember(viewWidth, viewHeight, bitmap) {
        CoordinateTransformer.computeImageBoundsInView(
            viewWidth = viewWidth,
            viewHeight = viewHeight,
            imageWidth = bitmap.width.toFloat(),
            imageHeight = bitmap.height.toFloat()
        )
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("손끝 영역 확인 및 수정 (BF-03)") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.Default.ArrowBack, contentDescription = "뒤로가기")
                    }
                },
                colors = TopAppBarDefaults.topAppBarColors(
                    containerColor = MaterialTheme.colorScheme.primaryContainer,
                    titleContentColor = MaterialTheme.colorScheme.onPrimaryContainer
                )
            )
        },
        modifier = modifier.fillMaxSize()
    ) { paddingValues ->
        Column(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(16.dp),
            verticalArrangement = Arrangement.spacedBy(12.dp)
        ) {
            sessionNotice?.let {
                Text(it, style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.primary)
            }
            Text(
                text = if (regions.isEmpty()) "자동 탐지는 아직 연결되지 않았습니다. ‘영역 추가’로 지문이 보이는 손끝을 직접 지정해 주세요."
                    else "수동 선택 영역 ${regions.size}개 · 지문이 보이는 손끝 패드에 맞추세요. 손톱과 손등은 제외하세요.",
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                textAlign = TextAlign.Center,
                modifier = Modifier.fillMaxWidth()
            )

            // 이미지 및 오버레이 캔버스
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .background(Color.Black.copy(alpha = 0.05f), RoundedCornerShape(12.dp))
                    .onGloballyPositioned { coordinates ->
                        viewWidth = coordinates.size.width.toFloat()
                        viewHeight = coordinates.size.height.toFloat()
                    },
                contentAlignment = Alignment.Center
            ) {
                Image(
                    bitmap = bitmap.asImageBitmap(),
                    contentDescription = "손끝 영역 편집 이미지",
                    modifier = Modifier.fillMaxSize()
                )

                FingertipOverlayCanvas(
                    regions = regions,
                    imageBounds = imageBounds,
                    selectedRegionIndex = selectedIndex,
                    onRegionSelected = { selectedIndex = it },
                    onRegionUpdated = onUpdateRegion,
                    modifier = Modifier.fillMaxSize()
                )
            }

            Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()), horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                regions.forEachIndexed { index, _ ->
                    FilterChip(selected = selectedIndex == index, onClick = { selectedIndex = index }, label = { Text("영역 ${index+1}") })
                }
            }
            selectedIndex?.let { index ->
                regions.getOrNull(index)?.let { region ->
                    RegionSizeControls(region, bitmap.width, bitmap.height) { onUpdateRegion(index,it) }
                }
            }
            Row(Modifier.fillMaxWidth(), horizontalArrangement = Arrangement.SpaceBetween) {
                TextButton(onClick = onUndo, enabled = canUndo) { Text("실행 취소") }
                TextButton(onClick = onRedo, enabled = canRedo) { Text("다시 실행") }
                TextButton(onClick = onClearRegions, enabled = regions.isNotEmpty()) { Text("영역 모두 지우기") }
            }
            // 하단 조작 바
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.spacedBy(8.dp),
                verticalAlignment = Alignment.CenterVertically
            ) {
                OutlinedButton(
                    onClick = onAddRegion,
                    modifier = Modifier.weight(1f)
                ) {
                    Icon(Icons.Default.Add, contentDescription = null, modifier = Modifier.size(18.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text("영역 추가")
                }

                if (selectedIndex != null && selectedIndex in regions.indices) {
                    OutlinedButton(
                        onClick = {
                            val targetIndex = selectedIndex!!
                            onDeleteRegion(targetIndex)
                            selectedIndex = if (regions.size > 1) 0 else null
                        },
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error)
                    ) {
                        Icon(Icons.Default.Delete, contentDescription = null, modifier = Modifier.size(18.dp))
                        Spacer(modifier = Modifier.width(4.dp))
                        Text("선택 삭제")
                    }
                }

                Button(
                    onClick = onProceedToSettings,
                    enabled = regions.isNotEmpty(),
                    modifier = Modifier.weight(1.2f)
                ) {
                    Text("보호 설정 (BF-04)")
                }
            }
        }
    }
}

@Composable
private fun RegionSizeControls(region: NormalizedRegion, imageWidth: Int, imageHeight: Int,
    onChange: (NormalizedRegion) -> Unit) {
    var width by remember(region) { mutableFloatStateOf(region.width) }
    var height by remember(region) { mutableFloatStateOf(region.height) }
    val minimumWidth = minOf(1f/imageWidth,region.width)
    val minimumHeight = minOf(1f/imageHeight,region.height)
    Text("선택 영역 크기 · ${ (width*imageWidth).toInt().coerceAtLeast(1) } × ${ (height*imageHeight).toInt().coerceAtLeast(1) }px",
        style = MaterialTheme.typography.bodySmall)
    Slider(value = width, onValueChange = { width=it }, valueRange = minimumWidth..maxOf(minimumWidth,1f-region.x),
        onValueChangeFinished = { onChange(region.copy(width=width)) },
        modifier = Modifier.height(32.dp).semantics { contentDescription="선택 영역 너비" })
    Slider(value = height, onValueChange = { height=it }, valueRange = minimumHeight..maxOf(minimumHeight,1f-region.y),
        onValueChangeFinished = { onChange(region.copy(height=height)) },
        modifier = Modifier.height(32.dp).semantics { contentDescription="선택 영역 높이" })
}
