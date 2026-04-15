import os
from google import genai
from dotenv import load_dotenv

load_dotenv()
keys = [
    os.getenv("GEMINI_KEY_1"),
    os.getenv("GEMINI_KEY_2"),
    os.getenv("GEMINI_KEY_3"),
    os.getenv("GEMINI_KEY_4"),
    os.getenv("GEMINI_KEY_5"),
]

model = "gemini-2.5-flash"

for i, key in enumerate(keys):
    if not key:
        continue
    try:
        client = genai.Client(api_key=key)
        resp = client.models.generate_content(model=model, contents=["Hello"])
        print(f"KEY_{i+1}: SUCCESS")
    except Exception as e:
        print(f"KEY_{i+1}: ERR - {e}")
