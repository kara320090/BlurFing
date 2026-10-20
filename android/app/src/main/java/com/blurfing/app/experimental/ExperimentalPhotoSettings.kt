package com.blurfing.app.experimental

import android.content.Context
import com.blurfing.app.BuildConfig

/** V2 has its own endpoint and engine; never inherit V1's tunnel or mock settings. */
internal class ExperimentalPhotoSettings(context: Context) {
    private val preferences = context.applicationContext.getSharedPreferences("experimental-photo-settings", Context.MODE_PRIVATE)
    data class Value(val address: String, val engine: ExperimentalPhotoEngine)
    fun load(): Value = try {
        Value(preferences.getString("address", defaultAddress).orEmpty().take(2048),
            ExperimentalPhotoEngine.entries.firstOrNull { it.id == preferences.getString("engine", "") }
                ?: ExperimentalPhotoEngine.NATIVE)
    } catch (_: ClassCastException) { Value(defaultAddress, ExperimentalPhotoEngine.NATIVE) }
    fun save(address: String, engine: ExperimentalPhotoEngine) {
        preferences.edit().putString("address", address.take(2048)).putString("engine", engine.id).apply()
    }
    companion object {
        val defaultAddress: String get() = if (BuildConfig.DEBUG) EXPERIMENTAL_PHOTO_EMULATOR_DEFAULT else ""
    }
}

@kotlinx.serialization.Serializable
data class ExperimentalServerReadiness(
    val status: String,
    @kotlinx.serialization.SerialName("contract_version") val contractVersion: String,
    @kotlinx.serialization.SerialName("result_kind") val resultKind: String,
    @kotlinx.serialization.SerialName("photo_engines") val photoEngines: List<String>,
    @kotlinx.serialization.SerialName("production_approved") val productionApproved: Boolean
) {
    fun verify(): ExperimentalServerReadiness {
        require(status == "ready" && contractVersion == "photo-experimental-v2" && resultKind == "experimental" && !productionApproved)
        require(photoEngines.isNotEmpty() && photoEngines.size <= ExperimentalPhotoEngine.entries.size && photoEngines.distinct() == photoEngines)
        photoEngines.forEach(ExperimentalPhotoEngine::fromId)
        return this
    }
}

/** Local guidance only: response bodies can contain private paths or HTML and are never displayed. */
internal fun experimentalHttpFailure(code: Int): ExperimentalPhotoException {
    val guidance = when (code) {
        401, 403 -> "서버 접근 권한을 확인해 주세요."
        404, 405 -> "사진 AI V2 서버 주소인지 확인해 주세요. 일반 V1 서버에서는 실행할 수 없습니다."
        409 -> "같은 요청이 처리 중입니다. 잠시 후 새 요청으로 다시 실행해 주세요."
        413 -> "사진 용량 제한을 초과했습니다. 더 작은 사진을 선택해 주세요."
        415, 422 -> "서버가 사진 형식을 받지 못했습니다. 사진을 다시 선택하고 V2 서버 구성을 확인해 주세요."
        429 -> "서버가 다른 사진을 처리 중입니다. 잠시 후 다시 실행해 주세요."
        503 -> "선택한 AI 엔진이 준비되지 않았습니다. 서버 연결 확인과 엔진 구성을 확인해 주세요."
        504 -> "서버 처리 시간을 초과했습니다. 서버 상태를 확인한 뒤 다시 실행해 주세요."
        in 300..399 -> "다른 주소로 이동하는 서버는 지원하지 않습니다. 최종 HTTPS 주소를 입력해 주세요."
        else -> "서버가 요청을 완료하지 못했습니다. 서버 상태를 확인한 뒤 다시 실행해 주세요."
    }
    return ExperimentalPhotoException("$guidance (HTTP $code) 원본은 유지됩니다.")
}
