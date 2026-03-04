from pathlib import Path
from app.services.emotion_inference import EmotionPredictor

model_path = Path("ml/member2_chatbot/models/best_emotion_model.pt")
labels_path = Path("ml/member2_chatbot/models/emotion_labels.json")

wav_path = Path(r"C:\Users\ASUS\Desktop\b'1010'_ANG_291.wav")

p = EmotionPredictor(model_path, labels_path)

label, conf = p.predict(wav_path)

print("Predicted:", label)
print("Confidence:", conf)
