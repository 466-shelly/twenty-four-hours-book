# -*- coding: utf-8 -*-
"""《一个女人一生中的二十四小时》— Streamlit 交互书主入口"""

from __future__ import annotations

import html
import json
import re
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

from book_content import SCENE_CARDS

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


def build_soul_scratch_html(analysis: str, scene_idx: int) -> str:
    """灵魂拂尘：Canvas 刮擦显影组件 HTML/CSS/JS。"""
    body = html.escape(analysis).replace("\n", "<br>")
    storage_key = f"zw_soul_scratch_{scene_idx}"
    # 供 JS 使用的纯文本长度，估算高度
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
    <div class="scratch-title">心灵解剖 · Deep Soul</div>
    <p class="scratch-text" id="soulText">{body}</p>
    <canvas id="fog"></canvas>
  </div>
<script>
(function() {{
  const storageKey = {json.dumps(storage_key)};
  const canvas = document.getElementById('fog');
  const wrap = document.getElementById('wrap');
  const ctx = canvas.getContext('2d');
  let drawing = false;
  let strokes = 0;
  let lastX = null, lastY = null;
  let revealed = false;
  const BRUSH = 28;

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
    ctx.fillText('长按并滑动鼠标，拂去尘埃，窥探深渊', rect.width / 2, rect.height / 2);
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
    if (strokes >= 3 || scratchedRatio() >= 0.40) reveal();
  }}
  function onUp(e) {{
    drawing = false;
    lastX = lastY = null;
    if (!revealed && (strokes >= 3 || scratchedRatio() >= 0.40)) reveal();
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


def render_soul_analysis(analysis: str, scene_idx: int) -> None:
    """心灵解剖：首次以刮擦显影呈现，之后保持清晰。"""
    height = max(240, min(560, 150 + len(analysis) // 2))
    components.html(
        build_soul_scratch_html(analysis, scene_idx),
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
  font-size: 22px;
  font-weight: 700;
  color: {CARBON};
  letter-spacing: 0.06em;
  line-height: 1.4;
  white-space: nowrap;
  overflow: visible;
}}
.brush-underline {{
  display: block;
  width: min(480px, 92%);
  height: 14px;
  margin: 10px auto 0;
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
</style>
"""


def inject_global_styles() -> None:
    st.markdown(GLOBAL_CSS, unsafe_allow_html=True)


# ---------------------------------------------------------------------------
# Session / 打字机
# ---------------------------------------------------------------------------
def init_session_state() -> None:
    if "opened_cards" not in st.session_state:
        st.session_state.opened_cards = {}
    if "choices" not in st.session_state:
        st.session_state.choices = {}


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


def render_choice_block(card: dict, scene_idx: int) -> None:
    prompt = card.get("choice_prompt", "")
    if prompt:
        st.markdown(
            f'<p class="choice-prompt">{html.escape(prompt)}</p>',
            unsafe_allow_html=True,
        )

    already_chosen = st.session_state.choices.get(scene_idx) is not None
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button(
            "A · 选择理智",
            key=f"choice_{scene_idx}_A",
            type="secondary",
            width="stretch",
            disabled=already_chosen,
        ):
            st.session_state.choices[scene_idx] = "A"
    with col_b:
        if st.button(
            "B · 选择狂热",
            key=f"choice_{scene_idx}_B",
            type="primary",
            width="stretch",
            disabled=already_chosen,
        ):
            st.session_state.choices[scene_idx] = "B"

    choice = st.session_state.choices.get(scene_idx)
    if not choice:
        st.markdown(
            f'<div class="choice-hint">{CHOICE_HINT}</div>',
            unsafe_allow_html=True,
        )
        return

    render_confession(card.get(f"feedback_{choice}", ""))
    note = card.get("author_note")
    if note:
        st.caption(note)


def render_card_detail(card: dict, scene_idx: int) -> None:
    """展开态：上排原文+纪实双栏，下排心灵解剖（刮擦显影）。"""
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

    render_soul_analysis(analysis, scene_idx)

    if card.get("has_choice"):
        render_choice_block(card, scene_idx)


@st.fragment
def render_scene_card(card: dict, scene_idx: int) -> None:
    """单卡局部刷新：展开/收起不重绘整条时间线。"""

    def _toggle() -> None:
        if st.session_state.opened_cards.get(scene_idx):
            st.session_state.opened_cards.pop(scene_idx, None)
        else:
            st.session_state.opened_cards[scene_idx] = True

    opened = bool(st.session_state.opened_cards.get(scene_idx))
    clock = SCENE_CLOCKS[scene_idx] if scene_idx < len(SCENE_CLOCKS) else "——"
    period = card.get("time", "")
    title = card.get("title", "")
    img_path = get_image_path(card.get("image"))
    offset = DIARY_OFFSETS[scene_idx % len(DIARY_OFFSETS)]
    open_cls = "is-open" if opened else ""

    media_col, body_col = st.columns([1.45, 1], gap="small")

    with media_col:
        st.markdown(
            f'<div class="card-media scene-card-marker {offset} {open_cls}"></div>',
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
        toggle_label = "收起此页" if opened else "翻开此页"
        st.button(
            toggle_label,
            key=f"toggle_card_{scene_idx}",
            width="stretch",
            on_click=_toggle,
        )

    if opened:
        render_card_detail(card, scene_idx)


def render_timeline() -> None:
    for scene_idx, card in enumerate(SCENE_CARDS):
        render_scene_card(card, scene_idx)


def main() -> None:
    st.set_page_config(
        page_title="一个女人一生中的二十四小时",
        page_icon="📖",
        layout="centered",
        initial_sidebar_state="collapsed",
    )
    inject_global_styles()
    init_session_state()
    ensure_placeholder_file()

    render_book_header()
    render_timeline()


if __name__ == "__main__":
    main()
