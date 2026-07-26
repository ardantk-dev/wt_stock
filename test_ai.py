import json

with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

api_key = cfg.get("gemini_api_key", "")
print("Testing Key:", api_key)

print("\n--- Test 1: google.generativeai (Legacy SDK) ---")
try:
    import google.generativeai as genai_old
    genai_old.configure(api_key=api_key)
    model = genai_old.GenerativeModel('gemini-1.5-flash')
    response = model.generate_content("Hello")
    print("SUCCESS 1.5-flash:", response.text.strip())
except Exception as e:
    print("FAIL 1.5-flash:", e)

try:
    import google.generativeai as genai_old
    genai_old.configure(api_key=api_key)
    model = genai_old.GenerativeModel('gemini-2.0-flash')
    response = model.generate_content("Hello")
    print("SUCCESS 2.0-flash:", response.text.strip())
except Exception as e:
    print("FAIL 2.0-flash:", e)

print("\n--- Test 2: google.genai (New SDK) ---")
try:
    from google import genai
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model='gemini-1.5-flash', contents="Hello")
    print("SUCCESS New SDK 1.5-flash:", response.text.strip())
except Exception as e:
    print("FAIL New SDK 1.5-flash:", e)
