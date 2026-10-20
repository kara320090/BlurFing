package com.blurfing.app.experimental

import android.net.Uri
import android.content.Intent
import android.os.Bundle
import androidx.activity.ComponentActivity
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
import com.blurfing.app.utils.CameraCaptureContract
import com.blurfing.app.viewmodel.CameraCaptureViewModel
import androidx.lifecycle.createSavedStateHandle
import androidx.lifecycle.viewmodel.initializer
import androidx.lifecycle.viewmodel.viewModelFactory

/** Separate explicit experiment. The normal v1 Gaussian/mock flow remains available. */
class ExperimentalPhotoActivity: ComponentActivity() {
    private val model: ExperimentalPhotoViewModel by viewModels {
        viewModelFactory { initializer { ExperimentalPhotoViewModel(savedState=createSavedStateHandle()) } }
    }
    private val cameraModel: CameraCaptureViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        model.initialize(applicationContext)
        if(savedInstanceState==null && intent.getStringExtra("preferred_engine")=="synthetic_v23" &&
            model.state.value.source==null && !model.state.value.hasActiveWork) {
            model.setEngine(ExperimentalPhotoEngine.SYNTHETIC)
        }
        setContent {
            BlurFingTheme {
                val state by model.state.collectAsState()
                val cameraPending by cameraModel.pendingUri.collectAsState()
                val cameraError by cameraModel.error.collectAsState()
                val requestExit = rememberExperimentalExitRequest(state, model::cancel) { model.discardSession();finish() }
                var saveWarning by rememberSaveable { mutableStateOf(false) }
                var shareWarning by rememberSaveable { mutableStateOf(false) }
                var saveTicket by rememberSaveable { mutableStateOf<String?>(null) }
                var showOverlay by rememberSaveable { mutableStateOf(true) }
                val picker=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri: Uri? -> model.select(applicationContext,uri) }
                val camera=rememberLauncherForActivityResult(CameraCaptureContract()) { success ->
                    cameraModel.completeCapture(success)?.let { model.select(applicationContext,it) }
                }
                LaunchedEffect(state.awaitingSave,state.saving) { if(!state.awaitingSave && !state.saving)saveTicket=null }
                LaunchedEffect(state.pendingShare) {
                    state.pendingShare?.let { share ->
                        val launched=try {
                            startActivity(Intent.createChooser(ExperimentalPhotoShareFiles.intent(share),"실험 PNG 처리본 공유"));true
                        } catch(_: Exception) { false }
                        model.consumeShare(share,launched)
                    }
                }
                ExperimentalPhotoReplacementDialog(state.replacement,model::confirmReplacement,model::dismissReplacement)
                val save=rememberLauncherForActivityResult(ActivityResultContracts.CreateDocument("image/png")) { uri: Uri? ->
                    val ticket=saveTicket;saveTicket=null;model.finishSave(applicationContext,uri,ticket)
                }
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
                if(shareWarning && state.result!=null)AlertDialog(onDismissRequest={shareWarning=false},title={Text("실험 처리본을 공유할까요?")},
                    text={Text("미검출·거절 영역에 원본 지문이 남을 수 있습니다. 전체 보호가 검증되지 않은 실험 PNG를 선택한 앱에 전달합니다.")},
                    confirmButton={TextButton(onClick={shareWarning=false;model.share(applicationContext)}) { Text("공유 앱 선택") }},
                    dismissButton={TextButton(onClick={shareWarning=false}) { Text("취소") }})
                Surface(Modifier.fillMaxSize()) {
                    Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                        Text("사진 AI 보호 실험",style=MaterialTheme.typography.headlineSmall)
                        Text("실험 버전: ${com.blurfing.app.BuildConfig.SOURCE_REVISION.take(12)}",style=MaterialTheme.typography.bodySmall)
                        Text("미검증 실험입니다. 미검출·거절 영역에는 원본 지문이 남을 수 있습니다.",color=MaterialTheme.colorScheme.error)
                        Text("사진을 지정한 서버에 업로드하며 원본 파일은 보존합니다.")
                        OutlinedTextField(value=state.serverAddress,onValueChange=model::setAddress,label={Text("실험 서버 주소")},
                            enabled=!state.hasActiveWork && state.replacement==null && cameraPending==null,singleLine=true,modifier=Modifier.fillMaxWidth())
                        OutlinedButton(onClick=model::checkServer,enabled=!state.hasActiveWork && state.replacement==null && cameraPending==null) { Text("서버 연결 확인 · 사진 전송 없음") }
                        if(state.checkingServer) { LinearProgressIndicator(Modifier.fillMaxWidth());Text("사진 AI V2 서버 설정을 확인 중…") }
                        state.readiness?.let { ready ->
                            Text("구성된 엔진: "+ready.photoEngines.joinToString { ExperimentalPhotoEngine.fromId(it).title })
                            if(state.engine.id !in ready.photoEngines)Text("현재 엔진은 이 서버에서 사용할 수 없습니다.",color=MaterialTheme.colorScheme.error)
                        }
                        ExperimentalPhotoEngine.entries.forEach { engine ->
                            Row { RadioButton(selected=state.engine==engine,onClick={model.setEngine(engine)},enabled=!state.hasActiveWork && state.replacement==null && cameraPending==null)
                                Text(engine.title,modifier=Modifier.padding(top=12.dp)) }
                        }
                        if(state.engine==ExperimentalPhotoEngine.DISTAL)Text("V13은 경계 검토가 필요하며 기존 정답 자료에서 검출 정확도 회귀가 관측됐습니다.",color=MaterialTheme.colorScheme.error)
                        if(state.engine==ExperimentalPhotoEngine.POSE)Text("V14 손 자세 경계는 사람의 확인이 필요합니다. 실제 적용은 지문 품질 검사 결과에 따라 달라집니다.")
                        if(state.engine==ExperimentalPhotoEngine.SYNTHETIC)Text("사진을 선택하면 지정한 서버로 자동 전송하여 V23 지문 합성을 실행합니다. 경계·지문선 증거가 불확실한 후보는 처리하지 않고 결과에 표시합니다.")
                        Button(onClick={picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))},
                            enabled=!state.importing && !state.saving && !state.awaitingSave && !state.checkingServer && !state.sharing && state.pendingShare==null && cameraPending==null && state.replacement==null && saveTicket==null) { Text(if(state.source==null)"실험할 사진 선택" else "다른 사진 선택") }
                        OutlinedButton(onClick={
                            cameraModel.clearError()
                            cameraModel.beginCapture()?.let { uri -> try { camera.launch(uri) } catch(e: Exception) { cameraModel.launchFailed(e) } }
                        },enabled=!state.hasActiveWork && state.replacement==null && saveTicket==null && cameraPending==null) { Text("카메라로 촬영") }
                        cameraError?.let { Text(it,color=MaterialTheme.colorScheme.error) }
                        if(state.importing) { LinearProgressIndicator(Modifier.fillMaxWidth());Text("원본 방향·RGB 정규화 중…") }
                        state.source?.let { source ->
                            Text("업로드 원본 · ${source.width} × ${source.height} · 무손실 RGB PNG")
                            Image(source.preview.asImageBitmap(),"정규화된 원본 미리보기",Modifier.fillMaxWidth().height(260.dp))
                            if(!state.busy)Button(onClick=model::start,enabled=!state.hasActiveWork && state.replacement==null && saveTicket==null && cameraPending==null && state.readiness?.let { state.engine.id in it.photoEngines }!=false) { Text("선택한 AI 실험 실행") }
                        }
                        if(state.busy) {
                            LinearProgressIndicator(Modifier.fillMaxWidth());Text("AI 처리와 반환 픽셀·마스크 검증 중… 수 분 걸릴 수 있습니다.")
                            OutlinedButton(onClick=model::cancel) { Text("요청 취소 · 원본 유지") }
                        }
                        if(state.checkingServer || state.importing || state.sharing)OutlinedButton(onClick=model::cancel) { Text("작업 취소 · 원본 유지") }
                        state.result?.let { result ->
                            Text(result.presentation.title,style=MaterialTheme.typography.titleLarge)
                            Text(result.presentation.detail)
                            state.runTiming?.takeIf { it.requestId==result.requestId }?.let { timing ->
                                val label=if(timing.includesImport)"사진 불러오기부터" else "재실행 시작부터"
                                timing.resultElapsedMs?.let { Text("$label 결과 검증: ${it / 1000.0}초") }
                                timing.savedElapsedMs?.let {
                                    Text("$label 저장·재읽기: ${it / 1000.0}초 · 120초 목표 ${if(timing.withinDemoTarget==true)"충족" else "초과"}")
                                    Text("저장 위치 선택·대기 시간을 포함합니다. AI 성능·전체 보호 성공률이 아닙니다.",style=MaterialTheme.typography.bodySmall)
                                }
                            }
                            Text("요청: ${result.requestId}",style=MaterialTheme.typography.bodySmall)
                            Text("후보 ${result.candidateComponents} · 적용 ${result.transformedComponents} · 거절 ${result.rejectedComponents} · 변경 ${result.changedPixels} 픽셀")
                            if(result.rejectedComponents>0)Text("거절된 영역은 원본 지문이 그대로 남아 있습니다.",color=MaterialTheme.colorScheme.error)
                            Row { Switch(checked=showOverlay,onCheckedChange={showOverlay=it});Text("검증된 마스크 표시 · 초록=적용 / 주황=거절",Modifier.padding(top=12.dp)) }
                            state.source?.let { ExperimentalPhotoComparison(it,result,showOverlay) }
                            Text("색상은 검증된 전체 해상도 마스크의 미리보기입니다. 저장 파일에는 색상 표시가 없습니다.")
                            result.regions.forEach { r -> Text("후보 ${r.regionId}: ${r.userExplanation()}",style=MaterialTheme.typography.bodySmall) }
                            if(result.presentation.canSaveChangedCopy) {
                                Button(onClick={saveWarning=true},enabled=!state.hasActiveWork && state.replacement==null && saveTicket==null && cameraPending==null) { Text("실험 PNG 복사본 저장") }
                                OutlinedButton(onClick={shareWarning=true},enabled=!state.hasActiveWork && state.replacement==null && saveTicket==null && cameraPending==null) { Text("실험 PNG 처리본 공유") }
                            }
                        }
                        if(state.saving)Text("검증된 원본 해상도 PNG를 저장 중…")
                        if(state.sharing)Text("검증된 실험 PNG 공유 사본을 준비 중…")
                        state.recoveryWarning?.let { Text(it,color=MaterialTheme.colorScheme.error) }
                        state.message?.let { Text(it,color=MaterialTheme.colorScheme.error) }
                        OutlinedButton(onClick=requestExit) { Text("일반 화면으로 돌아가기") }
                    }
                }
            }
        }
    }
}
