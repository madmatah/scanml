package fr.scanmylib.update

import java.util.Collections
import java.util.concurrent.CountDownLatch
import kotlin.concurrent.thread
import kotlin.properties.Delegates
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith

@RunWith(Enclosed::class)
class CurrentAttemptTest {
    @RunWith(Enclosed::class)
    class TheIfCurrentMethod {
        class WhenTheAttemptIsCurrent {
            private var hasRunTheBlock by Delegates.notNull<Boolean>()
            private var saysItRan by Delegates.notNull<Boolean>()

            @Before
            fun actForTheAttempt() {
                val attempts = CurrentAttempt()
                val first = attempts.next()
                var hasRun = false
                saysItRan = attempts.ifCurrent(first) { hasRun = true }
                hasRunTheBlock = hasRun
            }

            @Test
            fun `should run the block`() {
                assertTrue(hasRunTheBlock)
            }

            @Test
            fun `should say it ran the block`() {
                assertTrue(saysItRan)
            }
        }

        class WhenTheAttemptHasEnded {
            private var hasRunTheBlock by Delegates.notNull<Boolean>()
            private var saysItRan by Delegates.notNull<Boolean>()

            @Before
            fun actForTheEndedAttempt() {
                val attempts = CurrentAttempt()
                val first = attempts.next()
                attempts.next()
                var hasRun = false
                saysItRan = attempts.ifCurrent(first) { hasRun = true }
                hasRunTheBlock = hasRun
            }

            @Test
            fun `should not run the block, since an attempt that ended no longer acts`() {
                assertFalse(hasRunTheBlock)
            }

            @Test
            fun `should say it did not run the block`() {
                assertFalse(saysItRan)
            }
        }

        class WhenTheNextAttemptIsCurrent {
            private var hasRunTheBlock by Delegates.notNull<Boolean>()
            private var saysItRan by Delegates.notNull<Boolean>()

            @Before
            fun actForTheNextAttempt() {
                val attempts = CurrentAttempt()
                attempts.next()
                val second = attempts.next()
                var hasRun = false
                saysItRan = attempts.ifCurrent(second) { hasRun = true }
                hasRunTheBlock = hasRun
            }

            @Test
            fun `should run the block`() {
                assertTrue(hasRunTheBlock)
            }

            @Test
            fun `should say it ran the block`() {
                assertTrue(saysItRan)
            }
        }
    }

    @RunWith(Enclosed::class)
    class TheNextMethod {
        class WhenAStepOfTheAttemptIsUnderWay {
            private lateinit var events: List<String>

            @Before
            fun cancelDuringTheStep() {
                val attempts = CurrentAttempt()
                val id = attempts.next()
                val recordedEvents = Collections.synchronizedList(mutableListOf<String>())
                val stepStarted = CountDownLatch(1)
                val stepMayEnd = CountDownLatch(1)
                val step = thread {
                    attempts.ifCurrent(id) {
                        stepStarted.countDown()
                        stepMayEnd.await()
                        recordedEvents += "step"
                    }
                }
                stepStarted.await()
                val cancel = thread { attempts.next { recordedEvents += "canceled" } }
                while (cancel.isAlive && cancel.state != Thread.State.BLOCKED) Thread.yield()
                stepMayEnd.countDown()
                step.join()
                cancel.join()
                events = recordedEvents.toList()
            }

            @Test
            fun `should end the attempt only once the step is over, never halfway through it`() {
                assertEquals(listOf("step", "canceled"), events)
            }
        }
    }
}
