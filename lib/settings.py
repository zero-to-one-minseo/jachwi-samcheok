from datetime import timedelta, timezone
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parent.parent
CRITERIA_PATH = APP_ROOT / "criteria.csv"
INSTRUCTIONS_PATH = APP_ROOT / "prompts" / "instructions.txt"

KST = timezone(timedelta(hours=9))

# 모델을 바꾸면 기본 effort, 생각 끄기 가능 여부, 대체 모델 동작이 함께 바뀐다(기술_확인.md 2장 '21:00 비상안').
# 아래 다섯 값은 한 묶음으로 바꾼다.
MODEL = "claude-opus-5-5"
EFFORT = "medium"
MAX_TOKENS = 16000
USE_FALLBACK = False
FALLBACK_BETA = "server-side-fallback-2026-07-01"

TIMEOUT_S = 120
# SDK 재시도는 시간 초과까지 다시 보내서 끈다. 앱 코드가 정한 오류만 1회 다시 보낸다.
MAX_RETRIES = 0
RETRY_AFTER_MAX_S = 10.0
RETRY_DELAY_S = 1.0

SESSION_LIMIT = 10
DAILY_LIMIT = 150

IMAGE_MAX_LONG_SIDE = 2576
IMAGE_MAX_TOKENS = 4784
IMAGE_PATCH_PX = 28
# 4,800만 화소 휴대폰 원본(8064x6048)은 통과시키고, Pillow 경고선(약 8,900만)보다는 낮게 둔다.
IMAGE_MAX_PIXELS = 50_000_000
JPEG_QUALITY = 90

UPLOAD_MAX_MB = 20  # .streamlit/config.toml의 maxUploadSize와 같은 값
PDF_MAX_MB = 10
UPLOAD_TYPES = ("jpg", "jpeg", "png", "pdf")

FEE_THRESHOLD_WON = 100_000
FEE_SUSPICIOUS_WON = 500_000
MAX_QUESTIONS = 7
MAX_OK_CARDS = 4
