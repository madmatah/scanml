package fr.scanmylib.update

/**
 * The updater's current attempt: a check, or a download and its install. Starting the next one
 * ends it, and an attempt that ended (canceled or replaced) no longer acts: [ifCurrent] runs code
 * for the current attempt only. What [next] and [ifCurrent] run never overlaps, so an attempt
 * never ends halfway through such a block. Thread-safe.
 */
internal class CurrentAttempt {
    private var current = 0

    /** Ends the current attempt and starts the next one, running [block] (short) as it does; returns its id. */
    @Synchronized
    fun next(block: () -> Unit = {}): Int {
        current++
        block()
        return current
    }

    /** Runs [block] (short) if the attempt [id] is still the current one; returns whether it did. */
    @Synchronized
    fun ifCurrent(id: Int, block: () -> Unit): Boolean {
        if (id != current) return false
        block()
        return true
    }
}
