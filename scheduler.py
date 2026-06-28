import time
import schedule
import json
import os
import pytz
from datetime import datetime
import telegram_bot
import stock_analyzer

ALERT_STATE_FILE = "alert_state.json"

def load_alert_state():
    if not os.path.exists(ALERT_STATE_FILE):
        return {"date": "", "sent": {}}
    try:
        with open(ALERT_STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Scheduler: Error loading alert state: {e}")
        return {"date": "", "sent": {}}

def save_alert_state(state):
    try:
        with open(ALERT_STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"Scheduler: Error saving alert state: {e}")

def is_market_open():
    """Checks if the Korean or US stock market is currently open (KST)."""
    tz_kst = pytz.timezone('Asia/Seoul')
    now_kst = datetime.now(tz_kst)
    
    # Weekends (Saturday=5, Sunday=6)
    if now_kst.weekday() >= 5:
        return False
        
    time_kst = now_kst.time()
    
    # KR Market: 08:55 - 15:45 KST (with 5 min buffer before/after)
    kr_open = datetime.strptime("08:55", "%H:%M").time()
    kr_close = datetime.strptime("15:45", "%H:%M").time()
    if kr_open <= time_kst <= kr_close:
        return True
        
    # US Market: 21:25 - 06:35 KST (Covers both DST and standard time)
    us_open = datetime.strptime("21:25", "%H:%M").time()
    us_close = datetime.strptime("06:35", "%H:%M").time()
    if time_kst >= us_open or time_kst <= us_close:
        return True
        
    return False

def check_price_alerts():
    """Checks the daily price change of all portfolio stocks and sends alerts on 5% thresholds."""
    if not is_market_open():
        return

    print("Scheduler: Running real-time price alert check...")
    portfolio = telegram_bot.load_json(telegram_bot.PORTFOLIO_FILE, {"KR": [], "US": []})
    
    tz_kst = pytz.timezone('Asia/Seoul')
    today_str = datetime.now(tz_kst).strftime("%Y-%m-%d")
    
    state = load_alert_state()
    if state.get("date") != today_str:
        print(f"Scheduler: New day detected ({today_str}). Resetting alert state.")
        state = {"date": today_str, "sent": {}}

    all_stocks = []
    for s in portfolio.get("KR", []):
        all_stocks.append((s, "KR"))
    for s in portfolio.get("US", []):
        all_stocks.append((s, "US"))

    if not all_stocks:
        return

    state_changed = False
    for stock_info, nation in all_stocks:
        ticker = stock_info["ticker"]
        name = stock_info["name"]
        
        data = stock_analyzer.get_stock_summary(ticker, nation)
        if not data:
            continue
            
        pct_change = data.get("pct_change", 0.0)
        close = data.get("close", 0.0)
        change = data.get("change", 0.0)
        high = data.get("high", 0.0)
        low = data.get("low", 0.0)
        
        # Calculate level (threshold multiplier of 5%)
        # e.g. 5.3% -> 1, 10.2% -> 2, -6.1% -> -1
        if pct_change >= 5.0:
            level = int(pct_change / 5.0)
        elif pct_change <= -5.0:
            level = int(pct_change / 5.0)
        else:
            level = 0
            
        prev_level = state["sent"].get(ticker, 0)
        
        if level != prev_level:
            if level != 0:
                # Send Alert
                sign = "🔺" if pct_change > 0 else "🔻"
                change_sign = "+" if pct_change > 0 else ""
                direction = "급등" if level > 0 else "급락"
                threshold_desc = f"{change_sign}{level * 5}%"
                
                curr_symbol = "원" if nation == "KR" else "$"
                
                alert_msg = (
                    f"📢 *[주가 {direction} 알림]*\n\n"
                    f"★ *{name}* ({ticker})\n"
                    f"현재 주가가 전일 대비 *{pct_change:+.2f}%* 변동하여 *[{threshold_desc} 돌파선]*에 도달했습니다.\n\n"
                    f"• 현재가: {close:,.2f}{curr_symbol} ({sign} {change:+,.2f}{curr_symbol})\n"
                    f"• 오늘 고가: {high:,.2f}{curr_symbol} | 저가: {low:,.2f}{curr_symbol}"
                )
                
                print(f"Scheduler: Sending alert for {name} ({ticker}) - {pct_change:.2f}%")
                telegram_bot.send_alert(alert_msg)
                
            state["sent"][ticker] = level
            state_changed = True

    if state_changed:
        save_alert_state(state)

def run_morning_briefing():
    print("Scheduler: Generating morning briefing...")
    portfolio = telegram_bot.load_json(telegram_bot.PORTFOLIO_FILE, {"KR": [], "US": []})
    brief = stock_analyzer.format_morning_briefing(portfolio)
    success = telegram_bot.send_alert(brief)
    if success:
        print("Scheduler: Morning briefing sent successfully.")
    else:
        print("Scheduler: Failed to send morning briefing.")

def run_evening_briefing():
    print("Scheduler: Generating evening briefing...")
    portfolio = telegram_bot.load_json(telegram_bot.PORTFOLIO_FILE, {"KR": [], "US": []})
    brief = stock_analyzer.format_evening_briefing(portfolio)
    success = telegram_bot.send_alert(brief)
    if success:
        print("Scheduler: Evening briefing sent successfully.")
    else:
        print("Scheduler: Failed to send evening briefing.")

def setup_schedule(morning_time, evening_time):
    schedule.clear()
    schedule.every().day.at(morning_time).do(run_morning_briefing)
    schedule.every().day.at(evening_time).do(run_evening_briefing)
    print(f"Scheduler: Configured schedules - Morning at {morning_time}, Evening at {evening_time}")

def run_scheduler_loop():
    config = telegram_bot.load_json(telegram_bot.CONFIG_FILE, {})
    m_time = config.get("morning_time", "07:00")
    e_time = config.get("evening_time", "20:30")
    
    setup_schedule(m_time, e_time)
    last_check_time = time.time()
    
    # Check price alerts every 10 minutes (600 seconds)
    last_price_alert_time = 0
    
    print("Scheduler: Started background loop.")
    while True:
        try:
            schedule.run_pending()
            
            curr_time = time.time()
            
            # Check price alerts every 10 minutes (600 seconds)
            if curr_time - last_price_alert_time > 600:
                check_price_alerts()
                last_price_alert_time = curr_time
                
            # Check for config changes every 60 seconds
            if curr_time - last_check_time > 60:
                new_config = telegram_bot.load_json(telegram_bot.CONFIG_FILE, {})
                new_m = new_config.get("morning_time", "07:00")
                new_e = new_config.get("evening_time", "20:30")
                if new_m != m_time or new_e != e_time:
                    print(f"Scheduler: Schedule times changed in config. Reconfiguring...")
                    m_time, e_time = new_m, new_e
                    setup_schedule(m_time, e_time)
                last_check_time = curr_time
        except Exception as e:
            print(f"Scheduler error in loop: {e}")
            
        time.sleep(5)

