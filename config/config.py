import os
from dotenv import load_dotenv

load_dotenv()

# 실제투자용 HTTP와 소켓 URL
real_host_url = "https://api.kiwoom.com"
real_socket_url = "wss://api.kiwoom.com:10000"

# 모의투자용 HTTP와 소켓 URL
paper_host_url = "https://mockapi.kiwoom.com"
paper_socket_url = "wss://mockapi.kiwoom.com:10000"

# 실제투자용 앱 키와 시크릿
real_app_key = os.getenv("KIWOOM_APP_KEY")
real_app_secret = os.getenv("KIWOOM_APP_SECRET_KEY")

# 모의투자용 앱 키와 시크릿
paper_app_key = os.getenv("MO_KIWOOM_APP_KEY")
paper_app_secret = os.getenv("MO_KIWOOM_APP_SECRET_KEY")

# 텔레그램용 챗 아이디와 토큰
telegram_chat_id = os.getenv("TELEGRAM_CHAT_ID")
telegram_token = os.getenv("TELEGRAM_TOKEN")