"""Render the Jev capability card (1600x1600 PNG) with Pillow."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

SS = 2  # supersampling
W = H = 1600

HELVETICA = "/System/Library/Fonts/Helvetica.ttc"
FONT_REG = (HELVETICA, 0)
FONT_BOLD = (HELVETICA, 1)

COLORS = {
    "bg_top": (11, 18, 32),
    "bg_bottom": (16, 27, 49),
    "panel_left": (15, 30, 51),
    "panel_left_border": (30, 58, 95),
    "panel_right": (26, 18, 32),
    "panel_right_border": (95, 33, 48),
    "green": (52, 211, 153),
    "red": (248, 113, 113),
    "blue": (96, 165, 250),
    "white": (248, 250, 252),
    "text": (241, 245, 249),
    "muted": (148, 163, 184),
    "dim": (100, 116, 139),
    "divider_left": (30, 41, 59),
    "divider_right": (63, 29, 40),
}

_fonts: dict[tuple, ImageFont.FreeTypeFont] = {}


def font(spec: tuple, size: int):
    key = (spec, size)
    if key not in _fonts:
        path, index = spec
        _fonts[key] = ImageFont.truetype(path, size * SS, index=index)
    return _fonts[key]


def text(draw, xy, content, spec=FONT_REG, size=24, color=(255, 255, 255), anchor="ls"):
    x, y = xy
    draw.text((x * SS, y * SS), content, font=font(spec, size), fill=color, anchor=anchor)


def main() -> None:
    img = Image.new("RGB", (W * SS, H * SS))
    draw = ImageDraw.Draw(img)

    # background vertical gradient
    for y in range(H * SS):
        t = y / (H * SS - 1)
        color = tuple(
            int(COLORS["bg_top"][i] + (COLORS["bg_bottom"][i] - COLORS["bg_top"][i]) * t)
            for i in range(3)
        )
        draw.line([(0, y), (W * SS, y)], fill=color)

    # top accent gradient bar
    for x in range(W * SS):
        t = x / (W * SS - 1)
        color = tuple(
            int(COLORS["blue"][i] + (COLORS["green"][i] - COLORS["blue"][i]) * t)
            for i in range(3)
        )
        draw.line([(x, 0), (x, 8 * SS)], fill=color)

    # header
    text(draw, (80, 120), "JEV  ·  BLACK-BOX BENCHMARK", FONT_BOLD, 26, COLORS["blue"])
    text(draw, (80, 222), "A decision model for", FONT_BOLD, 68, COLORS["white"])
    text(draw, (80, 306), "agent harnesses", FONT_BOLD, 68, COLORS["white"])
    text(draw, (80, 378), "22,500 API calls  ·  10 public datasets  ·  $2.19 total  ·  ~0.3s per call", FONT_REG, 30, COLORS["muted"])

    # left panel
    draw.rounded_rectangle(
        [80 * SS, 440 * SS, 780 * SS, 1140 * SS], radius=20 * SS,
        fill=COLORS["panel_left"], outline=COLORS["panel_left_border"], width=2 * SS,
    )
    draw.rounded_rectangle([80 * SS, 440 * SS, 90 * SS, 1140 * SS], radius=5 * SS, fill=COLORS["green"])
    text(draw, (128, 520), "WORKS WELL", FONT_BOLD, 34, COLORS["green"])

    left_rows = [
        ("Injection detection", "P/R 100%", None),
        ("Reranking", "MRR 0.62 → 0.84", None),
        ("Tool catalog routing", "96.5%", None),
        ("Shell risk gate", "100% / 1.8%", "caught  ·  false alarm"),
    ]
    y = 610
    for label, value, note in left_rows:
        text(draw, (128, y), label, FONT_BOLD, 31, COLORS["text"])
        text(draw, (728, y), value, FONT_BOLD, 31, COLORS["green"], anchor="rs")
        draw.line([(128 * SS, (y + 36) * SS), (728 * SS, (y + 36) * SS)], fill=COLORS["divider_left"], width=2 * SS)
        if note:
            text(draw, (128, y + 44), note, FONT_REG, 24, COLORS["dim"])
        y += 116
    text(draw, (128, 1090), "InjecAgent  ·  SciFact  ·  MetaTool (199 tools)", FONT_REG, 24, COLORS["dim"])

    # right panel
    draw.rounded_rectangle(
        [820 * SS, 440 * SS, 1520 * SS, 1140 * SS], radius=20 * SS,
        fill=COLORS["panel_right"], outline=COLORS["panel_right_border"], width=2 * SS,
    )
    draw.rounded_rectangle([1510 * SS, 440 * SS, 1520 * SS, 1140 * SS], radius=5 * SS, fill=COLORS["red"])
    text(draw, (868, 520), "DOES NOT WORK", FONT_BOLD, 34, COLORS["red"])

    right_rows = [
        ("Model-difficulty routing", "51%", None),
        ("Trajectory attribution", "AUROC 0.56", None),
        ("Non-English", "48.9% vs 61.5%", None),
        ("Hard limits", "255 / 32k / text", "choices  ·  context  ·  modalities"),
    ]
    y = 610
    for label, value, note in right_rows:
        text(draw, (868, y), label, FONT_BOLD, 31, COLORS["text"])
        text(draw, (1468, y), value, FONT_BOLD, 31, COLORS["red"], anchor="rs")
        draw.line([(868 * SS, (y + 36) * SS), (1468 * SS, (y + 36) * SS)], fill=COLORS["divider_right"], width=2 * SS)
        if note:
            text(draw, (868, y + 44), note, FONT_REG, 24, COLORS["dim"])
        y += 116
    text(draw, (868, 1090), "RouterBench  ·  Who&When  ·  KO vs EN", FONT_REG, 24, COLORS["dim"])

    # lesson box
    draw.rounded_rectangle(
        [80 * SS, 1200 * SS, 1520 * SS, 1450 * SS], radius=20 * SS,
        fill=COLORS["panel_left"], outline=COLORS["panel_left_border"], width=2 * SS,
    )
    text(draw, (128, 1282), "Let choice compete. Then let noul verify.", FONT_BOLD, 40, COLORS["white"])
    text(draw, (128, 1352), "Skill routing R@1: 38% → 76%    ·    multi-skill: 9% → 81%", FONT_BOLD, 32, COLORS["blue"])
    text(draw, (128, 1408), "Model gives calibrated local judgments; code holds the control flow.", FONT_REG, 27, COLORS["muted"])

    # footer
    text(draw, (80, 1536), "github.com/Aitejiu/jev-harness-lab", FONT_BOLD, 27, COLORS["blue"])
    text(draw, (1520, 1536), "jev-1.13.0  ·  Sep 2026", FONT_REG, 25, COLORS["dim"], anchor="rs")

    out = Path(__file__).resolve().with_name("jev-card.png")
    img.resize((W, H), Image.LANCZOS).save(out, optimize=True)
    print(f"saved {out} ({out.stat().st_size / 1024:.0f} KB)")


if __name__ == "__main__":
    main()
