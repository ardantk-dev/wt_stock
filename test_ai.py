import json
import stock_analyzer

with open("config.json", "r", encoding="utf-8") as f:
    cfg = json.load(f)

api_key = cfg.get("gemini_api_key", "")
print(f"API Key present: {bool(api_key)}, Key length: {len(api_key)}")

res = stock_analyzer.analyze_single_stock_with_ai("삼성전자", api_key)
print("=" * 50)
print(res)
print("=" * 50)
