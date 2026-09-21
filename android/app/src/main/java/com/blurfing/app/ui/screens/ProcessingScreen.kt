package com.blurfing.app.ui.screens

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ArrowBack
import androidx.compose.material.icons.filled.Security
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.blurfing.app.model.ProtectionMethod
import com.blurfing.app.repository.BackendAddress
import kotlin.math.roundToInt

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProcessingScreen(
    isProcessing: Boolean,
    onStartProcessing: (ProtectionMethod, Float, String?) -> Unit,
    onCancelProcessing: () -> Unit,
    onBack: () -> Unit,
    processingError: String? = null,
    modifier: Modifier = Modifier
) {
    var selectedMethod by remember { mutableStateOf(ProtectionMethod.GAUSSIAN_BLUR) }
    var strength by rememberSaveable { mutableFloatStateOf(0.5f) }
    var useServer by rememberSaveable { mutableStateOf(false) }
    var serverAddress by rememberSaveable { mutableStateOf(BackendAddress.EMULATOR_DEFAULT) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("보호 설정 및 처리") },
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
                        text = if (useServer) "서버의 처리 결과를 기다리고 있습니다." else "로컬 Mock 프리뷰를 만드는 중입니다.",
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
                        modifier = Modifier.verticalScroll(rememberScrollState()).padding(20.dp),
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

                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Checkbox(checked = useServer, onCheckedChange = { useServer = it })
                            Text("백엔드 서버에서 처리")
                        }
                        if (useServer) {
                            OutlinedTextField(
                                value = serverAddress,
                                onValueChange = { serverAddress = it },
                                label = { Text("서버 주소") },
                                singleLine = true,
                                modifier = Modifier.fillMaxWidth()
                            )
                            Text(
                                "처리를 시작하면 선택한 사진을 이 서버로 전송합니다. 서버가 준비되지 않았다면 Mock 프리뷰를 사용하세요.",
                                style = MaterialTheme.typography.bodySmall
                            )
                        } else {
                            Text(
                                "로컬 Mock 프리뷰 · 사진을 전송하지 않습니다. 보호 성능은 미측정 상태입니다.",
                                style = MaterialTheme.typography.bodySmall
                            )
                        }
                        processingError?.let {
                            Text(it, color = MaterialTheme.colorScheme.error,
                                style = MaterialTheme.typography.bodyMedium)
                            Text("사진과 수정한 영역은 유지됩니다. 설정 확인 후 다시 시도할 수 있습니다.",
                                style = MaterialTheme.typography.bodySmall)
                        }

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
                                Text("강함 (흐림 증가)", style = MaterialTheme.typography.labelSmall)
                            }
                        }

                        Button(
                            onClick = { onStartProcessing(selectedMethod, strength, if (useServer) serverAddress else null) },
                            shape = RoundedCornerShape(12.dp),
                            modifier = Modifier.fillMaxWidth(),
                            contentPadding = PaddingValues(vertical = 14.dp)
                        ) {
                            Text(if (useServer) "서버로 전송 및 처리" else "Mock 프리뷰 만들기")
                        }
                    }
                }
            }
        }
    }
}
