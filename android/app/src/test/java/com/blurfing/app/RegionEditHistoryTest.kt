package com.blurfing.app

import com.blurfing.app.model.NormalizedRegion
import com.blurfing.app.model.RegionEditHistory
import org.junit.Assert.*
import org.junit.Test

class RegionEditHistoryTest {
    private val region = NormalizedRegion(.1f,.2f,.2f,.3f)
    @Test fun editUndoRedoAndNewEditDropsRedo() {
        val history = RegionEditHistory()
        history.record(emptyList())
        assertEquals(emptyList<NormalizedRegion>(), history.undo(listOf(region)))
        assertEquals(listOf(region), history.redo(emptyList()))
        history.undo(listOf(region))
        history.record(emptyList())
        assertFalse(history.canRedo)
    }
    @Test fun capacityAndNewPhotoClearHistory() {
        val history = RegionEditHistory(2)
        history.record(emptyList()); history.record(listOf(region)); history.record(emptyList())
        assertNotNull(history.undo(listOf(region)))
        assertNotNull(history.undo(emptyList()))
        assertNull(history.undo(listOf(region)))
        history.clear()
        assertFalse(history.canUndo); assertFalse(history.canRedo)
    }
}
