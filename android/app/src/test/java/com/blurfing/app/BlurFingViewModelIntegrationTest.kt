package com.blurfing.app

import android.graphics.Bitmap
import android.graphics.Color
import android.net.Uri
import com.blurfing.app.model.ProtectionRequest
import com.blurfing.app.model.ProtectionResponse
import com.blurfing.app.repository.ProtectionRepository
import com.blurfing.app.viewmodel.BlurFingViewModel
import com.blurfing.app.viewmodel.ScreenStep
import com.blurfing.app.viewmodel.UiState
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.setMain
import org.junit.After
import org.junit.Assert.*
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config
import org.robolectric.annotation.GraphicsMode
import androidx.lifecycle.ViewModelStore
import java.io.ByteArrayOutputStream
import java.io.File
import java.io.IOException
import java.util.Base64
import java.util.concurrent.atomic.AtomicInteger
import kotlinx.serialization.json.Json
import okhttp3.mockwebserver.MockResponse
import okhttp3.mockwebserver.MockWebServer
import okhttp3.mockwebserver.RecordedRequest

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class BlurFingViewModelIntegrationTest {
    private val store = ViewModelStore()
    @Before fun setUp() { Dispatchers.setMain(Dispatchers.Unconfined) }
    @After fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
    }

    private fun response(request: ProtectionRequest, color: Int = Color.RED): ProtectionResponse {
        val bitmap = Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(color) }
        val stream = ByteArrayOutputStream()
        bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream)
        return ProtectionResponse(request.requestId, "succeeded", "real",
            Base64.getEncoder().encodeToString(stream.toByteArray()), appliedRegions = request.regions.orEmpty())
    }

    private suspend fun load(vm: BlurFingViewModel): UiState.Ready {
        store.put("test", vm)
        val context = RuntimeEnvironment.getApplication()
        val file = File.createTempFile("blurfing-synthetic-", ".png", context.cacheDir)
        try {
            file.outputStream().use {
                Bitmap.createBitmap(8, 8, Bitmap.Config.ARGB_8888).apply { eraseColor(Color.BLUE) }
                    .compress(Bitmap.CompressFormat.PNG, 100, it)
            }
            vm.onImageSelected(Uri.fromFile(file), context)
            return withTimeout(5000) { vm.uiState.first { it is UiState.Ready } as UiState.Ready }
        } finally {
            file.delete()
        }
    }

    @Test fun failedServerRequestPreservesEditedRegionsAndRetryUsesServerImage() = runBlocking {
        val count = AtomicInteger()
        var selectedUrl: String? = null
        val repository = object : ProtectionRepository {
            override suspend fun protectImage(request: ProtectionRequest, imageBytes: ByteArray): Result<ProtectionResponse> =
                if (count.incrementAndGet() == 1) Result.failure(IOException("synthetic server failure"))
                else Result.success(response(request))
            override fun cancelRequest(requestId: String) {}
        }
        val vm = BlurFingViewModel(apiRepositoryFactory = { selectedUrl = it; repository })
        val loaded = load(vm)
        vm.deleteRegion(1)
        val edited = (vm.uiState.value as UiState.Ready).regions
        vm.startProtection(serverUrl = "https://demo.example.org/")
        val failed = withTimeout(5000) {
            vm.uiState.first { it is UiState.Ready && it.processingError != null } as UiState.Ready
        }
        assertSame(loaded.originalBitmap, failed.originalBitmap)
        assertEquals(edited, failed.regions)
        assertEquals(ScreenStep.PROCESSING, failed.step)
        assertNull(failed.protectedBitmap)
        vm.startProtection(serverUrl = "https://demo.example.org/")
        val completed = withTimeout(5000) {
            vm.uiState.first { it is UiState.Ready && it.step == ScreenStep.COMPARISON } as UiState.Ready
        }
        assertEquals("https://demo.example.org", selectedUrl)
        assertEquals(Color.RED, completed.protectedBitmap!!.getPixel(0, 0))
        assertEquals(Color.BLUE, completed.originalBitmap.getPixel(0, 0))
        assertEquals(2, count.get())
    }

    @Test fun syntheticHttpServerImageReachesComparisonScreenState() = runBlocking {
        MockWebServer().use { server ->
            server.dispatcher = object : okhttp3.mockwebserver.Dispatcher() {
                override fun dispatch(request: RecordedRequest): MockResponse {
                    val multipart = request.body.readUtf8()
                    val id = multipart.substringAfter("name=\"request_id\"")
                        .substringAfter("\r\n\r\n")
                        .substringBefore("\r\n")
                    return MockResponse().setBody(
                        Json.encodeToString(ProtectionResponse.serializer(), response(ProtectionRequest(id)))
                    )
                }
            }
            server.start()
            val vm = BlurFingViewModel()
            load(vm)
            vm.startProtection(serverUrl = server.url("/").toString())
            val completed = withTimeout(10000) {
                vm.uiState.first { it is UiState.Ready && !it.isProcessing } as UiState.Ready
            }
            assertNull(completed.processingError)
            assertEquals(ScreenStep.COMPARISON, completed.step)
            assertEquals("real", completed.protectionResponse!!.resultKind)
            assertEquals(Color.RED, completed.protectedBitmap!!.getPixel(0, 0))
            assertEquals(Color.BLUE, completed.originalBitmap.getPixel(0, 0))
            assertEquals("/v1/protect", server.takeRequest().path)
        }
    }

    @Test fun resetWhileRequestFinishesCannotRestoreOldPhoto() = runBlocking {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val finished = CompletableDeferred<Unit>()
        val repository = object : ProtectionRepository {
            override suspend fun protectImage(request: ProtectionRequest, imageBytes: ByteArray): Result<ProtectionResponse> {
                entered.complete(Unit)
                try {
                    withContext(NonCancellable) { release.await() }
                    return Result.success(response(request))
                } finally {
                    finished.complete(Unit)
                }
            }
            override fun cancelRequest(requestId: String) {}
        }
        val vm = BlurFingViewModel(repository)
        load(vm)
        vm.startProtection()
        withTimeout(5000) { entered.await() }
        vm.resetToIdle()
        release.complete(Unit)
        withTimeout(5000) { finished.await() }
        yield()
        assertEquals(UiState.Idle, vm.uiState.value)
    }

    @Test fun duplicateStartDoesNotIssueSecondRequest() = runBlocking {
        val entered = CompletableDeferred<Unit>()
        val release = CompletableDeferred<Unit>()
        val count = AtomicInteger()
        val repository = object : ProtectionRepository {
            override suspend fun protectImage(request: ProtectionRequest, imageBytes: ByteArray): Result<ProtectionResponse> {
                count.incrementAndGet()
                entered.complete(Unit)
                release.await()
                return Result.success(response(request))
            }
            override fun cancelRequest(requestId: String) {}
        }
        val vm = BlurFingViewModel(repository)
        load(vm)
        vm.startProtection()
        withTimeout(5000) { entered.await() }
        vm.startProtection()
        assertEquals(1, count.get())
        release.complete(Unit)
        withTimeout(5000) { vm.uiState.first { it is UiState.Ready && !it.isProcessing } }
        Unit
    }
}
