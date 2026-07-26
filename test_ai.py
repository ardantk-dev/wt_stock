import stock_analyzer

config = stock_analyzer.load_config()
api_key = config.get("gemini_api_key", "")
print(f"API Key present: {bool(api_key)}, Key length: {len(api_key)}")

res = stock_analyzer.analyze_single_stock_with_ai("삼성전자", api_key)
print("=" * 50)
print(res)
print("=" * 50)
