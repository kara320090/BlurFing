package com.blurfing.app.experimental

import android.graphics.Bitmap
import androidx.compose.foundation.Image
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.utils.ComparisonCrop
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ensureActive
import kotlinx.coroutines.withContext
import kotlin.coroutines.coroutineContext

/** Stream canonical RGB rows; retain only the same bounded full-coordinate crop on each side. */
internal fun experimentalRegionPreview(png: ByteArray,crop: ComparisonCrop,result: ValidatedExperimentalPhoto?=null,
    checkActive: ()->Unit = {}): Bitmap {
    val header=ExperimentalPngCodec.parse(png,2)
    require(crop.left>=0 && crop.top>=0 && crop.width>0 && crop.height>0 &&
        crop.left.toLong()+crop.width<=header.width && crop.top.toLong()+crop.height<=header.height)
    if(result!=null)require(result.accepted.width==header.width && result.accepted.height==header.height)
    var sample=1
    while((maxOf(crop.width,crop.height)+sample-1)/sample>1024)sample*=2
    val bitmap=Bitmap.createBitmap((crop.width+sample-1)/sample,(crop.height+sample-1)/sample,Bitmap.Config.ARGB_8888)
    try {
        val row=IntArray(bitmap.width)
        ExperimentalPngCodec.rows(header,checkActive) { y,rgb ->
            if(y>=crop.top && y<crop.top+crop.height && (y-crop.top)%sample==0) {
                repeat(bitmap.width) { x ->
                    val originalX=crop.left+x*sample
                    val at=originalX*3
                    var c=0xff000000.toInt() or ((rgb[at].toInt() and 255) shl 16) or
                        ((rgb[at+1].toInt() and 255) shl 8) or (rgb[at+2].toInt() and 255)
                    val index=y*header.width+originalX
                    val tint=if(result==null)-1 else if(result.accepted[index])0x30cc60 else if(result.rejected[index])0xffa020 else -1
                    if(tint>=0)c=0xff000000.toInt() or
                        ((((c ushr 16 and 255)+(tint ushr 16 and 255))/2) shl 16) or
                        ((((c ushr 8 and 255)+(tint ushr 8 and 255))/2) shl 8) or ((c and 255)+(tint and 255))/2
                    row[x]=c
                }
                bitmap.setPixels(row,0,bitmap.width,0,(y-crop.top)/sample,bitmap.width,1)
            }
        }
        checkActive();return bitmap
    } catch(e: Throwable) { bitmap.recycle();throw e }
}

@Composable
internal fun ExperimentalPhotoComparison(source: ExperimentalPhotoUpload,result: ValidatedExperimentalPhoto,overlay: Boolean) {
    var region by rememberSaveable(result.requestId) { mutableIntStateOf(-1) }
    var zoom by rememberSaveable(result.requestId) { mutableFloatStateOf(1f) }
    var sideBySide by rememberSaveable(result.requestId) { mutableStateOf(true) }
    var originalOnly by rememberSaveable(result.requestId) { mutableStateOf(false) }
    val selected=result.regions.getOrNull(region)?.let { NormalizedRegion(it.x.toFloat(),it.y.toFloat(),it.width.toFloat(),it.height.toFloat()) }
    val crop=ComparisonCrop.calculate(source.width,source.height,selected,zoom)
    var error by remember(result.requestId,crop,overlay) { mutableStateOf<String?>(null) }
    val images by produceState<Pair<Bitmap,Bitmap>?>(null,source,result,crop,overlay) {
        value=null
        try {
            value=withContext(Dispatchers.IO) {
                val job=coroutineContext
                val original=experimentalRegionPreview(source.png,crop,checkActive={job.ensureActive()})
                try { original to experimentalRegionPreview(result.png,crop,if(overlay)result else null,{job.ensureActive()}) }
                catch(e: Throwable) { original.recycle();throw e }
            }
        } catch(e: CancellationException) { throw e }
        catch(_: OutOfMemoryError) { error="확대 미리보기 메모리가 부족합니다. 전체 보기로 돌아가 주세요." }
        catch(_: Exception) { error="확대 미리보기를 표시하지 못했습니다. 검증된 저장 결과는 유지됩니다." }
    }
    Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        FilterChip(selected=sideBySide,onClick={sideBySide=true},label={Text("나란히 비교")})
        FilterChip(selected=!sideBySide,onClick={sideBySide=false},label={Text("한 장씩")})
    }
    Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
        FilterChip(selected=region==-1,onClick={region=-1;zoom=1f},label={Text("전체")})
        result.regions.forEachIndexed { index,r ->
            FilterChip(selected=region==index,onClick={region=index;zoom=1f},label={Text("후보 ${r.regionId}")})
        }
    }
    Text("추가 확대 ${String.format(java.util.Locale.ROOT,"%.1f",zoom)}배")
    Slider(value=zoom,onValueChange={zoom=it},valueRange=1f..4f,modifier=Modifier.semantics { contentDescription="AI 비교 확대 배율" })
    if(!sideBySide)TextButton(onClick={originalOnly=!originalOnly}) { Text(if(originalOnly)"처리본 보기" else "원본 보기") }
    images?.let { (original,processed) ->
        if(sideBySide)Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            Column(Modifier.weight(1f)) { Text("원본");Image(original.asImageBitmap(),"AI 비교 원본",Modifier.fillMaxWidth().height(280.dp)) }
            Column(Modifier.weight(1f)) { Text(if(overlay)"처리본 · 마스크" else "처리본");Image(processed.asImageBitmap(),"AI 비교 처리본",Modifier.fillMaxWidth().height(280.dp)) }
        } else {
            Text(if(originalOnly)"원본" else if(overlay)"처리본 · 마스크" else "처리본")
            Image((if(originalOnly)original else processed).asImageBitmap(),if(originalOnly)"AI 비교 원본" else "AI 비교 처리본",Modifier.fillMaxWidth().height(300.dp))
        }
    } ?: if(error==null)LinearProgressIndicator(Modifier.fillMaxWidth()) else Unit
    error?.let { Text(it,color=MaterialTheme.colorScheme.error) }
    Text("양쪽에 같은 원본 좌표와 확대 영역을 적용합니다. 미리보기 배율·색상 표시는 저장·공유 PNG에 포함되지 않습니다.",style=MaterialTheme.typography.bodySmall)
}
