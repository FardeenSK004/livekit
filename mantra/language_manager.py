"""
Production-Grade Multilingual Language Manager for Mantra Voice Agent.

Architecture:
- LanguageIntentParser: Semantic token-based intent analyzer for explicit language switch requests.
- NativeLanguageDetector: Unicode script block inspector & langdetect fallback.
- PhoneticClassifier: Subword character 3-gram classifier for Romanized Indian speech.
- LanguageHysteresisTracker: Hysteresis state machine for stability and code-switching tolerance.
- LanguageManager: High-level pipeline coordinator for STT/TTS and system prompts.
"""

import asyncio
import logging
import time
from typing import Dict, List, Optional, Tuple, Set
import langdetect

from livekit.agents import stt, utils
from livekit.agents.language import LanguageCode
from livekit.agents.types import APIConnectOptions, DEFAULT_API_CONNECT_OPTIONS, NOT_GIVEN, NotGivenOr
from livekit.plugins import deepgram

logger = logging.getLogger("mantra.language_manager")

SUPPORTED_LANGUAGES: Set[str] = {"en", "hi", "kn", "te", "mr"}

LANGUAGE_NAMES: Dict[str, str] = {
    "en": "English",
    "hi": "Hindi",
    "kn": "Kannada",
    "te": "Telugu",
    "mr": "Marathi",
}

NATIVE_SCRIPTS: Dict[str, str] = {
    "en": "Latin",
    "hi": "Devanagari (हिन्दी)",
    "kn": "Kannada (ಕನ್ನಡ)",
    "te": "Telugu (తెలుగు)",
    "mr": "Devanagari (मराठी)",
}

# ── 1. Semantic Token Intent Parser ──────────────────────────────────────

class LanguageIntentParser:
    """
    Parses explicit language switch requests using clean semantic token matching.
    Avoids brittle regex string constructions or hardcoded string lists.
    """

    LANGUAGE_ENTITIES: Dict[str, str] = {
        "kannada": "kn", "kan": "kn", "ಕನ್ನಡ": "kn",
        "telugu": "te", "tel": "te", "తెలుగు": "te",
        "hindi": "hi", "hin": "hi", "हिंदी": "hi", "हिन्दी": "hi",
        "marathi": "mr", "mar": "mr", "मराठी": "mr",
        "english": "en", "eng": "en",
    }

    INTENT_INDICATORS: Set[str] = {
        "speak", "talk", "continue", "switch", "use", "baat", "bolo",
        "bolie", "mathadi", "matladandi", "bola", "please", "can", "let's"
    }

    def parse_explicit_intent(self, text: str) -> Optional[str]:
        """Detects if an utterance expresses an explicit request to switch language."""
        text_lower = text.lower().strip()
        words = [w.strip(".,!?-':;()\"") for w in text_lower.split() if w.strip(".,!?-':;()\"")]
        if not words:
            return None

        # 1. Identify target language entity
        target_code = None
        for word in words:
            for entity, code in self.LANGUAGE_ENTITIES.items():
                if word == entity or word.startswith(entity):
                    target_code = code
                    break
            if target_code:
                break

        if not target_code:
            return None

        # 2. Verify if the utterance expresses a switch directive
        has_intent_word = any(w in self.INTENT_INDICATORS for w in words)
        is_short_directive = len(words) <= 5

        if has_intent_word or is_short_directive:
            logger.info(f"[LANG] Explicit language switch intent parsed: '{text}' -> {target_code}")
            return target_code

        return None


# ── 2. Native Script & Block Inspector ───────────────────────────────────

class NativeLanguageDetector:
    """
    Deterministic Unicode script block profiling & statistical ML language detection.
    Operates without hardcoded keyword dictionaries.
    """

    def detect(self, text: str, current_lang: str) -> Tuple[Optional[str], float]:
        """Detects language code and confidence for native scripts."""
        counts = {"devanagari": 0, "kannada": 0, "telugu": 0, "latin": 0}
        for ch in text:
            code = ord(ch)
            if 0x0900 <= code <= 0x097F:
                counts["devanagari"] += 1
            elif 0x0C80 <= code <= 0x0CFF:
                counts["kannada"] += 1
            elif 0x0C00 <= code <= 0x0C7F:
                counts["telugu"] += 1
            elif (0x0041 <= code <= 0x005A) or (0x0061 <= code <= 0x007A):
                counts["latin"] += 1

        total = sum(counts.values())
        if total == 0:
            return None, 0.0

        if counts["kannada"] > 0 and counts["kannada"] >= max(counts["devanagari"], counts["telugu"]):
            return "kn", counts["kannada"] / total

        if counts["telugu"] > 0 and counts["telugu"] >= max(counts["devanagari"], counts["kannada"]):
            return "te", counts["telugu"] / total

        if counts["devanagari"] > 0:
            ratio = counts["devanagari"] / total
            try:
                detected = langdetect.detect(text)
                if detected in ["mr", "hi"]:
                    return detected, ratio
            except Exception:
                pass
            return current_lang if current_lang in ["hi", "mr"] else "hi", ratio

        if counts["latin"] > 0:
            return "latin", counts["latin"] / total

        return None, 0.0


# ── 3. Subword Phonetic Classifier ───────────────────────────────────────

class PhoneticClassifier:
    """
    Subword character trigram log-likelihood classifier for Romanized Indian speech.
    """

    TRIGRAMS: Dict[str, Set[str]] = {
        "kn": {"nan", "ang", "bek", "tha", "mat", "adb", "nam", "ell", "iga", "ide", "eya", "rut", "got"},
        "hi": {"muj", "ujh", "jhe", "kar", "arn", "cha", "ahi", "hai", "hoo", "rah", "thi", "kya", "aap"},
        "te": {"naa", "aak", "aku", "kav", "val", "ali", "che", "eyl", "und", "ndi", "elg", "tel"},
        "mr": {"mal", "ala", "pah", "ahi", "ije", "mha", "anj", "kas", "bol", "tay", "lta", "lte"},
    }

    def classify_romanized(self, text: str) -> Tuple[str, float]:
        """Classifies Latin-script text using character 3-gram likelihood scoring."""
        words = [w.lower().strip(".,!?-':;()\"") for w in text.split() if w.strip(".,!?-':;()\"")]
        if not words:
            return "en", 0.9

        trigrams = set()
        for w in words:
            if len(w) >= 3:
                for i in range(len(w) - 2):
                    trigrams.add(w[i:i+3])

        if not trigrams:
            return "en", 0.9

        scores = {lang: len(trigrams.intersection(profile)) / max(1, len(profile)) for lang, profile in self.TRIGRAMS.items()}
        best_lang, best_score = max(scores.items(), key=lambda x: x[1])

        if best_score > 0.08:
            return best_lang, min(1.0, best_score * 3.0)

        # Fallback to langdetect ML model for standard English / foreign text
        try:
            detected = langdetect.detect(text)
            if detected in SUPPORTED_LANGUAGES:
                return detected, 0.9
        except Exception:
            pass

        return "en", 0.95


# ── 4. Language Hysteresis Tracker ───────────────────────────────────────

class LanguageHysteresisTracker:
    """
    Hysteresis state machine tracking language transitions and code-switching tolerance.
    """

    def __init__(self, initial_lang: str):
        self.current_language: str = initial_lang
        self.pending_candidate: Optional[str] = None
        self.pending_count: int = 0

    def evaluate_transition(
        self,
        detected_lang: str,
        confidence: float,
        is_explicit: bool,
        is_native_script: bool,
        has_indic_context: bool,
    ) -> Tuple[str, bool]:
        """Evaluates state transition based on confidence, script, and hysteresis."""
        if is_explicit:
            if detected_lang != self.current_language:
                old = self.current_language
                self.current_language = detected_lang
                self._reset()
                logger.info(f"[LANG] Explicit switch applied: {old} -> {self.current_language}")
                return self.current_language, True
            return self.current_language, False

        # Code-switching tolerance: English words inside active Indian language
        if detected_lang == "en" and self.current_language in ["hi", "kn", "te", "mr"] and has_indic_context:
            logger.info(f"[LANG] Hysteresis: preserved {self.current_language} (code-switched English words)")
            return self.current_language, False

        if detected_lang == self.current_language:
            self._reset()
            return self.current_language, False

        if is_native_script or confidence >= 0.75:
            old = self.current_language
            self.current_language = detected_lang
            self._reset()
            logger.info(f"[LANG] Confirmed switch: {old} -> {self.current_language} (conf={confidence:.2f})")
            return self.current_language, True

        if self.pending_candidate == detected_lang:
            self.pending_count += 1
            if self.pending_count >= 2:
                old = self.current_language
                self.current_language = detected_lang
                self._reset()
                logger.info(f"[LANG] Multi-turn confirmed switch: {old} -> {self.current_language}")
                return self.current_language, True
        else:
            self.pending_candidate = detected_lang
            self.pending_count = 1

        return self.current_language, False

    def _reset(self):
        self.pending_candidate = None
        self.pending_count = 0


# ── 5. Main Language Manager ─────────────────────────────────────────────

class LanguageManager:
    """
    Coordinating manager for multilingual speech-to-text, text-to-speech, and prompt orchestration.
    """

    def __init__(self, initial_language: str = "en"):
        normalized_init = self.normalize_language_code(initial_language)
        self.intent_parser = LanguageIntentParser()
        self.native_detector = NativeLanguageDetector()
        self.phonetic_classifier = PhoneticClassifier()
        self.tracker = LanguageHysteresisTracker(normalized_init)
        logger.info(f"[LANG] LanguageManager active with language='{self.tracker.current_language}'")

    @staticmethod
    def normalize_language_code(code: Optional[str]) -> str:
        """Normalizes raw input strings into supported 2-letter ISO codes."""
        if not code:
            return "en"
        raw = str(code).lower().strip()
        if raw in ["kn", "kannada", "kn-in"]:
            return "kn"
        elif raw in ["hi", "hindi", "hi-in"]:
            return "hi"
        elif raw in ["te", "telugu", "te-in"]:
            return "te"
        elif raw in ["mr", "marathi", "mr-in"]:
            return "mr"
        elif raw in ["en", "english", "en-us", "en-in", "en-gb"]:
            return "en"
        return "en"

    def process_user_utterance(self, text: str) -> Tuple[str, bool]:
        """Processes a user utterance and updates active language state."""
        cleaned = text.strip()
        if not cleaned:
            return self.tracker.current_language, False

        # Step 1: Semantic Intent Parsing
        explicit_code = self.intent_parser.parse_explicit_intent(cleaned)
        if explicit_code:
            return self.tracker.evaluate_transition(
                detected_lang=explicit_code,
                confidence=1.0,
                is_explicit=True,
                is_native_script=False,
                has_indic_context=False,
            )

        # Step 2: Native Script & ML Detection
        script_lang, confidence = self.native_detector.detect(cleaned, self.tracker.current_language)

        is_native_script = False
        has_indic_context = False

        if script_lang == "latin":
            detected_lang, confidence = self.phonetic_classifier.classify_romanized(cleaned)
            has_indic_context = detected_lang in ["hi", "kn", "te", "mr"] and confidence > 0.3
        elif script_lang:
            detected_lang = script_lang
            is_native_script = True
            has_indic_context = True
        else:
            detected_lang = self.tracker.current_language

        # Step 3: Hysteresis Evaluation
        return self.tracker.evaluate_transition(
            detected_lang=detected_lang,
            confidence=confidence,
            is_explicit=False,
            is_native_script=is_native_script,
            has_indic_context=has_indic_context,
        )

    def get_current_language(self) -> str:
        """Returns the active language code."""
        return self.tracker.current_language

    def get_prompt_directive(self) -> str:
        """Returns the dynamic prompt instruction matching the current language state."""
        lang_code = self.tracker.current_language
        lang_name = LANGUAGE_NAMES.get(lang_code, "English")
        native_script = NATIVE_SCRIPTS.get(lang_code, "Latin")

        return (
            f"CURRENT CONVERSATIONAL LANGUAGE: {lang_name} ({lang_code}).\n"
            f"- Always respond in {lang_name} using its natural script: {native_script}.\n"
            f"- The application dynamically tracks and updates the conversational language state based on the caller's speech.\n"
            f"- Follow the current language state without hesitation or preambles.\n"
            f"- Never output meta-explanations like 'Sure, I can speak {lang_name}' or 'I detected you are speaking {lang_name}'.\n"
            f"- Speak naturally like a native multilingual human speaker."
        )


# ── 6. All-Ears Multilingual Parallel STT Engine ────────────────────────

def _score_transcript(lang: str, text: str, confidence: float) -> float:
    """Scores a candidate transcript based on confidence, native script match, and ML detection."""
    text = text.strip()
    if not text:
        return 0.0

    score = confidence

    has_kannada = any(0x0C80 <= ord(c) <= 0x0CFF for c in text)
    has_telugu = any(0x0C00 <= ord(c) <= 0x0C7F for c in text)
    has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in text)

    if lang == "kn" and has_kannada:
        score += 0.4
    elif lang == "te" and has_telugu:
        score += 0.4
    elif lang in ("mr", "hi") and has_devanagari:
        score += 0.4
        try:
            detected = langdetect.detect(text)
            if detected == lang:
                score += 0.2
        except Exception:
            pass
    elif lang == "en" and not (has_kannada or has_telugu or has_devanagari):
        score += 0.3

    return score


class MultilingualParallelStream(stt.RecognizeStream):
    """
    Broadcasts audio frames across multiple language-specific Deepgram streams
    in real time and arbitrates incoming transcripts with debounced turn scoring.
    """

    def __init__(
        self,
        *,
        stt_instance: "MultilingualParallelSTT",
        languages: List[str],
        conn_options: APIConnectOptions,
    ):
        super().__init__(stt=stt_instance, conn_options=conn_options)
        self._languages: List[str] = list(dict.fromkeys(languages))
        self._child_streams: Dict[str, stt.RecognizeStream] = {}
        self._child_tasks: List[asyncio.Task] = []
        self._pending_finals: List[Tuple[str, stt.SpeechEvent]] = []
        self._debounce_task: Optional[asyncio.Task] = None
        self._speaking: bool = False
        self._lock = asyncio.Lock()

    async def _run(self) -> None:
        for lang in self._languages:
            try:
                child_stt = deepgram.STT(
                    model="nova-3",
                    language=lang,
                    smart_format=True,
                    numerals=True,
                    endpointing_ms=100,
                    utterance_end_ms=1000,
                )
                stream = child_stt.stream()
                self._child_streams[lang] = stream
                task = asyncio.create_task(self._listen_child(lang, stream))
                self._child_tasks.append(task)
            except Exception as e:
                logger.warning(f"[LANG] Failed to initialize Deepgram stream for '{lang}': {e}")

        async def _forward_input_frames():
            while not self._input_ch.closed:
                try:
                    frame_or_sentinel = await self._input_ch.recv()
                except utils.aio.ChanClosed:
                    break
                if isinstance(frame_or_sentinel, self._FlushSentinel):
                    for s in list(self._child_streams.values()):
                        try:
                            s.flush()
                        except Exception:
                            pass
                else:
                    for s in list(self._child_streams.values()):
                        try:
                            s.push_frame(frame_or_sentinel)
                        except Exception:
                            pass

        input_task = asyncio.create_task(_forward_input_frames())
        try:
            await asyncio.gather(*self._child_tasks, input_task)
        finally:
            await utils.aio.cancel_and_wait(input_task)
            if self._debounce_task and not self._debounce_task.done():
                self._debounce_task.cancel()
            for s in list(self._child_streams.values()):
                try:
                    await s.aclose()
                except Exception:
                    pass

    async def _flush_finals(self, delay: float = 0.08) -> None:
        await asyncio.sleep(delay)
        async with self._lock:
            if not self._pending_finals:
                return
            best_lang, best_ev = max(
                self._pending_finals,
                key=lambda item: _score_transcript(
                    item[0],
                    item[1].alternatives[0].text if item[1].alternatives else "",
                    item[1].alternatives[0].confidence if item[1].alternatives else 0.0,
                ),
            )
            self._pending_finals.clear()
            self._debounce_task = None

        if best_ev.alternatives:
            best_ev.alternatives[0].language = LanguageCode(best_lang)
            self._event_ch.send_nowait(best_ev)

    async def _listen_child(self, lang: str, stream: stt.RecognizeStream) -> None:
        try:
            async for ev in stream:
                if ev.type == stt.SpeechEventType.START_OF_SPEECH:
                    if not self._speaking:
                        self._speaking = True
                        self._event_ch.send_nowait(ev)
                elif ev.type == stt.SpeechEventType.END_OF_SPEECH:
                    if self._speaking:
                        self._speaking = False
                        self._event_ch.send_nowait(ev)
                elif ev.type == stt.SpeechEventType.FINAL_TRANSCRIPT:
                    if not ev.alternatives or not ev.alternatives[0].text.strip():
                        continue
                    async with self._lock:
                        self._pending_finals.append((lang, ev))
                        if self._debounce_task is None or self._debounce_task.done():
                            self._debounce_task = asyncio.create_task(self._flush_finals(0.08))
                elif ev.type == stt.SpeechEventType.RECOGNITION_USAGE:
                    self._event_ch.send_nowait(ev)
        except Exception:
            pass
        except Exception:
            pass


class MultilingualParallelSTT(stt.STT):
    """
    All-Ears Multilingual STT engine.
    Runs parallel Deepgram STT streams across English, Marathi, Kannada, Telugu, and Hindi
    simultaneously so the agent captures any language the caller speaks in real time.
    """

    def __init__(self, languages: Optional[List[str]] = None):
        super().__init__(
            capabilities=stt.STTCapabilities(
                streaming=True,
                interim_results=True,
            )
        )
        self._languages: List[str] = languages or ["en", "mr", "kn", "te", "hi"]

    @property
    def model(self) -> str:
        return "nova-3-multilingual"

    @property
    def provider(self) -> str:
        return "deepgram"

    def update_options(self, **kwargs) -> None:
        if "languages" in kwargs and kwargs["languages"]:
            self._languages = list(kwargs["languages"])
        elif "language" in kwargs and kwargs["language"]:
            lang = kwargs["language"]
            if lang not in self._languages:
                self._languages.insert(0, lang)

    def stream(
        self,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.RecognizeStream:
        langs = list(self._languages)
        if language is not NOT_GIVEN and language and language not in langs:
            langs.insert(0, language)
        return MultilingualParallelStream(
            stt_instance=self,
            languages=langs,
            conn_options=conn_options,
        )

    async def _recognize_impl(
        self,
        buffer,
        *,
        language: NotGivenOr[str] = NOT_GIVEN,
        conn_options: APIConnectOptions = DEFAULT_API_CONNECT_OPTIONS,
    ) -> stt.SpeechEvent:
        raise NotImplementedError("Use streaming mode with MultilingualParallelSTT")

