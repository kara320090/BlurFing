package com.blurfing.app

import androidx.lifecycle.ViewModelStore
import com.blurfing.app.repository.BackendReadiness
import com.blurfing.app.repository.ReadinessKind
import com.blurfing.app.viewmodel.BlurFingViewModel
import kotlinx.coroutines.CompletableDeferred
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
import kotlinx.coroutines.NonCancellable
import kotlinx.coroutines.test.StandardTestDispatcher
import kotlinx.coroutines.test.resetMain
import kotlinx.coroutines.test.runCurrent
import kotlinx.coroutines.test.runTest
import kotlinx.coroutines.test.setMain
import kotlinx.coroutines.withContext
import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
class BackendReadinessLifecycleTest {
    private val dispatcher = StandardTestDispatcher()
    private val store = ViewModelStore()

    @Before fun setUp() { Dispatchers.setMain(dispatcher) }

    @After fun tearDown() {
        store.clear()
        Dispatchers.resetMain()
    }

    private fun viewModel(check: suspend (String) -> BackendReadiness): BlurFingViewModel =
        BlurFingViewModel(readinessCheck = check).also {
            store.put("readiness", it)
            it.updateSettings(it.settings.value.copy(
                useServer = true, serverAddress = "https://first.example.org/"
            ))
        }

    @Test fun changingAddressDiscardsLateResponse() = runTest(dispatcher) {
        val response = CompletableDeferred<BackendReadiness>()
        val addresses = mutableListOf<String>()
        val vm = viewModel { address ->
            addresses += address
            // Simulate a transport that still returns after cancellation.
            withContext(NonCancellable) { response.await() }
        }
        vm.checkBackendReadiness()
        runCurrent()
        assertEquals(ReadinessKind.CHECKING, vm.readiness.value.kind)
        assertEquals(listOf("https://first.example.org"), addresses)

        vm.updateSettings(vm.settings.value.copy(serverAddress = "https://second.example.org"))
        assertEquals(ReadinessKind.IDLE, vm.readiness.value.kind)
        response.complete(BackendReadiness(ReadinessKind.READY, "obsolete server"))
        runCurrent()
        assertEquals(ReadinessKind.IDLE, vm.readiness.value.kind)
    }

    @Test fun newerCheckIsNotOverwrittenByOlderResponse() = runTest(dispatcher) {
        val older = CompletableDeferred<BackendReadiness>()
        val newer = CompletableDeferred<BackendReadiness>()
        var requests = 0
        val vm = viewModel {
            val response = if (requests++ == 0) older else newer
            withContext(NonCancellable) { response.await() }
        }
        vm.checkBackendReadiness()
        runCurrent()
        vm.checkBackendReadiness()
        runCurrent()
        assertEquals(2, requests)

        val current = BackendReadiness(ReadinessKind.UNAVAILABLE, "current server")
        newer.complete(current)
        runCurrent()
        assertEquals(current, vm.readiness.value)
        older.complete(BackendReadiness(ReadinessKind.READY, "obsolete response"))
        runCurrent()
        assertEquals(current, vm.readiness.value)
    }

    @Test fun switchingToMockCancelsCheckAndStopsNewRequests() = runTest(dispatcher) {
        val response = CompletableDeferred<BackendReadiness>()
        var requests = 0
        var cancelled = false
        val vm = viewModel {
            requests++
            try { response.await() } finally { cancelled = true }
        }
        vm.checkBackendReadiness()
        runCurrent()
        vm.updateSettings(vm.settings.value.copy(useServer = false))
        runCurrent()
        assertTrue(cancelled)
        assertEquals(ReadinessKind.IDLE, vm.readiness.value.kind)
        vm.checkBackendReadiness()
        runCurrent()
        assertEquals(1, requests)
    }

    @Test fun resettingPhotoWorkflowCancelsPendingCheck() = runTest(dispatcher) {
        val response = CompletableDeferred<BackendReadiness>()
        var cancelled = false
        val vm = viewModel {
            try { response.await() } finally { cancelled = true }
        }
        vm.checkBackendReadiness()
        runCurrent()
        assertEquals(ReadinessKind.CHECKING, vm.readiness.value.kind)
        vm.resetToIdle()
        runCurrent()
        assertTrue(cancelled)
        assertEquals(ReadinessKind.IDLE, vm.readiness.value.kind)
    }
}
