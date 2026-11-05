"""가상 계약서 샘플(sample_a.jpg, sample_y.jpg, sample_b.pdf)을 그린다.

실행: app 폴더에서 .venv/bin/python tools/make_samples.py
글꼴은 이 Mac의 시스템 글꼴을 그 자리에서 읽기만 한다(저장소로 복사하지 않는다).
모든 이름·주소·전화·계좌번호는 지어낸 값이다.
"""

import glob
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "samples"

W, H = 1240, 1754  # A4, 150dpi
MARGIN = 90

SD_GOTHIC = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
MYUNGJO = "/System/Library/Fonts/Supplemental/AppleMyungjo.ttf"
# 나눔손글씨는 macOS가 내려받아 둔 글꼴 자산에만 있어 경로에 해시가 들어간다.
HAND_CANDIDATES = [
    ("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/NanumScript.ttc", 1),
    ("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/Pilgiche.ttf", 0),
    ("/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/Hanzipen.ttc", 0),
]

INK = (30, 30, 30)
RED = (200, 30, 30)
PEN = (25, 45, 125)


def _font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


def hand_font(size):
    for pattern, index in HAND_CANDIDATES:
        found = sorted(glob.glob(pattern))
        if found:
            return _font(found[0], size, index)
    sys.exit("손글씨 글꼴(NanumScript/Pilgiche/Hanzipen)을 찾지 못했어요. 서체 관리자에서 내려받아 주세요.")


class Page:
    def __init__(self):
        self.img = Image.new("RGB", (W, H), (252, 251, 247))
        self.d = ImageDraw.Draw(self.img)
        self.y = 60
        self.body = _font(MYUNGJO, 25)
        self.label = _font(SD_GOTHIC, 24, 2)
        self.head = _font(SD_GOTHIC, 28, 6)

    def banner(self):
        big = _font(SD_GOTHIC, 58, 14)
        small = _font(SD_GOTHIC, 24, 2)
        text = "가상 샘플 · 실제 계약서가 아닙니다"
        tw = self.d.textlength(text, font=big)
        self.d.rectangle([MARGIN - 10, self.y - 10, W - MARGIN + 10, self.y + 118], outline=RED, width=5)
        self.d.text(((W - tw) / 2, self.y), text, font=big, fill=RED)
        sub = "이름·주소·전화·계좌번호는 모두 지어낸 값이에요 (해커톤 시험용)"
        sw = self.d.textlength(sub, font=small)
        self.d.text(((W - sw) / 2, self.y + 76), sub, font=small, fill=RED)
        self.y += 150

    def title(self, text):
        f = _font(SD_GOTHIC, 44, 6)
        tw = self.d.textlength(text, font=f)
        self.d.text(((W - tw) / 2, self.y), text, font=f, fill=INK)
        self.y += 74

    def heading(self, text):
        self.y += 10
        self.d.text((MARGIN, self.y), text, font=self.head, fill=INK)
        self.y += 44

    def _wrap(self, text, font, width):
        # 단어 단위로 끊어 전화·계좌번호가 줄 끝에서 갈라지지 않게 한다(개인정보 가리기 시험용).
        lines, cur = [], ""
        for word in text.split(" "):
            trial = f"{cur} {word}" if cur else word
            if self.d.textlength(trial, font=font) <= width:
                cur = trial
                continue
            if cur:
                lines.append(cur)
            cur = word
            while self.d.textlength(cur, font=font) > width:
                cut = len(cur)
                while self.d.textlength(cur[:cut], font=font) > width:
                    cut -= 1
                lines.append(cur[:cut])
                cur = cur[cut:]
        if cur:
            lines.append(cur)
        return lines

    def para(self, text, indent=0, hang=0, gap=8):
        width = W - 2 * MARGIN - indent
        lines = self._wrap(text, self.body, width)
        for i, line in enumerate(lines):
            x = MARGIN + indent + (hang if i else 0)
            self.d.text((x, self.y), line, font=self.body, fill=INK)
            self.y += 36
        self.y += gap

    def table(self, rows, label_w=190):
        x0, x1 = MARGIN, W - MARGIN
        for label, value in rows:
            lines = self._wrap(value, self.body, x1 - x0 - label_w - 24)
            h = 22 + 36 * len(lines)
            self.d.rectangle([x0, self.y, x1, self.y + h], outline=INK, width=2)
            self.d.line([x0 + label_w, self.y, x0 + label_w, self.y + h], fill=INK, width=2)
            self.d.text((x0 + 14, self.y + 12), label, font=self.label, fill=INK)
            for i, line in enumerate(lines):
                self.d.text((x0 + label_w + 14, self.y + 11 + 36 * i), line, font=self.body, fill=INK)
            self.y += h
        self.y += 14

    def handwriting(self, text, size=50, angle=-3.5, x=MARGIN + 30):
        f = hand_font(size)
        tw = int(self.d.textlength(text, font=f)) + 40
        layer = Image.new("RGBA", (tw, size + 40), (0, 0, 0, 0))
        ImageDraw.Draw(layer).text((20, 10), text, font=f, fill=PEN + (235,))
        layer = layer.rotate(angle, expand=True, resample=Image.BICUBIC)
        self.img.paste(layer, (x, self.y - 6), layer)
        self.y += layer.height + 6

    def signatures(self, date, parties):
        self.y += 6
        self.para(f"계약일: {date}", gap=4)
        for role, fields in parties:
            self.table([(role, " / ".join(fields))], label_w=150)

    def stamp(self, x, y, text):
        f = _font(SD_GOTHIC, 22, 6)
        self.d.ellipse([x, y, x + 64, y + 64], outline=RED, width=3)
        tw = self.d.textlength(text, font=f)
        self.d.text((x + 32 - tw / 2, y + 19), text, font=f, fill=RED)


def photo(img, seed, angle, noise=0.07, blur=0.7):
    rnd = random.Random(seed)
    bg = (200 + rnd.randint(-8, 8), 195 + rnd.randint(-8, 8), 185 + rnd.randint(-8, 8))
    out = img.rotate(angle, resample=Image.BICUBIC, fillcolor=bg)
    shade = Image.linear_gradient("L").resize(out.size).point(lambda v: 255 - v // 7)
    out = ImageChops.multiply(out, Image.merge("RGB", [shade] * 3))
    grain = Image.effect_noise(out.size, 40).convert("RGB")
    out = Image.blend(out, grain, noise)
    return out.filter(ImageFilter.GaussianBlur(blur))


def scan(img, seed):
    return photo(img, seed, angle=0.35, noise=0.035, blur=0.4)


def sample_a():
    p = Page()
    p.banner()
    p.title("주택 월세 계약서")
    p.para("임대인과 임차인은 아래 주택에 대하여 다음과 같이 임대차계약을 맺는다.")
    p.heading("1. 부동산의 표시")
    p.table([
        ("소재지", "강원특별자치도 삼척시 가상길 12, 가상하우스 302호"),
        ("구조·용도", "원룸(다가구주택) · 주거용 · 면적 23㎡"),
    ])
    p.heading("2. 계약 내용")
    p.table([
        ("보증금", "금 삼백만원정 (₩3,000,000)"),
        ("계약금", "금 삼십만원정은 계약할 때 지급하고 영수함"),
        ("잔금", "금 이백칠십만원정은 2027년 3월 1일에 지급한다"),
        ("월세", "금 삼십오만원정 (₩350,000), 매월 10일 지급"),
        ("관리비", "월 120,000원 (정액)"),
        ("기간", "2027년 3월 1일부터 2028년 2월 29일까지 (12개월)"),
    ])
    p.heading("3. 특약사항")
    items = [
        "1) 임차인은 잔금 지급일에 전입신고와 확정일자를 받고, 임대인은 그다음 날까지 저당권 등 담보권을 설정하지 않는다.",
        "2) 시설물의 노후화나 통상 생길 수 있는 파손은 원상복구 의무에 포함되지 않는다.",
        "3) 퇴실 시 청소비 10만 원을 보증금에서 공제한다.",
        "4) 수리비는 전부 임차인 부담으로 한다.",
        "5) 임차인이 계약 기간 중 퇴실하려면 1~2개월 전에 알리고, 새 임차인의 중개보수는 임차인이 부담한다.",
    ]
    for t in items:
        p.para(t, indent=10, hang=34, gap=4)
    p.handwriting("6) 반려동물 금지. 어기면 계약 해지함", size=52, angle=-3.0)
    p.signatures("2026년 11월 5일", [
        ("임대인", ["성명 김가상 (인)", "주소 강원특별자치도 삼척시 가상로 1", "전화 010-0000-0000", "주민등록번호 000000-0000000"]),
        ("임차인", ["성명 이예시 (인)", "주소 서울특별시 가상구 예시로 2", "전화 010-0000-0001"]),
        ("입금 계좌", ["가상은행 000-00-000000 (예금주 김가상)"]),
    ])
    p.stamp(W - MARGIN - 80, p.y - 250, "김가상")
    return photo(p.img, seed=11, angle=-1.3)


def sample_y():
    p = Page()
    p.banner()
    p.title("주택 임대차 계약서 (연세)")
    p.para("임대인과 임차인은 아래 주택에 대하여 1년분 방값을 미리 내는 연세 계약을 다음과 같이 맺는다.")
    p.heading("1. 부동산의 표시")
    p.table([
        ("소재지", "강원특별자치도 삼척시 가상길 34, 예시원룸 105호"),
        ("구조·용도", "원룸 · 주거용 · 면적 18㎡"),
    ])
    p.heading("2. 계약 내용")
    p.table([
        ("보증금", "금 삼십만원정 (₩300,000)"),
        ("연세(선세)", "금 삼백삼십만원정 (₩3,300,000), 잔금일에 1년분을 한 번에 지급한다"),
        ("관리비", "월 10,000원 (공용 전기·계단 청소)"),
        ("기간", "2027년 3월 1일부터 2028년 2월 29일까지 (1년)"),
    ])
    p.heading("3. 특약사항")
    items = [
        "1) 중도 퇴실 시 선세는 반환하지 않는다.",
        "2) 임차인은 남은 기간을 임의로 양도할 수 있으며, 양도 계약은 임차인과 양수인이 직접 한다.",
        "3) 보증금은 퇴실 시 청소비와 공과금을 정산한 뒤 반환한다.",
    ]
    for t in items:
        p.para(t, indent=10, hang=34, gap=4)
    p.signatures("2026년 11월 5일", [
        ("임대인", ["성명 박가상 (인)", "주소 강원특별자치도 삼척시 가상로 3", "전화 010-0000-0002"]),
        ("임차인", ["성명 최예시 (인)", "주소 경기도 가상시 예시로 4", "전화 010-0000-0003"]),
    ])
    return photo(p.img, seed=22, angle=1.1)


def sample_b():
    p1 = Page()
    p1.banner()
    p1.title("주택 월세 계약서")
    p1.para("임대인과 임차인은 아래 주택에 대하여 다음과 같이 임대차계약을 맺는다.")
    p1.heading("1. 부동산의 표시")
    p1.table([
        ("소재지", "강원특별자치도 삼척시 가상길 56, 모범빌 201호"),
        ("구조·용도", "원룸(다가구주택) · 주거용 · 면적 25㎡"),
    ])
    p1.heading("2. 계약 내용")
    p1.table([
        ("보증금", "금 오백만원정 (₩5,000,000)"),
        ("월세", "금 삼십삼만원정 (₩330,000), 매월 25일 지급"),
        ("관리비", "월 120,000원 (정액) — 일반(공용)관리비 50,000원, 수도료 20,000원, 인터넷 사용료 20,000원, TV 사용료 10,000원, 기타관리비(계단 청소) 20,000원"),
        ("기간", "2027년 3월 1일부터 2029년 2월 28일까지 (24개월)"),
    ])
    p1.heading("3. 계약 조항")
    p1.para("제1조(수리) 난방·상하수도·전기 등 주요 설비의 노후·불량으로 인한 수선은 임대인이 부담하고, 임차인의 고의·과실로 인한 파손과 전구 등 소모품 교체는 임차인이 부담한다.", gap=6)
    p1.para("제2조(계약의 종료) 계약이 끝나면 임차인은 주택을 원래 상태로 돌려주고, 임대인은 같은 날 보증금을 돌려준다. 다만 시설물의 노후화나 통상 생길 수 있는 파손은 원상복구 의무에 포함되지 않는다.", gap=6)
    p1.para("(다음 쪽에 이어짐 · 1/2)")

    p2 = Page()
    p2.banner()
    p2.heading("4. 특약사항")
    for t in [
        "1) 임차인은 잔금 지급일에 전입신고와 확정일자를 받고, 임대인은 그다음 날까지 저당권 등 담보권을 설정하지 않는다.",
        "2) 계약 기간 중 보증금과 월세는 바꾸지 않는다.",
        "3) 퇴실 청소는 임차인이 직접 하며, 따로 청소비를 받지 않는다.",
    ]:
        p2.para(t, indent=10, hang=34, gap=4)
    p2.signatures("2026년 11월 5일", [
        ("임대인", ["성명 정가상 (인)", "주소 강원특별자치도 삼척시 가상로 5", "전화 010-0000-0004"]),
        ("임차인", ["성명 한예시 (인)", "주소 강원특별자치도 가상군 예시로 6", "전화 010-0000-0005"]),
    ])
    p2.para("(2/2)")
    return [scan(p1.img, seed=31), scan(p2.img, seed=32)]


def main():
    OUT.mkdir(exist_ok=True)
    sample_a().save(OUT / "sample_a.jpg", quality=88)
    sample_y().save(OUT / "sample_y.jpg", quality=88)
    pages = sample_b()
    pages[0].save(OUT / "sample_b.pdf", save_all=True, append_images=pages[1:], resolution=150)
    for name in ("sample_a.jpg", "sample_y.jpg", "sample_b.pdf"):
        print(name, (OUT / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
