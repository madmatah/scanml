package fr.scanmylib

import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.RuntimeEnvironment
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class LauncherIconTest {
    @RunWith(Enclosed::class)
    class TheLauncherIconPlaceholder {
        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheBuildTypeIsNotDev {
            private var icon by Delegates.notNull<Int>()

            @Before
            fun readTheAppIcon() {
                icon = RuntimeEnvironment.getApplication().applicationInfo.icon
            }

            @Test
            fun `should name the ic_launcher mipmap, so that the production app shows its own icon`() {
                assertEquals(R.mipmap.ic_launcher, icon)
            }
        }
    }
}
