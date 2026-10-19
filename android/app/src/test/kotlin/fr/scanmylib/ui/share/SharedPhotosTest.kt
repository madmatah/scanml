package fr.scanmylib.ui.share

import kotlin.properties.Delegates
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class SharedPhotosTest {
    @RunWith(Enclosed::class)
    class TheIsReadableShareFunction {
        @RunWith(Parameterized::class)
        class WhenAnotherAppsProviderSharesThePhotos(private val case: String, private val authority: String) {
            private var isReadable by Delegates.notNull<Boolean>()

            @Before
            fun receiveTheShare() {
                isReadable = isReadableShare("content", authority, OWN_PACKAGE)
            }

            @Test
            fun `should read them`() {
                assertTrue(case, isReadable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun providers(): List<Array<Any>> = listOf(
                    arrayOf("the media store", "media"),
                    arrayOf("a gallery's provider", "com.example.gallery.provider"),
                    arrayOf("another app whose name starts like this one's", "fr.scanmylib.devices"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheShareIsNoContentOfAProvider(
            private val case: String,
            private val scheme: String?,
            private val authority: String?,
        ) {
            private var isReadable by Delegates.notNull<Boolean>()

            @Before
            fun receiveTheShare() {
                isReadable = isReadableShare(scheme, authority, OWN_PACKAGE)
            }

            @Test
            fun `should never read it`() {
                assertFalse(case, isReadable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun shares(): List<Array<Any?>> = listOf(
                    arrayOf("a file", "file", null),
                    arrayOf("a file with an empty authority", "file", ""),
                    arrayOf("content without a provider", "content", null),
                    arrayOf("a web address", "http", "example.invalid"),
                    arrayOf("no scheme", null, "media"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheProviderIsThisApps(private val case: String, private val authority: String) {
            private var isReadable by Delegates.notNull<Boolean>()

            @Before
            fun receiveTheShare() {
                isReadable = isReadableShare("content", authority, OWN_PACKAGE)
            }

            @Test
            fun `should never read it, so that the app never sends its own private files to the PC`() {
                assertFalse(case, isReadable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun providers(): List<Array<Any>> = listOf(
                    arrayOf("the app's own provider", OWN_PACKAGE),
                    arrayOf("the app's startup provider", "$OWN_PACKAGE.androidx-startup"),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheAuthorityIsNoPlainProviderName(private val case: String, private val authority: String) {
            private var isReadable by Delegates.notNull<Boolean>()

            @Before
            fun receiveTheShare() {
                isReadable = isReadableShare("content", authority, OWN_PACKAGE)
            }

            @Test
            fun `should never read it, since only a plain name can be checked against the app's own`() {
                assertFalse(case, isReadable)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun authorities(): List<Array<Any>> = listOf(
                    arrayOf(
                        "a user part, which the content resolver drops to reach the app's own provider",
                        "0@$OWN_PACKAGE.androidx-startup",
                    ),
                    arrayOf("a user part before another provider", "0@media"),
                    arrayOf("a port", "media:1"),
                )
            }
        }
    }
}

private const val OWN_PACKAGE = "fr.scanmylib.dev"
