import tensorflow_datasets as tfds

# This will download and prepare CREMA-D automatically
dataset, info = tfds.load(
    "crema_d",
    split=["train", "validation", "test"],
    with_info=True,
    as_supervised=False
)

print("CREMA-D downloaded successfully!")
print(info)
