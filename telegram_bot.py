import os
import json
import telebot
from telebot import types
from datetime import datetime
import stock_analyzer
import kiwoom_service

CONFIG_FILE = "config.json"
PORTFOLIO_FILE = "portfolio.json"
TRADE_LOG_FILE = "trade_log.json"

def load_json(filepath, default):
    if not os.path.exists(filepath):
        return default
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as e:
        print(f"Error reading {filepath}: {e}")
        return default

def save_json(filepath, data):
    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Error saving {filepath}: {e}")
        return False

# Initialize bot instance safely
config = load_json(CONFIG_FILE, {})
BOT_TOKEN = config.get("telegram_token", "")

bot = None
if BOT_TOKEN:
    try:
        bot = telebot.TeleBot(BOT_TOKEN, parse_mode="MARKDOWN")
    except Exception as e:
        print(f"Failed to initialise Telegram Bot: {e}")
else:
    print("WARNING: telegram_token is empty in config.json. Please set your Telegram bot token.")

def is_configured():
    global BOT_TOKEN, bot, config
    config = load_json(CONFIG_FILE, {})
    BOT_TOKEN = config.get("telegram_token", "")
    if not BOT_TOKEN:
        return False
    if bot is None:
        try:
            bot = telebot.TeleBot(BOT_TOKEN, parse_mode="MARKDOWN")
        except Exception:
            return False
    return True

# Keyboard helpers
def get_main_keyboard():
    keyboard = types.ReplyKeyboardMarkup(row_width=2, resize_keyboard=True)
    btn_portfolio = types.KeyboardButton("📊 포트폴리오 조회")
    btn_balance = types.KeyboardButton("💰 예수금 조회")
    btn_morning = types.KeyboardButton("🌅 아침 브리핑")
    btn_evening = types.KeyboardButton("🌆 저녁 브리핑")
    btn_trade = types.KeyboardButton("✍️ 매매 등록 안내")
    keyboard.add(btn_portfolio, btn_balance)
    keyboard.add(btn_morning, btn_evening)
    keyboard.add(btn_trade)
    return keyboard

# Command Handlers
if bot:
    @bot.message_handler(commands=['start', 'help'])
    def send_welcome(message):
        chat_id = str(message.chat.id)
        
        # Save chat ID to config if not set
        cfg = load_json(CONFIG_FILE, {})
        if cfg.get("telegram_chat_id") != chat_id:
            cfg["telegram_chat_id"] = chat_id
            save_json(CONFIG_FILE, cfg)
            print(f"Saved new Telegram Chat ID: {chat_id}")
            
        welcome_text = (
            "👋 안녕하세요! *국내외 주식관리 에이전트*입니다.\n\n"
            f"자동으로 귀하의 Chat ID `{chat_id}`가 시스템에 등록되었습니다.\n"
            "매일 아침 7시와 저녁 8시 30분에 설정된 브리핑이 발송됩니다.\n\n"
            "📌 *사용 가능한 명령어:*\n"
            "• /portfolio (또는 버튼) - 현재 내 보유 자산 및 수익률 실시간 조회\n"
            "• /balance (또는 버튼) - 키움증권 실제 예수금 및 출금가능금액 조회\n"
            "• /morning - 아침 7시 모닝 브리핑 수동 트리거\n"
            "• /evening - 저녁 8시 반 마감 브리핑 수동 트리거\n"
            "• /sync - 키움증권 실제 잔고와 포트폴리오 동기화\n"
            "• /buy `[종목]` `[수량]` `[단가]` - 실제 키움증권 계좌로 매수 주문 전송 (0 입력 시 시장가)\n"
            "• /sell `[종목]` `[수량]` `[단가]` - 실제 키움증권 계좌로 매도 주문 전송 (0 입력 시 시장가)\n"
            "• /add `[종목]` `[수량]` `[평단가]` - 종목 포트폴리오에 직접 추가 (국가 자동 판별)\n"
            "• /remove `[종목]` - 포트폴리오에서 종목 삭제\n\n"
            "✍️ *간편 매매 기록 등록 방법:*\n"
            "채팅창에 아래 양식으로 직접 메시지를 입력하시면 실제 키움 주문 전송 여부를 확인 후 처리합니다:\n"
            "`[종목명 또는 티커] 매수/매도 [수량] [단가]`\n"
            "• 예: `삼성전자 매수 10 75000`\n"
            "• 예: `AAPL 매수 5 180`"
        )
        bot.reply_to(message, welcome_text, reply_markup=get_main_keyboard())


    @bot.message_handler(commands=['portfolio'])
    def show_portfolio(message):
        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        bot.send_chat_action(message.chat.id, 'typing')
        brief = stock_analyzer.format_evening_briefing(portfolio)
        # We replace the header for real-time portfolio check
        brief = brief.replace("🌆 *[저녁 마감 브리핑]*", "📊 *[실시간 포트폴리오 현황]*")
        bot.reply_to(message, brief, reply_markup=get_main_keyboard())

    @bot.message_handler(commands=['balance'])
    def show_balance(message):
        if not kiwoom_service.is_configured():
            bot.reply_to(message, "⚠️ 키움증권 API 설정이 완료되지 않았습니다. config.json을 확인해 주세요.")
            return
            
        bot.send_chat_action(message.chat.id, 'typing')
        balance = kiwoom_service.get_balance()
        
        if not balance:
            bot.reply_to(message, "❌ 키움증권에서 잔고 정보를 가져오지 못했습니다. API 설정을 확인해 주세요.")
            return
            
        try:
            deposit = int(balance.get("entr", 0))
            d2_deposit = int(balance.get("d2_entra", 0))
            total_evaluation = int(balance.get("tot_est_amt", 0))
            total_asset = int(balance.get("aset_evlt_amt", 0))
            total_purchase = int(balance.get("tot_pur_amt", 0))
            total_profit_loss = total_evaluation - total_purchase
            profit_rate = (total_profit_loss / total_purchase * 100) if total_purchase > 0 else 0.0
            
            sign = "🔺" if total_profit_loss > 0 else "🔻" if total_profit_loss < 0 else "➖"
            
            balance_text = (
                "💰 *[키움증권 계좌 잔고 현황]*\n\n"
                f"• *예수금 (당일 출금가능):* {deposit:,.0f} 원\n"
                f"• *D+2 예수금:* {d2_deposit:,.0f} 원\n\n"
                f"• *주식 매입금액:* {total_purchase:,.0f} 원\n"
                f"• *주식 평가금액:* {total_evaluation:,.0f} 원\n"
                f"• *주식 평가손익:* {sign} {total_profit_loss:,.0f} 원 ({profit_rate:+.2f}%)\n\n"
                f"• *총 자산 평가액 (예수금+주식):* {total_asset:,.0f} 원\n"
            )
            bot.reply_to(message, balance_text, reply_markup=get_main_keyboard())
        except Exception as e:
            print(f"Error formatting balance: {e}")
            bot.reply_to(message, f"❌ 잔고 정보를 가공하는 중 오류가 발생했습니다: {e}")

    @bot.message_handler(commands=['morning'])
    def trigger_morning(message):
        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        bot.send_chat_action(message.chat.id, 'typing')
        brief = stock_analyzer.format_morning_briefing(portfolio)
        bot.reply_to(message, brief, reply_markup=get_main_keyboard())

    @bot.message_handler(commands=['evening'])
    def trigger_evening(message):
        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        bot.send_chat_action(message.chat.id, 'typing')
        brief = stock_analyzer.format_evening_briefing(portfolio)
        bot.reply_to(message, brief, reply_markup=get_main_keyboard())

    @bot.message_handler(commands=['add'])
    def add_stock_command(message):
        # Format: /add ticker qty price
        args = message.text.split()
        if len(args) < 4:
            bot.reply_to(message, "⚠️ 올바른 형식이 아닙니다.\n사용법: `/add [종목명/티커] [수량] [평단가]`\n예: `/add 삼성전자 10 75000` 또는 `/add AAPL 5 180`")
            return
            
        name_or_symbol = args[1]
        try:
            qty = float(args[2])
            price = float(args[3])
        except ValueError:
            bot.reply_to(message, "⚠️ 수량과 평단가는 숫자여야 합니다.")
            return

        nation = "US" if any(c.isalpha() for c in name_or_symbol) else "KR"
        ticker, resolved_name = stock_analyzer.resolve_ticker(name_or_symbol, nation)
        
        # If KR check failed but it had letters, try KR just in case, or default.
        if nation == "US" and not ticker:
            # Maybe it's a Korean stock name in English? Or just fallback to US.
            ticker, resolved_name = name_or_symbol.upper(), name_or_symbol
            
        if not ticker:
            bot.reply_to(message, f"⚠️ 종목 '{name_or_symbol}'을 찾을 수 없습니다. 국가나 티커를 확인해주세요.")
            return

        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        nation_key = "US" if nation == "US" else "KR"
        
        # Update portfolio
        exists = False
        for stock in portfolio[nation_key]:
            if stock["ticker"] == ticker:
                # Recalculate average price
                old_qty = stock["quantity"]
                old_price = stock["buy_price"]
                stock["quantity"] = old_qty + qty
                stock["buy_price"] = ((old_price * old_qty) + (price * qty)) / (old_qty + qty)
                exists = True
                break
                
        if not exists:
            portfolio[nation_key].append({
                "ticker": ticker,
                "name": resolved_name,
                "quantity": qty,
                "buy_price": price
            })
            
        save_json(PORTFOLIO_FILE, portfolio)
        
        # Log trade
        trade_logs = load_json(TRADE_LOG_FILE, [])
        trade_logs.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "BUY (MANUAL_ADD)",
            "nation": nation_key,
            "ticker": ticker,
            "name": resolved_name,
            "quantity": qty,
            "price": price
        })
        save_json(TRADE_LOG_FILE, trade_logs)
        
        curr_sym = "$" if nation_key == "US" else "원"
        bot.reply_to(
            message, 
            f"✅ *{resolved_name}* ({ticker}) 종목이 포트폴리오에 추가되었습니다!\n• 수량: {qty}주\n• 매수단가: {price:,.2f}{curr_sym}",
            reply_markup=get_main_keyboard()
        )

    @bot.message_handler(commands=['remove'])
    def remove_stock_command(message):
        args = message.text.split()
        if len(args) < 2:
            bot.reply_to(message, "⚠️ 올바른 형식이 아닙니다.\n사용법: `/remove [종목명/티커]`\n예: `/remove 삼성전자` 또는 `/remove AAPL`")
            return
            
        name_or_symbol = args[1]
        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        
        removed = False
        for nation in ["KR", "US"]:
            for stock in portfolio[nation]:
                if stock["name"] == name_or_symbol or stock["ticker"].startswith(name_or_symbol.upper()):
                    portfolio[nation].remove(stock)
                    removed = True
                    resolved_name = stock["name"]
                    ticker = stock["ticker"]
                    break
            if removed:
                break
                
        if removed:
            save_json(PORTFOLIO_FILE, portfolio)
            bot.reply_to(message, f"❌ *{resolved_name}* ({ticker}) 종목이 포트폴리오에서 삭제되었습니다.")
        else:
            bot.reply_to(message, f"⚠️ 포트폴리오에서 '{name_or_symbol}' 종목을 찾지 못했습니다.")

    # Keyboard text button handlers
    @bot.message_handler(func=lambda message: message.text in ["📊 포트폴리오 조회", "💰 예수금 조회", "🌅 아침 브리핑", "🌆 저녁 브리핑", "✍️ 매매 등록 안내"])
    def handle_keyboard_buttons(message):
        if message.text == "📊 포트폴리오 조회":
            show_portfolio(message)
        elif message.text == "💰 예수금 조회":
            show_balance(message)
        elif message.text == "🌅 아침 브리핑":
            trigger_morning(message)
        elif message.text == "🌆 저녁 브리핑":
            trigger_evening(message)
        elif message.text == "✍️ 매매 등록 안내":
            info_text = (
                "✍️ *매매 기록 간편 등록*\n\n"
                "채팅창에 아래 규칙으로 직접 입력해주시면 포트폴리오에 즉시 연동됩니다.\n\n"
                "📌 *입력 양식:*\n"
                "`[종목명 또는 티커] 매수/매도 [수량] [체결단가]`\n\n"
                "💡 *실제 입력 예시:*\n"
                "• `삼성전자 매수 15 76500`\n"
                "• `sk하이닉스 매도 5 185000`\n"
                "• `TSLA 매수 3 175.5`\n"
                "• `AAPL 매도 2 188`\n\n"
                "매도 시 보유량보다 많은 수량을 입력하면 에러가 발생하니 주의해 주세요."
            )
            bot.reply_to(message, info_text, reply_markup=get_main_keyboard())

    def process_local_trade_helper(ticker, resolved_name, action_type, qty, price, nation_key):
        try:
            portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
            is_buy = action_type in ["매수", "buy", "BUY"]
            
            # Process Portfolio Updates
            stocks_list = portfolio[nation_key]
            found_stock = None
            for stock in stocks_list:
                if stock["ticker"] == ticker:
                    found_stock = stock
                    break
                    
            if is_buy:
                if found_stock:
                    old_qty = found_stock["quantity"]
                    old_price = found_stock["buy_price"]
                    found_stock["quantity"] = old_qty + qty
                    found_stock["buy_price"] = ((old_price * old_qty) + (price * qty)) / (old_qty + qty)
                else:
                    portfolio[nation_key].append({
                        "ticker": ticker,
                        "name": resolved_name,
                        "quantity": qty,
                        "buy_price": price
                    })
            else:  # Sell
                if not found_stock:
                    return False, f"현재 포트폴리오에 *{resolved_name}* 종목이 존재하지 않아 매도할 수 없습니다."
                if found_stock["quantity"] < qty:
                    return False, f"매도 수량이 보유 수량을 초과합니다. (보유: {found_stock['quantity']}주 | 요청: {qty}주)"
                elif found_stock["quantity"] == qty:
                    stocks_list.remove(found_stock)
                else:
                    found_stock["quantity"] -= qty
                    
            save_json(PORTFOLIO_FILE, portfolio)
            
            # Log Trade
            trade_logs = load_json(TRADE_LOG_FILE, [])
            trade_logs.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "type": "BUY" if is_buy else "SELL",
                "nation": nation_key,
                "ticker": ticker,
                "name": resolved_name,
                "quantity": qty,
                "price": price
            })
            save_json(TRADE_LOG_FILE, trade_logs)
            return True, ""
        except Exception as e:
            return False, str(e)

    @bot.message_handler(commands=['sync'])
    def sync_kiwoom_portfolio(message):
        if not kiwoom_service.is_configured():
            bot.reply_to(message, "⚠️ 키움증권 API 설정이 완료되지 않았습니다. config.json을 확인해 주세요.")
            return
            
        bot.send_chat_action(message.chat.id, 'typing')
        bot.reply_to(message, "🔄 키움증권 계좌에서 보유 종목 정보를 가져오는 중입니다...")
        
        holdings = kiwoom_service.get_holdings()
        
        if holdings is None:
            bot.send_message(message.chat.id, "❌ 키움증권 데이터를 가져오는데 실패했습니다. API 설정을 확인해 주세요.")
            return
            
        resolved_holdings = []
        sync_desc = ""
        
        for h in holdings:
            code = h["ticker"]
            name = h["name"]
            qty = h["quantity"]
            buy_price = h["buy_price"]
            
            yf_ticker, resolved_name = stock_analyzer.resolve_ticker(code, "KR")
            if not yf_ticker:
                yf_ticker = f"{code}.KS"
                resolved_name = name
                
            resolved_holdings.append({
                "ticker": yf_ticker,
                "name": resolved_name,
                "quantity": qty,
                "buy_price": buy_price
            })
            sync_desc += f"• *{resolved_name}* ({yf_ticker}): {qty}주 | 평단가: {buy_price:,.0f}원\n"
            
        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        portfolio["KR"] = resolved_holdings
        save_json(PORTFOLIO_FILE, portfolio)
        
        trade_logs = load_json(TRADE_LOG_FILE, [])
        trade_logs.append({
            "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "type": "SYNC_KIWOOM",
            "nation": "KR",
            "count": len(resolved_holdings)
        })
        save_json(TRADE_LOG_FILE, trade_logs)
        
        if resolved_holdings:
            reply_msg = (
                f"✅ *키움증권 포트폴리오 동기화 완료!*\n\n"
                f"다음 보유 종목 정보가 로컬 포트폴리오에 업데이트 되었습니다:\n\n"
                f"{sync_desc}"
            )
        else:
            reply_msg = (
                f"✅ *키움증권 포트폴리오 동기화 완료!*\n\n"
                f"보유 중인 국내 주식이 없어 로컬 포트폴리오의 국내 주식 내역이 비워졌습니다."
            )
        bot.send_message(message.chat.id, reply_msg)

    @bot.message_handler(commands=['buy', 'sell'])
    def handle_trade_commands(message):
        args = message.text.split()
        cmd = args[0].replace("/", "")
        if len(args) < 3:
            bot.reply_to(
                message,
                f"⚠️ 올바른 형식이 아닙니다.\n사용법: `/{cmd} [종목명/티커] [수량] [단가]`\n"
                f"예: `/{cmd} 삼성전자 10 75000` (지정가)\n"
                f"예: `/{cmd} 삼성전자 10 0` (0 입력 시 시장가 주문)"
            )
            return
            
        name_or_symbol = args[1]
        try:
            qty = float(args[2])
            price = float(args[3]) if len(args) > 3 else 0.0
        except ValueError:
            bot.reply_to(message, "⚠️ 수량과 단가는 숫자여야 합니다.")
            return
            
        nation = "US" if any(c.isalpha() for c in name_or_symbol) else "KR"
        ticker, resolved_name = stock_analyzer.resolve_ticker(name_or_symbol, nation)
        if not ticker:
            bot.reply_to(message, f"⚠️ 종목 '{name_or_symbol}'을 찾을 수 없습니다.")
            return
            
        action_desc = "매수" if cmd == "buy" else "매도"
        
        if kiwoom_service.is_configured() and nation == "KR":
            markup = types.InlineKeyboardMarkup(row_width=2)
            cb_yes = f"kw_tr:yes:{cmd}:{ticker}:{qty}:{price}"
            cb_no = f"kw_tr:no:{cmd}:{ticker}:{qty}:{price}"
            
            btn_yes = types.InlineKeyboardButton("예 (실제 주문)", callback_data=cb_yes)
            btn_no = types.InlineKeyboardButton("아니오 (로컬 기록)", callback_data=cb_no)
            markup.add(btn_yes, btn_no)
            
            price_desc = "시장가" if price == 0 else f"{price:,.0f}원"
            confirm_text = (
                f"❓ *실제 키움증권 계좌로 주문을 전송할까요?*\n\n"
                f"• 종목: *{resolved_name}* ({ticker})\n"
                f"• 거래: {action_desc}\n"
                f"• 수량: {qty}주\n"
                f"• 단가: {price_desc}\n\n"
                f"⚠️ '예'를 누르면 실제 주문이 전송됩니다."
            )
            bot.send_message(message.chat.id, confirm_text, reply_markup=markup)
        else:
            success, err_msg = process_local_trade_helper(ticker, resolved_name, cmd, qty, price, nation)
            if not success:
                bot.reply_to(message, f"❌ {err_msg}")
                return
            curr_sym = "$" if nation == "US" else "원"
            reply_msg = (
                f"✍️ *로컬 매매 기록 완료*\n\n"
                f"• 종목: *{resolved_name}* ({ticker})\n"
                f"• 거래: {action_desc}\n"
                f"• 수량: {qty}주\n"
                f"• 단가: {price:,.2f}{curr_sym}\n\n"
                f"포트폴리오가 업데이트 되었습니다. '/portfolio' 명령어로 전체 현황을 확인할 수 있습니다."
            )
            bot.reply_to(message, reply_msg, reply_markup=get_main_keyboard())

    @bot.callback_query_handler(func=lambda call: call.data.startswith("kw_tr:"))
    def handle_kiwoom_trade_callback(call):
        parts = call.data.split(":")
        decision = parts[1]
        action_type = parts[2]
        ticker = parts[3]
        qty = float(parts[4])
        price = float(parts[5])
        
        nation_key = "US" if any(c.isalpha() for c in ticker) else "KR"
        resolved_name = ticker
        
        portfolio = load_json(PORTFOLIO_FILE, {"KR": [], "US": []})
        for s in portfolio[nation_key]:
            if s["ticker"] == ticker:
                resolved_name = s["name"]
                break
        if resolved_name == ticker and nation_key == "KR":
            resolved_name = stock_analyzer.get_kr_stock_name(ticker.split(".")[0])
            
        is_buy = action_type in ["buy", "매수"]
        action_desc = "매수" if is_buy else "매도"
        curr_sym = "원" if nation_key == "KR" else "$"
        
        try:
            bot.delete_message(call.message.chat.id, call.message.message_id)
        except Exception:
            pass
            
        if decision == "no":
            success, err_msg = process_local_trade_helper(ticker, resolved_name, action_type, qty, price, nation_key)
            if success:
                reply_msg = (
                    f"✍️ *로컬 매매 기록 완료*\n\n"
                    f"• 종목: *{resolved_name}* ({ticker})\n"
                    f"• 거래: {action_desc} (로컬 기록만 진행)\n"
                    f"• 수량: {qty}주\n"
                    f"• 단가: {price:,.0f}{curr_sym}\n\n"
                    f"포트폴리오가 업데이트 되었습니다. '/portfolio' 명령어로 전체 현황을 확인할 수 있습니다."
                )
            else:
                reply_msg = f"❌ 로컬 기록 실패: {err_msg}"
            bot.send_message(call.message.chat.id, reply_msg)
            
        elif decision == "yes":
            bot.send_chat_action(call.message.chat.id, 'typing')
            trde_tp = "03" if price == 0 else "00"
            
            res = kiwoom_service.execute_order(ticker, qty, price, is_buy=is_buy, trde_tp=trde_tp)
            if res["success"]:
                success, err_msg = process_local_trade_helper(ticker, resolved_name, action_type, qty, price, nation_key)
                price_desc = "시장가" if price == 0 else f"{price:,.0f}원"
                reply_msg = (
                    f"✅ *키움증권 실제 주문 성공!*\n\n"
                    f"• 종목: *{resolved_name}* ({ticker})\n"
                    f"• 거래: {action_desc}\n"
                    f"• 수량: {qty}주\n"
                    f"• 단가: {price_desc}\n\n"
                    f"주문이 정상적으로 접수되었습니다. 로컬 포트폴리오도 동기화되었습니다."
                )
            else:
                reply_msg = (
                    f"❌ *키움증권 주문 전송 실패*\n\n"
                    f"상세 에러: {res['message']}"
                )
            bot.send_message(call.message.chat.id, reply_msg)

    # Text parsing handler for trades: "[종목] 매수/매도 [수량] [단가]"
    @bot.message_handler(func=lambda message: True)
    def parse_trade_text(message):
        parts = message.text.strip().split()
        if len(parts) != 4:
            if any(word in message.text for word in ["매수", "매도", "buy", "sell"]):
                bot.reply_to(message, "⚠️ 입력 형식이 바르지 않습니다.\n양식: `[종목명] 매수/매도 [수량] [단가]`\n예: `삼성전자 매수 10 75000`")
            return
            
        name_or_symbol = parts[0]
        action = parts[1]
        
        if action not in ["매수", "매도", "buy", "sell"]:
            return
            
        try:
            qty = float(parts[2])
            price = float(parts[3])
        except ValueError:
            bot.reply_to(message, "⚠️ 수량과 단가는 올바른 숫자여야 합니다.")
            return

        bot.send_chat_action(message.chat.id, 'typing')

        # Detect nation
        nation = "US" if any(c.isalpha() for c in name_or_symbol) else "KR"
        ticker, resolved_name = stock_analyzer.resolve_ticker(name_or_symbol, nation)
        
        if nation == "US" and not ticker:
            ticker, resolved_name = name_or_symbol.upper(), name_or_symbol
            
        if not ticker:
            bot.reply_to(message, f"⚠️ 종목 '{name_or_symbol}'을 찾을 수 없습니다. 다시 시도해 주세요.")
            return

        # Check if Kiwoom is configured and stock is domestic
        if kiwoom_service.is_configured() and nation == "KR":
            markup = types.InlineKeyboardMarkup(row_width=2)
            act_type = "buy" if action in ["매수", "buy"] else "sell"
            cb_yes = f"kw_tr:yes:{act_type}:{ticker}:{qty}:{price}"
            cb_no = f"kw_tr:no:{act_type}:{ticker}:{qty}:{price}"
            
            btn_yes = types.InlineKeyboardButton("예 (실제 주문)", callback_data=cb_yes)
            btn_no = types.InlineKeyboardButton("아니오 (로컬 기록)", callback_data=cb_no)
            markup.add(btn_yes, btn_no)
            
            price_desc = "시장가" if price == 0 else f"{price:,.0f}원"
            confirm_text = (
                f"❓ *실제 키움증권 계좌로 주문을 전송할까요?*\n\n"
                f"• 종목: *{resolved_name}* ({ticker})\n"
                f"• 거래: {'매수' if act_type == 'buy' else '매도'}\n"
                f"• 수량: {qty}주\n"
                f"• 단가: {price_desc}\n\n"
                f"⚠️ '예'를 누르면 실제 주문이 전송됩니다."
            )
            bot.send_message(message.chat.id, confirm_text, reply_markup=markup)
            return

        success, err_msg = process_local_trade_helper(ticker, resolved_name, action, qty, price, "US" if nation == "US" else "KR")
        if not success:
            bot.reply_to(message, f"❌ {err_msg}")
            return
            
        action_desc = "매수" if action in ["매수", "buy"] else "매도"
        curr_sym = "$" if nation == "US" else "원"
        reply_msg = (
            f"✍️ *매매 기록 완료*\n\n"
            f"• 종목: *{resolved_name}* ({ticker})\n"
            f"• 거래: {action_desc}\n"
            f"• 수량: {qty}주\n"
            f"• 단가: {price:,.2f}{curr_sym}\n\n"
            f"포트폴리오가 업데이트 되었습니다. '/portfolio' 명령어로 전체 현황을 확인할 수 있습니다."
        )
        bot.reply_to(message, reply_msg, reply_markup=get_main_keyboard())


def send_alert(message_text):
    """Utility function for scheduler to send briefings to registered chat ID."""
    global bot
    if not is_configured():
        print("Cannot send alert. Telegram bot is not configured.")
        return False
        
    chat_id = config.get("telegram_chat_id", "")
    if not chat_id:
        print("Cannot send alert. telegram_chat_id is not registered in config.json. Use /start first.")
        return False
        
    try:
        bot.send_message(chat_id, message_text, parse_mode="MARKDOWN", reply_markup=get_main_keyboard())
        return True
    except Exception as e:
        print(f"Error sending scheduled alert: {e}")
        return False
