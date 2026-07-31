# Viejito — BW Assistant V2

Telegram production calculator with **text and free offline voice recognition**.

## Features

- Basis Weight calculations
- Feet calculations
- S-Wrap calculations
- 48-inch and 51-inch mandrel memory per user
- English and Spanish text
- English and Spanish Telegram voice notes
- No OpenAI key and no paid speech API
- Voice processing with Vosk and FFmpeg

## Voice examples

Say one of these in a Telegram voice note:

- “Six hundred twenty pounds, eight thousand five hundred fifty feet.”
- “Seiscientas veinte libras, ocho mil quinientos cincuenta pies.”
- “Current weight seven point two five, speed one fifty, target six point three.”
- “Peso actual siete punto dos cinco, velocidad ciento cincuenta, objetivo seis punto tres.”
- “Mandrel fifty one.”
- “Mandril cuarenta y ocho.”

The bot displays what it understood before returning the result.

## Railway deployment

1. Upload all files in this project to the GitHub repository.
2. Keep the existing Railway variable named `BOT_TOKEN`.
3. Railway detects the `Dockerfile`, installs FFmpeg, and downloads the official small English and Spanish Vosk models during the build.
4. Wait for **Deployment successful**.
5. Test text first, then send a Telegram voice note.

The first Docker build is slower because it downloads approximately 80 MB of language models.

## Commands

- `/start`
- `/help`
- `/bw 620 8550`
- `/ft 5.71 620`
- `/swrap 7.25 150 6.3`
- `/mandrel 48`
- `/mandrel 51`
- `/language auto`
- `/language es`
- `/language en`

`/language auto` tries both language models and chooses the best result. Selecting `es` or `en` is faster and uses less memory.

## Privacy and cost

Vosk performs speech recognition inside the Railway container. Voice notes are downloaded temporarily, converted, transcribed, and deleted when processing finishes. No paid speech API is used.
