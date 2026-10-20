package fr.scanmylib.ui.components

import java.text.BreakIterator
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Before
import org.junit.Test
import org.junit.experimental.runners.Enclosed
import org.junit.runner.RunWith
import org.junit.runners.Parameterized

@RunWith(Enclosed::class)
class TextFromPcTest {
    @RunWith(Enclosed::class)
    class TheSanitizeTextFromPcFunction {
        class WhenTheTextIsShortAndPlain {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(PLAIN_MESSAGE)
            }

            @Test
            fun `should show it as the PC sent it`() {
                assertEquals(PLAIN_MESSAGE, shown)
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTextHoldsACharacterAReaderCannotSee(private val name: String, private val character: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc${character}def")
            }

            @Test
            fun `should drop it, so that it neither hides nor reorders the text around it`() {
                assertEquals(name, "abcdef", shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun characters(): List<Array<Any>> = listOf(
                    arrayOf("a left-to-right mark", makeCharacter(0x200E)),
                    arrayOf("a right-to-left mark", makeCharacter(0x200F)),
                    arrayOf("an Arabic letter mark", makeCharacter(0x061C)),
                    arrayOf("a right-to-left override", makeCharacter(0x202E)),
                    arrayOf("a left-to-right isolate", makeCharacter(0x2066)),
                    arrayOf("a zero-width space", makeCharacter(0x200B)),
                    arrayOf("a tag character", makeCharacter(0xE0041)),
                    arrayOf("a variation selector of glyphs", makeCharacter(0xFE00)),
                    arrayOf("a supplementary variation selector", makeCharacter(0xE0100)),
                    arrayOf("a combining grapheme joiner", makeCharacter(0x034F)),
                    arrayOf("a Khmer inherent vowel", makeCharacter(0x17B4)),
                    arrayOf("another Khmer inherent vowel", makeCharacter(0x17B5)),
                    arrayOf("a Mongolian free variation selector", makeCharacter(0x180B)),
                    arrayOf("the last Mongolian free variation selector", makeCharacter(0x180F)),
                    arrayOf("a Hangul filler", makeCharacter(0x3164)),
                    arrayOf("the Braille blank", makeCharacter(0x2800)),
                    arrayOf("a private-use character", makeCharacter(0xE000)),
                    arrayOf("an unassigned code point", makeCharacter(0x0378)),
                    arrayOf("a lone surrogate", makeCharacter(0xD800)),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTextHoldsACharacterThatSpellingNeeds(private val name: String, private val word: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(word)
            }

            @Test
            fun `should keep it, since it neither hides nor reorders the text around it`() {
                assertEquals(name, word, shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun words(): List<Array<Any>> = listOf(
                    arrayOf("a zero-width non-joiner, as in Persian", "abc" + ZERO_WIDTH_NON_JOINER + "def"),
                    arrayOf(
                        "a zero-width joiner, as in an emoji of a family",
                        MAN + ZERO_WIDTH_JOINER + WOMAN + ZERO_WIDTH_JOINER + GIRL,
                    ),
                    arrayOf("a family of four with skin tones, at three joiners", FAMILY_OF_FOUR_WITH_SKIN_TONES),
                    arrayOf("a kiss of two men with skin tones, at three joiners", KISS_WITH_SKIN_TONES),
                    arrayOf(
                        "a zero-width non-joiner after a virama, as in Hindi",
                        makeCharacter(0x0915) + makeCharacter(0x094D) + ZERO_WIDTH_NON_JOINER + makeCharacter(0x0937),
                    ),
                    arrayOf(
                        "a zero-width joiner after a presentation selector, as in the rainbow flag",
                        makeCharacter(0x1F3F3) + EMOJI_PRESENTATION_SELECTOR +
                            ZERO_WIDTH_JOINER + makeCharacter(0x1F308),
                    ),
                    arrayOf(
                        "the emoji presentation selector, as in a red heart",
                        RED_HEART + EMOJI_PRESENTATION_SELECTOR,
                    ),
                    arrayOf("the text presentation selector", RED_HEART + TEXT_PRESENTATION_SELECTOR),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenTheTextHoldsALineBreakOrAControl(private val name: String, private val separator: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc${separator}def")
            }

            @Test
            fun `should show it as one space, so that the text stays on one line and its words apart`() {
                assertEquals(name, "abc def", shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun separators(): List<Array<Any>> = listOf(
                    arrayOf("a line feed", makeCharacter(0x0A)),
                    arrayOf("a carriage return and a line feed", makeCharacter(0x0D) + makeCharacter(0x0A)),
                    arrayOf("a tab", makeCharacter(0x09)),
                    arrayOf("a line separator", makeCharacter(0x2028)),
                    arrayOf("a paragraph separator", makeCharacter(0x2029)),
                    arrayOf("a control between two letters", makeCharacter(0x07)),
                    arrayOf("an escape character", makeCharacter(0x1B)),
                    arrayOf("spaces of several kinds", " " + makeCharacter(0x00A0) + "  " + makeCharacter(0x3000)),
                )
            }
        }

        class WhenTheTextStartsAndEndsWithLineBreaksAndSpaces {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(LINE_BREAK + " " + PLAIN_MESSAGE + " " + LINE_BREAK + " ")
            }

            @Test
            fun `should show it without them`() {
                assertEquals(PLAIN_MESSAGE, shown)
            }

            companion object {
                private val LINE_BREAK = makeCharacter(0x0D) + makeCharacter(0x0A)
            }
        }

        class WhenALetterCarriesManyMarks {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("x" + ACUTE_ACCENT.repeat(MANY_MARKS))
            }

            @Test
            fun `should keep only the first four, so that they cannot draw over the rest of the screen`() {
                assertEquals("x" + ACUTE_ACCENT.repeat(4), shown)
            }
        }

        class WhenTheTextHasExactlyTheLimit {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(MESSAGE_AT_THE_LIMIT)
            }

            @Test
            fun `should keep it whole`() {
                assertEquals(MESSAGE_AT_THE_LIMIT, shown)
            }
        }

        class WhenTheTextIsLongerThanTheLimit {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(MESSAGE_AT_THE_LIMIT + "x")
            }

            @Test
            fun `should cut it to the limit, its last character an ellipsis, so that the cut shows`() {
                assertEquals("x".repeat(MAX_TEXT_FROM_PC_GRAPHEMES - 1) + ELLIPSIS, shown)
            }
        }

        class WhenTheCutFallsAfterASpace {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    "x".repeat(LETTERS_BEFORE_THE_CUT) + " " + "y".repeat(LETTERS_BEFORE_THE_CUT),
                )
            }

            @Test
            fun `should put the ellipsis right after the last word`() {
                assertEquals("x".repeat(LETTERS_BEFORE_THE_CUT) + ELLIPSIS, shown)
            }
        }

        class WhenTheCutFallsOnALetterWithACombiningMark {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    "x".repeat(LETTERS_BEFORE_THE_CUT) + ACCENTED_E + "y".repeat(LETTERS_BEFORE_THE_CUT),
                )
            }

            @Test
            fun `should keep the letter with its mark`() {
                assertEquals("x".repeat(LETTERS_BEFORE_THE_CUT) + ACCENTED_E + ELLIPSIS, shown)
            }
        }

        class WhenTheCutFallsOnACharacterOfTwoCodeUnits {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    "x".repeat(LETTERS_BEFORE_THE_CUT) + MUSICAL_SYMBOL + "y".repeat(LETTERS_BEFORE_THE_CUT),
                )
            }

            @Test
            fun `should keep the character whole`() {
                assertEquals("x".repeat(LETTERS_BEFORE_THE_CUT) + MUSICAL_SYMBOL + ELLIPSIS, shown)
            }

            companion object {
                private val MUSICAL_SYMBOL = makeCharacter(0x1D11E)
            }
        }

        class WhenAHugeTextStartsWithCharactersAReaderCannotSee {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(ZERO_WIDTH_SPACE.repeat(HUGE_LENGTH_CODE_UNITS) + PLAIN_MESSAGE)
            }

            @Test
            fun `should read only its start, so that a huge text costs no more than a long one`() {
                assertEquals(ELLIPSIS, shown)
            }

            companion object {
                private const val HUGE_LENGTH_CODE_UNITS = 1_000_000
            }
        }

        class WhenTheStartReadEndsInsideALetterWithAMark {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(ZERO_WIDTH_SPACE.repeat(CODE_UNITS_READ - 1) + ACCENTED_E + "x")
            }

            @Test
            fun `should leave out the letter it cannot show with its mark`() {
                assertEquals(ELLIPSIS, shown)
            }
        }

        class WhenTheStartReadEndsInsideAMarkOfTwoCodeUnits {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(ZERO_WIDTH_SPACE.repeat(CODE_UNITS_READ - 2) + "e" + COMBINING_MARK + "x")
            }

            @Test
            fun `should leave out the letter it cannot show with its mark`() {
                assertEquals(ELLIPSIS, shown)
            }

            companion object {
                private val COMBINING_MARK = makeCharacter(0x1D167)
            }
        }

        @RunWith(Parameterized::class)
        class WhenJoinersStandBetweenMarks(private val name: String, private val joiner: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("x" + (ACUTE_ACCENT.repeat(MANY_MARKS) + joiner).repeat(RUNS_OF_MARKS))
            }

            @Test
            fun `should keep four marks at most and the first joiner alone, so that no more pile up on a letter`() {
                assertEquals(name, "x" + ACUTE_ACCENT.repeat(4) + joiner, shown)
            }

            companion object {
                private const val RUNS_OF_MARKS = 20

                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun joiners(): List<Array<Any>> = listOf(
                    arrayOf("a zero-width joiner", ZERO_WIDTH_JOINER),
                    arrayOf("a zero-width non-joiner", ZERO_WIDTH_NON_JOINER),
                )
            }
        }

        class WhenAChainOfSkinTonedEmojiMakesOneLongGrapheme {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(SKIN_TONED_CHAIN_OVER_THE_BOUND)
            }

            @Test
            fun `should show nothing, since the space that replaces it would stand at an end`() {
                assertEquals("", shown)
            }
        }

        @RunWith(Parameterized::class)
        class WhenALongGraphemeIsReplaced(
            private val name: String,
            private val text: String,
            private val expectedText: String,
        ) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(text)
            }

            @Test
            fun `should put one space in its place, none at an end or by another, so that no neighbors join`() {
                assertEquals(name, expectedText, shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun replacements(): List<Array<Any>> = listOf(
                    arrayOf("between two letters", "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND + "def", "abc def"),
                    arrayOf("before two words", "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND + "def ghi", "abc def ghi"),
                    arrayOf(
                        "before a word and a space that carries a sound mark, which stays",
                        "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND + "de " + HALFWIDTH_VOICED_SOUND_MARK + "f",
                        "abc de " + HALFWIDTH_VOICED_SOUND_MARK + "f",
                    ),
                    arrayOf(
                        "before a space that carries a sound mark, which goes with the space",
                        "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND + " " + HALFWIDTH_VOICED_SOUND_MARK + "f",
                        "abc f",
                    ),
                    arrayOf(
                        "before two spaces that each carry a sound mark, which go with them",
                        "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND + " " + HALFWIDTH_VOICED_SOUND_MARK +
                            " " + HALFWIDTH_VOICED_SOUND_MARK + "f",
                        "abc f",
                    ),
                    arrayOf(
                        "at the start, before a space that carries a sound mark, which goes with the space",
                        SKIN_TONED_CHAIN_OVER_THE_BOUND + " " + HALFWIDTH_VOICED_SOUND_MARK + "f",
                        "f",
                    ),
                    arrayOf(
                        "after a letter that joins what follows it, before a space that carries sound marks, " +
                            "which go with the space",
                        DOT_REPH_AND_SOUND_MARKS_AROUND_A_LONG_GRAPHEME,
                        "a" + MALAYALAM_DOT_REPH + " b",
                    ),
                    arrayOf("between two spaces", "abc " + SKIN_TONED_CHAIN_OVER_THE_BOUND + " def", "abc def"),
                    arrayOf("at the start", SKIN_TONED_CHAIN_OVER_THE_BOUND + " def", "def"),
                    arrayOf("at the end", "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND, "abc"),
                )
            }
        }

        class WhenALetterCarriesARunOfHalfwidthSoundMarks {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc" + GRAPHEME_OVER_THE_BOUND + "def")
            }

            @Test
            fun `should replace the letter and its marks with a space, as together they make one oversized grapheme`() {
                assertEquals("abc def", shown)
            }
        }

        @RunWith(Parameterized::class)
        class WhenASpaceCarriesMoreThanAGraphemeMayHold(
            private val name: String,
            private val carriedCharacters: String,
        ) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc " + carriedCharacters + "def")
            }

            @Test
            fun `should replace the space and what it carries with one space`() {
                assertEquals(name, "abc def", shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun carriedCharacters(): List<Array<Any>> = listOf(
                    arrayOf(
                        "sound marks, over the code units of a grapheme",
                        HALFWIDTH_VOICED_SOUND_MARK.repeat(MAX_CODE_UNITS_PER_GRAPHEME),
                    ),
                    arrayOf(
                        "sound marks with non-joiners, over the joiners of a grapheme",
                        (HALFWIDTH_VOICED_SOUND_MARK + ZERO_WIDTH_NON_JOINER).repeat(MAX_JOINERS_PER_GRAPHEME + 1),
                    ),
                )
            }
        }

        class WhenAGraphemeIsExactlyAsLongAsTheBound {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc" + GRAPHEME_AT_THE_BOUND + "def")
            }

            @Test
            fun `should keep it whole`() {
                assertEquals("abc" + GRAPHEME_AT_THE_BOUND + "def", shown)
            }
        }

        @RunWith(Parameterized::class)
        class WhenAGraphemeHoldsMoreThanThreeJoiners(private val name: String, private val grapheme: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc " + grapheme + " def")
            }

            @Test
            fun `should replace it with a space, so that no grapheme shown holds more than three joiners`() {
                assertEquals(name, "abc def", shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun graphemes(): List<Array<Any>> = listOf(
                    arrayOf(
                        "five men, one joiner more than a kiss or a family holds",
                        (MAN + ZERO_WIDTH_JOINER).repeat(MAX_JOINERS_PER_GRAPHEME + 1) + MAN,
                    ),
                    arrayOf("men, as many as fit in the code units of a grapheme", joinAsManyAsFitInAGrapheme(MAN)),
                    arrayOf(
                        "hearts, as many as fit in the code units of a grapheme",
                        joinAsManyAsFitInAGrapheme(RED_HEART),
                    ),
                    arrayOf(
                        "a letter with four accents, each followed by a zero-width non-joiner",
                        "x" + (ACUTE_ACCENT + ZERO_WIDTH_NON_JOINER).repeat(4),
                    ),
                )
            }
        }

        @RunWith(Parameterized::class)
        class WhenAJoinedEmojiWithinTheBoundsStandsInASentence(private val name: String, private val emoji: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc " + emoji + " def")
            }

            @Test
            fun `should keep it whole`() {
                assertEquals(name, "abc " + emoji + " def", shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun emoji(): List<Array<Any>> = listOf(
                    arrayOf("a family of four with skin tones", FAMILY_OF_FOUR_WITH_SKIN_TONES),
                    arrayOf("a kiss of two men with skin tones", KISS_WITH_SKIN_TONES),
                )
            }
        }

        class WhenTwoJoinersFollowEachOther {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("x" + ZERO_WIDTH_JOINER + ZERO_WIDTH_JOINER + "y")
            }

            @Test
            fun `should keep the first alone, since the second has nothing to join`() {
                assertEquals("x" + ZERO_WIDTH_JOINER + "y", shown)
            }
        }

        class WhenRegionalIndicatorsStandAroundALongGrapheme {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    REGIONAL_INDICATOR_F + GRAPHEME_OVER_THE_BOUND + REGIONAL_INDICATOR_R + REGIONAL_INDICATOR_U,
                )
            }

            @Test
            fun `should keep a space where it was, so that the letters around it never pair into another flag`() {
                assertEquals(REGIONAL_INDICATOR_F + " " + REGIONAL_INDICATOR_R + REGIONAL_INDICATOR_U, shown)
            }

            companion object {
                private val REGIONAL_INDICATOR_F = makeCharacter(0x1F1EB)
                private val REGIONAL_INDICATOR_R = makeCharacter(0x1F1F7)
                private val REGIONAL_INDICATOR_U = makeCharacter(0x1F1FA)
            }
        }

        class WhenEmojiJoinedToLongGraphemesRepeat {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc((MAN + ZERO_WIDTH_JOINER + GRAPHEME_OVER_THE_BOUND).repeat(RUNS) + MAN)
            }

            @Test
            fun `should put a space in place of each long grapheme, so that the emoji around it cannot join`() {
                assertEquals((MAN + ZERO_WIDTH_JOINER + " ").repeat(RUNS) + MAN, shown)
            }

            @Test
            fun `should leave no oversized grapheme, even where the graphemes around a replaced one could join`() {
                val graphemes = splitIntoGraphemes(shown)
                assertEquals(GRAPHEMES_SHOWN, graphemes.size)
                assertEquals(emptyList<String>(), graphemes.filter(::isOversized))
            }

            companion object {
                private const val RUNS = 80
                private const val GRAPHEMES_SHOWN = RUNS * 2 + 1
            }
        }

        class WhenRunsOfHangulLeadingConsonantsAndLongGraphemesAlternate {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    (LEADING_CONSONANTS_AT_THE_BOUND + GRAPHEME_OVER_THE_BOUND).repeat(RUNS) +
                        LEADING_CONSONANTS_AT_THE_BOUND,
                )
            }

            @Test
            fun `should put a space in place of each long grapheme, so that the consonants around it cannot join`() {
                assertEquals(
                    (LEADING_CONSONANTS_AT_THE_BOUND + " ").repeat(RUNS) + LEADING_CONSONANTS_AT_THE_BOUND,
                    shown,
                )
            }

            @Test
            fun `should leave no oversized grapheme, even where the graphemes around a replaced one could join`() {
                val graphemes = splitIntoGraphemes(shown)
                assertEquals(GRAPHEMES_SHOWN, graphemes.size)
                assertEquals(emptyList<String>(), graphemes.filter(::isOversized))
            }

            companion object {
                private const val RUNS = 10
                private const val GRAPHEMES_SHOWN = RUNS * 2 + 1
                private val LEADING_CONSONANTS_AT_THE_BOUND = makeCharacter(0x1100).repeat(MAX_CODE_UNITS_PER_GRAPHEME)
            }
        }

        class WhenChainsOfJoinedEmojiAndLongGraphemesAlternate {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc((CHAIN_AT_THE_JOINER_BOUND + GRAPHEME_OVER_THE_BOUND).repeat(RUNS))
            }

            @Test
            fun `should put a space in place of each long grapheme, so that the chains around it cannot join`() {
                assertEquals(List(RUNS) { CHAIN_AT_THE_JOINER_BOUND }.joinToString(" "), shown)
            }

            @Test
            fun `should leave no oversized grapheme, even where the graphemes around a replaced one could join`() {
                val graphemes = splitIntoGraphemes(shown)
                assertEquals(GRAPHEMES_SHOWN, graphemes.size)
                assertEquals(emptyList<String>(), graphemes.filter(::isOversized))
            }

            companion object {
                private const val RUNS = 48
                private const val GRAPHEMES_SHOWN = RUNS * 2 - 1
                private val CHAIN_AT_THE_JOINER_BOUND = (MAN + ZERO_WIDTH_JOINER).repeat(MAX_JOINERS_PER_GRAPHEME)
            }
        }

        class WhenALetterJoinsTheSpaceBeforeALongGrapheme {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(DOT_REPH_AND_SOUND_MARKS_AROUND_A_LONG_GRAPHEME)
            }

            @Test
            fun `should leave no oversized grapheme, even where the graphemes around a replaced one could join`() {
                val graphemes = splitIntoGraphemes(shown)
                assertEquals(GRAPHEMES_SHOWN, graphemes.size)
                assertEquals(emptyList<String>(), graphemes.filter(::isOversized))
            }

            companion object {
                private const val GRAPHEMES_SHOWN = 3
            }
        }

        @RunWith(Parameterized::class)
        class WhenALongGraphemeIsReplacedNextToATextAtTheLimit(private val name: String, private val text: String) {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(text)
            }

            @Test
            fun `should keep the text whole, since no space takes its place at an end`() {
                assertEquals(name, MESSAGE_AT_THE_LIMIT, shown)
            }

            companion object {
                @JvmStatic
                @Parameterized.Parameters(name = "{0}")
                fun texts(): List<Array<Any>> = listOf(
                    arrayOf("before it", GRAPHEME_OVER_THE_BOUND + " " + MESSAGE_AT_THE_LIMIT),
                    arrayOf("after it", MESSAGE_AT_THE_LIMIT + " " + GRAPHEME_OVER_THE_BOUND),
                )
            }
        }

        class WhenALongGraphemeIsReplacedBeforeATextLongerThanTheLimit {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(GRAPHEME_OVER_THE_BOUND + " " + MESSAGE_AT_THE_LIMIT + "x")
            }

            @Test
            fun `should cut the text to the limit`() {
                assertEquals("x".repeat(MAX_TEXT_FROM_PC_GRAPHEMES - 1) + ELLIPSIS, shown)
            }
        }

        class WhenALongGraphemeIsReplacedInATextLongerThanTheStartRead {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    "abc" + SKIN_TONED_CHAIN_OVER_THE_BOUND + "def" + ZERO_WIDTH_SPACE.repeat(CODE_UNITS_READ),
                )
            }

            @Test
            fun `should put a space in its place, and the ellipsis after what was read`() {
                assertEquals("abc def" + ELLIPSIS, shown)
            }
        }

        class WhenTheTextHoldsOnlyJoinersAndPresentationSelectors {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(" " + JOINERS_AND_PRESENTATION_SELECTORS)
            }

            @Test
            fun `should come out empty, since nothing is left for them to join or to present`() {
                assertEquals("", shown)
            }
        }

        class WhenJoinersAndPresentationSelectorsFollowASpace {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("abc " + JOINERS_AND_PRESENTATION_SELECTORS + " def")
            }

            @Test
            fun `should drop them, since no character comes before them`() {
                assertEquals("abc def", shown)
            }
        }

        class WhenAnAccentFollowsASpace {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc("a " + ACUTE_ACCENT + "b")
            }

            @Test
            fun `should drop it, since no character comes before it`() {
                assertEquals("a b", shown)
            }
        }

        class WhenTheTextIsExactlyAsLongAsTheStartRead {
            private lateinit var shown: String

            @Before
            fun sanitizeIt() {
                shown = sanitizeTextFromPc(
                    ZERO_WIDTH_SPACE.repeat(CODE_UNITS_READ - PLAIN_MESSAGE.length) + PLAIN_MESSAGE,
                )
            }

            @Test
            fun `should read it whole, without cutting it`() {
                assertEquals(PLAIN_MESSAGE, shown)
            }
        }

        class WhenGivenTheLimitOfAPageLabel {
            private lateinit var shown: String

            @Before
            fun sanitizeALongLabel() {
                shown = sanitizeTextFromPc(MESSAGE_AT_THE_LIMIT, MAX_PAGE_LABEL_GRAPHEMES)
            }

            @Test
            fun `should cut it to that limit`() {
                assertEquals("x".repeat(MAX_PAGE_LABEL_GRAPHEMES - 1) + ELLIPSIS, shown)
            }
        }

        class WhenGivenNoRoomForACharacterBeforeTheEllipsis {
            private lateinit var act: () -> String

            @Before
            fun keepTheAct() {
                act = { sanitizeTextFromPc(PLAIN_MESSAGE, maxGraphemes = 1) }
            }

            @Test
            fun `should refuse the limit`() {
                val refusal = assertThrows(IllegalArgumentException::class.java) { act() }
                assertEquals("no room for a grapheme before the ellipsis", refusal.message)
            }
        }
    }

    class TheMaxTextFromPcGraphemesConstant {
        @Test
        fun `should hold a whole title, which the api caps at 300 characters`() {
            assertEquals(300, MAX_TEXT_FROM_PC_GRAPHEMES)
        }
    }

    class TheMaxPageLabelGraphemesConstant {
        @Test
        fun `should hold the two numbers of a spread, short enough for the chip over a page`() {
            assertEquals(16, MAX_PAGE_LABEL_GRAPHEMES)
        }
    }

    class TheMaxCodeUnitsPerGraphemeConstant {
        @Test
        fun `should allow 24 code units, which a kiss and a family of four with skin tones fit in`() {
            assertEquals(24, MAX_CODE_UNITS_PER_GRAPHEME)
        }
    }

    class TheMaxJoinersPerGraphemeConstant {
        @Test
        fun `should allow three joiners, as many as a kiss or a family of four holds`() {
            assertEquals(3, MAX_JOINERS_PER_GRAPHEME)
        }
    }
}

private const val ELLIPSIS = "…"
private const val PLAIN_MESSAGE = "HTTP 503: text recognition is not ready"
private val MESSAGE_AT_THE_LIMIT = "x".repeat(MAX_TEXT_FROM_PC_GRAPHEMES)

// The character at the cut is the last one kept before the ellipsis.
private const val LETTERS_BEFORE_THE_CUT = MAX_TEXT_FROM_PC_GRAPHEMES - 2

private val ZERO_WIDTH_SPACE = makeCharacter(0x200B)
private val ZERO_WIDTH_NON_JOINER = makeCharacter(0x200C)
private val ZERO_WIDTH_JOINER = makeCharacter(0x200D)
private val TEXT_PRESENTATION_SELECTOR = makeCharacter(0xFE0E)
private val EMOJI_PRESENTATION_SELECTOR = makeCharacter(0xFE0F)
private val JOINERS_AND_PRESENTATION_SELECTORS =
    ZERO_WIDTH_NON_JOINER + ZERO_WIDTH_JOINER + TEXT_PRESENTATION_SELECTOR + EMOJI_PRESENTATION_SELECTOR
private val JOINERS = setOf(ZERO_WIDTH_JOINER, ZERO_WIDTH_NON_JOINER)
private const val MANY_MARKS = 20
private const val CODE_UNITS_READ = MAX_TEXT_FROM_PC_GRAPHEMES * CODE_UNITS_READ_PER_GRAPHEME
private val ACUTE_ACCENT = makeCharacter(0x0301)
private val MAN = makeCharacter(0x1F468)
private val WOMAN = makeCharacter(0x1F469)
private val GIRL = makeCharacter(0x1F467)
private val BOY = makeCharacter(0x1F466)
private val SKIN_TONE = makeCharacter(0x1F3FD)
private val RED_HEART = makeCharacter(0x2764)
private val KISS_MARK = makeCharacter(0x1F48B)
private val FAMILY_OF_FOUR_WITH_SKIN_TONES =
    MAN + SKIN_TONE + ZERO_WIDTH_JOINER + WOMAN + SKIN_TONE + ZERO_WIDTH_JOINER +
        GIRL + SKIN_TONE + ZERO_WIDTH_JOINER + BOY + SKIN_TONE
private val KISS_WITH_SKIN_TONES =
    MAN + SKIN_TONE + ZERO_WIDTH_JOINER + RED_HEART + EMOJI_PRESENTATION_SELECTOR + ZERO_WIDTH_JOINER +
        KISS_MARK + ZERO_WIDTH_JOINER + MAN + SKIN_TONE
private val SKIN_TONED_CHAIN_OVER_THE_BOUND =
    (MAN + SKIN_TONE + ZERO_WIDTH_JOINER).repeat(MAX_CODE_UNITS_PER_GRAPHEME) + MAN
private val HALFWIDTH_KA = makeCharacter(0xFF76)
private val HALFWIDTH_VOICED_SOUND_MARK = makeCharacter(0xFF9E)
private val GRAPHEME_AT_THE_BOUND = HALFWIDTH_KA + HALFWIDTH_VOICED_SOUND_MARK.repeat(MAX_CODE_UNITS_PER_GRAPHEME - 1)
private val GRAPHEME_OVER_THE_BOUND = GRAPHEME_AT_THE_BOUND + HALFWIDTH_VOICED_SOUND_MARK
private val MALAYALAM_DOT_REPH = makeCharacter(0x0D4E)
private val SPACE_WITH_SOUND_MARKS_AT_THE_BOUND =
    " " + HALFWIDTH_VOICED_SOUND_MARK.repeat(MAX_CODE_UNITS_PER_GRAPHEME - 1)
private val DOT_REPH_AND_SOUND_MARKS_AROUND_A_LONG_GRAPHEME =
    "a" + MALAYALAM_DOT_REPH + " " + GRAPHEME_OVER_THE_BOUND + SPACE_WITH_SOUND_MARKS_AT_THE_BOUND + "b"
private val ACCENTED_E = "e" + ACUTE_ACCENT

private fun makeCharacter(codePoint: Int): String = String(Character.toChars(codePoint))

private fun joinAsManyAsFitInAGrapheme(emoji: String): String {
    val linkCount = (MAX_CODE_UNITS_PER_GRAPHEME - emoji.length) / (emoji.length + ZERO_WIDTH_JOINER.length)
    return (emoji + ZERO_WIDTH_JOINER).repeat(linkCount) + emoji
}

private fun splitIntoGraphemes(text: String): List<String> {
    val graphemes: BreakIterator = BreakIterator.getCharacterInstance().apply { setText(text) }
    val boundaries = generateSequence(graphemes.first()) { graphemes.next().takeIf { it != BreakIterator.DONE } }
    return boundaries.zipWithNext { start, end -> text.substring(start, end) }.toList()
}

private fun isOversized(grapheme: String): Boolean = grapheme.length > MAX_CODE_UNITS_PER_GRAPHEME ||
    grapheme.count { it.toString() in JOINERS } > MAX_JOINERS_PER_GRAPHEME
