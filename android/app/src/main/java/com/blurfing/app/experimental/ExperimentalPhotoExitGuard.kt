package com.blurfing.app.experimental

import androidx.activity.compose.BackHandler
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue

/** The system Back gesture and the return button share the same discard decision. */
@Composable
internal fun rememberExperimentalExitRequest(
    state: ExperimentalPhotoState,
    onCancel: () -> Unit,
    onExit: () -> Unit
): () -> Unit {
    var confirmationVisible by rememberSaveable { mutableStateOf(false) }
    LaunchedEffect(state.requiresExitConfirmation) {
        if (!state.requiresExitConfirmation) confirmationVisible = false
    }
    val requestExit: () -> Unit = {
        if (state.requiresExitConfirmation) confirmationVisible = true else onExit()
    }
    BackHandler(onBack = requestExit)
    if (confirmationVisible && state.requiresExitConfirmation) {
        AlertDialog(
            onDismissRequest = { confirmationVisible = false },
            title = { Text(if (state.hasActiveWork) "실험을 종료할까요?" else "저장하지 않은 결과가 있습니다") },
            text = {
                Text(if (state.hasActiveWork)
                    "진행 중인 작업을 취소하고 실험 화면을 닫습니다. 원본 사진 파일과 이미 저장한 복사본은 유지됩니다."
                else
                    "저장하지 않고 종료하면 현재 실험 결과를 이 화면에서 다시 저장할 수 없습니다. 원본 사진 파일은 유지됩니다.")
            },
            confirmButton = {
                TextButton(onClick = {
                    confirmationVisible = false
                    onCancel()
                    onExit()
                }) { Text(if (state.hasActiveWork) "취소 후 종료" else "저장하지 않고 종료") }
            },
            dismissButton = {
                TextButton(onClick = { confirmationVisible = false }) { Text("계속 보기") }
            }
        )
    }
    return requestExit
}
