from collections import Counter

# map model labels -> elder-friendly words
HUMAN = {
    "joy": "happy",
    "happy": "happy",
    "sad": "sad",
    "sadness": "sad",
    "anger": "upset",
    "angry": "upset",
    "fear": "anxious",
    "anxiety": "anxious",
    "neutral": "calm",
    "surprise": "surprised",
    "disgust": "disgusted",
}

def summarize_emotions(items: list[dict], only_emotion: str | None = None) -> str:
    if not items:
        return (
            "I couldn’t find any emotion records for that time. "
            "Would you like to tell me how you feel now?"
        )

    # filter if user asked for one emotion
    if only_emotion:
        only_emotion = only_emotion.lower()
        items = [x for x in items if (x.get("emotion") or "").lower() == only_emotion]

        if not items:
            return f"I didn’t find any **{HUMAN.get(only_emotion, only_emotion)}** moments in that time."

    emotions = [x.get("emotion", "").lower() for x in items if x.get("emotion")]
    counts = Counter(emotions)
    total = len(emotions)

    top = counts.most_common(1)[0][0]
    top_h = HUMAN.get(top, top)

    # examples (up to 2)
    examples = []
    for x in reversed(items):
        t = (x.get("text") or "").strip()
        if t:
            examples.append(t)
        if len(examples) == 2:
            break

    if only_emotion:
        e_h = HUMAN.get(only_emotion, only_emotion)
        msg = f"I found **{total} {e_h}** moments in that time."
    else:
        msg = f"In that time, you mostly felt **{top_h}**. I noticed {total} emotion moments."

    if examples:
        msg += f' For example: “{examples[0]}”.'
        if len(examples) > 1:
            msg += f' Also: “{examples[1]}”.'

    msg += " Do you want a weekly summary too?"
    return msg
