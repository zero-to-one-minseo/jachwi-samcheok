"""클립보드에 복사한 열쇠를 .streamlit/secrets.toml에 저장한다. 값은 화면에 보이지 않고, 저장한 뒤 클립보드를 비운다.

    .venv/bin/python tools/save_secret.py JUSO_COORD_KEY

같은 이름이 이미 있으면 새 값으로 바꾼다. 고치기 전에 그날 처음 한 번 secrets.toml.bak-날짜로 백업한다(git이 무시하는 이름).
"""

from __future__ import annotations

import datetime as dt
import re
import shutil
import subprocess
import sys
from pathlib import Path

SECRETS = Path(__file__).resolve().parent.parent / ".streamlit" / "secrets.toml"
NAME = re.compile(r"[A-Z][A-Z0-9_]{2,40}")
VALUE = re.compile(r"[A-Za-z0-9+/=_.\-]{10,300}")


def main(argv: list[str]) -> int:
    if len(argv) != 1 or not NAME.fullmatch(argv[0]):
        print("쓰는 법: tools/save_secret.py 열쇠_이름(예: JUSO_COORD_KEY)")
        return 2
    name = argv[0]
    value = subprocess.run(["pbpaste"], capture_output=True, text=True, check=True).stdout.strip()
    if not VALUE.fullmatch(value):
        print("클립보드 내용이 열쇠 모양이 아니에요. 열쇠만 다시 복사해 주세요.")
        return 1
    text = SECRETS.read_text(encoding="utf-8") if SECRETS.exists() else ""
    if text:
        backup = SECRETS.with_name(f"secrets.toml.bak-{dt.date.today():%Y-%m-%d}")
        if not backup.exists():
            shutil.copy2(SECRETS, backup)
    lines = [line for line in text.splitlines() if not re.match(rf"\s*{name}\s*=", line)]
    lines.append(f'{name} = "{value}"')
    SECRETS.write_text("\n".join(lines) + "\n", encoding="utf-8")
    subprocess.run(["pbcopy"], input="", text=True, check=False)
    print(f"{name} 저장함(값은 보여 주지 않음, {len(value)}자). 클립보드는 비웠어요.")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
