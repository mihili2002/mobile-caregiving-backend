import pandas as pd
from pathlib import Path

LABELS_CSV = Path("crema_d_labels_all.csv")

MAP = {
    "NEU": "neutral",
    "HAP": "positive",
    "SAD": "negative",
    "DIS": "negative",
    "ANG": "negative",
    "FEA": "anxious",
}

df = pd.read_csv(LABELS_CSV)

df["label"] = df["emotion"].map(MAP)
df = df.dropna(subset=["label"])

# Use normalized paths (replace crema_d_wav -> crema_d_16k)
df["path"] = df["path"].str.replace("crema_d_wav", "crema_d_16k", regex=False)

out_dir = Path("data")
out_dir.mkdir(exist_ok=True)

for split, out_name in [("train", "train.csv"), ("validation", "val.csv"), ("test", "test.csv")]:
    d = df[df["split"] == split][["path", "label", "speaker"]].copy()
    d.to_csv(out_dir / out_name, index=False)
    print(f"✅ Saved {out_name}: {len(d)} rows")

print("✅ Done. CSVs are in ./data/")
