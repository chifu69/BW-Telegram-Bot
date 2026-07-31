import asyncio
import gc
import json
import logging
import os
import re
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Optional

from telegram import BotCommand, Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    PicklePersistence,
    filters,
)
from vosk import KaldiRecognizer, Model, SetLogLevel

TOKEN_ENV = "BOT_TOKEN"
DEFAULT_MANDREL = 48.0
VALID_MANDRELS = {48.0, 51.0}
PERSISTENCE_FILE = os.getenv("PERSISTENCE_FILE", "bot_data.pkl")
MODEL_ROOT = Path(os.getenv("VOSK_MODEL_ROOT", "/app/models"))
MODEL_PATHS = {
    "en": MODEL_ROOT / "vosk-model-small-en-us-0.15",
    "es": MODEL_ROOT / "vosk-model-small-es-0.42",
}
MAX_VOICE_SECONDS = 30

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)
SetLogLevel(-1)


def detect_language(text: str) -> str:
    lowered = text.lower()
    spanish_words = (
        "cuánto", "cuanto", "peso", "libras", "pies", "mandril", "calcula",
        "quiero", "cambiar", "subir", "bajar", "velocidad", "actual", "ayuda",
        "usar", "usa", "nuevo", "nueva", "objetivo", "deseado",
    )
    return "es" if any(word in lowered for word in spanish_words) else "en"


def extract_numbers(text: str) -> list[float]:
    normalized = text.replace(",", ".")
    values = re.findall(r"(?<![\w.])-?\d+(?:\.\d+)?", normalized)
    return [float(value) for value in values]


def format_number(value: float, decimals: int = 3) -> str:
    formatted = f"{value:.{decimals}f}"
    return formatted.rstrip("0").rstrip(".")


def get_mandrel(context: ContextTypes.DEFAULT_TYPE) -> float:
    value = context.user_data.get("mandrel", DEFAULT_MANDREL)
    try:
        value = float(value)
    except (TypeError, ValueError):
        value = DEFAULT_MANDREL
    return value if value in VALID_MANDRELS else DEFAULT_MANDREL


def set_mandrel(context: ContextTypes.DEFAULT_TYPE, mandrel: float) -> None:
    context.user_data["mandrel"] = mandrel


def get_voice_language(context: ContextTypes.DEFAULT_TYPE) -> str:
    value = str(context.user_data.get("voice_language", "auto")).lower()
    return value if value in {"auto", "en", "es"} else "auto"


def calculate_bw(weight_lb: float, length_ft: float, mandrel_in: float) -> float:
    return (weight_lb * 453.59237) / ((length_ft * 12 * mandrel_in) / 100)


def calculate_ft(bw: float, weight_lb: float, mandrel_in: float) -> float:
    return (weight_lb * 453.59237 * 100) / (bw * 12 * mandrel_in)


def calculate_swrap(current_weight: float, current_speed: float, target_weight: float) -> float:
    return current_weight * current_speed / target_weight


def contains_any(text: str, terms: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(term in lowered for term in terms)


def is_swrap_request(text: str) -> bool:
    return contains_any(
        text,
        (
            "s-wrap", "s wrap", "swrap", "velocidad", "speed",
            "peso actual", "current weight", "target weight",
            "peso deseado", "objetivo", "target", "desired weight",
        ),
    )


def has_weight_unit(text: str) -> bool:
    return bool(re.search(r"\b(lb|lbs|pound|pounds|libra|libras|peso|weight)\b", text.lower()))


def has_length_unit(text: str) -> bool:
    return bool(re.search(r"\b(ft|feet|foot|pie|pies|largo|longitud|length)\b", text.lower()))


def has_bw_word(text: str) -> bool:
    return bool(re.search(r"\b(bw|basis weight|peso base|gramaje)\b", text.lower()))


def is_explicit_ft_request(text: str) -> bool:
    lowered = text.lower().strip()
    return bool(
        lowered.startswith("/ft")
        or lowered.startswith("ft ")
        or re.search(r"\b(calculate|calcula|calcular|find|dime|cuantos|cuántos|how many)\s+(?:the\s+)?(?:feet|ft|pies)\b", lowered)
        or re.search(r"\b(?:feet|ft|pies)\s*(?:=|:|result|resultado|needed|necesarios)\b", lowered)
    )


def classify_request(text: str) -> str:
    """Return one of: mandrel, swrap, ft, bw, unknown.

    Important rule: a message containing both a weight and an existing roll
    length (for example "650 libras 8720 pies") is a BW calculation, not FT.
    """
    if standalone_mandrel_command(text) is not None:
        return "mandrel"
    explicit = explicit_mandrel(text)
    numbers = remove_explicit_mandrel_number(text, explicit)
    if is_swrap_request(text) or len(numbers) >= 3:
        return "swrap"
    if is_explicit_ft_request(text):
        return "ft"
    if has_weight_unit(text) and has_length_unit(text) and len(numbers) >= 2:
        return "bw"
    if has_bw_word(text) and has_weight_unit(text) and len(numbers) >= 2 and not has_length_unit(text):
        return "ft"
    if len(numbers) >= 2:
        return "bw"
    return "unknown"


def explicit_mandrel(text: str) -> Optional[float]:
    lowered = text.lower()
    patterns = (
        r"(?:mandrel|mandril|core)\s*(?:de|of|is|=|:)?\s*(48|51)\b",
        r"\b(48|51)\s*(?:inch|inches|pulgadas|pulgada|[\"”])",
    )
    for pattern in patterns:
        match = re.search(pattern, lowered)
        if match:
            return float(match.group(1))
    return None


def standalone_mandrel_command(text: str) -> Optional[float]:
    cleaned = text.lower().strip()
    patterns = (
        r"^(?:use|usar|usa|set|cambia(?:r)?(?:\s+el)?(?:\s+mandril|\s+mandrel)?\s*)?(48|51)(?:\s*(?:inch|inches|pulgadas|pulgada|[\"”]))?$",
        r"^(?:mandrel|mandril)\s*(48|51)$",
    )
    for pattern in patterns:
        match = re.match(pattern, cleaned)
        if match:
            return float(match.group(1))
    return None


def remove_explicit_mandrel_number(text: str, mandrel: Optional[float]) -> list[float]:
    numbers = extract_numbers(text)
    if mandrel is None:
        return numbers
    removed = False
    result: list[float] = []
    for number in numbers:
        if not removed and number == mandrel:
            removed = True
            continue
        result.append(number)
    return result


EN_SMALL = {
    "zero": 0, "oh": 0, "one": 1, "two": 2, "three": 3, "four": 4,
    "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9,
    "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
    "twenty": 20, "thirty": 30, "forty": 40, "fifty": 50,
    "sixty": 60, "seventy": 70, "eighty": 80, "ninety": 90,
}
ES_SMALL = {
    "cero": 0, "uno": 1, "una": 1, "un": 1, "dos": 2, "tres": 3, "cuatro": 4,
    "cinco": 5, "seis": 6, "siete": 7, "ocho": 8, "nueve": 9, "diez": 10,
    "once": 11, "doce": 12, "trece": 13, "catorce": 14, "quince": 15,
    "dieciseis": 16, "dieciséis": 16, "diecisiete": 17, "dieciocho": 18,
    "diecinueve": 19, "veinte": 20, "veintiuno": 21, "veintidos": 22,
    "veintidós": 22, "veintitres": 23, "veintitrés": 23, "veinticuatro": 24,
    "veinticinco": 25, "veintiseis": 26, "veintiséis": 26, "veintisiete": 27,
    "veintiocho": 28, "veintinueve": 29, "treinta": 30, "cuarenta": 40,
    "cincuenta": 50, "sesenta": 60, "setenta": 70, "ochenta": 80, "noventa": 90,
    "cien": 100, "ciento": 100, "doscientos": 200, "trescientos": 300,
    "cuatrocientos": 400, "quinientos": 500, "seiscientos": 600,
    "setecientos": 700, "ochocientos": 800, "novecientos": 900,
}


def _parse_en_integer(words: list[str]) -> Optional[int]:
    total = current = 0
    used = False
    for word in words:
        if word == "and":
            continue
        if word in EN_SMALL:
            current += EN_SMALL[word]
            used = True
        elif word == "hundred":
            current = max(current, 1) * 100
            used = True
        elif word == "thousand":
            total += max(current, 1) * 1000
            current = 0
            used = True
        else:
            return None
    return total + current if used else None


def _parse_es_integer(words: list[str]) -> Optional[int]:
    total = current = 0
    used = False
    for word in words:
        if word == "y":
            continue
        if word in ES_SMALL:
            value = ES_SMALL[word]
            if value >= 100:
                current += value
            else:
                current += value
            used = True
        elif word in {"mil", "miles"}:
            total += max(current, 1) * 1000
            current = 0
            used = True
        else:
            return None
    return total + current if used else None


def _number_phrase_to_string(words: list[str], language: str) -> Optional[str]:
    decimal_markers = {"en": {"point", "dot"}, "es": {"punto", "coma"}}[language]
    split_at = next((i for i, w in enumerate(words) if w in decimal_markers), None)
    integer_words = words if split_at is None else words[:split_at]
    decimal_words = [] if split_at is None else words[split_at + 1:]
    parser = _parse_en_integer if language == "en" else _parse_es_integer
    integer = parser(integer_words)
    if integer is None:
        return None
    if not decimal_words:
        return str(integer)
    digit_map = EN_SMALL if language == "en" else ES_SMALL
    digits: list[str] = []
    for word in decimal_words:
        if word in digit_map and 0 <= digit_map[word] <= 9:
            digits.append(str(digit_map[word]))
        else:
            parsed = parser(decimal_words)
            if parsed is None:
                return None
            digits = list(str(parsed))
            break
    return f"{integer}.{''.join(digits)}" if digits else str(integer)


def normalize_spoken_numbers(text: str, language: str) -> str:
    tokens = re.findall(r"[\wáéíóúüñ]+|[^\w\s]", text.lower(), flags=re.UNICODE)
    vocab = set(EN_SMALL if language == "en" else ES_SMALL)
    extras = {"en": {"and", "hundred", "thousand", "point", "dot"},
              "es": {"y", "mil", "miles", "punto", "coma"}}[language]
    allowed = vocab | extras
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if tokens[i] not in allowed:
            out.append(tokens[i])
            i += 1
            continue
        best_value = None
        best_end = i
        for j in range(i + 1, min(len(tokens), i + 12) + 1):
            phrase = tokens[i:j]
            if not all(token in allowed for token in phrase):
                break
            value = _number_phrase_to_string(phrase, language)
            if value is not None:
                best_value = value
                best_end = j
        if best_value is None:
            out.append(tokens[i])
            i += 1
        else:
            out.append(best_value)
            i = best_end
    return " ".join(out).replace(" .", ".").replace(" ,", ",")


def help_text(language: str, mandrel: float) -> str:
    voice_lang = "Auto"
    if language == "es":
        return (
            "🤖 *Viejito — BW Assistant V2.1*\n\n"
            "✍️ Escribe o 🎤 manda una nota de voz.\n"
            f"Mandril actual: *{int(mandrel)}”*\n\n"
            "*BW:* `620 8550`\n"
            "*FT:* `FT 5.71 620`\n"
            "*S-Wrap:* `7.25 150 6.3` o dilo con palabras\n"
            "*Mandril:* `48` o `51`\n\n"
            "Voz: `/language auto`, `/language es`, `/language en`\n"
            "Comandos: /bw /ft /swrap /mandrel /language /help"
        )
    return (
        "🤖 *Viejito — BW Assistant V2.1*\n\n"
        "✍️ Type or 🎤 send a voice note.\n"
        f"Current mandrel: *{int(mandrel)}”*\n\n"
        "*BW:* `620 8550`\n"
        "*FT:* `FT 5.71 620`\n"
        "*S-Wrap:* `7.25 150 6.3` or say it naturally\n"
        "*Mandrel:* `48` or `51`\n\n"
        "Voice: `/language auto`, `/language es`, `/language en`\n"
        "Commands: /bw /ft /swrap /mandrel /language /help"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = detect_language(update.effective_message.text or "")
    await update.effective_message.reply_text(help_text(language, get_mandrel(context)), parse_mode="Markdown")


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await start(update, context)


async def language_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").lower()
    choice = next((x for x in ("auto", "en", "es") if re.search(rf"\b{x}\b", text)), None)
    if choice:
        context.user_data["voice_language"] = choice
        labels = {"auto": "automático / automatic", "en": "English", "es": "Español"}
        await update.effective_message.reply_text(f"🎤 Voice language: {labels[choice]}")
    else:
        current = get_voice_language(context)
        await update.effective_message.reply_text(
            f"Current voice language: {current}\nUse /language auto, /language es, or /language en"
        )


async def mandrel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    language = detect_language(text)
    numbers = extract_numbers(text)
    if numbers and numbers[0] in VALID_MANDRELS:
        mandrel = numbers[0]
        set_mandrel(context, mandrel)
        message = f"✅ Mandril: {int(mandrel)}”" if language == "es" else f"✅ Mandrel: {int(mandrel)}”"
    else:
        current = get_mandrel(context)
        message = (
            f"Mandril actual: {int(current)}”. Usa `/mandrel 48` o `/mandrel 51`."
            if language == "es" else
            f"Current mandrel: {int(current)}”. Use `/mandrel 48` or `/mandrel 51`."
        )
    await update.effective_message.reply_text(message, parse_mode="Markdown")


async def bw_command(update: Update, context: ContextTypes.DEFAULT_TYPE, source_text: Optional[str] = None) -> None:
    text = source_text if source_text is not None else (update.effective_message.text or "")
    language = detect_language(text)
    explicit = explicit_mandrel(text)
    numbers = remove_explicit_mandrel_number(text, explicit)
    if len(numbers) < 2:
        message = "Escribe: `/bw peso pies`" if language == "es" else "Enter: `/bw weight feet`"
        await update.effective_message.reply_text(message, parse_mode="Markdown")
        return
    weight, length = numbers[0], numbers[1]
    if weight <= 0 or length <= 0:
        await update.effective_message.reply_text("Weight and feet must be greater than zero.")
        return
    mandrel = explicit or get_mandrel(context)
    result = calculate_bw(weight, length, mandrel)
    suffix = "" if mandrel == DEFAULT_MANDREL else f"\n({int(mandrel)}” mandrel)"
    await update.effective_message.reply_text(f"*BW = {format_number(result)}*{suffix}", parse_mode="Markdown")


async def ft_command(update: Update, context: ContextTypes.DEFAULT_TYPE, source_text: Optional[str] = None) -> None:
    text = source_text if source_text is not None else (update.effective_message.text or "")
    language = detect_language(text)
    explicit = explicit_mandrel(text)
    numbers = remove_explicit_mandrel_number(text, explicit)
    if len(numbers) < 2:
        message = "Escribe: `/ft BW peso`" if language == "es" else "Enter: `/ft BW weight`"
        await update.effective_message.reply_text(message, parse_mode="Markdown")
        return
    bw, weight = numbers[0], numbers[1]
    if bw <= 0 or weight <= 0:
        await update.effective_message.reply_text("BW and weight must be greater than zero.")
        return
    mandrel = explicit or get_mandrel(context)
    result = calculate_ft(bw, weight, mandrel)
    label = "Pies" if language == "es" else "Feet"
    suffix = "" if mandrel == DEFAULT_MANDREL else f"\n({int(mandrel)}” mandrel)"
    await update.effective_message.reply_text(f"*{label} = {format_number(result, 2)} ft*{suffix}", parse_mode="Markdown")


async def swrap_command(update: Update, context: ContextTypes.DEFAULT_TYPE, source_text: Optional[str] = None) -> None:
    text = source_text if source_text is not None else (update.effective_message.text or "")
    language = detect_language(text)
    numbers = extract_numbers(text)
    if len(numbers) < 3:
        message = "Escribe: `/swrap peso velocidad objetivo`" if language == "es" else "Enter: `/swrap current-weight speed target-weight`"
        await update.effective_message.reply_text(message, parse_mode="Markdown")
        return
    current_weight, speed, target_weight = numbers[:3]
    if min(current_weight, speed, target_weight) <= 0:
        await update.effective_message.reply_text("All values must be greater than zero.")
        return
    result = calculate_swrap(current_weight, speed, target_weight)
    label = "Nuevo S-Wrap" if language == "es" else "New S-Wrap"
    await update.effective_message.reply_text(f"*{label}: {format_number(result, 1)}*", parse_mode="Markdown")


async def process_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    *,
    from_voice: bool = False,
) -> None:
    text = text.strip()
    language = detect_language(text)
    selected = standalone_mandrel_command(text)
    if selected is not None:
        set_mandrel(context, selected)
        response = (
            f"✅ Usaré mandril de {int(selected)}”." if language == "es"
            else f"✅ I’ll use a {int(selected)}” mandrel."
        )
        await update.effective_message.reply_text(response)
        return

    if text.lower() in {"help", "ayuda"}:
        await update.effective_message.reply_text(
            help_text(language, get_mandrel(context)), parse_mode="Markdown"
        )
        return

    intent = classify_request(text)
    numbers = extract_numbers(text)

    if from_voice and intent in {"bw", "ft", "swrap"}:
        if intent == "bw" and len(numbers) >= 2:
            summary = (
                f"🎤 Entendí: peso {format_number(numbers[0])} lb, largo {format_number(numbers[1])} ft"
                if language == "es" else
                f"🎤 I heard: weight {format_number(numbers[0])} lb, length {format_number(numbers[1])} ft"
            )
        elif intent == "ft" and len(numbers) >= 2:
            summary = (
                f"🎤 Entendí: BW {format_number(numbers[0])}, peso {format_number(numbers[1])} lb"
                if language == "es" else
                f"🎤 I heard: BW {format_number(numbers[0])}, weight {format_number(numbers[1])} lb"
            )
        elif len(numbers) >= 3:
            summary = (
                f"🎤 Entendí: actual {format_number(numbers[0])}, velocidad {format_number(numbers[1])}, objetivo {format_number(numbers[2])}"
                if language == "es" else
                f"🎤 I heard: current {format_number(numbers[0])}, speed {format_number(numbers[1])}, target {format_number(numbers[2])}"
            )
        else:
            summary = f"🎤 {text}"
        await update.effective_message.reply_text(summary)

    if intent == "swrap":
        await swrap_command(update, context, text)
        return
    if intent == "ft":
        await ft_command(update, context, text)
        return
    if intent == "bw":
        await bw_command(update, context, text)
        return

    response = (
        "No pude identificar el cálculo. Escribe *Ayuda*." if language == "es"
        else "I couldn’t identify the calculation. Type *Help*."
    )
    await update.effective_message.reply_text(response, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message and update.effective_message.text:
        await process_text(update, context, update.effective_message.text)


def convert_to_wav(source: Path, destination: Path) -> None:
    command = [
        "ffmpeg", "-y", "-loglevel", "error", "-i", str(source),
        "-ac", "1", "-ar", "16000", "-sample_fmt", "s16", str(destination),
    ]
    subprocess.run(command, check=True, timeout=45)


def transcribe_wav(wav_path: Path, language: str) -> tuple[str, float]:
    model_path = MODEL_PATHS[language]
    if not model_path.exists():
        raise FileNotFoundError(f"Missing Vosk model: {model_path}")
    model = Model(str(model_path))
    with wave.open(str(wav_path), "rb") as audio:
        recognizer = KaldiRecognizer(model, audio.getframerate())
        recognizer.SetWords(True)
        while True:
            data = audio.readframes(4000)
            if not data:
                break
            recognizer.AcceptWaveform(data)
        result = json.loads(recognizer.FinalResult())
    text = result.get("text", "").strip()
    words = result.get("result", [])
    confidence = sum(float(item.get("conf", 0)) for item in words) / len(words) if words else 0.0
    del model
    gc.collect()
    return text, confidence


def transcribe_best(wav_path: Path, preference: str) -> tuple[str, str, float]:
    languages = [preference] if preference in {"en", "es"} else ["en", "es"]
    candidates: list[tuple[str, str, float]] = []
    for language in languages:
        text, confidence = transcribe_wav(wav_path, language)
        normalized = normalize_spoken_numbers(text, language)
        number_bonus = min(len(extract_numbers(normalized)) * 0.08, 0.24)
        keyword_bonus = 0.08 if any(k in normalized for k in ("weight", "peso", "feet", "pies", "speed", "velocidad", "mandrel", "mandril")) else 0
        candidates.append((normalized, language, confidence + number_bonus + keyword_bonus))
    return max(candidates, key=lambda item: item[2])


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.voice:
        return
    if message.voice.duration and message.voice.duration > MAX_VOICE_SECONDS:
        await message.reply_text("Voice note is too long. Maximum: 30 seconds.")
        return
    status = await message.reply_text("🎤 Escuchando… / Listening…")
    try:
        telegram_file = await context.bot.get_file(message.voice.file_id)
        with tempfile.TemporaryDirectory() as tmpdir:
            ogg_path = Path(tmpdir) / "voice.ogg"
            wav_path = Path(tmpdir) / "voice.wav"
            await telegram_file.download_to_drive(custom_path=str(ogg_path))
            await asyncio.to_thread(convert_to_wav, ogg_path, wav_path)
            text, language, score = await asyncio.to_thread(
                transcribe_best, wav_path, get_voice_language(context)
            )
        if not text:
            await status.edit_text("No pude entender el audio. / I couldn’t understand the audio.")
            return
        await status.edit_text(f"🎤 {text}")
        await process_text(update, context, text, from_voice=True)
    except Exception:
        logger.exception("Voice processing failed")
        await status.edit_text(
            "No pude procesar el audio. Inténtalo otra vez. / I couldn’t process the audio. Try again."
        )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Unhandled bot error", exc_info=context.error)


async def post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Start / Empezar"),
        BotCommand("bw", "Calculate Basis Weight"),
        BotCommand("ft", "Calculate feet"),
        BotCommand("swrap", "Calculate S-Wrap"),
        BotCommand("mandrel", "Set 48 or 51 inch mandrel"),
        BotCommand("language", "Voice language: auto, en, es"),
        BotCommand("help", "Examples / Ejemplos"),
    ]
    await application.bot.set_my_commands(commands)
    logger.info("Viejito V2.1 started. Voice models: %s", MODEL_PATHS)


def main() -> None:
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(f"Missing required environment variable: {TOKEN_ENV}")
    persistence = PicklePersistence(filepath=Path(PERSISTENCE_FILE))
    application = (
        Application.builder()
        .token(token)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("bw", bw_command))
    application.add_handler(CommandHandler("ft", ft_command))
    application.add_handler(CommandHandler("swrap", swrap_command))
    application.add_handler(CommandHandler("mandrel", mandrel_command))
    application.add_handler(CommandHandler("language", language_command))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    application.add_error_handler(error_handler)
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
