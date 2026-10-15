package com.blurfing.app.experimental

import android.net.Uri
import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.compose.setContent
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.activity.viewModels
import androidx.compose.foundation.Image
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.unit.dp
import com.blurfing.app.ui.theme.BlurFingTheme

/** Separate explicit experiment. The normal v1 Gaussian/mock flow remains available. */
class ExperimentalPhotoActivity: ComponentActivity() {
    private val model: ExperimentalPhotoViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setContent {
            BlurFingTheme {
                val state by model.state.collectAsState()
                var leave by rememberSaveable { mutableStateOf(false) }
                var saveWarning by rememberSaveable { mutableStateOf(false) }
                var saveTicket by rememberSaveable { mutableStateOf<String?>(null) }
                var showOverlay by rememberSaveable { mutableStateOf(true) }
                val picker=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri: Uri? -> model.select(applicationContext,uri) }
                val save=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("image/png")) { uri: Uri? ->
                    val ticket=saveTicket;saveTicket=null;model.finishSave(applicationContext,uri,ticket)
                }
                BackHandler { if(state.busy || state.saving || state.importing)leave=true else finish() }
                if(leave) AlertDialog(onDismissRequest={leave=false},title={Text("실험을 종료할까요?")},
                    text={Text("진행 중인 요청을 취소합니다. 원본 사진 파일은 유지됩니다.")},
                    confirmButton={TextButton(onClick={model.cancel();leave=false;finish()}) { Text("취소 후 종료") }},
                    dismissButton={TextButton(onClick={leave=false}) { Text("계속 보기") }})
                if(saveWarning && state.result!=null) AlertDialog(onDismissRequest={saveWarning=false},title={Text("실험 복사본 저장")},
                    text={Text("검출되지 않았거나 거절된 지문은 원본으로 남을 수 있습니다. 이 이미지는 전체 지문 보호가 검증되지 않은 실험 결과입니다. 원본과 별도 PNG로 저장합니다.")},
                    confirmButton={TextButton(onClick={
                        saveWarning=false
                        model.prepareSave()?.let { ticket ->
                            saveTicket=ticket
                            try { save.launch("BlurFing-experimental-${state.result!!.requestId}.png") }
                            catch(_: Exception) { saveTicket=null;model.finishSave(applicationContext,null,ticket) }
                        }
                    }) { Text("실험 복사본 저장") }},dismissButton={TextButton(onClick={saveWarning=false}) { Text("취소") }})
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                        Text("사진 AI 보호 실험",style=MaterialTheme.typography.headlineSmall)
                        Text("미검증 실험입니다. 미검출·거절 영역에는 원본 지문이 남을 수 있습니다.",color=MaterialTheme.colorScheme.error)
                        Text("사진을 지정한 서버에 업로드하며 원본 파일은 보존합니다.")
                        OutlinedTextField(value=state.serverAddress,onValueChange=model::setAddress,label={Text("실험 서버 주소")},
                            enabled=!state.busy && !state.importing && !state.saving,singleLine=true,modifier=Modifier.fillMaxWidth())
                        ExperimentalPhotoEngine.entries.forEach { engine ->
                            Row { RadioButton(selected=state.engine==engine,onClick={model.setEngine(engine)},enabled=!state.busy && !state.importing && !state.saving)
                                Text(engine.title,modifier=Modifier.padding(top=12.dp)) }
                        }
                        if(state.engine==ExperimentalPhotoEngine.DISTAL)Text("V13은 경계 검토가 필요하며 기존 정답 자료에서 검출 정확도 회귀가 관측됐습니다.",color=MaterialTheme.colorScheme.error)
                        if(state.engine==ExperimentalPhotoEngine.POSE)Text("V14 손 자세 경계는 사람의 확인이 필요합니다. 실제 적용은 지문 품질 검사 결과에 따라 달라집니다.")
                        Button(onClick={picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))},
                            enabled=!state.importing && !state.saving && saveTicket==null) { Text(if(state.source==null)"실험할 사진 선택" else "다른 사진 선택") }
                        if(state.importing) { LinearProgressIndicator(Modifier.fillMaxWidth());Text("원본 방향·RGB 정규화 중…") }
                        state.source?.let { source ->
                            Text("업로드 원본 · ${source.width} × ${source.height} · 무손실 RGB PNG")
                            Image(source.preview.asImageBitmap(),"정규화된 원본 미리보기",Modifier.fillMaxWidth().height(260.dp))
                            if(!state.busy)Button(onClick=model::start,enabled=!state.importing && !state.saving && saveTicket==null) { Text("선택한 AI 실험 실행") }
                        }
                        if(state.busy) {
                            LinearProgressIndicator(Modifier.fillMaxWidth());Text("AI 처리와 반환 픽셀·마스크 검증 중… 수 분 걸릴 수 있습니다.")
                            OutlinedButton(onClick=model::cancel) { Text("요청 취소 · 원본 유지") }
                        }
                        state.result?.let { result ->
                            Text(result.presentation.title,style=MaterialTheme.typography.titleLarge)
                            Text(result.presentation.detail)
                            Text("후보 ${result.candidateComponents} · 적용 ${result.transformedComponents} · 거절 ${result.rejectedComponents} · 변경 ${result.changedPixels} 픽셀")
                            if(result.rejectedComponents>0)Text("거절된 영역은 원본 지문이 그대로 남아 있습니다.",color=MaterialTheme.colorScheme.error)
                            Row { Switch(checked=showOverlay,onCheckedChange={showOverlay=it});Text("검증된 마스크 표시 · 초록=적용 / 주황=거절",Modifier.padding(top=12.dp)) }
                            Image((if(showOverlay)result.overlayPreview else result.preview).asImageBitmap(),"실제 반환 이미지 비교",Modifier.fillMaxWidth().height(300.dp))
                            Text("색상은 검증된 전체 해상도 마스크의 미리보기입니다. 저장 파일에는 색상 표시가 없습니다.")
                            result.regions.forEach { r -> Text("후보 ${r.regionId}: ${if(r.status=="transformed")"변환됨" else "거절됨"} · ${r.reasonCode}",style=MaterialTheme.typography.bodySmall) }
                            if(result.presentation.canSaveChangedCopy)Button(onClick={saveWarning=true},enabled=!state.saving && !state.awaitingSave && saveTicket==null) { Text("실험 PNG 복사본 저장") }
                        }
                        if(state.saving)Text("검증된 원본 해상도 PNG를 저장 중…")
                        state.message?.let { Text(it,color=MaterialTheme.colorScheme.error) }
                        OutlinedButton(onClick={if(state.busy || state.saving || state.importing)leave=true else finish()}) { Text("일반 화면으로 돌아가기") }
                    }
                }
            }
        }
    }
}
