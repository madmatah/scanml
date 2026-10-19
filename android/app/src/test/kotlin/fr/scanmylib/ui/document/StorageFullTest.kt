package fr.scanmylib.ui.document

import java.io.IOException
import kotlin.properties.Delegates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class StorageFullTest {
    @RunWith(Enclosed::class)
    class TheIsStorageFullFunction {
        @RunWith(Parameterized::class)
        class WhenTheFailureSaysNoSpaceIsLeft(private val case: String, private val error: Throwable) {
            private var isStorageFull by Delegates.notNull<Boolean>()

            @Before
            fun readTheFailure() {
                isStorageFull = error.isStorageFull()
            }

            @Test
            fun `should tell a full storage apart from other failures`() {
                assertTrue(case, isStorageFull)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun failures(): List<Array<Any>> = listOf(
                    arrayOf(
                        "a write with no space left",
                        IOException("write failed: ENOSPC (No space left on device)"),
                    ),
                    arrayOf(
                        "a failure caused by a write with no space left",
                        IllegalStateException("could not copy", IOException("write failed: ENOSPC")),
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheFailureHasAnotherCause(private val case: String, private val error: Throwable) {
            private var isStorageFull by Delegates.notNull<Boolean>()

            @Before
            fun readTheFailure() {
                isStorageFull = error.isStorageFull()
            }

            @Test
            fun `should not take it for a full storage`() {
                assertFalse(case, isStorageFull)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun failures(): List<Array<Any>> = listOf(
                    arrayOf("an I/O error", IOException("read failed: EIO (I/O error)")),
                    arrayOf("a refused access", SecurityException()),
                )
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheIsStorageLowFunction {
        @RunWith(Parameterized::class)
        class WhenLittleSpaceIsFree(private val case: String, private val freeBytes: Long) {
            private var isStorageLow by Delegates.notNull<Boolean>()

            @Before
            fun measureTheSpace() {
                isStorageLow = isStorageLow(freeBytes)
            }

            @Test
            fun `should be low, so that an empty result of Google's scanner is reported as a full storage`() {
                assertTrue(case, isStorageLow)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun spaces(): List<Array<Any>> = listOf(
                    arrayOf("nothing free", 0L),
                    arrayOf("20 MiB free", 20L * MEBIBYTE_IN_BYTES),
                )
            }
        }

        class WhenGigabytesAreFree {
            private var isStorageLow by Delegates.notNull<Boolean>()

            @Before
            fun measureTheSpace() {
                isStorageLow = isStorageLow(2L * GIBIBYTE_IN_BYTES)
            }

            @Test
            fun `should not be low, so that an empty result of Google's scanner is never reported`() {
                assertFalse(isStorageLow)
            }
        }
    }
}

private const val MEBIBYTE_IN_BYTES = 1024L * 1024
private const val GIBIBYTE_IN_BYTES = 1024L * MEBIBYTE_IN_BYTES
