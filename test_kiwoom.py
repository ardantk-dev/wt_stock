import sys
import kiwoom_service

def main():
    print("=" * 60)
    print("  Kiwoom REST API Integration Verification Script")
    print("=" * 60)
    
    if not kiwoom_service.is_configured():
        print("[Configuration Error] Kiwoom credentials are missing in config.json.")
        print("Please edit config.json and set:")
        print("  - \"kiwoom_app_key\"")
        print("  - \"kiwoom_app_secret\"")
        print("  - \"kiwoom_account_number\"")
        print("  - \"kiwoom_is_mock\" (true or false)")
        sys.exit(1)
        
    print("Attempting to initialize Kiwoom REST API client and login...")
    api = kiwoom_service.get_client(force_new=True)
    if not api:
        print("[Error] Login failed. Please check your AppKey, SecretKey, and internet connection.")
        sys.exit(1)
        
    print("[Success] Login successful!")
    
    print("\n[Info] Fetching account numbers...")
    accounts = kiwoom_service.get_account_numbers()
    print(f"Registered Accounts: {accounts}")
    
    print("\n[Info] Fetching account balance status...")
    balance = kiwoom_service.get_balance()
    if balance:
        print("[Success] Account evaluation fetched successfully!")
        print(f"Raw Response: {balance}")
    else:
        print("[Error] Failed to fetch balance status.")
        
    print("\n[Info] Fetching domestic stock holdings (Positions)...")
    holdings = kiwoom_service.get_holdings()
    print(f"Holdings (Parsed):")
    if holdings:
        for idx, h in enumerate(holdings, 1):
            print(f"  {idx}. {h['name']} ({h['ticker']}) - Qty: {h['quantity']} | Avg Cost: {h['buy_price']}")
    else:
        print("  (No holdings found or failed to fetch)")
        
    print("\n[Info] Verification complete. If balance and holdings look correct, the bot is ready!")
    print("=" * 60)

if __name__ == "__main__":
    main()
