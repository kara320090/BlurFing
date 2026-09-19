package com.blurfing.app.ui.screens

import android.graphics.Bitmap
import android.graphics.RectF
import androidx.compose.foundation.Image
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
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.ui.components.FingertipOverlayCanvas
import com.blurfing.app.utils.CoordinateTransformer

@Composable
fun RegionEditorScreen(
    bitmap: Bitmap,
    regions: List<NormalizedRegion>,
    onAddRegion: () -> Unit,
    onDeleteRegion: (Int) -> Unit,
    onUpdateRegion: (Int, NormalizedRegion) -> Unit,
    onProceedToSettings: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var selectedIndex by remember { mutableStateOf<Int?>(if (regions.isNotEmpty()) 0 else null) }
    var viewWidth by remember { mutableStateOf(0f) }
    var viewHeight by remember { mutableStateOf(0f) }

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
            Text(
                text = "지문이 노출된 손끝 패드 영역만 선택하세요. 손톱이나 손등은 제외할 수 있습니다.",
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
