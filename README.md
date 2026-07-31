# Viejito Industrial Assistant V3 — Free Chemical Edition

Telegram production assistant with:

- BW, FT, and S-Wrap calculations.
- English/Spanish voice recognition with Vosk.
- Automatic English/Spanish replies.
- Per-user sarcasm controls for normal calculations.
- Serious emergency mode for eye, skin, inhalation, ingestion, and spills.
- Chemical search by common name or CAS through the free PubChem PUG REST service.
- Label-photo OCR using free, offline Tesseract OCR.
- SDS 16-section guide in English and Spanish.
- No paid AI API.

## New chemical examples

```text
/chemical acetone
/chemical 67-64-1
cloro
What is sodium hydroxide?
¿Qué es el ácido muriático?
```

Photo:
- Send a clear, straight-on picture of the complete product label.
- Viejito reads the name/CAS with OCR and verifies it in PubChem.
- It refuses to identify an unlabeled liquid by appearance alone.

Emergency examples:

```text
I got Clorox on my skin
Me cayó cloro en el ojo
I inhaled solvent
Se derramó acetona
```

Emergency detection runs before calculator classification, so safety messages no longer fall through to “calculation not identified.”

## Important limitations

- PubChem is a broad chemical database, not the manufacturer's SDS.
- A brand product may be a mixture with concentrations and additives that differ from a pure compound.
- For workplace action, use the exact manufacturer's SDS and plant emergency procedure.
- OCR can misread blurred, curved, reflective, damaged, or incomplete labels.
- Viejito never identifies a chemical from color, smell, or liquid appearance alone.

## Railway deployment

Required environment variable:

```text
BOT_TOKEN=your_telegram_bot_token
```

Railway builds the Dockerfile. It installs:
- FFmpeg
- Vosk models
- Tesseract OCR English and Spanish
- Pillow and pytesseract

After deployment, test:

```text
I got Clorox in my skin
Cloro
/chemical 67-64-1
```

Then send a clear photo of a chemical label.
