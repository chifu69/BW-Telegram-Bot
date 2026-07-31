# BW Assistant — Telegram Bot

Bilingual Telegram bot for production calculations in English and Spanish.

## Features

- Calculates Basis Weight from weight and roll length.
- Calculates roll length in feet from Basis Weight and weight.
- Calculates a new S-Wrap speed.
- Uses a 48-inch mandrel by default.
- Accepts a 51-inch mandrel when specified.
- Remembers each Telegram user's selected mandrel.
- Understands short numeric inputs and natural phrases in English or Spanish.

## Examples

### Basis Weight

```text
620 8550
620 lb 8550 ft
620 libras 8550 pies
/bw 620 8550
620 lb 8550 ft mandril 51
```

### Roll length

```text
/ft 5.71 620
FT 5.71 620
¿Cuántos pies con BW 5.71 y peso 620?
How many feet with BW 5.71 and weight 620?
```

### S-Wrap

```text
/swrap 7.25 150 6.3
Mi peso actual es 7.25 y mi velocidad es 150; quiero cambiar a 6.3
Current weight is 7.25, speed is 150, and target weight is 6.3
```

Result:

```text
Sube el S-Wrap a 172.6
```

### Change the default mandrel

```text
48
51
/mandrel 48
/mandrel 51
Use 51 mandrel
Usa mandril 51
```

## Formulae

The bot uses the same Basis Weight formula as the BW Tools web app:

```text
BW = (weight_lb × 453.59237) ÷ ((length_ft × 12 × mandrel_in) ÷ 100)
```

Reverse length calculation:

```text
FT = (weight_lb × 453.59237 × 100) ÷ (BW × 12 × mandrel_in)
```

S-Wrap calculation:

```text
new_speed = current_weight × current_speed ÷ target_weight
```

## Deploy to Railway from GitHub

1. Create a new GitHub repository named `BW-Telegram-Bot`.
2. Upload every file from this project.
3. In Railway, select **New Project → Deploy from GitHub repo**.
4. Choose `BW-Telegram-Bot`.
5. Open the Railway service and select **Variables**.
6. Add:

```text
BOT_TOKEN=your_private_token_from_BotFather
```

7. Deploy the staged changes.
8. Open **Deployments → View Logs**. You should see:

```text
BW Assistant is starting.
```

Do not put the real token in GitHub. Railway provides variables to the running application as environment variables.

Railway should detect the Python project automatically. This repository also includes `railway.json` and a `Procfile`; the intended start command is:

```text
python main.py
```

## Persistent mandrel settings on Railway

The bot remembers user settings in `bot_data.pkl`. Railway storage may be replaced during redeployments unless you attach a persistent volume.

For permanent storage:

1. Add a Railway volume to the service.
2. Mount it at:

```text
/data
```

3. Add this Railway variable:

```text
PERSISTENCE_FILE=/data/bot_data.pkl
```

Without a volume, the bot still works and remembers settings while the current deployment is running. The default always returns to 48 inches when no saved setting exists.

## Security

- Never upload your BotFather token to GitHub.
- Never paste the token into screenshots or public chats.
- If the token is exposed, use BotFather's `/revoke` command and create a replacement.
