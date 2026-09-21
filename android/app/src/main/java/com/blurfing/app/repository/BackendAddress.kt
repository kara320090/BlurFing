package com.blurfing.app.repository

import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** 사용자가 선택한 서버 주소만 사용하며 인증정보·쿼리가 섞인 주소는 받지 않는다. */
object BackendAddress {
    const val EMULATOR_DEFAULT = "http://10.0.2.2:8000"
    private val localHosts = setOf("10.0.2.2", "127.0.0.1", "localhost")

    fun normalize(value: String, allowLocalHttp: Boolean): String {
        val url = value.trim().toHttpUrlOrNull()
            ?: throw IllegalArgumentException("http:// 또는 https://로 시작하는 서버 주소를 입력해 주세요.")
        require(url.username.isEmpty() && url.password.isEmpty() &&
            url.query == null && url.fragment == null) {
            "서버 주소에 로그인 정보, 쿼리 또는 #을 넣을 수 없습니다."
        }
        require(url.isHttps || (allowLocalHttp && url.host in localHosts)) {
            "HTTPS 주소를 사용해 주세요. 개발 빌드에서는 에뮬레이터·localhost의 HTTP도 지원합니다."
        }
        return url.toString().trimEnd('/')
    }
}
