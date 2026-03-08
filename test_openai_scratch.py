import asyncio
import os
from dotenv import load_dotenv
load_dotenv()

from app.services.openai_service import process_voice_with_llm

async def test():
    # Test greeting
    print("--- Testing Greeting ---")
    res1 = await process_voice_with_llm("Give me a very short, warm, and natural greeting as Alex. Acknowledge the time of day if possible.", "test_user", "test_greet_1")
    print(f"Alex: {res1['reply']}")

    # Test task detection
    print("\n--- Testing Task Detection ---")
    res2 = await process_voice_with_llm("remind me to eat noodles at 6:30 p.m.", "test_user", "test_session_1")
    print(f"Alex: {res2['reply']}")
    print(f"Task: {res2.get('task')}")

if __name__ == "__main__":
    asyncio.run(test())
