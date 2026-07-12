# -*- coding: utf-8 -*-
"""《一个女人一生中的二十四小时》— Streamlit 交互书主入口"""

from __future__ import annotations

import base64
import html
import io
import json
import re
from functools import lru_cache
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components
from PIL import Image

from book_content import EPILOGUE, INTRO, SCENE_CARDS

# ---------------------------------------------------------------------------
# 路径与资源
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent
IMAGES_DIR = BASE_DIR / "images"
IMAGES_DIR.mkdir(exist_ok=True)

PLACEHOLDER_SVG_NAME = "_placeholder_16x9.svg"
PLACEHOLDER_BG = "#EDE8DC"
PLACEHOLDER_FG = "#8A8478"
PLACEHOLDER_GOLD = "#C49A45"

# 16:9 规范
IMG_W, IMG_H = 800, 450

CANVAS_BG = "#E4DFD3"
CARD_BG = "#EDE8DC"
GOLD_BORDER = "#C49A45"
SAGE = "#536257"
MADDER = "#8C2B2B"
CARBON = "#21201D"
BRASS = "#2C2416"
IVORY = "#EDE8DC"
BROWN = "#6B4A30"
# 书桌阶段：暖暗褐，与画布米色同属一系，避免黑白割裂
BOOK_DESK = "#2A241C"
BOOK_COVER = "#3A3228"
CREAM = "#F2EBD8"
PARCHMENT = "#E8DFD0"
TOTAL_PAGES = len(SCENE_CARDS)
PREVIEW_COUNT = 2  # 对开右页预览插图数量（疏朗，不紧凑）

SCENE_CLOCKS = [
    "18:00",
    "19:00",
    "——",
    "23:00",
    "23:30",
    "00:00",
    "00:30",
    "02:00",
    "07:30",
    "12:00",
    "14:30",
    "16:00",
    "17:00",
    "19:35",
    "21:00",
]

DIARY_OFFSETS = ("offset-a", "offset-b", "offset-c", "offset-d")
CHOICE_HINT = "这里，命运向你递出了两张卡牌……"


# ---------------------------------------------------------------------------
# 插图：16:9 占位与路径解析
# ---------------------------------------------------------------------------
def _build_placeholder_svg(label: str = "油画插图占位") -> str:
    """完美 16:9（800×450）旧画布 SVG 占位图。"""
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" width="{IMG_W}" height="{IMG_H}"
     viewBox="0 0 {IMG_W} {IMG_H}" preserveAspectRatio="xMidYMid meet">
  <rect width="{IMG_W}" height="{IMG_H}" fill="{PLACEHOLDER_BG}"/>
  <rect x="18" y="18" width="{IMG_W - 36}" height="{IMG_H - 36}" fill="none"
        stroke="{PLACEHOLDER_GOLD}" stroke-width="1" opacity="0.55"/>
  <rect x="24" y="24" width="{IMG_W - 48}" height="{IMG_H - 48}" fill="none"
        stroke="{PLACEHOLDER_FG}" stroke-width="0.75" stroke-dasharray="6 5" opacity="0.35"/>
  <text x="{IMG_W // 2}" y="{IMG_H // 2 - 8}" text-anchor="middle"
        font-family="Georgia, 'Noto Serif SC', serif"
        font-size="28" font-style="italic" fill="{PLACEHOLDER_FG}">{label}</text>
  <text x="{IMG_W // 2}" y="{IMG_H // 2 + 28}" text-anchor="middle"
        font-family="Georgia, serif"
        font-size="14" letter-spacing="3" fill="{PLACEHOLDER_GOLD}" opacity="0.85">
    16:9 · VAN GOGH CANVAS
  </text>
</svg>
"""


@st.cache_resource
def ensure_placeholder_file() -> str:
    """占位图只写一次，避免每次交互落盘。"""
    path = IMAGES_DIR / PLACEHOLDER_SVG_NAME
    if not path.exists():
        path.write_text(_build_placeholder_svg(), encoding="utf-8")
    return str(path)


def get_image_path(image_ref: str | None) -> str:
    """解析插图路径；缺失时返回 16:9 SVG 占位图。不缓存，便于热替换插画。"""
    placeholder = ensure_placeholder_file()
    if not image_ref:
        return placeholder

    raw = Path(image_ref)
    candidates = []
    if raw.is_absolute():
        candidates.append(raw)
    else:
        candidates.append(BASE_DIR / raw)
        candidates.append(IMAGES_DIR / raw.name)
        candidates.append(IMAGES_DIR / raw)

    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)

    stem = raw.stem
    for ext in (".png", ".jpg", ".jpeg", ".webp", ".svg", ".gif"):
        alt = IMAGES_DIR / f"{stem}{ext}"
        if alt.is_file():
            return str(alt)

    return placeholder


@lru_cache(maxsize=32)
def _thumb_data_uri(image_ref: str | None, max_w: int = 320) -> str:
    """生成小尺寸 JPEG data URI，供对开右页内嵌（体积小、可稳定微旋居中）。"""
    path = Path(get_image_path(image_ref))
    try:
        with Image.open(path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_w, int(max_w * 9 / 16) + 8))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=78, optimize=True)
        return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode("ascii")
    except Exception:
        # 回退：原文件（可能较大，仅作兜底）
        raw = path.read_bytes()
        mime = "image/svg+xml" if path.suffix.lower() == ".svg" else "image/png"
        return f"data:{mime};base64,{base64.b64encode(raw).decode('ascii')}"


SECRET_WORD_RE = re.compile(
    r'<span\s+class="secret-word"\s+data-tooltip="([^"]*)">(.*?)</span>',
    re.DOTALL,
)


def _escape_multiline(text: str) -> str:
    return html.escape(text).replace("\n", "<br>")


def _apply_drop_cap(rich_html: str) -> str:
    """在富文本中找到首个可见字符并包裹为首字下沉。"""
    i = 0
    n = len(rich_html)
    while i < n:
        if rich_html[i] == "<":
            j = rich_html.find(">", i)
            i = j + 1 if j != -1 else n
            continue
        if rich_html[i].isspace() or rich_html.startswith("<br>", i):
            if rich_html.startswith("<br>", i):
                i += 4
            else:
                i += 1
            continue
        return f'{rich_html[:i]}<span class="drop-cap">{rich_html[i]}</span>{rich_html[i + 1:]}'
    return rich_html


def format_rich_quote(text: str, *, drop_cap: bool = True) -> str:
    """
    允许原著摘录中的隐秘手账标签通过，其余文本转义。
    合法片段：<span class="secret-word" data-tooltip="...">关键词</span>
    """
    parts: list[str] = []
    last = 0
    for match in SECRET_WORD_RE.finditer(text):
        parts.append(html.escape(text[last:match.start()]))
        tip = html.escape(match.group(1), quote=True)
        inner = html.escape(match.group(2))
        parts.append(
            f'<span class="secret-word" data-tooltip="{tip}">{inner}</span>'
        )
        last = match.end()
    parts.append(html.escape(text[last:]))
    rich = "".join(parts).replace("\n", "<br>")
    if drop_cap:
        rich = _apply_drop_cap(rich)
    return rich


def build_soul_scratch_html(analysis: str, scene_idx: int, *, light: bool = False) -> str:
    """灵魂拂尘：Canvas 刮擦显影。light=True 时降低刮擦成本。"""
    body = html.escape(analysis).replace("\n", "<br>")
    storage_key = f"zw_soul_scratch_{scene_idx}"
    # 轻刮：1 划或 18%；完整：3 划或 40%
    min_strokes = 1 if light else 3
    min_ratio = 0.18 if light else 0.40
    hint = "轻拂即显" if light else "拂去雾面，显影心灵"
    return f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500&family=Playfair+Display:ital@0;1&display=swap');
  html, body {{
    margin: 0; padding: 0;
    background: transparent;
    font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif;
  }}
  .scratch-wrap {{
    position: relative;
    width: 100%;
    background: #8C2B2B0A;
    border: 1px dotted rgba(140, 43, 43, 0.55);
    border-radius: 2px;
    box-shadow: inset 0 0 0 3px rgba(140, 43, 43, 0.03);
    overflow: hidden;
    min-height: 160px;
  }}
  .scratch-title {{
    padding: 14px 18px 0;
    font-size: 0.72rem;
    letter-spacing: 0.1em;
    color: #8C2B2B;
    font-family: "Playfair Display", "Noto Serif SC", serif;
  }}
  .scratch-text {{
    padding: 10px 18px 18px;
    margin: 0;
    font-style: italic;
    font-size: 14.5px;
    line-height: 1.85;
    text-align: justify;
    color: #8C2B2B;
    opacity: 0.95;
  }}
  #fog {{
    position: absolute;
    left: 0; top: 0;
    width: 100%; height: 100%;
    cursor: crosshair;
    touch-action: none;
    transition: opacity 1.5s ease;
    z-index: 2;
  }}
  #fog.fade-out {{
    opacity: 0;
    pointer-events: none;
  }}
</style>
</head><body>
  <div class="scratch-wrap" id="wrap">
    <div class="scratch-title">心灵解剖 · Deep Soul · {html.escape(hint)}</div>
    <p class="scratch-text" id="soulText">{body}</p>
    <canvas id="fog"></canvas>
  </div>
<script>
(function() {{
  const storageKey = {json.dumps(storage_key)};
  const minStrokes = {min_strokes};
  const minRatio = {min_ratio};
  const fogHint = {json.dumps("轻拂雾面即可显影" if light else "长按并滑动鼠标，拂去尘埃，窥探深渊")};
  const canvas = document.getElementById('fog');
  const wrap = document.getElementById('wrap');
  const ctx = canvas.getContext('2d');
  let drawing = false;
  let strokes = 0;
  let lastX = null, lastY = null;
  let revealed = false;
  const BRUSH = {22 if light else 28};

  function sizeCanvas() {{
    const rect = wrap.getBoundingClientRect();
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.max(1, Math.floor(rect.width * dpr));
    canvas.height = Math.max(1, Math.floor(rect.height * dpr));
    canvas.style.width = rect.width + 'px';
    canvas.style.height = rect.height + 'px';
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return rect;
  }}

  function paintFog(rect) {{
    // 厚重油画底漆
    ctx.globalCompositeOperation = 'source-over';
    ctx.fillStyle = 'rgba(237, 232, 220, 0.94)';
    ctx.fillRect(0, 0, rect.width, rect.height);

    // 噪点毛玻璃
    const img = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const data = img.data;
    for (let i = 0; i < data.length; i += 16) {{
      const n = (Math.random() * 40) | 0;
      data[i] = Math.min(255, data[i] - 8 + n);
      data[i+1] = Math.min(255, data[i+1] - 10 + n);
      data[i+2] = Math.min(255, data[i+2] - 12 + n);
    }}
    ctx.putImageData(img, 0, 0);

    // 底层暗红阴影暗示
    ctx.fillStyle = 'rgba(140, 43, 43, 0.08)';
    ctx.fillRect(0, 0, rect.width, rect.height);

    // 中央提示
    ctx.fillStyle = 'rgba(44, 36, 22, 0.55)';
    ctx.font = 'italic 15px "Playfair Display", "Noto Serif SC", Georgia, serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillText(fogHint, rect.width / 2, rect.height / 2);
  }}

  function pos(e) {{
    const r = canvas.getBoundingClientRect();
    const src = e.touches ? e.touches[0] : e;
    return {{ x: src.clientX - r.left, y: src.clientY - r.top }};
  }}

  function scratch(x, y) {{
    // 柔软擦除
    ctx.globalCompositeOperation = 'destination-out';
    let g = ctx.createRadialGradient(x, y, 0, x, y, BRUSH);
    g.addColorStop(0, 'rgba(0,0,0,1)');
    g.addColorStop(0.55, 'rgba(0,0,0,0.55)');
    g.addColorStop(1, 'rgba(0,0,0,0)');
    ctx.fillStyle = g;
    ctx.beginPath();
    ctx.arc(x, y, BRUSH, 0, Math.PI * 2);
    ctx.fill();

    // 火柴光影边缘（落在剩余雾面上）
    ctx.globalCompositeOperation = 'source-atop';
    let rim = ctx.createRadialGradient(x, y, BRUSH * 0.4, x, y, BRUSH * 1.2);
    rim.addColorStop(0, 'rgba(196,154,69,0)');
    rim.addColorStop(0.55, 'rgba(196,154,69,0.0)');
    rim.addColorStop(0.78, 'rgba(196,154,69,0.42)');
    rim.addColorStop(0.9, 'rgba(140,43,43,0.28)');
    rim.addColorStop(1, 'rgba(196,154,69,0)');
    ctx.fillStyle = rim;
    ctx.beginPath();
    ctx.arc(x, y, BRUSH * 1.2, 0, Math.PI * 2);
    ctx.fill();
    ctx.globalCompositeOperation = 'source-over';
  }}

  function scratchedRatio() {{
    const sample = ctx.getImageData(0, 0, canvas.width, canvas.height).data;
    let cleared = 0, total = 0;
    // 步进采样，降低开销
    for (let i = 3; i < sample.length; i += 32) {{
      total++;
      if (sample[i] < 48) cleared++;
    }}
    return total ? cleared / total : 0;
  }}

  function reveal() {{
    if (revealed) return;
    revealed = true;
    try {{ localStorage.setItem(storageKey, '1'); }} catch (e) {{}}
    canvas.classList.add('fade-out');
    setTimeout(function() {{
      canvas.style.display = 'none';
    }}, 1550);
  }}

  function onDown(e) {{
    e.preventDefault();
    drawing = true;
    strokes += 1;
    const p = pos(e);
    lastX = p.x; lastY = p.y;
    scratch(p.x, p.y);
  }}
  function onMove(e) {{
    if (!drawing || revealed) return;
    e.preventDefault();
    const p = pos(e);
    // 插值，连续笔触
    if (lastX != null) {{
      const dx = p.x - lastX, dy = p.y - lastY;
      const dist = Math.sqrt(dx*dx + dy*dy);
      const steps = Math.max(1, Math.ceil(dist / 6));
      for (let i = 1; i <= steps; i++) {{
        scratch(lastX + dx * i / steps, lastY + dy * i / steps);
      }}
    }} else {{
      scratch(p.x, p.y);
    }}
    lastX = p.x; lastY = p.y;
    if (strokes >= minStrokes || scratchedRatio() >= minRatio) reveal();
  }}
  function onUp(e) {{
    drawing = false;
    lastX = lastY = null;
    if (!revealed && (strokes >= minStrokes || scratchedRatio() >= minRatio)) reveal();
  }}

  function init() {{
    const rect = sizeCanvas();
    if (localStorage.getItem(storageKey) === '1') {{
      canvas.style.display = 'none';
      return;
    }}
    paintFog(rect);
  }}

  canvas.addEventListener('mousedown', onDown);
  canvas.addEventListener('mousemove', onMove);
  window.addEventListener('mouseup', onUp);
  canvas.addEventListener('touchstart', onDown, {{passive:false}});
  canvas.addEventListener('touchmove', onMove, {{passive:false}});
  window.addEventListener('touchend', onUp);
  window.addEventListener('resize', function() {{
    if (revealed || localStorage.getItem(storageKey) === '1') return;
    const rect = sizeCanvas();
    paintFog(rect);
  }});

  // 等字体与布局稳定后再绘制
  setTimeout(init, 40);
}})();
</script>
</body></html>"""


def render_soul_analysis(analysis: str, scene_idx: int, *, light: bool = False) -> None:
    """心灵解剖：首次以刮擦显影呈现，之后保持清晰。"""
    height = max(220, min(560, 150 + len(analysis) // 2))
    components.html(
        build_soul_scratch_html(analysis, scene_idx, light=light),
        height=height,
        scrolling=False,
    )

# ---------------------------------------------------------------------------
# 全局 CSS — 梵高油画 / 中世纪手稿美学
# ---------------------------------------------------------------------------
GLOBAL_CSS = f"""
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@400;500;600;700&family=Playfair+Display:ital,wght@0,400;0,500;0,600;0,700;1,400;1,500&display=swap" rel="stylesheet">

<style>
#MainMenu {{visibility: hidden;}}
header[data-testid="stHeader"] {{display: none;}}
footer {{visibility: hidden;}}
[data-testid="stDecoration"],
[data-testid="stToolbar"],
[data-testid="stStatusWidget"],
.stDeployButton,
div[data-testid="stBottom"] {{
  display: none !important;
}}

.stApp {{
  background-color: {CANVAS_BG} !important;
  background-image:
    url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E");
  background-blend-mode: multiply;
  background-size: 180px 180px;
}}

[data-testid="stAppViewContainer"],
.main .block-container {{
  background: transparent !important;
}}

.main .block-container {{
  position: relative;
  padding-top: 2rem;
  padding-bottom: 4rem;
  padding-left: 52px !important;
  padding-right: 1.25rem !important;
  max-width: 960px;
}}

/* 贯穿全部节点圆点的时间线竖轨 */
.main .block-container::before {{
  content: "";
  position: absolute;
  left: 22px;
  top: 6.8rem;
  bottom: 2.5rem;
  width: 2px;
  background: linear-gradient(
    180deg,
    rgba(83, 98, 87, 0.25) 0%,
    {SAGE} 4%,
    {SAGE} 96%,
    rgba(83, 98, 87, 0.25) 100%
  );
  opacity: 1;
  border-radius: 1px;
  z-index: 0;
  pointer-events: none;
  box-shadow: 0 0 0 1px rgba(83, 98, 87, 0.08);
}}

html, body, .stApp, .stMarkdown, .stText, p, li, label,
h1, h2, h3, h4, h5, h6,
[data-testid="stMarkdownContainer"],
[data-testid="stWidgetLabel"] {{
  font-family: "Noto Serif SC", "Source Han Serif SC", serif !important;
  color: #2C2416;
}}

.scene-clock, .stCaption, [data-testid="stCaptionContainer"],
.detail-en, .brass-label {{
  font-family: "Playfair Display", Georgia, serif !important;
  letter-spacing: 0.04em;
}}

/* ---------- 书名 ---------- */
.book-header {{
  position: relative;
  z-index: 1;
  text-align: center;
  margin: 0.25rem 0 2.25rem;
}}
.book-title {{
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: {CARBON};
  letter-spacing: 0.08em;
  line-height: 1.4;
  white-space: nowrap;
  overflow: visible;
}}
.brush-underline {{
  display: block;
  width: min(420px, 88%);
  height: 14px;
  margin: 8px auto 0;
}}

/* ---------- 时间节点卡片（含内嵌启封按钮） ---------- */
/* Streamlit 双栏卡片：用 :has(.scene-card-marker) 识别 */
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker) {{
  position: relative;
  z-index: 1;
  background-color: {CARD_BG};
  background-image:
    linear-gradient(115deg, rgba(255,255,255,0.22), transparent 42%),
    repeating-linear-gradient(
      transparent,
      transparent 26px,
      rgba(83, 98, 87, 0.04) 27px
    );
  border: 1px solid rgba(196, 154, 69, 0.55);
  border-radius: 3px;
  padding: 22px 22px !important; /* 避开内外双重金线边框 */
  margin: 0 0 1.35rem !important;
  box-shadow:
    0 1px 2px rgba(44, 36, 22, 0.06),
    0 8px 20px rgba(44, 36, 22, 0.07);
  transition: transform 0.35s ease, box-shadow 0.35s ease, margin 0.35s ease;
  align-items: center !important;
  gap: 1rem !important;
}}
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker)::after {{
  content: "";
  position: absolute;
  inset: 6px;
  border: 0.5px solid rgba(196, 154, 69, 0.55);
  border-radius: 1px;
  pointer-events: none;
  z-index: 0;
}}
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker):hover {{
  transform: translateY(-2px);
  box-shadow:
    0 4px 6px rgba(44, 36, 22, 0.08),
    0 14px 28px rgba(44, 36, 22, 0.1);
}}
/* 时间线圆点 */
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker)::before {{
  content: "";
  position: absolute;
  left: -35px;
  top: 1.55rem;
  width: 12px;
  height: 12px;
  border-radius: 50%;
  background: {CANVAS_BG};
  border: 2px solid {SAGE};
  box-shadow: 0 0 0 3px rgba(83, 98, 87, 0.14);
  z-index: 2;
}}
div[data-testid="stHorizontalBlock"]:has(.card-media.is-open)::before {{
  background: {GOLD_BORDER};
  border-color: {GOLD_BORDER};
  box-shadow: 0 0 0 3px rgba(196, 154, 69, 0.22);
}}

/* 日记纸张错落 */
div[data-testid="stHorizontalBlock"]:has(.card-media.offset-a) {{
  margin-left: 0 !important;
  margin-right: 9% !important;
  transform: rotate(-1.1deg);
}}
div[data-testid="stHorizontalBlock"]:has(.card-media.offset-b) {{
  margin-left: 7% !important;
  margin-right: 2% !important;
  transform: rotate(0.85deg);
}}
div[data-testid="stHorizontalBlock"]:has(.card-media.offset-c) {{
  margin-left: 2% !important;
  margin-right: 11% !important;
  transform: rotate(-0.55deg);
}}
div[data-testid="stHorizontalBlock"]:has(.card-media.offset-d) {{
  margin-left: 11% !important;
  margin-right: 0 !important;
  transform: rotate(1.15deg);
}}
div[data-testid="stHorizontalBlock"]:has(.card-media.is-open) {{
  margin-left: 2% !important;
  margin-right: 2% !important;
  transform: rotate(0deg) !important;
}}
div[data-testid="stHorizontalBlock"]:has(.card-media.is-open):hover {{
  transform: translateY(-2px) !important;
}}

.card-media {{
  position: relative;
  z-index: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  box-sizing: border-box;
  width: 100%;
  max-width: 100%;
  padding: 2px; /* 与内金线留出间隙 */
}}
.card-media.scene-card-marker {{
  /* 仅作卡片识别锚点，真实图片由 st.image 渲染 */
  height: 0;
  padding: 0;
  margin: 0;
  overflow: hidden;
}}
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker) [data-testid="stImage"] {{
  position: relative;
  z-index: 1;
}}
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker) [data-testid="stImage"] img {{
  display: block;
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  aspect-ratio: 16 / 9;
  object-fit: cover;
  object-position: center;
  border-radius: 2px;
  border: 1px solid rgba(196, 154, 69, 0.35);
  background: {CARD_BG};
}}
.card-body {{
  position: relative;
  z-index: 1;
  display: flex;
  flex-direction: column;
  justify-content: center;
  gap: 0.15rem;
  padding: 2px 2px 0.15rem 0;
  box-sizing: border-box;
}}
.scene-clock {{
  display: block;
  font-size: 1.08rem;
  font-weight: 600;
  color: {GOLD_BORDER} !important;
  margin-bottom: 0.15rem;
}}
.scene-period {{
  display: block;
  font-size: 0.78rem;
  color: {BROWN};
  opacity: 0.85;
  margin-bottom: 0.35rem;
}}
.card-body h3 {{
  margin: 0 0 0.35rem;
  font-size: 1.08rem;
  font-weight: 700;
  color: {CARBON} !important;
  line-height: 1.4;
}}
/* 卡片内启封按钮：贴在文案区下方 */
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker)
  [data-testid="column"]:last-child div[data-testid="stButton"] {{
  margin-top: 0.85rem;
  position: relative;
  z-index: 1;
}}
div[data-testid="stHorizontalBlock"]:has(.scene-card-marker)
  [data-testid="column"]:last-child div[data-testid="stButton"] > button {{
  min-height: 2.2rem !important;
  font-size: 13px !important;
}}

@media (max-width: 640px) {{
  div[data-testid="stHorizontalBlock"]:has(.card-media.offset-a),
  div[data-testid="stHorizontalBlock"]:has(.card-media.offset-b),
  div[data-testid="stHorizontalBlock"]:has(.card-media.offset-c),
  div[data-testid="stHorizontalBlock"]:has(.card-media.offset-d),
  div[data-testid="stHorizontalBlock"]:has(.card-media.is-open) {{
    margin-left: 0 !important;
    margin-right: 0 !important;
    transform: none !important;
  }}
}}

/* ---------- 展开：上双栏手稿+纪实，下通栏心灵解剖 ---------- */
.detail-shell {{
  margin: 0.4rem 0 1.1rem;
  padding: 0;
}}
div[data-testid="stHorizontalBlock"]:has(.original-quote) {{
  gap: 0.65rem !important;
  margin-bottom: 0.55rem !important;
}}

.original-quote {{
  position: relative;
  height: 100%;
  overflow: visible;
  background:
    linear-gradient(180deg, rgba(255,252,245,0.7), rgba(237,232,220,0.45));
  border-left: 4px solid {GOLD_BORDER};
  padding: 16px 16px 16px 18px;
  color: {CARBON};
  font-family: "Noto Serif SC", "Source Han Serif SC", Georgia, serif !important;
  font-size: 16.5px;
  line-height: 1.9;
  text-align: justify;
}}
.original-quote .quote-mark {{
  display: block;
  margin-bottom: 0.35rem;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 1.25rem;
  color: {GOLD_BORDER};
  letter-spacing: 0.08em;
  opacity: 0.9;
}}
.original-quote .drop-cap {{
  float: left;
  font-family: "Playfair Display", "Noto Serif SC", serif;
  font-size: 3rem;
  line-height: 0.85;
  padding: 0.1rem 0.3rem 0 0;
  color: {GOLD_BORDER};
  font-weight: 600;
}}
.original-quote p {{
  margin: 0;
  overflow: visible;
}}

/* ---------- 隐秘手账：关键词批注 ---------- */
.secret-word {{
  position: relative;
  font-weight: 700;
  border-bottom: 2px dashed #C49A45;
  padding-right: 1.15em;
  cursor: text;
  transition: border-color 0.25s ease, color 0.25s ease, background-color 0.25s ease;
}}
.secret-word:hover {{
  border-bottom-color: #A67B2D;
  border-bottom-width: 2.5px;
  color: #5C2A2A;
  background-color: rgba(196, 154, 69, 0.12);
}}
.secret-word::before {{
  content: "🖊";
  position: absolute;
  right: 0;
  top: -0.2em;
  font-size: 0.78em;
  font-style: normal;
  font-weight: 400;
  line-height: 1;
  opacity: 0.9;
  pointer-events: none;
}}
.secret-word::after {{
  content: attr(data-tooltip);
  position: absolute;
  left: 50%;
  bottom: calc(100% + 10px);
  transform: translateX(-50%) translateY(6px);
  min-width: 140px;
  max-width: 260px;
  padding: 10px 12px;
  background: #EDE8DC;
  border: 1px solid #8C2B2B;
  border-radius: 2px;
  box-shadow: 0 6px 16px rgba(44, 36, 22, 0.12);
  color: #8C2B2B;
  font-family: "Playfair Display", "Noto Serif SC", Georgia, serif;
  font-style: italic;
  font-weight: 600;
  font-size: 12.5px;
  line-height: 1.55;
  letter-spacing: 0.02em;
  text-align: left;
  white-space: normal;
  opacity: 0;
  visibility: hidden;
  pointer-events: none;
  transition: opacity 0.25s ease, transform 0.25s ease, visibility 0.25s;
  z-index: 40;
}}
.secret-word:hover::after {{
  opacity: 1;
  visibility: visible;
  transform: translateX(-50%) translateY(0);
}}

.event-summary {{
  height: 100%;
  background: #53625710;
  border-radius: 2px;
  padding: 14px 14px 12px;
  margin: 0;
}}
.event-summary .note-title,
.psy-analysis .note-title {{
  display: block;
  margin: 0 0 0.45rem;
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  color: {SAGE};
}}
.event-summary .note-title {{
  padding-bottom: 0.3rem;
  border-bottom: 1px solid rgba(83, 98, 87, 0.35);
}}
.event-summary p {{
  margin: 0;
  font-size: 14px;
  line-height: 1.8;
  text-align: justify;
  color: #2C2416;
}}

.psy-analysis {{
  width: 100%;
  background: #8C2B2B0A;
  border: 1px dotted rgba(140, 43, 43, 0.55);
  border-radius: 2px;
  padding: 16px 18px;
  margin: 0 0 0.35rem;
  box-shadow: inset 0 0 0 3px rgba(140, 43, 43, 0.03);
}}
.psy-analysis .note-title {{
  color: {MADDER};
  font-family: "Playfair Display", "Noto Serif SC", serif !important;
  letter-spacing: 0.1em;
  border-bottom: none;
  margin-bottom: 0.5rem;
}}
.psy-analysis p {{
  margin: 0;
  font-style: italic;
  font-size: 14.5px;
  line-height: 1.85;
  text-align: justify;
  color: {MADDER};
  opacity: 0.95;
}}

.choice-hint {{
  margin: 0.85rem 0 0.25rem;
  padding: 12px 16px;
  border: 1px dashed rgba(83, 98, 87, 0.45);
  border-radius: 4px;
  color: {SAGE};
  font-size: 0.95rem;
  letter-spacing: 0.04em;
}}
.choice-prompt {{
  margin: 0.85rem 0 0.45rem;
  font-size: 0.92rem;
  line-height: 1.7;
  color: #3A2F22;
}}
.confession-box {{
  background-color: rgba(107, 74, 48, 0.14);
  border-left: 3px solid {BROWN};
  border-radius: 0 4px 4px 0;
  padding: 14px 18px;
  margin: 0.85rem 0 0.25rem;
  font-style: italic;
  font-size: 15px;
  line-height: 1.8;
  color: #3A2F22;
  white-space: pre-wrap;
  animation: confessionIn 0.35s ease;
}}
@keyframes confessionIn {{
  from {{ opacity: 0; transform: translateY(4px); }}
  to {{ opacity: 1; transform: translateY(0); }}
}}

/* ---------- 轻交互节拍 / 命运回响 ---------- */
.beat-panel {{
  margin: 0.85rem 0 1rem;
  padding: 0.95rem 1.1rem;
  background: linear-gradient(165deg, rgba(237,232,220,0.92), rgba(228,223,211,0.88));
  border: 1px solid rgba(196, 154, 69, 0.45);
  border-radius: 3px;
  box-shadow: inset 0 1px 0 rgba(255,255,255,0.4);
}}
.beat-panel .beat-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.68rem;
  letter-spacing: 0.16em;
  color: {SAGE};
  margin-bottom: 0.45rem;
}}
.beat-panel .beat-clock {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 1.05rem;
  color: {GOLD_BORDER};
  margin-bottom: 0.35rem;
}}
.beat-panel p {{
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.75;
  color: #3A2F22;
}}
.beat-contrast {{
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0.75rem;
  margin-top: 0.35rem;
}}
.beat-contrast .side {{
  padding: 0.65rem 0.75rem;
  background: rgba(255,255,255,0.35);
  border: 1px solid rgba(196, 154, 69, 0.28);
}}
.beat-contrast .side-label {{
  display: block;
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  color: {BROWN};
  margin-bottom: 0.35rem;
}}
.fate-echo {{
  margin: 1rem 0 0.5rem;
  padding: 1rem 1.15rem;
  background: rgba(140, 43, 43, 0.07);
  border: 1px solid rgba(140, 43, 43, 0.28);
  border-left: 3px solid {MADDER};
  border-radius: 0 3px 3px 0;
}}
.fate-echo .echo-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  color: {MADDER};
  margin-bottom: 0.45rem;
}}
.fate-echo p {{
  margin: 0;
  font-size: 0.92rem;
  line-height: 1.8;
  color: #3A2F22;
  font-style: italic;
}}
.fate-echo .echo-you {{
  margin-top: 0.65rem;
  padding-top: 0.55rem;
  border-top: 1px solid rgba(140, 43, 43, 0.18);
  font-style: normal;
  font-size: 0.88rem;
  color: {BROWN};
}}
.coda-choices {{
  margin: 1.25rem auto 0.5rem;
  max-width: 36em;
  text-align: left;
  padding: 1rem 1.15rem;
  background: rgba(237, 232, 220, 0.65);
  border: 1px solid rgba(196, 154, 69, 0.4);
}}
.coda-choices .coda-choice-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.7rem;
  letter-spacing: 0.14em;
  color: {SAGE};
  margin-bottom: 0.65rem;
}}
.coda-choices .coda-choice-row {{
  margin: 0 0 0.75rem;
  font-size: 0.9rem;
  line-height: 1.7;
  color: #3A2F22;
}}
.coda-choices .coda-choice-row:last-child {{ margin-bottom: 0; }}
.coda-choices em {{
  font-style: italic;
  color: {BROWN};
}}

/* ---------- 米色纸张铭牌按钮 ---------- */
div.stButton > button,
div[data-testid="stButton"] > button {{
  background-color: {IVORY} !important;
  background-image:
    linear-gradient(180deg, rgba(255,255,255,0.35), transparent 55%) !important;
  color: {CARBON} !important;
  border: 1px solid {GOLD_BORDER} !important;
  border-radius: 3px 7px 3px 6px !important;
  font-family: "Playfair Display", Georgia, "Noto Serif SC", serif !important;
  font-size: 14px !important;
  letter-spacing: 0.06em !important;
  font-weight: 500 !important;
  box-shadow:
    inset 0 1px 3px rgba(44, 36, 22, 0.12),
    inset 0 -1px 2px rgba(196, 154, 69, 0.18),
    0 1px 3px rgba(44, 36, 22, 0.08) !important;
  transition: all 0.4s ease !important;
  min-height: 2.4rem;
}}
div.stButton > button:hover,
div[data-testid="stButton"] > button:hover {{
  background-color: rgba(196, 154, 69, 0.78) !important;
  background-image:
    linear-gradient(180deg, rgba(255,255,255,0.22), transparent 55%) !important;
  border-color: {GOLD_BORDER} !important;
  color: {CARBON} !important;
  box-shadow:
    inset 0 0 5px rgba(44, 36, 22, 0.12),
    0 0 0 1px rgba(196, 154, 69, 0.45),
    0 0 14px rgba(196, 154, 69, 0.4),
    0 3px 10px rgba(196, 154, 69, 0.22) !important;
  filter: none !important;
  transform: translateY(-1px);
}}
div.stButton > button:active,
div[data-testid="stButton"] > button:active {{
  transform: translateY(1px);
  box-shadow: inset 0 0 8px rgba(0, 0, 0, 0.2) !important;
}}
div.stButton > button:disabled,
div[data-testid="stButton"] > button:disabled {{
  opacity: 0.55 !important;
  transform: none !important;
}}
div.stButton > button[kind="primary"],
div[data-testid="stButton"] > button[kind="primary"],
div.stButton > button[kind="secondary"],
div[data-testid="stButton"] > button[kind="secondary"] {{
  background-color: {IVORY} !important;
  color: {CARBON} !important;
  border: 1px solid {GOLD_BORDER} !important;
}}
div.stButton > button[kind="primary"]:hover,
div[data-testid="stButton"] > button[kind="primary"]:hover,
div.stButton > button[kind="secondary"]:hover,
div[data-testid="stButton"] > button[kind="secondary"]:hover {{
  background-color: rgba(196, 154, 69, 0.78) !important;
  color: {CARBON} !important;
}}

/* ---------- 书桌阶段（封面 / 对开 / 尾声） ---------- */
.stage-desk-mark {{
  position: absolute;
  width: 0;
  height: 0;
  overflow: hidden;
}}
.cover-fallback {{
  max-width: 300px;
  margin: 0.35rem auto 1rem;
}}
.cover-fallback div[data-testid="stButton"] > button {{
  background: transparent !important;
  background-image: none !important;
  color: {BRASS} !important;
  border: 1px solid rgba(196, 154, 69, 0.65) !important;
  border-radius: 999px !important;
  letter-spacing: 0.14em !important;
  font-size: 12px !important;
  min-height: 2.15rem !important;
  box-shadow: none !important;
}}
.cover-fallback div[data-testid="stButton"] > button:hover {{
  background: rgba(196, 154, 69, 0.22) !important;
  color: {CARBON} !important;
  transform: none !important;
  box-shadow: 0 0 14px rgba(196, 154, 69, 0.28) !important;
}}

/* 对开羊皮纸：固定与封面同高 */
div[data-testid="stHorizontalBlock"]:has(.open-book-left) {{
  position: relative;
  max-width: 680px;
  height: 490px;
  margin: 0.35rem auto 0.75rem !important;
  background:
    linear-gradient(90deg,
      {PARCHMENT} 0%,
      {CARD_BG} 46%,
      #C9B89A 49.4%,
      #B5A288 50%,
      #C9B89A 50.6%,
      {CARD_BG} 54%,
      {PARCHMENT} 100%);
  border: 1px solid rgba(196, 154, 69, 0.42);
  border-radius: 3px 8px 8px 3px;
  box-shadow:
    0 0 0 1px rgba(44, 36, 22, 0.12),
    0 12px 28px rgba(44, 36, 22, 0.12),
    inset 0 0 50px rgba(107, 74, 48, 0.05);
  padding: 14px 12px 12px !important;
  gap: 0.2rem !important;
  align-items: stretch !important;
  overflow: hidden;
  animation: openBookIn 0.35s ease;
}}
div[data-testid="stHorizontalBlock"]:has(.open-book-left)::before {{
  content: "";
  position: absolute;
  left: 50%;
  top: 0;
  bottom: 0;
  width: 16px;
  transform: translateX(-50%);
  background: linear-gradient(90deg,
    rgba(44, 36, 22, 0.07),
    rgba(44, 36, 22, 0.2) 45%,
    rgba(255, 255, 255, 0.12) 55%,
    rgba(44, 36, 22, 0.05));
  pointer-events: none;
  z-index: 2;
}}
.open-book-leaf {{
  position: relative;
  z-index: 1;
  padding: 4px 10px 8px;
  box-sizing: border-box;
}}
.open-book-left.open-book-leaf {{
  min-height: 455px;
  display: flex;
  flex-direction: column;
}}
.open-book-leaf .leaf-kicker {{
  display: block;
  text-align: center;
  font-family: "Playfair Display", Georgia, serif !important;
  font-size: 0.68rem;
  letter-spacing: 0.2em;
  color: {SAGE};
  margin-bottom: 0.4rem;
}}
.open-book-leaf h2 {{
  text-align: center;
  font-size: 1.05rem;
  color: {CARBON} !important;
  margin: 0 0 0.45rem;
  line-height: 1.35;
  font-weight: 700;
}}
.open-book-left .leaf-body {{
  font-size: 0.72rem;
  line-height: 1.7;
  color: #3A2F22;
  text-align: justify;
  text-indent: 2em;
  margin: 0;
}}
.open-book-left .leaf-quote {{
  margin-top: auto;
  margin-bottom: 0.2rem;
  padding-top: 0.85rem;
  width: 100%;
  max-width: 100%;
  align-self: center;
  text-align: center;
  font-family: "Playfair Display", "Noto Serif SC", Georgia, serif !important;
  font-size: 0.68rem;
  line-height: 1.55;
  font-style: italic !important;
  font-weight: 400;
  color: {SAGE};
  opacity: 0.9;
  letter-spacing: 0.02em;
}}
.open-book-leaf .preview-hint {{
  text-align: center;
  font-size: 0.62rem;
  color: {BROWN};
  margin: 0 0 0.35rem;
  letter-spacing: 0.04em;
}}
/* 右页：以图为主；章节名缩小；插图微旋错落 */
div[data-testid="column"]:has(.preview-tilt-a) p.preview-caption,
div[data-testid="column"]:has(.preview-tilt-a) .preview-caption {{
  text-align: center !important;
  font-size: 0.52rem !important;
  line-height: 1.3 !important;
  color: {BROWN} !important;
  margin: 0.1rem 0 0.55rem !important;
  opacity: 0.62 !important;
  letter-spacing: 0.02em !important;
  font-weight: 400 !important;
}}
div[data-testid="column"]:has(.preview-tilt-a) [data-testid="stImage"]:nth-of-type(1) {{
  width: 84% !important;
  max-width: 84% !important;
  margin: 0.15rem 0 0.1rem 1% !important;
  transform: rotate(-4.8deg) !important;
  transform-origin: center center !important;
}}
div[data-testid="column"]:has(.preview-tilt-a) [data-testid="stImage"]:nth-of-type(2) {{
  width: 78% !important;
  max-width: 78% !important;
  margin: 0.45rem 2% 0.1rem 16% !important;
  transform: rotate(3.6deg) !important;
  transform-origin: center center !important;
}}
div[data-testid="column"]:has(.preview-tilt-a) [data-testid="stImage"] img {{
  max-height: 118px !important;
  width: 100% !important;
  object-fit: cover !important;
  border-radius: 2px !important;
  border: 1px solid rgba(168, 130, 72, 0.4) !important;
  box-shadow: 0 5px 14px rgba(44, 36, 22, 0.16) !important;
}}
/* 兼容：直接作用在 img（部分 Streamlit 版本 stImage 结构不同） */
div[data-testid="column"]:has(.preview-tilt-a) [data-testid="stImage"]:nth-of-type(1) img {{
  transform: rotate(-4.8deg) !important;
}}
div[data-testid="column"]:has(.preview-tilt-a) [data-testid="stImage"]:nth-of-type(2) img {{
  transform: rotate(3.6deg) !important;
}}
.open-book-hint {{
  text-align: center;
  font-size: 0.78rem;
  letter-spacing: 0.08em;
  color: {SAGE};
  opacity: 0.75;
  margin: 0.15rem 0 0.55rem;
}}
.open-book-wrap {{
  max-width: 720px;
  margin: 0 auto;
}}
@keyframes openBookIn {{
  from {{ opacity: 0.4; transform: translateY(6px); }}
  to {{ opacity: 1; transform: none; }}
}}

/* 阅读进度与横向翻页 */
.reading-meta {{
  text-align: center;
  font-family: "Playfair Display", Georgia, serif !important;
  font-size: 0.88rem;
  letter-spacing: 0.12em;
  color: {BROWN};
  margin: 0 0 1rem;
}}
.reading-nav-hint {{
  display: none;
}}
/* 左右翻页：fixed 贴视口两侧；勿改 section.main 的 overflow，否则页面无法滚动 */
div[data-testid="stHorizontalBlock"]:has(.flip-nav-left):has(.reading-mid-mark) {{
  align-items: flex-start !important;
  gap: 0 !important;
  background: transparent !important;
  border: none !important;
  box-shadow: none !important;
  padding: 0 !important;
  margin: 0 0 0.5rem !important;
  position: relative !important;
}}
div[data-testid="stHorizontalBlock"]:has(.flip-nav-left):has(.reading-mid-mark)::before,
div[data-testid="stHorizontalBlock"]:has(.flip-nav-left):has(.reading-mid-mark)::after {{
  display: none !important;
}}
div[data-testid="column"]:has(.flip-nav-mark) {{
  position: fixed !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
  z-index: 1000 !important;
  width: 44px !important;
  min-width: 44px !important;
  max-width: 44px !important;
  flex: 0 0 0 !important;
  padding: 0 !important;
  margin: 0 !important;
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
  align-items: center !important;
  height: auto !important;
  align-self: flex-start !important;
  pointer-events: auto !important;
}}
/* 左侧外移到视口左缘（避开折叠侧栏） */
div[data-testid="column"]:has(.flip-nav-left) {{
  left: 5rem !important;
  right: auto !important;
}}
/* 右侧外移到视口右缘 */
div[data-testid="column"]:has(.flip-nav-right) {{
  right: 1.75rem !important;
  left: auto !important;
}}
/* 直接钉住按钮本体，避免父级 transform 让 fixed 失效 */
button.ebook-nav-pinned,
div[data-testid="stButton"] > button.ebook-nav-pinned {{
  position: fixed !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
  z-index: 10000 !important;
  width: 44px !important;
  height: 44px !important;
  min-width: 44px !important;
  min-height: 44px !important;
}}
button.ebook-nav-pinned-left,
div[data-testid="stButton"] > button.ebook-nav-pinned-left {{
  left: 5rem !important;
  right: auto !important;
}}
button.ebook-nav-pinned-right,
div[data-testid="stButton"] > button.ebook-nav-pinned-right {{
  right: 1.75rem !important;
  left: auto !important;
}}
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] {{
  margin: 0 !important;
  width: 44px !important;
}}
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button,
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button[kind="primary"],
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button[kind="secondary"] {{
  width: 44px !important;
  height: 44px !important;
  min-width: 44px !important;
  min-height: 44px !important;
  max-width: 44px !important;
  max-height: 44px !important;
  padding: 0 !important;
  margin: 0 !important;
  border-radius: 3px !important;
  font-size: 1.15rem !important;
  line-height: 1 !important;
  letter-spacing: 0 !important;
  font-weight: 500 !important;
  font-family: "Playfair Display", Georgia, "Noto Serif SC", serif !important;
  background-color: {IVORY} !important;
  background-image:
    linear-gradient(180deg, rgba(255,255,255,0.35), transparent 55%) !important;
  color: {CARBON} !important;
  border: 1px solid {GOLD_BORDER} !important;
  box-shadow:
    inset 0 1px 3px rgba(44, 36, 22, 0.12),
    inset 0 -1px 2px rgba(196, 154, 69, 0.18),
    0 2px 8px rgba(44, 36, 22, 0.12) !important;
  aspect-ratio: 1 / 1 !important;
}}
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button:hover,
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button[kind="primary"]:hover,
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button[kind="secondary"]:hover {{
  background-color: rgba(196, 154, 69, 0.55) !important;
  background-image:
    linear-gradient(180deg, rgba(255,255,255,0.22), transparent 55%) !important;
  color: {CARBON} !important;
  border-color: {GOLD_BORDER} !important;
  transform: none !important;
  box-shadow:
    inset 0 0 5px rgba(44, 36, 22, 0.12),
    0 0 0 1px rgba(196, 154, 69, 0.35) !important;
}}
div[data-testid="column"]:has(.flip-nav-mark) div[data-testid="stButton"] > button:disabled {{
  opacity: 0.4 !important;
  transform: none !important;
}}
iframe[title="keyboard-nav-bridge"] {{
  position: absolute !important;
  width: 0 !important;
  height: 0 !important;
  border: 0 !important;
  opacity: 0 !important;
  pointer-events: none !important;
}}
@media (max-width: 900px) {{
  div[data-testid="column"]:has(.flip-nav-left),
  button.ebook-nav-pinned-left,
  div[data-testid="stButton"] > button.ebook-nav-pinned-left {{
    left: 3.5rem !important;
  }}
  div[data-testid="column"]:has(.flip-nav-right),
  button.ebook-nav-pinned-right,
  div[data-testid="stButton"] > button.ebook-nav-pinned-right {{
    right: 0.85rem !important;
  }}
}}
.coda-panel {{
  text-align: center;
  padding: 2rem 1.5rem;
  background:
    linear-gradient(165deg, {CARD_BG} 0%, {PARCHMENT} 100%);
  border: 1px solid rgba(196, 154, 69, 0.55);
  border-radius: 3px;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.4),
    0 12px 28px rgba(44, 36, 22, 0.12);
  margin: 1rem 0 1.25rem;
}}
.coda-panel .leaf-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif !important;
  font-size: 0.7rem;
  letter-spacing: 0.18em;
  color: {SAGE};
  margin-bottom: 0.65rem;
}}
.coda-panel h2 {{
  margin: 0 0 1rem;
  font-size: 1.15rem;
  color: {CARBON} !important;
}}
.coda-panel .leaf-body {{
  max-width: 36em;
  margin: 0 auto 0.5rem;
  font-style: italic;
  line-height: 1.85;
  color: #3A2F22;
  text-align: justify;
}}
.flip-choice-hint {{
  text-align: center;
  font-size: 0.78rem;
  color: {MADDER};
  letter-spacing: 0.06em;
  margin: 0.65rem 0 0;
  opacity: 0.9;
}}
</style>
"""


def inject_global_styles() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session / 导航状态机
# view: cover | open_book | reading | coda
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    ss = st.session_state
    if "view" not in ss:
        ss.view = "cover"
    if "page" not in ss:
        ss.page = 0
    if "opened_cards" not in ss:
        ss.opened_cards = {}
    if "choices" not in ss:
        ss.choices = {}
    if "beats_confirmed" not in ss:
        ss.beats_confirmed = {}


def inject_stage_styles(view: str) -> None:
    """封面/对开/尾声与阅读共用画布米色背景，避免书桌色割裂。"""
    if view in ("cover", "open_book", "coda"):
        st.markdown(
            f"""
            <style>
            .stApp {{
              background-color: {CANVAS_BG} !important;
              background-image:
                url("data:image/svg+xml,%3Csvg viewBox='0 0 200 200' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.85' numOctaves='4' stitchTiles='stitch'/%3E%3CfeColorMatrix type='saturate' values='0'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)' opacity='0.55'/%3E%3C/svg%3E") !important;
              background-blend-mode: multiply !important;
              background-size: 180px 180px !important;
            }}
            .main .block-container {{
              padding-left: 1.5rem !important;
              padding-right: 1.5rem !important;
              max-width: 760px;
            }}
            .main .block-container::before {{
              display: none !important;
            }}
            .book-header {{
              margin: 0.15rem 0 0.85rem !important;
            }}
            .book-title {{
              color: {CARBON} !important;
              font-size: 20px !important;
              font-weight: 700 !important;
              letter-spacing: 0.08em !important;
              opacity: 1;
            }}
            .brush-underline {{
              display: block !important;
              width: min(420px, 88%) !important;
              margin: 8px auto 0 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    else:
        # reading：单卡，隐藏整条时间线竖轨
        st.markdown(
            f"""
            <style>
            .main .block-container::before {{ display: none !important; }}
            /* 恢复主区纵向滚动（勿设 overflow:visible） */
            section.main,
            [data-testid="stMain"] {{
              overflow-x: hidden !important;
              overflow-y: auto !important;
            }}
            .main .block-container {{
              padding-left: 5.5rem !important;
              padding-right: 5.5rem !important;
              max-width: 980px;
            }}
            div[data-testid="column"]:has(.flip-nav-left) {{
              left: 5rem !important;
            }}
            div[data-testid="column"]:has(.flip-nav-right) {{
              right: 1.75rem !important;
            }}
            .book-header {{
              margin: 0.15rem 0 0.85rem !important;
            }}
            .book-title {{
              color: {CARBON} !important;
              font-size: 20px !important;
              font-weight: 700 !important;
              letter-spacing: 0.08em !important;
            }}
            .brush-underline {{
              display: block !important;
              width: min(420px, 88%) !important;
              margin: 8px auto 0 !important;
            }}
            div[data-testid="stHorizontalBlock"]:has(.scene-card-marker)::before {{
              display: none !important;
            }}
            /* 阅读阶段取消日记错落 */
            div[data-testid="stHorizontalBlock"]:has(.card-media.offset-a),
            div[data-testid="stHorizontalBlock"]:has(.card-media.offset-b),
            div[data-testid="stHorizontalBlock"]:has(.card-media.offset-c),
            div[data-testid="stHorizontalBlock"]:has(.card-media.offset-d),
            div[data-testid="stHorizontalBlock"]:has(.card-media.is-open) {{
              margin-left: 0 !important;
              margin-right: 0 !important;
              transform: none !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )


def go_cover() -> None:
    st.session_state.view = "cover"
    st.session_state.page = 0


def go_open_book() -> None:
    st.session_state.view = "open_book"


def enter_reading() -> None:
    """进入阅读"""
    ss = st.session_state
    ss.view = "reading"
    ss.page = 0
    ss.opened_cards[0] = True


def goto_page(idx: int) -> None:
    idx = max(0, min(TOTAL_PAGES - 1, idx))
    ss = st.session_state
    ss.view = "reading"
    ss.page = idx
    ss.opened_cards[idx] = True


def go_prev_page() -> None:
    ss = st.session_state
    if ss.page <= 0:
        ss.view = "open_book"
        return
    ss.page -= 1
    ss.opened_cards[ss.page] = True


def go_next_page() -> None:
    ss = st.session_state
    card = SCENE_CARDS[ss.page]
    if card.get("has_choice") and ss.page not in ss.choices:
        return
    if ss.page >= TOTAL_PAGES - 1:
        ss.view = "coda"
        return
    ss.page += 1
    ss.opened_cards[ss.page] = True


def go_coda() -> None:
    st.session_state.view = "coda"


def render_confession(text: str) -> None:
    """即时展示独白（轻量淡入，避免打字机阻塞整页）。"""
    st.markdown(
        f'<div class="confession-box">{_escape_multiline(text)}</div>',
        unsafe_allow_html=True,
    )


# ---------------------------------------------------------------------------
# 页面区块
# ---------------------------------------------------------------------------
def render_book_header() -> None:
    st.markdown(
        f"""
        <div class="book-header">
          <h1 class="book-title">《一个女人一生中的二十四小时》</h1>
          <svg class="brush-underline" viewBox="0 0 420 14" xmlns="http://www.w3.org/2000/svg" aria-hidden="true">
            <path d="M4 8 C40 3, 90 11, 140 7 C190 3, 240 12, 290 6 C340 2, 380 10, 416 7"
                  fill="none" stroke="{GOLD_BORDER}" stroke-width="3.2"
                  stroke-linecap="round" stroke-linejoin="round" opacity="0.92"/>
            <path d="M12 10 C70 13, 130 5, 200 11 C270 15, 340 6, 400 10"
                  fill="none" stroke="{GOLD_BORDER}" stroke-width="1.6"
                  stroke-linecap="round" opacity="0.45"/>
          </svg>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_cover() -> None:
    """实体封面：点击后 3D 翻开，进入对开页。"""
    cover_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Playfair+Display:ital,wght@0,400;0,600;0,700;1,400&family=Noto+Serif+SC:wght@500;700&display=swap');
  html, body {{ margin:0; padding:0; background:transparent; overflow:hidden;
    font-family:"Noto Serif SC",serif; }}
  .stage {{ perspective:2000px; display:flex; justify-content:center; align-items:center;
    min-height:520px; padding:8px; }}
  .book {{ position:relative; width:min(340px,86vw); height:490px;
    transform-style:preserve-3d; cursor:pointer; }}
  .pages {{ position:absolute; inset:8px 8px 8px 4px;
    background:linear-gradient(90deg,#C4B49A,{PARCHMENT} 14%,#F7F1E4);
    border-radius:0 5px 5px 0; z-index:1;
    box-shadow:inset -8px 0 16px rgba(0,0,0,0.06); }}
  .cover {{ position:absolute; inset:0; transform-origin:left center;
    transform-style:preserve-3d; transition:transform 1s cubic-bezier(0.42,0.02,0.22,1); z-index:2; }}
  .book.open .cover {{ transform:rotateY(-155deg); }}
  .face {{ position:absolute; inset:0; backface-visibility:hidden;
    background:
      linear-gradient(145deg, #F7F2E6 0%, {CARD_BG} 42%, #E0D5C2 100%);
    border-radius:2px 7px 7px 2px;
    box-shadow:
      3px 0 0 #C9B89A,
      4px 0 0 #B5A288,
      10px 16px 36px rgba(44,36,22,0.22),
      inset 0 0 0 1px rgba(196,154,69,0.55);
    display:flex; align-items:center; justify-content:center; padding:24px; }}
  .face::before {{ content:""; position:absolute; left:0; top:0; bottom:0; width:14px;
    background:linear-gradient(90deg,
      rgba(107,74,48,0.28),
      rgba(255,255,255,0.35) 40%,
      rgba(107,74,48,0.12));
    border-radius:2px 0 0 2px; }}
  .frame {{ position:relative; width:100%; height:100%; box-sizing:border-box;
    border:1px solid rgba(196,154,69,0.7);
    box-shadow:inset 0 0 0 5px {CARD_BG}, inset 0 0 0 6px rgba(196,154,69,0.4);
    display:flex; flex-direction:column; align-items:center; justify-content:space-between;
    padding:28px 18px 18px; text-align:center; color:{CARBON}; }}
  .corner {{ position:absolute; width:12px; height:12px; border-color:{GOLD_BORDER}; border-style:solid; }}
  .tl {{ top:7px; left:7px; border-width:1px 0 0 1px; }}
  .tr {{ top:7px; right:7px; border-width:1px 1px 0 0; }}
  .bl {{ bottom:7px; left:7px; border-width:0 0 1px 1px; }}
  .br {{ bottom:7px; right:7px; border-width:0 1px 1px 0; }}
  .series {{ font-family:"Playfair Display",Georgia,serif; font-size:9.5px;
    letter-spacing:0.28em; color:{SAGE}; margin:4px 0 0; }}
  .title {{ font-size:24px; font-weight:700; line-height:1.4; margin:0; color:{CARBON}; }}
  .title em {{ display:block; margin-top:8px; font-family:"Playfair Display",Georgia,serif;
    font-style:italic; font-weight:400; font-size:18px; color:{GOLD_BORDER}; }}
  .rule {{ width:64%; height:1px; background:rgba(196,154,69,0.55); margin:10px auto; }}
  .sub {{ font-family:"Playfair Display",Georgia,serif; font-size:10px;
    letter-spacing:0.22em; color:{BROWN}; margin:0; opacity:0.85; }}
  .author {{ font-size:14px; margin:0; color:{CARBON}; }}
  .cta {{ font-family:"Playfair Display",Georgia,serif; font-size:9px;
    letter-spacing:0.2em; color:{SAGE}; margin:0 0 2px; }}
  .hint {{ text-align:center; color:{BROWN}; font-size:11px; opacity:0.65;
    letter-spacing:0.12em; margin:4px 0 0; font-family:"Playfair Display",Georgia,serif; }}
</style></head><body>
  <div class="stage">
    <div class="book" id="book" title="点击翻开">
      <div class="pages"></div>
      <div class="cover"><div class="face"><div class="frame">
        <span class="corner tl"></span><span class="corner tr"></span>
        <span class="corner bl"></span><span class="corner br"></span>
        <p class="series">LITERARY DECONSTRUCTION</p>
        <div>
          <h1 class="title">一个女人<em>一生中的二十四小时</em></h1>
          <div class="rule"></div>
          <p class="sub">THE BOOK OF MEMORY</p>
          <div class="rule"></div>
        </div>
        <p class="author">Stefan Zweig</p>
        <p class="cta">TOUCH TO BEGIN THE CYCLE</p>
      </div></div></div>
    </div>
  </div>
  <p class="hint">点击封面 · 翻开书页</p>
<script>
(function(){{
  const book=document.getElementById('book');
  let opening=false;
  function clickParent(){{
    try{{
      const btn=window.parent.document.querySelector('button[kind="primary"]')
        || Array.from(window.parent.document.querySelectorAll('button')).find(function(b){{
          const t=(b.innerText||'').trim();
          return t.indexOf('TOUCH TO BEGIN')>=0 || t.indexOf('翻开此书')>=0;
        }});
      if(btn) btn.click();
    }}catch(e){{}}
  }}
  book.addEventListener('click',function(){{
    if(opening) return;
    opening=true;
    book.classList.add('open');
    /* 短延迟：让翻开动画起势，但不拖到整页重绘卡死 */
    setTimeout(clickParent, 420);
  }});
}})();
</script>
</body></html>"""
    components.html(cover_html, height=560, scrolling=False)
    _, mid, _ = st.columns([1, 1.3, 1])
    with mid:
        st.markdown('<div class="cover-fallback">', unsafe_allow_html=True)
        st.button(
            "TOUCH TO BEGIN · 翻开此书",
            key="btn_go_open_book",
            width="stretch",
            on_click=go_open_book,
            type="primary",
        )
        st.markdown("</div>", unsafe_allow_html=True)


def render_open_book() -> None:
    """对开羊皮纸：Streamlit 原生渲染（避免 iframe 嵌入大图导致空白/卡顿）。"""
    intro_title = INTRO.get("title", "")
    # 完整展示引言首段（book_content.INTRO 第一段）
    first_para = INTRO.get("text", "").split("\n\n")[0].strip()

    st.markdown('<div class="open-book-wrap">', unsafe_allow_html=True)
    left, right = st.columns(2, gap="small")

    with left:
        st.markdown(
            f"""
            <div class="open-book-left open-book-leaf">
              <span class="leaf-kicker">PROLOGUE · 题记</span>
              <h2>{html.escape(intro_title)}</h2>
              <p class="leaf-body">{html.escape(first_para)}</p>
              <p class="leaf-quote">一半真实毫无价值，有意义的永远只在全部真实。</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        # components.html：避免 Streamlit markdown 转义 <figure>/<img> 导致源码外泄
        figs = []
        node_labels = ("节点一", "节点二", "节点三")
        tilts = (-3.8, 3.2, -2.4)
        for i in range(min(PREVIEW_COUNT, TOTAL_PAGES)):
            card = SCENE_CARDS[i]
            src = _thumb_data_uri(card.get("image"), 280)
            label = html.escape(
                node_labels[i] if i < len(node_labels) else f"节点{i + 1}"
            )
            rot = tilts[i % len(tilts)]
            w = "72%" if i else "78%"
            figs.append(
                f'<figure class="fig fig-{i}" style="transform:rotate({rot}deg);width:{w};">'
                f'<img src="{src}" alt="{label}"/>'
                f"<figcaption>{label}</figcaption></figure>"
            )
        gallery_html = "".join(figs)
        right_html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<style>
  @import url('https://fonts.googleapis.com/css2?family=Noto+Serif+SC:wght@500;600&family=Playfair+Display:wght@400;500&display=swap');
  html, body {{
    margin: 0; padding: 0; background: transparent; overflow: hidden;
    font-family: "Noto Serif SC", "Source Han Serif SC", serif;
  }}
  .wrap {{
    text-align: center;
    padding: 4px 8px 6px;
    box-sizing: border-box;
    height: 430px;
  }}
  .kicker {{
    margin: 0 0 8px;
    font-family: "Playfair Display", Georgia, serif;
    font-size: 11px;
    letter-spacing: 0.2em;
    color: #536257;
  }}
  .hint {{
    margin: 0 0 10px;
    font-size: 10px;
    letter-spacing: 0.06em;
    color: #6B4A30;
    opacity: 0.8;
  }}
  .gallery {{
    display: flex;
    flex-direction: column;
    align-items: center;
    gap: 14px;
  }}
  .fig {{
    margin: 0;
    max-width: 240px;
  }}
  .fig img {{
    display: block;
    width: 100%;
    max-height: 110px;
    object-fit: cover;
    border-radius: 2px;
    border: 1px solid rgba(168, 130, 72, 0.4);
    box-shadow: 0 5px 14px rgba(44, 36, 22, 0.14);
    background: #EDE8DC;
  }}
  .fig figcaption {{
    margin-top: 5px;
    font-size: 10px;
    letter-spacing: 0.12em;
    color: #6B4A30;
    opacity: 0.6;
    text-align: center;
  }}
</style></head><body>
  <div class="wrap">
    <p class="kicker">PRELUDE · 画页</p>
    <p class="hint">点按下方进入 · 开启第一幕</p>
    <div class="gallery">{gallery_html}</div>
  </div>
</body></html>"""
        components.html(right_html, height=440, scrolling=False)


    st.markdown("</div>", unsafe_allow_html=True)

    c1, c2, c3 = st.columns([1, 1.15, 1])
    with c2:
        st.markdown('<div class="cover-fallback">', unsafe_allow_html=True)
        st.button(
            "由此进入书中世界",
            key="btn_enter_reading",
            width="stretch",
            on_click=enter_reading,
            type="primary",
        )
        st.markdown("</div>", unsafe_allow_html=True)

    st.markdown(
        '<p class="open-book-hint">点上方按钮启程 · 自第一节点开始</p>',
        unsafe_allow_html=True,
    )
    _, back, _ = st.columns([1.2, 0.8, 1.2])
    with back:
        st.button("返回封面", key="btn_back_cover", width="stretch", on_click=go_cover)


def render_light_beat(beat: dict, scene_idx: int) -> None:
    """每隔数节点的轻交互：批注 / 对照 / 独白确认 / 时辰推进。"""
    if not beat:
        return
    kind = beat.get("type", "annotation")
    kicker = html.escape(beat.get("kicker", "节拍"))

    if kind == "whisper":
        prompt = html.escape(beat.get("prompt", ""))
        st.markdown(
            f"""
            <div class="beat-panel">
              <span class="beat-kicker">{kicker}</span>
              <p>{prompt}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        confirmed = bool(st.session_state.beats_confirmed.get(scene_idx))
        label = beat.get("confirm_label", "我听见了")
        if st.button(
            label if not confirmed else f"✓ {label}",
            key=f"beat_whisper_{scene_idx}",
            width="stretch",
            disabled=confirmed,
        ):
            st.session_state.beats_confirmed[scene_idx] = True
            st.rerun()
        if confirmed and beat.get("echo"):
            st.markdown(
                f'<div class="beat-panel"><p>{html.escape(beat["echo"])}</p></div>',
                unsafe_allow_html=True,
            )
        return

    if kind == "contrast":
        left_l = html.escape(beat.get("left_label", "一侧"))
        right_l = html.escape(beat.get("right_label", "另一侧"))
        left = html.escape(beat.get("left", ""))
        right = html.escape(beat.get("right", ""))
        st.markdown(
            f"""
            <div class="beat-panel">
              <span class="beat-kicker">{kicker}</span>
              <div class="beat-contrast">
                <div class="side"><span class="side-label">{left_l}</span>{left}</div>
                <div class="side"><span class="side-label">{right_l}</span>{right}</div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    if kind == "hour":
        clock = html.escape(beat.get("clock", ""))
        body = html.escape(beat.get("body", ""))
        st.markdown(
            f"""
            <div class="beat-panel">
              <span class="beat-kicker">{kicker}</span>
              <span class="beat-clock">{clock}</span>
              <p>{body}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
        return

    # annotation 默认
    body = html.escape(beat.get("body", ""))
    st.markdown(
        f"""
        <div class="beat-panel">
          <span class="beat-kicker">{kicker}</span>
          <p>{body}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_coda() -> None:
    st.markdown(
        f"""
        <div class="coda-panel">
          <span class="leaf-kicker">EPILOGUE · 尾声</span>
          <h2>{html.escape(EPILOGUE.get("title", "结语"))}</h2>
          <p class="leaf-body">{_escape_multiline(EPILOGUE.get("text", ""))}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )

    # 复述「你以为自己选择了什么」
    choice_rows = []
    for idx in (6, 7):  # 节点七、八（0-based）
        card = SCENE_CARDS[idx]
        picked = st.session_state.choices.get(idx)
        if not picked:
            continue
        label = card.get("choices", {}).get(picked, picked)
        title = card.get("title", f"节点{idx + 1}")
        note = card.get("author_note", "")
        choice_rows.append(
            f'<div class="coda-choice-row">'
            f'<strong>{html.escape(title)}</strong><br/>'
            f'你以为选了 <em>{html.escape(picked)} · {html.escape(label)}</em>'
            f'{"<br/>" + html.escape(note) if note else ""}'
            f"</div>"
        )
    if choice_rows:
        st.markdown(
            f"""
            <div class="coda-choices">
              <span class="coda-choice-kicker">你以为自己选择了</span>
              {"".join(choice_rows)}
            </div>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.markdown(
            """
            <div class="coda-choices">
              <span class="coda-choice-kicker">你以为自己选择了</span>
              <div class="coda-choice-row">你尚未在节点七、八做出抉择——
              或者命运已替你走完，只是未曾留下痕迹。</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    with c1:
        st.button("返回封面", width="stretch", on_click=go_cover)
    with c2:
        st.button(
            "回到最后一页",
            width="stretch",
            on_click=goto_page,
            args=(TOTAL_PAGES - 1,),
        )


def render_choice_block(card: dict, scene_idx: int) -> None:
    """伪分支抉择：选完后独白反馈 + 命运回响（强调「你以为自己选择了」）。"""
    prompt = card.get("choice_prompt", "")
    if prompt:
        st.markdown(
            f'<p class="choice-prompt">{html.escape(prompt)}</p>',
            unsafe_allow_html=True,
        )

    choices = card.get("choices") or {"A": "选择理智", "B": "选择狂热"}
    voices = card.get("reader_voice") or {}
    already_chosen = st.session_state.choices.get(scene_idx) is not None

    # 未选时展示两侧内心独白对照
    if not already_chosen and (voices.get("A") or voices.get("B")):
        st.markdown(
            f"""
            <div class="beat-panel">
              <span class="beat-kicker">内心对照</span>
              <div class="beat-contrast">
                <div class="side">
                  <span class="side-label">A · {html.escape(choices.get("A", ""))}</span>
                  {html.escape(voices.get("A", ""))}
                </div>
                <div class="side">
                  <span class="side-label">B · {html.escape(choices.get("B", ""))}</span>
                  {html.escape(voices.get("B", ""))}
                </div>
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            f"A · {choices.get('A', '选择理智')}",
            key=f"choice_{scene_idx}_A",
            type="secondary",
            width="stretch",
            disabled=already_chosen,
        ):
            st.session_state.choices[scene_idx] = "A"
            st.rerun()
    with col_b:
        if st.button(
            f"B · {choices.get('B', '选择狂热')}",
            key=f"choice_{scene_idx}_B",
            type="primary",
            width="stretch",
            disabled=already_chosen,
        ):
            st.session_state.choices[scene_idx] = "B"
            st.rerun()

    choice = st.session_state.choices.get(scene_idx)
    if not choice:
        st.markdown(
            f'<div class="choice-hint">{CHOICE_HINT}</div>',
            unsafe_allow_html=True,
        )
        return

    render_confession(card.get(f"feedback_{choice}", ""))

    picked_label = choices.get(choice, choice)
    note = card.get("author_note") or ""
    st.markdown(
        f"""
        <div class="fate-echo">
          <span class="echo-kicker">命运回响 · 你以为自己选择了</span>
          <p class="echo-you">你选了 <em>{html.escape(choice)} · {html.escape(picked_label)}</em></p>
          <p>{html.escape(note)}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def render_card_detail(card: dict, scene_idx: int) -> None:
    """展开态：原文+纪实，轻交互节拍，心灵解剖，抉择。"""
    text = card.get("text", "")
    summary = card.get("summary", "")
    analysis = card.get("analysis", "")

    left, right = st.columns([1.8, 1.2], gap="small")

    with left:
        st.markdown(
            f"""
            <div class="original-quote">
              <span class="quote-mark">❧ 「</span>
              <p>{format_rich_quote(text, drop_cap=True)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    with right:
        st.markdown(
            f"""
            <div class="event-summary">
              <span class="note-title">纪实</span>
              <p>{_escape_multiline(summary)}</p>
            </div>
            """,
            unsafe_allow_html=True,
        )

    if card.get("beat"):
        render_light_beat(card["beat"], scene_idx)

    beat = card.get("beat") or {}
    soul_gated = bool(beat.get("gate_soul"))
    soul_unlocked = (not soul_gated) or bool(
        st.session_state.beats_confirmed.get(scene_idx)
    )
    if soul_unlocked:
        render_soul_analysis(
            analysis,
            scene_idx,
            light=True,
        )
    elif soul_gated:
        st.caption("请先确认「我听见了」，再进入心灵解剖。")

    if card.get("has_choice"):
        render_choice_block(card, scene_idx)


def render_scene_card(card: dict, scene_idx: int) -> None:
    """单卡：插图 + 标题；进入节点即展开摘录/纪实/心灵解剖。"""
    # 阅读阶段默认展开，无需再点「翻开此页」
    st.session_state.opened_cards[scene_idx] = True

    clock = SCENE_CLOCKS[scene_idx] if scene_idx < len(SCENE_CLOCKS) else "——"
    period = card.get("time", "")
    title = card.get("title", "")
    img_path = get_image_path(card.get("image"))
    offset = DIARY_OFFSETS[scene_idx % len(DIARY_OFFSETS)]

    media_col, body_col = st.columns([1.45, 1], gap="small")

    with media_col:
        st.markdown(
            f'<div class="card-media scene-card-marker {offset} is-open"></div>',
            unsafe_allow_html=True,
        )
        st.image(img_path, width="stretch")

    with body_col:
        st.markdown(
            f"""
            <div class="card-body">
              <span class="scene-clock">{html.escape(clock)}</span>
              <span class="scene-period">{html.escape(period)}</span>
              <h3>{html.escape(title)}</h3>
            </div>
            """,
            unsafe_allow_html=True,
        )

    render_card_detail(card, scene_idx)


def consume_ebook_nav_param() -> None:
    """消费 URL ?ebook_nav=prev|next（键盘翻页桥接）。"""
    nav = st.query_params.get("ebook_nav")
    if nav not in ("prev", "next"):
        return
    try:
        del st.query_params["ebook_nav"]
    except Exception:
        pass
    if nav == "prev":
        go_prev_page()
    else:
        go_next_page()
    st.rerun()


def inject_keyboard_page_nav(*, can_next: bool) -> None:
    """钉住翻页按钮到视口两侧，并监听 ← / →（改 query 触发 Streamlit 翻页）。"""
    components.html(
        f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"/>
<script>
(function () {{
  try {{
    var frame = window.frameElement;
    if (frame) {{
      frame.setAttribute("title", "keyboard-nav-bridge");
      frame.style.cssText = "position:absolute!important;width:0!important;height:0!important;border:0!important;opacity:0!important;pointer-events:none!important;";
    }}
  }} catch (e) {{}}

  var win, doc;
  try {{
    win = window.parent;
    doc = win.document;
    void doc.body;
  }} catch (err) {{
    return;
  }}

  var canNext = {json.dumps(bool(can_next))};
  var FLAG = "__ebookNavBridgeV2";
  if (doc[FLAG] && doc[FLAG].handler) {{
    doc.removeEventListener("keydown", doc[FLAG].handler, true);
  }}
  if (doc[FLAG] && doc[FLAG].timer) {{
    clearInterval(doc[FLAG].timer);
  }}

  function findButton(slotId, cls) {{
    var slot = doc.getElementById(slotId) || doc.querySelector("." + cls);
    if (!slot) return null;
    var node = slot.parentElement;
    for (var i = 0; i < 12 && node; i++) {{
      var btn = node.querySelector("button");
      if (btn) return btn;
      node = node.parentElement;
    }}
    return null;
  }}

  function pinButtons() {{
    var prev = findButton("ebook-flip-prev-slot", "flip-nav-left");
    var next = findButton("ebook-flip-next-slot", "flip-nav-right");
    if (prev) {{
      prev.classList.add("ebook-nav-pinned", "ebook-nav-pinned-left");
      prev.style.setProperty("position", "fixed", "important");
      prev.style.setProperty("top", "50%", "important");
      prev.style.setProperty("left", "5rem", "important");
      prev.style.setProperty("right", "auto", "important");
      prev.style.setProperty("transform", "translateY(-50%)", "important");
      prev.style.setProperty("z-index", "10000", "important");
      prev.style.setProperty("width", "44px", "important");
      prev.style.setProperty("height", "44px", "important");
    }}
    if (next) {{
      next.classList.add("ebook-nav-pinned", "ebook-nav-pinned-right");
      next.style.setProperty("position", "fixed", "important");
      next.style.setProperty("top", "50%", "important");
      next.style.setProperty("right", "1.75rem", "important");
      next.style.setProperty("left", "auto", "important");
      next.style.setProperty("transform", "translateY(-50%)", "important");
      next.style.setProperty("z-index", "10000", "important");
      next.style.setProperty("width", "44px", "important");
      next.style.setProperty("height", "44px", "important");
    }}
    return !!(prev && next);
  }}

  function triggerNav(dir) {{
    if (dir === "next" && !canNext) return;
    try {{
      var url = new URL(win.location.href);
      url.searchParams.set("ebook_nav", dir);
      win.location.href = url.toString();
      return;
    }} catch (e1) {{}}
    var btn = findButton(
      dir === "prev" ? "ebook-flip-prev-slot" : "ebook-flip-next-slot",
      dir === "prev" ? "flip-nav-left" : "flip-nav-right"
    );
    if (btn && !btn.disabled) {{
      btn.click();
    }}
  }}

  var coolUntil = 0;
  function handler(e) {{
    if (e.defaultPrevented || e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    var t = e.target;
    if (t) {{
      var tag = (t.tagName || "").toLowerCase();
      if (tag === "input" || tag === "textarea" || tag === "select" || t.isContentEditable) return;
    }}
    var now = Date.now();
    if (now < coolUntil) return;
    if (e.key === "ArrowLeft") {{
      e.preventDefault();
      coolUntil = now + 500;
      triggerNav("prev");
    }} else if (e.key === "ArrowRight") {{
      if (!canNext) return;
      e.preventDefault();
      coolUntil = now + 500;
      triggerNav("next");
    }}
  }}

  pinButtons();
  var tries = 0;
  var timer = setInterval(function () {{
    tries += 1;
    if (pinButtons() || tries > 40) clearInterval(timer);
  }}, 50);

  doc[FLAG] = {{ handler: handler, timer: timer }};
  doc.addEventListener("keydown", handler, true);
}})();
</script>
</head><body></body></html>""",
        height=1,
        scrolling=False,
    )


def render_reading() -> None:
    """单节点阅读：按钮钉在视口两侧；支持 ← / → 键盘翻页。"""
    consume_ebook_nav_param()

    ss = st.session_state
    page = ss.page
    card = SCENE_CARDS[page]
    need_choice = bool(card.get("has_choice")) and page not in ss.choices

    st.markdown(
        f'<p class="reading-meta">纸页 {page + 1} / {TOTAL_PAGES}'
        f'<span style="opacity:0.55;font-size:0.85em;">'
        f' · 左侧边栏可跳转 · 键盘 ← → 亦可翻页</span></p>',
        unsafe_allow_html=True,
    )

    left_nav, mid, right_nav = st.columns([0.01, 9.98, 0.01], gap="small")

    with left_nav:
        st.markdown(
            '<span id="ebook-flip-prev-slot" class="flip-nav-mark flip-nav-left"></span>',
            unsafe_allow_html=True,
        )
        st.button(
            "<",
            key="flip_prev",
            width="stretch",
            on_click=go_prev_page,
            help="上一节点（←）" if page > 0 else "返回画页（←）",
        )

    with mid:
        st.markdown('<span class="reading-mid-mark"></span>', unsafe_allow_html=True)
        render_scene_card(card, page)
        if need_choice:
            st.markdown(
                '<p class="flip-choice-hint">请先做出抉择，再点击右侧 › 或按 → 继续</p>',
                unsafe_allow_html=True,
            )

    with right_nav:
        st.markdown(
            '<span id="ebook-flip-next-slot" class="flip-nav-mark flip-nav-right"></span>',
            unsafe_allow_html=True,
        )
        next_help = (
            "请先做出抉择"
            if need_choice
            else ("合上这一日（→）" if page >= TOTAL_PAGES - 1 else "下一节点（→）")
        )
        st.button(
            ">",
            key="flip_next",
            width="stretch",
            disabled=need_choice,
            on_click=go_next_page,
            help=next_help,
        )

    inject_keyboard_page_nav(can_next=not need_choice)


def render_side_toc() -> None:
    """书外目录：仅阅读阶段使用，不画进羊皮纸。"""
    with st.sidebar:
        st.markdown(
            f"""
            <p style="font-family:Playfair Display,Georgia,serif;letter-spacing:0.14em;
                       font-size:0.75rem;color:{SAGE};margin:0.25rem 0 0.75rem;">
              INDEX · 目录
            </p>
            """,
            unsafe_allow_html=True,
        )
        st.caption("跳转节点（书外导航）")
        page = st.session_state.page
        for i, sc in enumerate(SCENE_CARDS):
            label = f"{i + 1:02d}  {sc.get('title', '')}"
            st.button(
                label,
                key=f"sidebar_toc_{i}",
                width="stretch",
                disabled=(i == page),
                on_click=goto_page,
                args=(i,),
            )
        st.divider()
        st.button("返回画页", width="stretch", on_click=go_open_book)
        st.button("返回封面", width="stretch", on_click=go_cover)


def main() -> None:
    st.set_page_config(
        page_title="一个女人一生中的二十四小时",
        page_icon="📖",
        layout="wide",
        initial_sidebar_state="collapsed",
    )
    inject_global_styles()
    init_session_state()
    ensure_placeholder_file()

    view = st.session_state.view
    inject_stage_styles(view)

    if view == "reading":
        render_side_toc()

    if view != "cover":
        render_book_header()

    if view == "cover":
        render_cover()
    elif view == "open_book":
        render_open_book()
    elif view == "coda":
        render_coda()
    else:
        render_reading()


if __name__ == "__main__":
    main()
