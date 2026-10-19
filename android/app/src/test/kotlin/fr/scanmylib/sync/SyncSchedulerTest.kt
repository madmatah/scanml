package fr.scanmylib.sync

import androidx.work.ExistingWorkPolicy
import androidx.work.WorkInfo.State
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class SyncSchedulerTest {
    @RunWith(Enclosed::class)
    class TheEnqueuePolicyFunction {
        @RunWith(Parameterized::class)
        class WhenNoRunIsRunning(private val case: String, private val states: List<State>) {
            private lateinit var enqueuing: Enqueuing

            @Before
            fun requestARun() {
                enqueuing = Enqueuing(enqueuePolicy(states))
            }

            @Test
            fun `should start a run right away`() {
                assertEquals(case, ExistingWorkPolicy.REPLACE, enqueuing.policy)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun runs(): List<Array<Any>> = listOf(
                    arrayOf("no run", emptyList<State>()),
                    arrayOf("a run that succeeded", listOf(State.SUCCEEDED)),
                    arrayOf("runs that failed", listOf(State.FAILED, State.FAILED)),
                    arrayOf(
                        "a run waiting for the network or a backoff delay, which starts over without the delay",
                        listOf(State.ENQUEUED),
                    ),
                )
            }
        }

        class WhenARunIsRunning {
            private lateinit var enqueuing: Enqueuing

            @Before
            fun requestARun() {
                enqueuing = Enqueuing(enqueuePolicy(listOf(State.RUNNING)))
            }

            @Test
            fun `should queue one follow-up run behind it`() {
                assertEquals(ExistingWorkPolicy.APPEND_OR_REPLACE, enqueuing.policy)
            }
        }

        @RunWith(Parameterized::class)
        class WhenARunIsRunningAndAFollowUpIsQueued(private val case: String, private val states: List<State>) {
            private lateinit var enqueuing: Enqueuing

            @Before
            fun requestARun() {
                enqueuing = Enqueuing(enqueuePolicy(states))
            }

            @Test
            fun `should queue no other run`() {
                assertNull(case, enqueuing.policy)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun followUps(): List<Array<Any>> = listOf(
                    arrayOf("blocked behind the running one", listOf(State.RUNNING, State.BLOCKED)),
                    arrayOf("waiting to start", listOf(State.RUNNING, State.ENQUEUED)),
                )
            }
        }
    }
}

private data class Enqueuing(val policy: ExistingWorkPolicy?)
