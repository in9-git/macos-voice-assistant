"""음성비서 아이콘 생성 → icon.png(1024) + icon.icns + menubar_icon.png.

청록→보라 그라데이션 둥근 사각형 + 흰 음파 막대(가운데 높은 좌우대칭 비주얼라이저).
색(TOP/BOT)·막대 높이비(BARS)만 고치고 다시 실행하면 디자인이 바뀐다.
"""
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

HERE = Path(__file__).resolve().parent
S = 1024

TOP = (124, 214, 235)   # 하늘 청록
BOT = (152, 132, 226)   # 부드러운 보라
BARS = [0.30, 0.52, 0.74, 1.0, 0.74, 0.52, 0.30]   # 음파 막대 높이비 (중앙 최대, 대칭)


def _canvas():
    """세로 그라데이션 + 둥근 모서리."""
    base = Image.new("RGB", (S, S))
    dd = ImageDraw.Draw(base)
    for y in range(S):
        t = y / (S - 1)
        dd.line([(0, y), (S, y)],
                fill=tuple(int(TOP[i] * (1 - t) + BOT[i] * t) for i in range(3)))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=int(S * 0.22), fill=255)
    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    out.paste(base, (0, 0), mask)
    return out


def _draw_bars(draw, heights, cx, cy, bar_w, gap, max_h, radius, color, dy=0):
    """cx를 중심으로 대칭이 되게 둥근(캡슐) 막대들을 그린다."""
    n = len(heights)
    total_w = n * bar_w + (n - 1) * gap
    x = cx - total_w / 2
    for hf in heights:
        h = max_h * hf
        draw.rounded_rectangle(
            [x, cy - h / 2 + dy, x + bar_w, cy + h / 2 + dy],
            radius=radius, fill=color)
        x += bar_w + gap


def build():
    img = _canvas()

    bar_w, gap, max_h = S * 0.072, S * 0.052, S * 0.46
    r = bar_w / 2

    # 부드러운 그림자 — 별도 레이어에 어둡게 그린 뒤 블러 → 합성 (입체감)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    _draw_bars(ImageDraw.Draw(shadow), BARS, S / 2, S / 2,
               bar_w, gap, max_h, r, (40, 40, 90, 140), dy=S * 0.014)
    shadow = shadow.filter(ImageFilter.GaussianBlur(int(S * 0.014)))
    img = Image.alpha_composite(img, shadow)

    # 흰 음파 막대
    _draw_bars(ImageDraw.Draw(img), BARS, S / 2, S / 2,
               bar_w, gap, max_h, r, (255, 255, 255, 255))

    png = HERE / "icon.png"
    img.save(png)

    # .icns (iconutil이 요구하는 해상도 세트)
    iconset = HERE / "icon.iconset"
    iconset.mkdir(exist_ok=True)
    for s in (16, 32, 128, 256, 512):
        img.resize((s, s), Image.LANCZOS).save(iconset / f"icon_{s}x{s}.png")
        img.resize((s * 2, s * 2), Image.LANCZOS).save(iconset / f"icon_{s}x{s}@2x.png")
    subprocess.run(["iconutil", "-c", "icns",
                    "-o", str(HERE / "icon.icns"), str(iconset)], check=True)

    # 메뉴바용 작은 단색(템플릿) 음파 아이콘 — 다크/라이트 모드 자동 대응
    mb = Image.new("RGBA", (44, 44), (0, 0, 0, 0))
    _draw_bars(ImageDraw.Draw(mb), [0.4, 0.7, 1.0, 0.7, 0.4], 22, 22,
               4.2, 3.0, 26, 2.1, (0, 0, 0, 255))
    mb.save(HERE / "menubar_icon.png")

    print(f"✅ icon.png / icon.icns / menubar_icon.png 생성 완료 ({png})")


if __name__ == "__main__":
    build()
