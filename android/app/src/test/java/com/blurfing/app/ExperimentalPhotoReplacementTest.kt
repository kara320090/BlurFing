package com.blurfing.app.experimental

import android.net.Uri
import androidx.lifecycle.ViewModelStore
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.ExperimentalCoroutinesApi
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

/** Validated, public synthetic RGB/masks; tests decisions and request identity, not AI efficacy. */
@OptIn(ExperimentalCoroutinesApi::class)
@RunWith(RobolectricTestRunner::class)
@Config(sdk = [28])
@GraphicsMode(GraphicsMode.Mode.NATIVE)
class ExperimentalPhotoReplacementTest {
    private val context get() = RuntimeEnvironment.getApplication()
    private val store = ViewModelStore()
    private val fixtures = ExperimentalPhotoDecoderTest()
    private val loaded = mutableListOf<Uri>()
    private val requests = mutableListOf<String>()
    private lateinit var source: ExperimentalPhotoUpload
    private lateinit var vm: ExperimentalPhotoViewModel
    private val other = Uri.parse("content://synthetic/two")

    @Before fun setUp() {
        Dispatchers.setMain(Dispatchers.Unconfined)
        source = fixtures.source()
        val service = object : ExperimentalPhotoService {
            override fun cancel(requestId: String) = Unit
            override suspend fun protect(source: ExperimentalPhotoUpload, engine: ExperimentalPhotoEngine,
                                         requestId: String): ValidatedExperimentalPhoto {
                requests += requestId
                return ExperimentalPhotoDecoder.decode(fixtures.response(source).copy(requestId = requestId),
                    source, engine, requestId, checkMemory = false)
            }
        }
        vm = ExperimentalPhotoViewModel({ service }, { _, uri -> loaded += uri; source })
        store.put("replacement", vm)
        vm.select(context, Uri.parse("content://synthetic/one"))
        vm.start()
        assertTrue(vm.state.value.hasUnsavedResult)
    }

    @After fun tearDown() { store.clear(); Dispatchers.resetMain() }

    @Test fun tappingSelectedEngineLeavesTheEntireResultAndSaveIdentityUntouched() {
        val before = vm.state.value
        val png = before.result!!.png.clone()
        vm.setEngine(before.engine)
        assertSame(before, vm.state.value)
        assertArrayEquals(png, vm.state.value.result!!.png)
        assertEquals(1, requests.size)
        assertEquals(1, loaded.size)
    }

    @Test fun engineDecisionCanBeDismissedWithoutChangingSourceResultOrSettings() {
        val before = vm.state.value
        vm.setEngine(ExperimentalPhotoEngine.POSE)
        val pending = vm.state.value.replacement!!
        assertEquals(ExperimentalPhotoReplacementKind.ENGINE, pending.kind)
        assertEquals(ExperimentalPhotoEngine.POSE, pending.engine)
        assertEquals(before, vm.state.value.copy(replacement = null))
        vm.dismissReplacement(pending.token)
        assertEquals(before, vm.state.value)
    }

    @Test fun confirmedEngineChangeOnlyDiscardsTheResultOnceAndPreservesSourceBytes() {
        val original = source.png.clone()
        vm.setEngine(ExperimentalPhotoEngine.POSE)
        val token = vm.state.value.replacement!!.token
        vm.confirmReplacement(token)
        assertEquals(ExperimentalPhotoEngine.POSE, vm.state.value.engine)
        assertSame(source, vm.state.value.source)
        assertNull(vm.state.value.result)
        assertNull(vm.state.value.savedResultRequestId)
        assertNull(vm.state.value.replacement)
        val after = vm.state.value
        vm.confirmReplacement(token)
        assertSame(after, vm.state.value)
        assertEquals(1, requests.size)
        assertArrayEquals(original, source.png)
    }

    @Test fun rerunRequiresItsOwnConfirmationAndCannotStartTwiceFromTheSameDecision() {
        val previous = vm.state.value.result
        vm.start()
        val token = vm.state.value.replacement!!.token
        assertEquals(ExperimentalPhotoReplacementKind.RUN, vm.state.value.replacement!!.kind)
        vm.confirmReplacement("obsolete-token")
        assertSame(previous, vm.state.value.result)
        assertEquals(1, requests.size)
        vm.confirmReplacement(token)
        val next = vm.state.value.result!!
        assertNotEquals(previous!!.requestId, next.requestId)
        assertTrue(vm.state.value.hasUnsavedResult)
        vm.confirmReplacement(token)
        assertSame(next, vm.state.value.result)
        assertEquals(2, requests.size)
    }

    @Test fun cancelledPickerOrDismissedNewPhotoNeverInvokesTheLoader() {
        val before = vm.state.value
        vm.select(context, null)
        assertSame(before, vm.state.value)
        vm.select(context, other)
        val pending = vm.state.value.replacement!!
        assertEquals(ExperimentalPhotoReplacementKind.PHOTO, pending.kind)
        assertEquals(before, vm.state.value.copy(replacement = null))
        assertEquals(1, loaded.size)
        vm.dismissReplacement(pending.token)
        assertEquals(before, vm.state.value)
        assertEquals(1, loaded.size)
    }

    @Test fun photoConfirmationLoadsOnlyTheSelectedUriOnceWithoutStartingAnAiRequest() {
        vm.select(context, other)
        val token = vm.state.value.replacement!!.token
        vm.confirmReplacement(token)
        vm.confirmReplacement(token)
        assertEquals(listOf(Uri.parse("content://synthetic/one"), other), loaded)
        assertNull(vm.state.value.result)
        assertNull(vm.state.value.replacement)
        assertSame(source, vm.state.value.source)
        assertEquals(1, requests.size)
    }

    @Test fun obsoleteDecisionCannotDismissOrExecuteANewerDecisionAfterCancellation() {
        val result = vm.state.value.result
        vm.start()
        val old = vm.state.value.replacement!!.token
        vm.cancel()
        assertNull(vm.state.value.replacement)
        vm.select(context, other)
        val current = vm.state.value.replacement!!
        assertNotEquals(old, current.token)
        vm.dismissReplacement(old)
        vm.confirmReplacement(old)
        assertEquals(current, vm.state.value.replacement)
        assertSame(result, vm.state.value.result)
        assertEquals(1, loaded.size)
        vm.confirmReplacement(current.token)
        assertEquals(2, loaded.size)
    }

    @Test fun pendingDecisionBlocksCompetingActionsAndCannotBeOverwritten() {
        vm.setEngine(ExperimentalPhotoEngine.DISTAL)
        val before = vm.state.value
        vm.start()
        vm.select(context, other)
        vm.setEngine(ExperimentalPhotoEngine.POSE)
        vm.setEngine(before.engine)
        vm.setAddress("https://example.invalid")
        assertNull(vm.prepareSave())
        assertSame(before, vm.state.value)
        assertEquals(1, requests.size)
        assertEquals(1, loaded.size)
    }

    @Test fun documentPickerWaitBlocksReplacementUntilItsCallbackAndThenAllowsADecision() {
        val ticket = vm.prepareSave()
        assertNotNull(ticket)
        val before = vm.state.value
        vm.setEngine(ExperimentalPhotoEngine.POSE)
        vm.start()
        vm.select(context, other)
        vm.setAddress("https://example.invalid")
        assertSame(before, vm.state.value)
        assertEquals(1, requests.size)
        assertEquals(1, loaded.size)
        vm.finishSave(context, null, ticket)
        assertTrue(vm.state.value.hasUnsavedResult)
        vm.start()
        assertEquals(ExperimentalPhotoReplacementKind.RUN, vm.state.value.replacement!!.kind)
    }
}
