package com.blurfing.app.experimental

import androidx.compose.material3.AlertDialog
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable

enum class ExperimentalPhotoReplacementKind { ENGINE, PHOTO, RUN }

/** Display metadata only. The selected URI and action stay in the existing ViewModel. */
data class ExperimentalPhotoReplacement(
    val token: String,
    val kind: ExperimentalPhotoReplacementKind,
    val engine: ExperimentalPhotoEngine?=null
)

@Composable
internal fun ExperimentalPhotoReplacementDialog(
    replacement: ExperimentalPhotoReplacement?,
    onConfirm: (String) -> Unit,
    onDismiss: (String) -> Unit
) {
    if(replacement==null)return
    val action=when(replacement.kind) {
        ExperimentalPhotoReplacementKind.ENGINE -> "${replacement.engine?.title} 엔진으로 변경"
        ExperimentalPhotoReplacementKind.PHOTO -> "선택한 다른 사진 불러오기"
        ExperimentalPhotoReplacementKind.RUN -> "선택한 AI 실험 다시 실행"
    }
    AlertDialog(
        onDismissRequest={onDismiss(replacement.token)},
        title={Text("현재 결과를 바꿀까요?")},
        text={Text("$action 작업을 진행하면 저장하지 않은 현재 결과를 다시 저장할 수 없습니다. 원본 파일과 이미 저장한 복사본은 유지됩니다. 현재 결과를 저장하려면 계속 보기를 선택해 주세요.")},
        confirmButton={TextButton(onClick={onConfirm(replacement.token)}) { Text("저장하지 않고 진행") }},
        dismissButton={TextButton(onClick={onDismiss(replacement.token)}) { Text("계속 보기") }}
    )
}
