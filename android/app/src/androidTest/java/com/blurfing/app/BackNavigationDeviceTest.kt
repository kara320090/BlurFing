package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import androidx.compose.ui.test.*
import androidx.compose.ui.test.junit4.createAndroidComposeRule
import androidx.lifecycle.ViewModelProvider
import androidx.test.espresso.Espresso.pressBack
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.blurfing.app.model.ProcessingSettings
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import org.junit.Assert.*
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import java.io.ByteArrayOutputStream
import java.io.DataInputStream
import java.io.File
import java.net.InetAddress
import java.net.ServerSocket
import java.net.Socket
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.concurrent.thread

/** System Back and Activity recreation with synthetic images and a loopback HTTP fixture. */
@RunWith(AndroidJUnit4::class)
class BackNavigationDeviceTest {
    @get:Rule val compose = createAndroidComposeRule<MainActivity>()
    private val vm get() = ViewModelProvider(compose.activity)[BlurFingViewModel::class.java]
    @Before fun reset() { compose.runOnUiThread { vm.resetToIdle(); vm.updateSettings(ProcessingSettings()) } }

    private fun load(): File {
        val source = File(compose.activity.cacheDir, "back-navigation-synthetic.png")
        val bitmap = Bitmap.createBitmap(120, 160, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.CYAN) }
        source.outputStream().use { assertTrue(bitmap.compress(Bitmap.CompressFormat.PNG, 100, it)) }
        bitmap.recycle()
        compose.runOnUiThread { vm.onImageSelected(Uri.fromFile(source), compose.activity) }
        ready(ScreenStep.REGION_EDITOR)
        compose.onNodeWithText("영역 추가").performClick()
        return source
    }

    private fun ready(step: ScreenStep) {
        compose.waitUntil(15_000) { (vm.uiState.value as? UiState.Ready)?.let { it.step == step && !it.isProcessing } == true }
        compose.waitForIdle()
    }

    @Test fun systemBackReturnsThroughEditorAndClearsDraftWithoutChangingSource() {
        val draftDirectory = File(compose.activity.cacheDir, "editing-drafts")
        val previousDrafts = draftDirectory.listFiles().orEmpty().toSet()
        val source = load()
        val addedDrafts = draftDirectory.listFiles().orEmpty().toSet() - previousDrafts
        val original = source.readBytes()
        val regions = (vm.uiState.value as UiState.Ready).regions
        try {
            compose.onNodeWithText("보호 설정 (BF-04)").performClick()
            pressBack()
            ready(ScreenStep.REGION_EDITOR)
            assertEquals(regions, (vm.uiState.value as UiState.Ready).regions)
            compose.onNodeWithText("보호 설정 (BF-04)").performClick()
            compose.onNodeWithText("Mock 프리뷰 만들기").performScrollTo().performClick()
            ready(ScreenStep.COMPARISON)
            pressBack()
            ready(ScreenStep.REGION_EDITOR)
            assertEquals(regions, (vm.uiState.value as UiState.Ready).regions)
            pressBack()
            compose.waitUntil(5000) { vm.uiState.value == UiState.Idle }
            assertFalse(compose.activity.isFinishing)
            assertEquals(1, addedDrafts.size)
            assertTrue(addedDrafts.none { it.exists() })
            assertArrayEquals(original, source.readBytes())
        } finally { compose.runOnUiThread { vm.resetToIdle() }; source.delete() }
    }

    @Test fun processingBackCanContinueDismissRecreateAndConfirmCancellation() {
        val source = load()
        val regions = (vm.uiState.value as UiState.Ready).regions
        try {
            HoldingHttpServer().use { server ->
                compose.runOnUiThread { vm.updateSettings(ProcessingSettings(useServer = true, serverAddress = server.address)) }
                compose.onNodeWithText("보호 설정 (BF-04)").performClick()
                compose.onNodeWithText("서버로 전송 및 처리").performScrollTo().performClick()
                assertTrue(server.entered.await(10, TimeUnit.SECONDS))
                pressBack()
                compose.onNodeWithText("진행 중인 처리를 취소할까요?").assertExists()
                compose.onNodeWithText("계속 처리").performClick()
                compose.runOnIdle { assertTrue((vm.uiState.value as UiState.Ready).isProcessing) }
                pressBack()
                pressBack() // Dismissing the dialog also keeps the request running.
                compose.onNodeWithText("진행 중인 처리를 취소할까요?").assertDoesNotExist()
                compose.runOnIdle { assertTrue((vm.uiState.value as UiState.Ready).isProcessing) }
                pressBack()
                compose.activityRule.scenario.recreate()
                compose.onNodeWithText("진행 중인 처리를 취소할까요?").assertExists()
                compose.onNodeWithText("처리 취소").performClick()
                ready(ScreenStep.PROCESSING)
                server.release.countDown()
                assertTrue(server.finished.await(5000, TimeUnit.MILLISECONDS))
                compose.waitForIdle()
                compose.runOnIdle {
                    val cancelled = vm.uiState.value as UiState.Ready
                    assertEquals(ScreenStep.PROCESSING, cancelled.step)
                    assertEquals(regions, cancelled.regions)
                    assertNull(cancelled.protectedBitmap)
                    assertNull(cancelled.processingError)
                }
                assertNull(server.failure)
                assertFalse(compose.activity.isFinishing)
            }
        } finally { compose.runOnUiThread { vm.resetToIdle(); vm.updateSettings(ProcessingSettings()) }; source.delete() }
    }

    @Test fun completionClosesPendingConfirmationAndShowsComparison() {
        val source = load()
        try {
            HoldingHttpServer().use { server ->
                compose.runOnUiThread { vm.updateSettings(ProcessingSettings(useServer = true, serverAddress = server.address)) }
                compose.onNodeWithText("보호 설정 (BF-04)").performClick()
                compose.onNodeWithText("서버로 전송 및 처리").performScrollTo().performClick()
                assertTrue(server.entered.await(10, TimeUnit.SECONDS))
                pressBack()
                compose.onNodeWithText("진행 중인 처리를 취소할까요?").assertExists()
                server.release.countDown()
                ready(ScreenStep.COMPARISON)
                compose.onNodeWithText("진행 중인 처리를 취소할까요?").assertDoesNotExist()
                assertEquals("mock", (vm.uiState.value as UiState.Ready).protectionResponse!!.resultKind)
                assertNull(server.failure)
            }
        } finally { compose.runOnUiThread { vm.resetToIdle(); vm.updateSettings(ProcessingSettings()) }; source.delete() }
    }

    private class HoldingHttpServer : AutoCloseable {
        private val server = ServerSocket(0, 1, InetAddress.getByName("127.0.0.1"))
        val address = "http://127.0.0.1:${server.localPort}"
        val entered = CountDownLatch(1)
        val release = CountDownLatch(1)
        val finished = CountDownLatch(1)
        @Volatile var failure: Throwable? = null
        @Volatile private var socket: Socket? = null
        private val worker = thread(isDaemon = true, name = "synthetic-back-navigation-http") {
            try {
                server.accept().use { connection ->
                    socket = connection
                    connection.soTimeout = 15_000
                    val input = DataInputStream(connection.getInputStream())
                    val headers = ByteArrayOutputStream()
                    var tail = 0
                    while (tail != 0x0d0a0d0a) {
                        val next = input.readUnsignedByte()
                        headers.write(next)
                        check(headers.size() <= 16_384)
                        tail = (tail shl 8) or next
                    }
                    val length = Regex("(?im)^Content-Length: (\\d+)").find(headers.toString("UTF-8"))!!.groupValues[1].toInt()
                    require(length in 1..16_777_216)
                    val body = ByteArray(length).also { input.readFully(it) }.toString(Charsets.UTF_8)
                    val id = body.substringAfter("name=\"request_id\"").substringAfter("\r\n\r\n").substringBefore("\r\n")
                    require(id.matches(Regex("[a-f0-9-]{36}")))
                    entered.countDown()
                    check(release.await(25, TimeUnit.SECONDS))
                    val response = """{"request_id":"$id","status":"succeeded","result_kind":"mock","applied_regions":[{"x":0.4,"y":0.4,"width":0.15,"height":0.15}]}""".toByteArray()
                    // The client may already have cancelled; a closed socket is expected in that case.
                    runCatching {
                        connection.getOutputStream().apply {
                            write("HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: ${response.size}\r\nConnection: close\r\n\r\n".toByteArray())
                            write(response)
                            flush()
                        }
                    }
                }
            } catch (error: Throwable) { if (!server.isClosed) failure = error }
            finally { finished.countDown() }
        }
        override fun close() {
            release.countDown()
            server.close()
            socket?.close()
            worker.join(2000)
        }
    }
}
