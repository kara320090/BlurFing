package com.blurfing.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.blurfing.app.model.ProtectionMethod
import kotlin.math.roundToInt

@Composable
fun ProcessingScreen(
    isProcessing: Boolean,
    onStartProcessing: (ProtectionMethod, Float) -> Unit,
    onCancelProcessing: () -> Unit,
    onBack: () -> Unit,
    modifier: Modifier = Modifier
) {
    var selectedMethod by remember { mutableStateOf(ProtectionMethod.GAUSSIAN_BLUR) }
    var strength by remember { mutableFloatStateOf(0.5f) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("보호 설정 및 처리 (BF-04)") },
                navigationIcon = {
                    if (!isProcessing) {
                        IconButton(onClick = onBack) {
                            Icon(Icons.Default.ArrowBack, contentDescription = "뒤로가기")
                        }
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
        Box(
            modifier = Modifier
                .fillMaxSize()
                .padding(paddingValues)
                .padding(24.dp),
            contentAlignment = Alignment.Center
        ) {
            if (isProcessing) {
                Column(
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.spacedBy(20.dp)
                ) {
                    CircularProgressIndicator(modifier = Modifier.size(56.dp))
                    Text(
                        text = "지문 보호 처리를 진행 중입니다...",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.Bold
                    )
                    Text(
                        text = "선택된 손끝 영역의 지문 식별 특징을 약화하고 있습니다.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        textAlign = TextAlign.Center
                    )
                    Spacer(modifier = Modifier.height(16.dp))
                    OutlinedButton(
                        onClick = onCancelProcessing,
                        colors = ButtonDefaults.outlinedButtonColors(contentColor = MaterialTheme.colorScheme.error)
                    ) {
                        Text("요청 취소")
                    }
                }
            } else {
                Card(
                    shape = RoundedCornerShape(16.dp),
                    elevation = CardDefaults.cardElevation(defaultElevation = 2.dp),
                    modifier = Modifier.fillMaxWidth()
                ) {
                    Column(
                        modifier = Modifier.padding(20.dp),
                        verticalArrangement = Arrangement.spacedBy(20.dp)
                    ) {
                        Row(
                            verticalAlignment = Alignment.CenterVertically,
                            horizontalArrangement = Arrangement.spacedBy(12.dp)
                        ) {
                            Icon(
                                imageVector = Icons.Default.Security,
                                contentDescription = null,
                                tint = MaterialTheme.colorScheme.primary
                            )
                            Text(
                                text = "지문 보호 강도 설정",
                                style = MaterialTheme.typography.titleLarge,
                                fontWeight = FontWeight.Bold
                            )
                        }

                        Text(
                            text = "보호 방식: ${selectedMethod.displayName}",
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant
                        )

                        Column {
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("보호 강도", style = MaterialTheme.typography.bodyMedium)
                                Text(
                                    "${(strength * 100).roundToInt()}%",
                                    fontWeight = FontWeight.Bold,
                                    color = MaterialTheme.colorScheme.primary
                                )
                            }
                            Slider(
                                value = strength,
                                onValueChange = { strength = it },
                                valueRange = 0.1f..1.0f,
                                steps = 9
                            )
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.SpaceBetween
                            ) {
                                Text("약함 (자연스러움)", style = MaterialTheme.typography.labelSmall)
                                Text("강함 (확실한 방어)", style = MaterialTheme.typography.labelSmall)
                            }
                        }

                        Button(
                            onClick = { onStartProcessing(selectedMethod, strength) },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth(),
                            contentPadding = PaddingValues(vertical = 14.dp)
                        ) {
                            Text("보호 처리 실행 (BF-04)")
                        }
                    }
                }
            }
        }
    }
}
