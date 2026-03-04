import re
import numpy as np


class EmotionPredictor:
    """
    Combined emotion predictor:
    1. Primary   → text keyword matching (fast, accurate for clear speech)
    2. Fallback  → wav2vec2 deep learning model (audio-based)
    """

    QUADRANT_LABELS = {
        "Q1": "Happy / Excited",
        "Q2": "Angry / Fearful",
        "Q3": "Sad / Depressed",
        "Q4": "Calm / Relaxed",
    }

    KEYWORD_MAP = {
        "Q1": [
            "happy", "happiness", "joy", "joyful", "excited", "excitement",
            "glad", "great", "wonderful", "amazing", "fantastic", "good",
            "love", "loved", "grateful", "thankful", "blessed", "positive",
            "cheerful", "delighted", "thrilled", "elated", "energetic",
            "laugh", "laughing", "smile", "smiling", "enjoy", "enjoying",
            # Malay
            "gembira", "seronok", "suka", "syukur", "bahagia", "best",
            "terima kasih", "bersyukur", "sukacita",
        ],
        "Q2": [
            "angry", "anger", "furious", "rage", "mad", "frustrated",
            "annoyed", "irritated", "scared", "afraid", "fear", "fearful",
            "anxious", "anxiety", "worried", "worry", "nervous", "stressed",
            "stress", "panic", "terrified", "disgusted", "hate", "horrible",
            "upset", "overwhelmed", "tense", "agitated",
            # Malay
            "marah", "takut", "risau", "benci", "geram", "tension",
            "fobia", "cemas", "panik",
        ],
        "Q3": [
            "sad", "sadness", "unhappy", "depressed", "depression", "lonely",
            "alone", "miserable", "terrible", "awful", "hopeless", "helpless",
            "crying", "cry", "tears", "grief", "hurt", "pain", "heartbroken",
            "disappointed", "down", "low", "empty", "tired", "exhausted",
            "gloomy", "sorrowful", "melancholy", "suffering", "broken",
            # Malay
            "sedih", "susah", "penat", "lelah", "kecewa", "hampa", "sakit",
            "menangis", "putus asa", "menderita",
        ],
        "Q4": [
            "calm", "peaceful", "relaxed", "relax", "content", "satisfied",
            "okay", "ok", "fine", "normal", "stable", "comfortable", "quiet",
            "serene", "tranquil", "neutral", "alright", "decent", "rest",
            "resting", "easy", "smooth", "steady", "balanced",
            # Malay
            "tenang", "rehat", "biasa", "selesa", "baik", "ok je", "stabil",
        ],
    }

    EMOTION_TO_QUADRANT = {
        "happy":     "Q1",
        "excited":   "Q1",
        "surprised": "Q1",
        "angry":     "Q2",
        "fearful":   "Q2",
        "fear":      "Q2",
        "disgusted": "Q2",
        "disgust":   "Q2",
        "sad":       "Q3",
        "sadness":   "Q3",
        "neutral":   "Q4",
        "calm":      "Q4",
    }

    def __init__(self, model_path=None, scaler_path=None, encoder_path=None):
        # Load wav2vec2 as fallback audio model
        self._audio_pipe = None
        try:
            from transformers import pipeline
            print("Loading wav2vec2 audio emotion model (fallback)...")
            self._audio_pipe = pipeline(
                "audio-classification",
                model="ehcalabres/wav2vec2-lg-xlsr-en-speech-emotion-recognition",
                device=-1,  # CPU
            )
            print("✅ wav2vec2 fallback model loaded!")
        except Exception as e:
            print(f"⚠️ wav2vec2 not loaded (text-only mode): {e}")

    def predict_from_text(self, transcript: str) -> tuple[str, float]:
        """Primary method — keyword matching on transcript."""
        text = transcript.lower()
        text = re.sub(r'[^\w\s]', ' ', text)

        scores = {"Q1": 0, "Q2": 0, "Q3": 0, "Q4": 0}

        for quadrant, keywords in self.KEYWORD_MAP.items():
            for keyword in keywords:
                if keyword in text:
                    scores[quadrant] += 1

        best_quadrant = max(scores, key=scores.get)
        best_score = scores[best_quadrant]

        print(f"TEXT scores: {scores} → {best_quadrant}")

        # No keywords matched — use audio fallback
        if best_score == 0:
            return None, 0.0

        total = sum(scores.values())
        confidence = round(best_score / total, 3) if total > 0 else 0.5
        return best_quadrant, confidence

    def predict_from_audio(self, wav_path: str) -> tuple[str, float]:
        """Fallback method — wav2vec2 deep learning on audio."""
        if self._audio_pipe is None:
            print("⚠️ Audio model not available, defaulting to Q4")
            return "Q4", 0.5

        try:
            import torchaudio
            waveform, sr = torchaudio.load(str(wav_path))

            if sr != 16000:
                resampler = torchaudio.transforms.Resample(sr, 16000)
                waveform = resampler(waveform)

            if waveform.shape[0] > 1:
                waveform = waveform.mean(dim=0, keepdim=True)

            audio_array = waveform.squeeze().numpy()

            results = self._audio_pipe(
                {"raw": audio_array, "sampling_rate": 16000},
                top_k=1
            )

            top = results[0]
            label = top["label"].lower().strip()
            confidence = float(top["score"])

            quadrant = self.EMOTION_TO_QUADRANT.get(label, "Q4")
            print(f"AUDIO wav2vec2: {label} ({confidence:.2f}) → {quadrant}")
            return quadrant, confidence

        except Exception as e:
            print(f"Audio emotion failed: {e}")
            return "Q4", 0.5

    def predict(self, wav_path, transcript: str = None) -> tuple[str, float]:
        """
        Main predict method.
        1. Try text keywords first (fast + accurate)
        2. Fall back to wav2vec2 audio model if text gives no result
        3. Default to Q4 if both fail
        """
        # Step 1: Try text-based prediction
        if transcript and transcript.strip():
            quadrant, confidence = self.predict_from_text(transcript)
            if quadrant is not None:
                print(f"✅ Text-based emotion: {quadrant} ({confidence})")
                return quadrant, confidence
            else:
                print("⚠️ No keywords found in text, trying audio...")

        # Step 2: Try audio-based prediction
        if wav_path:
            quadrant, confidence = self.predict_from_audio(wav_path)
            print(f"✅ Audio-based emotion: {quadrant} ({confidence})")
            return quadrant, confidence

        # Step 3: Default
        print("⚠️ Both methods failed, defaulting to Q4")
        return "Q4", 0.5