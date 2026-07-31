from pathlib import Path
import shutil
import urllib.request
import zipfile

MODELS = {
    "vosk-model-small-en-us-0.15": "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
    "vosk-model-small-es-0.42": "https://alphacephei.com/vosk/models/vosk-model-small-es-0.42.zip",
}
root = Path("/app/models")
root.mkdir(parents=True, exist_ok=True)
for name, url in MODELS.items():
    destination = root / name
    if destination.exists():
        continue
    archive = root / f"{name}.zip"
    print(f"Downloading {name}...")
    urllib.request.urlretrieve(url, archive)
    with zipfile.ZipFile(archive) as zf:
        zf.extractall(root)
    archive.unlink()
print("Voice models ready.")
