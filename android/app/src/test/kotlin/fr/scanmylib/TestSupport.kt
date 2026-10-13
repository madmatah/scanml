package fr.scanmylib

/** Runs [block], which must throw a [T]; returns it. Inline so that [block] may suspend. */
inline fun <reified T : Throwable> expectFailure(block: () -> Unit): T {
    try {
        block()
    } catch (e: Throwable) {
        if (e is T) return e
        throw AssertionError("expected ${T::class.java.simpleName}, got $e", e)
    }
    throw AssertionError("expected ${T::class.java.simpleName}, nothing was thrown")
}
