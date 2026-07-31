import logging
import os
import re
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

TOKEN_ENV = "BOT_TOKEN"
DEFAULT_MANDREL = 48.0
VALID_MANDRELS = {48.0, 51.0}
PERSISTENCE_FILE = os.getenv("PERSISTENCE_FILE", "bot_data.pkl")

logging.basicConfig(
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


def detect_language(text: str) -> str:
    """Return 'es' or 'en' using lightweight keyword detection."""
    lowered = text.lower()
    spanish_words = (
        "cuánto", "cuanto", "peso", "libras", "pies", "mandril", "calcula",
        "quiero", "cambiar", "subir", "bajar", "velocidad", "actual", "ayuda",
        "usar", "usa", "nuevo", "nueva"
    )
    return "es" if any(word in lowered for word in spanish_words) else "en"


def extract_numbers(text: str) -> list[float]:
    """Extract positive decimal numbers, accepting commas as decimal separators."""
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


def calculate_bw(weight_lb: float, length_ft: float, mandrel_in: float) -> float:
    # Same formula used by the BW Tools web app.
    return (weight_lb * 453.59237) / ((length_ft * 12 * mandrel_in) / 100)


def calculate_ft(bw: float, weight_lb: float, mandrel_in: float) -> float:
    # Reverse of the BW formula.
    return (weight_lb * 453.59237 * 100) / (bw * 12 * mandrel_in)


def calculate_swrap(current_weight: float, current_speed: float, target_weight: float) -> float:
    return current_weight * current_speed / target_weight


def is_swrap_request(text: str) -> bool:
    lowered = text.lower()
    keywords = (
        "s-wrap", "s wrap", "swrap", "velocidad", "speed",
        "peso actual", "current weight", "target weight",
        "peso deseado", "quiero cambiar", "want to change"
    )
    return any(keyword in lowered for keyword in keywords)


def is_ft_request(text: str) -> bool:
    lowered = text.lower().strip()
    return bool(
        re.search(r"\b(ft|feet|foot|pies|pie|length|longitud)\b", lowered)
        or lowered.startswith("/ft")
        or lowered.startswith("ft ")
    )


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


def help_text(language: str, mandrel: float) -> str:
    if language == "es":
        return (
            "🤖 *BW Assistant*\n\n"
            f"Mandril predeterminado: *{int(mandrel)}”*\n\n"
            "*Basis Weight*\n"
            "`620 8550`\n"
            "`620 lb 8550 ft mandril 51`\n\n"
            "*Calcular pies*\n"
            "`FT 5.71 620`\n"
            "`¿Cuántos pies con BW 5.71 y peso 620?`\n\n"
            "*S-Wrap*\n"
            "`Peso actual 7.25, velocidad 150, quiero 6.3`\n\n"
            "*Cambiar mandril*\n"
            "`48` o `51`\n\n"
            "Comandos: /bw, /ft, /swrap, /mandrel, /help"
        )
    return (
        "🤖 *BW Assistant*\n\n"
        f"Default mandrel: *{int(mandrel)}”*\n\n"
        "*Basis Weight*\n"
        "`620 8550`\n"
        "`620 lb 8550 ft 51-inch mandrel`\n\n"
        "*Calculate feet*\n"
        "`FT 5.71 620`\n"
        "`How many feet with BW 5.71 and weight 620?`\n\n"
        "*S-Wrap*\n"
        "`Current weight 7.25, speed 150, target 6.3`\n\n"
        "*Change mandrel*\n"
        "`48` or `51`\n\n"
        "Commands: /bw, /ft, /swrap, /mandrel, /help"
    )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = detect_language(update.effective_message.text or "")
    await update.effective_message.reply_text(
        help_text(language, get_mandrel(context)),
        parse_mode="Markdown",
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    language = detect_language(update.effective_message.text or "")
    await update.effective_message.reply_text(
        help_text(language, get_mandrel(context)),
        parse_mode="Markdown",
    )


async def mandrel_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    language = detect_language(text)
    numbers = extract_numbers(text)

    if numbers and numbers[0] in VALID_MANDRELS:
        mandrel = numbers[0]
        set_mandrel(context, mandrel)
        message = (
            f"✅ Mandril predeterminado: {int(mandrel)}”"
            if language == "es"
            else f"✅ Default mandrel: {int(mandrel)}”"
        )
    else:
        current = get_mandrel(context)
        message = (
            f"Mandril actual: {int(current)}”. Usa `/mandrel 48` o `/mandrel 51`."
            if language == "es"
            else f"Current mandrel: {int(current)}”. Use `/mandrel 48` or `/mandrel 51`."
        )
    await update.effective_message.reply_text(message, parse_mode="Markdown")


async def bw_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    language = detect_language(text)
    explicit = explicit_mandrel(text)
    numbers = remove_explicit_mandrel_number(text, explicit)

    # Remove command itself; extract_numbers already ignores "/bw".
    if len(numbers) < 2:
        message = (
            "Escribe: `/bw peso pies` — ejemplo: `/bw 620 8550`"
            if language == "es"
            else "Enter: `/bw weight feet` — example: `/bw 620 8550`"
        )
        await update.effective_message.reply_text(message, parse_mode="Markdown")
        return

    weight, length = numbers[0], numbers[1]
    mandrel = explicit or get_mandrel(context)
    result = calculate_bw(weight, length, mandrel)
    await update.effective_message.reply_text(
        f"*BW = {format_number(result)}*\nMandrel: {int(mandrel)}”",
        parse_mode="Markdown",
    )


async def ft_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    language = detect_language(text)
    explicit = explicit_mandrel(text)
    numbers = remove_explicit_mandrel_number(text, explicit)

    if len(numbers) < 2:
        message = (
            "Escribe: `/ft BW peso` — ejemplo: `/ft 5.71 620`"
            if language == "es"
            else "Enter: `/ft BW weight` — example: `/ft 5.71 620`"
        )
        await update.effective_message.reply_text(message, parse_mode="Markdown")
        return

    bw, weight = numbers[0], numbers[1]
    mandrel = explicit or get_mandrel(context)
    result = calculate_ft(bw, weight, mandrel)
    label = "Pies" if language == "es" else "Feet"
    await update.effective_message.reply_text(
        f"*{label} = {format_number(result, 2)} ft*\nMandrel: {int(mandrel)}”",
        parse_mode="Markdown",
    )


async def swrap_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = update.effective_message.text or ""
    language = detect_language(text)
    numbers = extract_numbers(text)

    if len(numbers) < 3:
        message = (
            "Escribe: `/swrap peso_actual velocidad_actual peso_deseado`\n"
            "Ejemplo: `/swrap 7.25 150 6.3`"
            if language == "es"
            else "Enter: `/swrap current_weight current_speed target_weight`\n"
            "Example: `/swrap 7.25 150 6.3`"
        )
        await update.effective_message.reply_text(message, parse_mode="Markdown")
        return

    current_weight, current_speed, target_weight = numbers[:3]
    result = calculate_swrap(current_weight, current_speed, target_weight)
    if language == "es":
        direction = "Sube" if result > current_speed else "Baja"
        message = f"*{direction} el S-Wrap a {format_number(result, 1)}*"
    else:
        direction = "Increase" if result > current_speed else "Decrease"
        message = f"*{direction} the S-Wrap to {format_number(result, 1)}*"
    await update.effective_message.reply_text(message, parse_mode="Markdown")


async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    if not message or not message.text:
        return

    text = message.text.strip()
    language = detect_language(text)

    selected = standalone_mandrel_command(text)
    if selected is not None:
        set_mandrel(context, selected)
        response = (
            f"✅ Usaré mandril de {int(selected)}” hasta que lo cambies."
            if language == "es"
            else f"✅ I’ll use a {int(selected)}” mandrel until you change it."
        )
        await message.reply_text(response)
        return

    if text.lower() in {"help", "ayuda"}:
        await message.reply_text(
            help_text(language, get_mandrel(context)),
            parse_mode="Markdown",
        )
        return

    if is_swrap_request(text):
        await swrap_command(update, context)
        return

    if is_ft_request(text):
        await ft_command(update, context)
        return

    numbers = extract_numbers(text)
    if len(numbers) >= 2:
        await bw_command(update, context)
        return

    response = (
        "No pude identificar el cálculo. Escribe *Ayuda* para ver ejemplos."
        if language == "es"
        else "I couldn’t identify the calculation. Type *Help* for examples."
    )
    await message.reply_text(response, parse_mode="Markdown")


async def post_init(application: Application) -> None:
    await application.bot.set_my_commands(
        [
            BotCommand("start", "Open BW Assistant"),
            BotCommand("bw", "Calculate Basis Weight"),
            BotCommand("ft", "Calculate roll length"),
            BotCommand("swrap", "Calculate S-Wrap speed"),
            BotCommand("mandrel", "Set 48 or 51-inch mandrel"),
            BotCommand("help", "Show examples"),
        ]
    )


def main() -> None:
    token = os.getenv(TOKEN_ENV)
    if not token:
        raise RuntimeError(
            f"Missing {TOKEN_ENV}. Add it as a Railway environment variable."
        )

    persistence_path = Path(PERSISTENCE_FILE)
    persistence_path.parent.mkdir(parents=True, exist_ok=True)
    persistence = PicklePersistence(filepath=persistence_path)

    application = (
        Application.builder()
        .token(token)
        .persistence(persistence)
        .post_init(post_init)
        .build()
    )

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("mandrel", mandrel_command))
    application.add_handler(CommandHandler("bw", bw_command))
    application.add_handler(CommandHandler("ft", ft_command))
    application.add_handler(CommandHandler("swrap", swrap_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("BW Assistant is starting.")
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
