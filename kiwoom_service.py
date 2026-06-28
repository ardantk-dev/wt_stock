import os
import json
from kiwoom_rest_api import KiwoomAPI, KiwoomAPIError

CONFIG_FILE = "config.json"

# Cache for the KiwoomAPI client instance
_kiwoom_api_client = None

def load_config():
    if not os.path.exists(CONFIG_FILE):
        return {}
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}

def is_configured():
    config = load_config()
    return bool(
        config.get("kiwoom_app_key") and
        config.get("kiwoom_app_secret") and
        config.get("kiwoom_account_number")
    )

def get_client(force_new=False):
    global _kiwoom_api_client
    if _kiwoom_api_client is not None and not force_new:
        return _kiwoom_api_client
    
    if not is_configured():
        return None
    
    config = load_config()
    app_key = config.get("kiwoom_app_key", "")
    app_secret = config.get("kiwoom_app_secret", "")
    is_mock = config.get("kiwoom_is_mock", True)
    
    try:
        api = KiwoomAPI(app_key=app_key, app_secret=app_secret, is_mock=is_mock)
        api.login()
        _kiwoom_api_client = api
        print("Kiwoom REST API successfully logged in.")
        return _kiwoom_api_client
    except Exception as e:
        print(f"Kiwoom Login Error: {e}")
        return None

_cached_account_number = None

def get_effective_account_number():
    global _cached_account_number
    if _cached_account_number:
        return _cached_account_number
        
    config = load_config()
    raw_acc = str(config.get("kiwoom_account_number", "")).strip()
    if not raw_acc:
        return ""
        
    if len(raw_acc) == 10:
        _cached_account_number = raw_acc
        return raw_acc
        
    accounts = get_account_numbers()
    if accounts:
        for acc in accounts:
            if acc.startswith(raw_acc):
                _cached_account_number = acc
                return acc
        _cached_account_number = accounts[0]
        return accounts[0]
        
    if len(raw_acc) == 8:
        resolved = raw_acc + "10"
        _cached_account_number = resolved
        return resolved
        
    _cached_account_number = raw_acc
    return raw_acc

def get_account_numbers():
    api = get_client()
    if not api:
        return []
    try:
        res = api.account.account_number_inquiry()
        accounts = []
        for k, v in res.items():
            if isinstance(v, list):
                for item in v:
                    if isinstance(item, dict):
                        acc = item.get("acctNo") or item.get("acnt_no") or item.get("acntNo")
                        if acc:
                            accounts.append(acc)
            elif isinstance(v, str) and k in ["acctNo", "acnt_no", "acntNo"]:
                accounts.append(v)
        if not accounts and "acctNo" in res:
            accounts.append(res["acctNo"])
        return accounts
    except Exception as e:
        print(f"Error fetching account numbers: {e}")
        return []

def get_balance():
    api = get_client()
    if not api:
        return None
    acc_no = get_effective_account_number()
    
    params = {
        "acc_no": acc_no,
        "acnt_no": acc_no,
        "qry_tp": "1",
        "dmst_stex_tp": "KRX",
        "pwd": "",
        "pwd_gp": "00"
    }
    
    try:
        res = api.account.account_evaluation(**params)
        return res
    except Exception as e:
        print(f"Error fetching account evaluation (kt00004): {e}")
        return None

def get_holdings():
    api = get_client()
    if not api:
        return []
    acc_no = get_effective_account_number()
    
    params = {
        "acc_no": acc_no,
        "acnt_no": acc_no,
        "qry_tp": "1",
        "dmst_stex_tp": "KRX",
        "pwd": "",
        "pwd_gp": "00",
        "inqr_gb": "1",  # 1: 합산, 2: 개별
        "trde_gb": "1"
    }
    
    # Try evaluation_balance_detail (kt00018)
    try:
        res = api.account.evaluation_balance_detail(**params)
        return parse_holdings_response(res)
    except Exception as e:
        print(f"Error fetching evaluation_balance_detail (kt00018): {e}")
        # Try fallback today_account_status (kt00017)
        try:
            res = api.account.today_account_status(**params)
            return parse_holdings_response(res)
        except Exception as e2:
            print(f"Error fetching today_account_status (kt00017): {e2}")
            return []

def parse_holdings_response(res):
    holdings = []
    
    # Find list in response dict
    list_data = None
    for k, v in res.items():
        if isinstance(v, list):
            list_data = v
            break
            
    if not list_data:
        for k in ["output1", "output2", "acnt_evlt_remn_indv_tot", "output"]:
            if k in res and isinstance(res[k], list):
                list_data = res[k]
                break
                
    if not list_data:
        return []
        
    for item in list_data:
        if not isinstance(item, dict):
            continue
            
        ticker = item.get("stk_cd") or item.get("stk_no") or item.get("stock_code") or item.get("종목코드")
        if not ticker:
            continue
            
        ticker = ticker.strip()
        if len(ticker) > 6:
            if ticker.startswith("A") and len(ticker) == 7:
                ticker = ticker[1:]
            elif len(ticker) == 12:
                ticker = ticker[3:9]
        
        name = item.get("stk_nm") or item.get("stk_name") or item.get("stock_name") or item.get("종목명") or ticker
        
        qty = item.get("rmnd_qty") or item.get("qty") or item.get("quantity") or item.get("보유수량") or 0
        try:
            qty = float(qty)
        except ValueError:
            qty = 0
            
        buy_price = item.get("pur_pric") or item.get("buy_price") or item.get("pur_price") or item.get("매입단가") or 0
        try:
            buy_price = float(buy_price)
        except ValueError:
            buy_price = 0
            
        if qty > 0:
            holdings.append({
                "ticker": ticker,
                "name": name,
                "quantity": qty,
                "buy_price": buy_price
            })
            
    return holdings

def execute_order(ticker, qty, price=0, is_buy=True, trde_tp="03"):
    """
    Submits an order to Kiwoom REST API.
    ticker: 6-digit stock code (e.g. '005930')
    qty: Quantity of shares (int)
    price: Limit price (int). If 0 or trde_tp is "03" (market), price is ignored.
    is_buy: True to buy, False to sell.
    trde_tp: "00" for limit (지정가), "03" for market (시장가).
    """
    api = get_client()
    if not api:
        return {"success": False, "message": "Kiwoom REST API client is not initialized or configured."}
        
    config = load_config()
    acc_no = config.get("kiwoom_account_number", "")
    
    clean_ticker = ticker.split(".")[0]
    if clean_ticker.startswith("A") and len(clean_ticker) == 7:
        clean_ticker = clean_ticker[1:]
        
    params = {
        "acc_no": acc_no,
        "acnt_no": acc_no,
        "dmst_stex_tp": "01",  # "01" is KRX in younghwan91/kiwoom-rest-api
        "stk_cd": clean_ticker,
        "ord_qty": int(qty),
        "ord_uv": int(price) if trde_tp == "00" else 0,
        "trde_tp": trde_tp,
        "cond_uv": ""
    }
    
    try:
        if is_buy:
            res = api.order.buy_order(**params)
        else:
            res = api.order.sell_order(**params)
        return {"success": True, "data": res}
    except KiwoomAPIError as e:
        print(f"Kiwoom API Error executing order: {e}")
        return {"success": False, "message": f"API Error [{e.code}]: {e.message}", "response": e.response}
    except Exception as e:
        print(f"General Error executing order: {e}")
        return {"success": False, "message": str(e)}
