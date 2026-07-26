import json
from google import genai

with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

api_key = cfg.get("gemini_api_key", "")
print("Testing Key:", api_key[:10] + "..." + api_key[-5:])

client = genai.Client(api_key=api_key)

for m in ['gemini-1.5-flash-latest', 'gemini-2.0-flash-001', 'gemini-2.0-flash-exp', 'gemini-1.5-flash-8b', 'gemini-1.5-pro-latest']:
    try:
        res = client.models.generate_content(model=m, contents="Hello")
        print(f"[{m}] SUCCESS ->", res.text.strip()[:60])
    except Exception as e:
        print(f"[{m}] FAILED ->", type(e).__name__, str(e)[:150])
