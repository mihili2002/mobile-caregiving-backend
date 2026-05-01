import os
import tensorflow_datasets as tfds
import soundfile as sf
import pandas as pd

OUT_DIR = "crema_d_wav"
os.makedirs(OUT_DIR, exist_ok=True)

ds_train, info = tfds.load("crema_d", split="train", with_info=True)

label_names = info.features["label"].names
print("✅ Label names:", label_names)

rows = []
sr = 16000

for i, sample in enumerate(ds_train):
    audio = sample["audio"].numpy().astype("float32")  # ✅ FIX HERE

    label_id = int(sample["label"].numpy())
    label_name = label_names[label_id]

    speaker = str(sample["speaker_id"].numpy())

    filename = f"{speaker}_{i}.wav"
    path = os.path.join(OUT_DIR, filename)

    sf.write(path, audio, sr)

    rows.append({
        "path": path,
        "emotion": label_name,
        "speaker": speaker,
        "split": "train",
    })

df = pd.DataFrame(rows)
df.to_csv("crema_d_labels.csv", index=False)

print("✅ Extraction completed!")
print("Saved WAV folder:", OUT_DIR)
print("Saved CSV:", "crema_d_labels.csv")
