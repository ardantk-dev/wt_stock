import threading
import time
import sys
import telegram_bot
import scheduler

def start_bot():
    print("Bot: Starting message polling...")
    try:
        # Start telegram bot polling
        telegram_bot.bot.infinity_polling(timeout=10, long_polling_timeout=5)
    except Exception as e:
        print(f"Bot Error: {e}")

def main():
    # Double check configuration
    if not telegram_bot.is_configured():
        print("=" * 70)
        print(" 🚨 [설정 오류] 텔레그램 봇 토큰(telegram_token)이 등록되지 않았습니다.")
        print("=" * 70)
        print(" 에이전트 가동을 위해 아래 안내를 따라 설정해 주세요:")
        print(" 1. 텔레그램에서 '@BotFather'를 검색해 대화창을 엽니다.")
        print(" 2. '/newbot' 명령어를 입력하여 새로운 봇을 생성합니다.")
        print(" 3. 생성 완료 후 발급받은 'API Token'을 복사합니다.")
        print(" 4. 현재 폴더의 'config.json' 파일을 메모장 등으로 열어 아래와 같이 입력합니다.")
        print("    {")
        print("      \"telegram_token\": \"복사한_토큰_값\",")
        print("      \"telegram_chat_id\": \"\",")
        print("      \"morning_time\": \"07:00\",")
        print("      \"evening_time\": \"20:30\"")
        print("    }")
        print(" 5. 저장을 완료한 후 다시 'python run.py'를 실행합니다.")
        print(" 6. 텔레그램에서 생성하신 봇 이름을 검색해 '/start'를 누릅니다.")
        print("    -> 에이전트가 본인의 Chat ID를 자동으로 인식해 config.json에 저장합니다!")
        print("=" * 70)
        sys.exit(1)

    print("=" * 70)
    print(" 🚀 주식관리 에이전트가 가동되었습니다!")
    print(" - 아침 브리핑: 매일 오전 07:00 KST")
    print(" - 저녁 브리핑: 매일 오후 20:30 KST")
    print(" - 종료하려면 터미널에서 Ctrl+C를 누르십시오.")
    print("=" * 70)

    # Start bot polling in a daemon thread
    bot_thread = threading.Thread(target=start_bot, name="TelegramBotThread", daemon=True)
    bot_thread.start()

    # Run scheduler in the main thread (keeps the main process alive and handles Ctrl+C cleanly)
    try:
        scheduler.run_scheduler_loop()
    except KeyboardInterrupt:
        print("\n👋 에이전트 작동을 종료합니다. 감사합니다!")
        sys.exit(0)

if __name__ == "__main__":
    main()
