import os
from pathlib import Path
import librosa
import soundfile as sf

INPUT_DIR = Path("crema_d_wav")      # folder created by your extractor
OUTPUT_DIR = Path("crema_d_16k")     # new normalized folder
TARGET_SR = 16000

def normalize_folder(split_name: str):
    in_dir = INPUT_DIR / split_name
    out_dir = OUTPUT_DIR / split_name
    out_dir.mkdir(parents=True, exist_ok=True)

    wav_files = list(in_dir.glob("*.wav"))
    print(f"{split_name}: found {len(wav_files)} files")

    for p in wav_files:
        y, sr = librosa.load(str(p), sr=TARGET_SR, mono=True)  # ✅ resample + mono
        out_path = out_dir / p.name
        sf.write(str(out_path), y, TARGET_SR, subtype="PCM_16")

for split in ["train", "validation", "test"]:
    if (INPUT_DIR / split).exists():
        normalize_folder(split)
    else:
        print(f"Skipping {split} (folder not found)")

print("✅ Normalization done. Output:", OUTPUT_DIR)
