from PIL import Image, ImageDraw, ImageFont
from datetime import datetime


def _font(size=18):
    try:
        return ImageFont.truetype("arial.ttf", size)
    except:
        return ImageFont.load_default()


def _rounded_box(draw, xy, radius, fill):
    (x0, y0, x1, y1) = xy
    r = min(radius, int(min(x1 - x0, y1 - y0) / 2))
    draw.rounded_rectangle(xy, radius=r, fill=fill)


def annotate_quiet_trap(
    png_path: str,
    side: str,
    score: float,
    notes: list[str] | None = None,
    footer: str | None = None,
) -> str:
    """
    PNGにQuietTrap注釈を焼き込み。side: 'buy'|'sell'。score: 0.0-1.0。
    returns: 出力パス（上書き）
    """
    notes = notes or []
    im = Image.open(png_path).convert("RGBA")
    W, H = im.size
    draw = ImageDraw.Draw(im, "RGBA")

    # 配色
    color = (14, 160, 90, 220) if side == "buy" else (220, 38, 38, 220)
    accent = (14, 160, 90, 255) if side == "buy" else (220, 38, 38, 255)
    panel_fill = (17, 24, 39, 200)  # dark panel
    text_color = (255, 255, 255, 255)

    # タイトルパネル（右上）
    pad = 16
    w_panel, h_panel = int(W * 0.28), int(H * 0.20)
    x0, y0 = W - w_panel - pad, pad
    x1, y1 = W - pad, pad + h_panel
    _rounded_box(draw, (x0, y0, x1, y1), 16, panel_fill)

    # 見出し
    f1 = _font(20)
    f2 = _font(18)
    title = "QuietTrap"
    sub = f"Side: {side.upper()}   Score: {score:.2f}"
    draw.text((x0 + 14, y0 + 12), title, fill=accent, font=f1)
    draw.text((x0 + 14, y0 + 40), sub, fill=text_color, font=f2)

    # ノート列
    y = y0 + 70
    for n in notes:
        draw.text((x0 + 14, y), f"• {n}", fill=text_color, font=_font(16))
        y += 20

    # 方向リボン（左上）
    ribbon_h = 36
    draw.rectangle([(0, 0), (int(W * 0.22), ribbon_h)], fill=color)
    draw.text(
        (10, 8), f"{side.upper()} TRAP", fill=(255, 255, 255, 255), font=_font(18)
    )

    # フッタ（右下、タイムスタンプ）
    footer = footer or datetime.utcnow().strftime("UTC %Y-%m-%d %H:%M:%S")
    tw, th = draw.textlength(footer, font=_font(14)), 18
    fx1, fy1 = W - int(tw) - 24, H - th - 16
    _rounded_box(draw, (fx1 - 10, fy1 - 6, W - 10, H - 10), 10, (0, 0, 0, 120))
    draw.text((fx1, fy1), footer, fill=(255, 255, 255, 200), font=_font(14))

    im.save(png_path)
    return png_path
