package fr.scanmylib.ui.capture

import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.DisposableEffect
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.compose.ui.test.junit4.ComposeContentTestRule
import androidx.compose.ui.test.junit4.v2.createComposeRule
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleOwner
import androidx.lifecycle.LifecycleRegistry
import androidx.lifecycle.compose.LocalLifecycleOwner
import org.junit.Assert.assertEquals
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.robolectric.ParameterizedRobolectricTestRunner
import org.robolectric.RobolectricTestRunner
import org.robolectric.annotation.Config

@RunWith(Enclosed::class)
class CameraCloseEffectTest {
    @RunWith(Enclosed::class)
    class TheCameraCloseEffectFunction {
        @RunWith(ParameterizedRobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheScreenMovesAroundTheClose(private val row: String, private val interleaving: Interleaving) {
            enum class Interleaving(
                val phrase: String,
                val expectedClosings: List<Boolean>,
                val expectedHandledCloses: List<CameraClose>,
                private val steps: (ComposeContentTestRule) -> CameraScreenUnderTest,
            ) {
                SET_WHILE_STARTED("the close is set while the screen is only started", NOT_TRIED, NOT_HANDLED, {
                    showTheCameraScreen(it, Lifecycle.State.STARTED).apply { setTheClose(it, this) }
                }),
                SET_WHILE_RESUMED("the close is set while the screen is resumed", TRIED_ONCE, HANDLED_ONCE, {
                    showTheCameraScreen(it, Lifecycle.State.RESUMED).apply { setTheClose(it, this) }
                }),
                SET_WHILE_STARTED_THEN_RESUMED(
                    "the close is set while the screen is only started, then the screen resumes",
                    TRIED_ONCE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(it, Lifecycle.State.STARTED).apply {
                            setTheClose(it, this)
                            moveTheScreen(it, this, Lifecycle.State.RESUMED)
                        }
                    },
                ),
                SET_WHILE_STARTED_THEN_STOPPED(
                    "the close is set while the screen is only started, then the screen stops",
                    NOT_TRIED,
                    NOT_HANDLED,
                    {
                        showTheCameraScreen(it, Lifecycle.State.STARTED).apply {
                            setTheClose(it, this)
                            moveTheScreen(it, this, Lifecycle.State.CREATED)
                        }
                    },
                ),
                PAUSED_BEFORE_THE_ATTEMPT(
                    "the screen pauses before the attempt runs, and stays paused",
                    NOT_TRIED,
                    NOT_HANDLED,
                    {
                        showTheCameraScreen(it, Lifecycle.State.RESUMED).apply {
                            setTheClose(it, this, moveBeforeTheAttempt(lifecycle, Lifecycle.State.STARTED))
                        }
                    },
                ),
                PAUSED_AND_RESUMED_DURING_THE_CALL(
                    "the screen pauses during the call, which the nav host refuses, and resumes before it returns",
                    TRIED_TWICE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(
                            it,
                            Lifecycle.State.RESUMED,
                            pauseDuringTheFirstCall = PauseDuringACall.RESUMED_BEFORE_IT_RETURNS,
                        ).apply {
                            setTheClose(it, this)
                        }
                    },
                ),
                PAUSED_DURING_THE_CALL_THEN_RESUMED(
                    "the screen pauses during the call, which the nav host refuses, and resumes a frame later",
                    TRIED_TWICE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(
                            it,
                            Lifecycle.State.RESUMED,
                            pauseDuringTheFirstCall = PauseDuringACall.KEPT_AFTER_IT_RETURNS,
                        ).apply {
                            setTheClose(it, this)
                            moveTheScreen(it, this, Lifecycle.State.RESUMED)
                        }
                    },
                ),
                RESUMED_THEN_PAUSED_AND_RESUMED_DURING_THE_CALL(
                    "the close is set while the screen is only started, then the screen resumes, pauses during " +
                        "the call and resumes before it returns",
                    TRIED_TWICE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(
                            it,
                            Lifecycle.State.STARTED,
                            pauseDuringTheFirstCall = PauseDuringACall.RESUMED_BEFORE_IT_RETURNS,
                        ).apply {
                            setTheClose(it, this)
                            moveTheScreen(it, this, Lifecycle.State.RESUMED)
                        }
                    },
                ),
                PAUSED_BEFORE_THE_ATTEMPT_AND_RESUMED_BEFORE_THE_NEXT_FRAME(
                    "the screen pauses before the attempt runs, and resumes before the next frame",
                    TRIED_ONCE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(it, Lifecycle.State.RESUMED).apply {
                            setTheClose(it, this, moveBeforeTheAttemptThenBack(lifecycle, Lifecycle.State.STARTED))
                        }
                    },
                ),
                STOPPED_BEFORE_THE_ATTEMPT_THEN_STARTED(
                    "the screen stops before the attempt runs, then starts and resumes",
                    TRIED_ONCE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(it, Lifecycle.State.RESUMED).apply {
                            setTheClose(it, this, moveBeforeTheAttempt(lifecycle, Lifecycle.State.CREATED))
                            moveTheScreen(it, this, Lifecycle.State.STARTED)
                            moveTheScreen(it, this, Lifecycle.State.RESUMED)
                        }
                    },
                ),
                SET_WHILE_STARTED_THEN_STOPPED_AND_STARTED(
                    "the close is set while the screen is only started, then the screen stops, starts and resumes",
                    TRIED_ONCE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreen(it, Lifecycle.State.STARTED).apply {
                            setTheClose(it, this)
                            moveTheScreen(it, this, Lifecycle.State.CREATED)
                            moveTheScreen(it, this, Lifecycle.State.STARTED)
                            moveTheScreen(it, this, Lifecycle.State.RESUMED)
                        }
                    },
                ),
                COMPOSED_WITH_THE_CLOSE_WHILE_RESUMED(
                    "the screen is composed anew, already resumed, while the close is set",
                    TRIED_ONCE,
                    HANDLED_ONCE,
                    { showTheCameraScreenClosing(it, Lifecycle.State.RESUMED) },
                ),
                COMPOSED_WITH_THE_CLOSE_WHILE_STARTED_THEN_RESUMED(
                    "the screen is composed anew, only started, while the close is set, then resumes",
                    TRIED_ONCE,
                    HANDLED_ONCE,
                    {
                        showTheCameraScreenClosing(it, Lifecycle.State.STARTED).apply {
                            moveTheScreen(it, this, Lifecycle.State.RESUMED)
                        }
                    },
                ),
                ;

                internal fun play(compose: ComposeContentTestRule): CameraScreenUnderTest = steps(compose)
            }

            @get:Rule
            val compose = createComposeRule()

            private lateinit var statesAtTheCalls: List<Lifecycle.State>
            private lateinit var closings: List<Boolean>
            private lateinit var handledCloses: List<CameraClose>

            @Before
            fun playTheInterleaving() {
                val screen = interleaving.play(compose)
                compose.waitForIdle()
                statesAtTheCalls = screen.statesAtTheCalls.toList()
                closings = screen.closings.toList()
                handledCloses = screen.handledCloses.toList()
            }

            @Test
            fun `should never ask the nav host to close a screen that is not in front`() {
                val callsBelowResumed = statesAtTheCalls.filterNot { it.isAtLeast(Lifecycle.State.RESUMED) }
                assertEquals(row, emptyList<Lifecycle.State>(), callsBelowResumed)
            }

            @Test
            fun `should try the close each time the screen comes to the front, until the nav host closes it`() {
                assertEquals(row, interleaving.expectedClosings, closings)
            }

            @Test
            fun `should report the close handled once the screen closed, and never while it is not in front`() {
                assertEquals(row, interleaving.expectedHandledCloses, handledCloses)
            }

            companion object {
                @JvmStatic
                @ParameterizedRobolectricTestRunner.Parameters(name = "{0}")
                fun rows(): List<Array<Any>> = Interleaving.entries.map { arrayOf(it.phrase, it) }
            }
        }

        @RunWith(RobolectricTestRunner::class)
        @Config(sdk = [36])
        class WhenTheCloseKeepsThePhotos {
            @get:Rule
            val compose = createComposeRule()

            private lateinit var closings: List<Boolean>

            @Before
            fun setTheClose() {
                val screen = showTheCameraScreen(compose, Lifecycle.State.RESUMED)
                setTheClose(compose, screen, close = CameraClose(werePhotosKept = true))
                closings = screen.closings.toList()
            }

            @Test
            fun `should tell the nav host that the photos were kept`() {
                assertEquals(listOf(true), closings)
            }
        }
    }
}

private val DISCARDED = CameraClose(werePhotosKept = false)
private val NOT_TRIED = emptyList<Boolean>()
private val TRIED_ONCE = listOf(DISCARDED.werePhotosKept)
private val TRIED_TWICE = listOf(DISCARDED.werePhotosKept, DISCARDED.werePhotosKept)
private val NOT_HANDLED = emptyList<CameraClose>()
private val HANDLED_ONCE = listOf(DISCARDED)

// Internal, not private: the public table returns the screen to its group, and these types show in its members.
internal class ScreenLifecycle(state: Lifecycle.State) : LifecycleOwner {
    private val registry = LifecycleRegistry.createUnsafe(this).apply { currentState = state }

    override val lifecycle: Lifecycle get() = registry

    val currentState: Lifecycle.State get() = registry.currentState

    fun moveTo(state: Lifecycle.State) {
        registry.currentState = state
    }
}

internal enum class PauseDuringACall { NONE, RESUMED_BEFORE_IT_RETURNS, KEPT_AFTER_IT_RETURNS }

internal class CameraScreenUnderTest(
    val lifecycle: ScreenLifecycle,
    private var pauseDuringTheNextCall: PauseDuringACall,
) {
    var closing by mutableStateOf<CameraClose?>(null)
    var aroundTheAttempt by mutableStateOf<@Composable () -> Unit>({})
    val statesAtTheCalls = mutableListOf<Lifecycle.State>()
    val closings = mutableListOf<Boolean>()
    val handledCloses = mutableListOf<CameraClose>()

    fun closeAsTheNavHostDoes(werePhotosKept: Boolean): Boolean {
        statesAtTheCalls += lifecycle.currentState
        closings += werePhotosKept
        val pauseDuringThisCall = pauseDuringTheNextCall
        pauseDuringTheNextCall = PauseDuringACall.NONE
        val stateBeforeTheCall = lifecycle.currentState
        val stateAfterARefusal = when (pauseDuringThisCall) {
            PauseDuringACall.NONE, PauseDuringACall.RESUMED_BEFORE_IT_RETURNS -> stateBeforeTheCall
            PauseDuringACall.KEPT_AFTER_IT_RETURNS -> Lifecycle.State.STARTED
        }
        if (pauseDuringThisCall != PauseDuringACall.NONE) lifecycle.moveTo(Lifecycle.State.STARTED)
        val isClosed = lifecycle.currentState.isAtLeast(Lifecycle.State.RESUMED)
        lifecycle.moveTo(if (isClosed) Lifecycle.State.CREATED else stateAfterARefusal)
        return isClosed
    }

    fun handle(close: CameraClose) {
        handledCloses += close
        if (closing == close && lifecycle.currentState.isAtLeast(Lifecycle.State.STARTED)) closing = null
    }
}

private fun createTheCameraScreen(state: Lifecycle.State, pauseDuringTheFirstCall: PauseDuringACall) =
    CameraScreenUnderTest(ScreenLifecycle(state), pauseDuringTheFirstCall)

private fun composeTheCameraScreen(compose: ComposeContentTestRule, screen: CameraScreenUnderTest) {
    compose.setContent {
        CompositionLocalProvider(LocalLifecycleOwner provides screen.lifecycle) {
            CameraCloseEffect(
                closing = screen.closing,
                onClose = screen::closeAsTheNavHostDoes,
                onCloseHandled = screen::handle,
            )
            screen.aroundTheAttempt()
        }
    }
    compose.waitForIdle()
}

private fun showTheCameraScreen(
    compose: ComposeContentTestRule,
    state: Lifecycle.State,
    pauseDuringTheFirstCall: PauseDuringACall = PauseDuringACall.NONE,
): CameraScreenUnderTest =
    createTheCameraScreen(state, pauseDuringTheFirstCall).apply { composeTheCameraScreen(compose, this) }

private fun showTheCameraScreenClosing(compose: ComposeContentTestRule, state: Lifecycle.State): CameraScreenUnderTest =
    createTheCameraScreen(state, PauseDuringACall.NONE).apply {
        closing = DISCARDED
        composeTheCameraScreen(compose, this)
    }

private fun setTheClose(
    compose: ComposeContentTestRule,
    screen: CameraScreenUnderTest,
    aroundTheAttempt: @Composable () -> Unit = {},
    close: CameraClose = DISCARDED,
) {
    compose.runOnIdle {
        screen.closing = close
        screen.aroundTheAttempt = aroundTheAttempt
    }
    compose.waitForIdle()
}

private fun moveTheScreen(compose: ComposeContentTestRule, screen: CameraScreenUnderTest, state: Lifecycle.State) {
    compose.runOnIdle { screen.lifecycle.moveTo(state) }
    compose.waitForIdle()
}

// A DisposableEffect runs once the frame's effects are launched, before any of them runs.
private fun moveBeforeTheAttempt(lifecycle: ScreenLifecycle, state: Lifecycle.State): @Composable () -> Unit = {
    DisposableEffect(Unit) {
        lifecycle.moveTo(state)
        onDispose {}
    }
}

// The LaunchedEffect runs after the attempt, launched before it, and before the next frame.
private fun moveBeforeTheAttemptThenBack(lifecycle: ScreenLifecycle, state: Lifecycle.State): @Composable () -> Unit = {
    val stateToComeBackTo = lifecycle.currentState
    DisposableEffect(Unit) {
        lifecycle.moveTo(state)
        onDispose {}
    }
    LaunchedEffect(Unit) { lifecycle.moveTo(stateToComeBackTo) }
}
