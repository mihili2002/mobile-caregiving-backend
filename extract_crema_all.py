import os
import tensorflow_datasets as tfds
import soundfile as sf
import pandas as pd

OUT_DIR = "crema_d_wav"
os.makedirs(OUT_DIR, exist_ok=True)

rows = []
sr = 16000

splits = ["train", "validation", "test"]

# Load once with info to get label names
_, info = tfds.load("crema_d", split="train", with_info=True)
label_names = info.features["label"].names
print("✅ Label names:", label_names)

for split in splits:
    ds = tfds.load("crema_d", split=split)
    split_dir = os.path.join(OUT_DIR, split)
    os.makedirs(split_dir, exist_ok=True)

    for i, sample in enumerate(ds):
        audio = sample["audio"].numpy().astype("float32")
        label_id = int(sample["label"].numpy())
        label_name = label_names[label_id]    # NEU/HAP/...
        speaker = str(sample["speaker_id"].numpy())

        filename = f"{speaker}_{label_name}_{i}.wav"
        path = os.path.join(split_dir, filename)

        sf.write(path, audio, sr)

        rows.append({
            "path": path,
            "emotion": label_name,
            "speaker": speaker,
            "split": split,
        })

df = pd.DataFrame(rows)
df.to_csv("crema_d_labels_all.csv", index=False)

print("✅ Extracted all splits + CSV saved as crema_d_labels_all.csv")
