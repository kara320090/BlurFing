package com.blurfing.app.model

/** Stores coordinates only. A new edit discards redo, and history is bounded. */
class RegionEditHistory(private val limit: Int = 30) {
    private val past = ArrayDeque<List<NormalizedRegion>>()
    private val future = ArrayDeque<List<NormalizedRegion>>()
    val canUndo get() = past.isNotEmpty()
    val canRedo get() = future.isNotEmpty()
    fun record(previous: List<NormalizedRegion>) {
        past.addLast(previous.toList())
        while (past.size > limit) past.removeFirst()
        future.clear()
    }
    fun undo(current: List<NormalizedRegion>): List<NormalizedRegion>? {
        if (past.isEmpty()) return null
        future.addLast(current.toList())
        return past.removeLast()
    }
    fun redo(current: List<NormalizedRegion>): List<NormalizedRegion>? {
        if (future.isEmpty()) return null
        past.addLast(current.toList())
        return future.removeLast()
    }
    fun clear() { past.clear(); future.clear() }
}
