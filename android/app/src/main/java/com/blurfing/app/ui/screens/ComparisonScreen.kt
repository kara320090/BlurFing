package com.blurfing.app.ui.screens

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Compare
import androidx.compose.material.icons.filled.Save
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.blurfing.app.model.ProtectionResponse

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ComparisonScreen(
    originalBitmap: Bitmap,
    protectedBitmap: Bitmap,
    response: ProtectionResponse?,
    onSaveProtectedImage: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var showProtectedOnly by remember { mutableStateOf(true) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("전후 비교 및 저장 (BF-05, BF-06)") },
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
            // 비교 상태 안내 태그
            Row(
                modifier = Modifier.fillMaxWidth(),
                horizontalArrangement = Arrangement.SpaceBetween,
                verticalAlignment = Alignment.CenterVertically
            ) {
                Surface(
                    color = if (showProtectedOnly) MaterialTheme.colorScheme.primaryContainer else MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp)
                ) {
                    Text(
                        text = if (showProtectedOnly) "✓ 처리본 표시 중" else "● 원본 표시 중",
                        style = MaterialTheme.typography.labelMedium,
                        fontWeight = FontWeight.Bold,
                        color = if (showProtectedOnly) MaterialTheme.colorScheme.onPrimaryContainer else MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(horizontal = 10.dp, vertical = 6.dp)
                    )
                }

                FilledTonalButton(
                    onClick = { showProtectedOnly = !showProtectedOnly },
                    contentPadding = PaddingValues(horizontal = 12.dp, vertical = 6.dp)
                ) {
                    Icon(Icons.Default.Compare, contentDescription = null, modifier = Modifier.size(16.dp))
                    Spacer(modifier = Modifier.width(4.dp))
                    Text(if (showProtectedOnly) "원본 보기" else "보호본 보기")
                }
            }

            // 이미지 표시 영역
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .weight(1f)
                    .background(Color.Black.copy(alpha = 0.05f), RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center
            ) {
                val currentBitmap = if (showProtectedOnly) protectedBitmap else originalBitmap
                Image(
                    bitmap = currentBitmap.asImageBitmap(),
                    contentDescription = if (showProtectedOnly) "보호본 이미지" else "원본 이미지",
                    modifier = Modifier.fillMaxSize()
                )
            }

            // Mock 경고 및 결과 안내
            if (response != null && response.resultKind == "mock") {
                Surface(
                    color = MaterialTheme.colorScheme.surfaceVariant,
                    shape = RoundedCornerShape(8.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Text(
                        text = "[Mock 결과] 본 결과는 UI 및 통신 개발용이며 실제 AI 모델 및 센서 평가는 진행되지 않았습니다.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(10.dp),
                        textAlign = TextAlign.Center
                    )
                }
            }
            if (response?.resultKind == "real") {
                Text("서버 처리 이미지 · 지문 보호 성능은 별도 평가가 필요합니다.",
                    style = MaterialTheme.typography.bodySmall)
            }

            // 하단 저장 버튼
            Button(
                onClick = onSaveProtectedImage,
                shape = RoundedCornerShape(12.dp),
                modifier = Modifier.fillMaxWidth(),
                contentPadding = PaddingValues(vertical = 14.dp)
            ) {
                Icon(Icons.Default.Save, contentDescription = null)
                Spacer(modifier = Modifier.width(8.dp))
                Text("보호 사본 저장 (원본 보존) [BF-06]")
            }
        }
    }
}
