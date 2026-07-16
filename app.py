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

from book_content import EPILOGUE, SCENE_CARDS

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
# 展廊便签微旋（15 张）
EXHIBIT_TILTS = (
    -3.2, 2.6, -2.1, 3.4, -2.8, 2.2, -3.6, 2.9,
    -1.8, 3.1, -2.4, 2.7, -3.0, 1.9, -2.5,
)

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


def render_soul_analysis(
    analysis: str,
    scene_idx: int,
    *,
    scratch: bool = False,
    light: bool = False,
) -> None:
    """心灵解剖：默认直接显示；仅 scratch=True（节点十五）时刮擦显影。"""
    if not analysis:
        return
    if scratch:
        height = max(220, min(560, 150 + len(analysis) // 2))
        components.html(
            build_soul_scratch_html(analysis, scene_idx, light=light),
            height=height,
            scrolling=False,
        )
        return
    st.markdown(
        f"""
        <div class="soul-analysis">
          <div class="soul-title">心灵解剖 · Deep Soul</div>
          <p class="soul-text">{_escape_multiline(analysis)}</p>
        </div>
        """,
        unsafe_allow_html=True,
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
.soul-analysis {{
  position: relative;
  width: 100%;
  margin: 0.35rem 0 0.85rem;
  background: rgba(140, 43, 43, 0.04);
  border: 1px dotted rgba(140, 43, 43, 0.55);
  border-radius: 2px;
  box-shadow: inset 0 0 0 3px rgba(140, 43, 43, 0.03);
  overflow: hidden;
}}
.soul-analysis .soul-title {{
  padding: 14px 18px 0;
  font-size: 0.72rem;
  letter-spacing: 0.1em;
  color: {MADDER};
  font-family: "Playfair Display", "Noto Serif SC", serif;
}}
.soul-analysis .soul-text {{
  padding: 10px 18px 18px;
  margin: 0;
  font-style: italic;
  font-size: 14.5px;
  line-height: 1.85;
  text-align: justify;
  color: {MADDER};
  opacity: 0.95;
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

/* ---------- 命运双门抉择 ---------- */
.fate-door-stage {{
  margin: 0.75rem 0 0.35rem;
}}
.fate-door-hint {{
  text-align: center;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.72rem;
  letter-spacing: 0.14em;
  color: {SAGE};
  margin: 0 0 0.75rem;
}}
.fate-door-face {{
  position: relative;
  width: min(100%, 440px);
  max-width: 440px;
  aspect-ratio: 2 / 3;
  margin: 0 auto;
  padding: 1.25rem 1.05rem 1.35rem;
  box-sizing: border-box;
  border-radius: 4px 4px 2px 2px;
  border: 1px solid rgba(196, 154, 69, 0.55);
  box-shadow:
    inset 0 0 0 5px rgba(237, 232, 220, 0.55),
    inset 0 0 0 6px rgba(196, 154, 69, 0.28),
    0 10px 22px rgba(44, 36, 22, 0.1);
  text-align: center;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}}
.fate-door-face.mood-warm {{
  background:
    radial-gradient(ellipse 80% 55% at 50% 18%, rgba(196, 154, 69, 0.35), transparent 62%),
    linear-gradient(165deg, #F4EFE3 0%, {IVORY} 45%, #E0D5C2 100%);
}}
.fate-door-face.mood-rain {{
  background:
    linear-gradient(180deg, rgba(83, 98, 87, 0.14), transparent 42%),
    repeating-linear-gradient(
      185deg,
      transparent 0 10px,
      rgba(44, 36, 22, 0.04) 10px 11px
    ),
    linear-gradient(165deg, #E8E4DA 0%, {PARCHMENT} 50%, #D5CFC2 100%);
}}
.fate-door-face .door-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  color: {SAGE};
  margin-bottom: 0.5rem;
}}
.fate-door-face .door-title {{
  display: block;
  font-family: "Noto Serif SC", "Source Han Serif SC", serif;
  font-size: 1.45rem;
  font-weight: 700;
  color: {CARBON};
  letter-spacing: 0.08em;
  margin-bottom: 0.45rem;
}}
.fate-door-face .door-sub {{
  margin: 0 0 0.55rem;
  font-size: 0.88rem;
  line-height: 1.55;
  color: {BROWN};
}}
.fate-door-face .door-voice {{
  margin: 0;
  padding-top: 0.55rem;
  border-top: 1px solid rgba(196, 154, 69, 0.28);
  font-size: 0.82rem;
  font-style: italic;
  line-height: 1.6;
  color: #3A2F22;
  opacity: 0.9;
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
  max-width: 100%;
}}
div[data-testid="column"]:has(.fate-door-face.is-pickable) {{
  display: flex !important;
  flex-direction: column !important;
  align-items: center !important;
}}
.fate-doors-resolved {{
  position: relative;
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 700px;
  margin: 0.5rem 0 1rem;
}}
.fate-doors-resolved .fate-door-face {{
  /* 与选中前 .is-pickable 同为 440×660，禁止因容器变宽而放大 */
  width: 440px;
  max-width: 440px;
  height: 660px;
  aspect-ratio: 2 / 3;
  flex-shrink: 0;
  box-sizing: border-box;
  transition: opacity 0.45s ease;
}}
.fate-doors-resolved .fate-door-face.is-picked {{
  position: relative;
  z-index: 2;
  transform: none;
  animation: doorSettle 0.45s ease both;
}}
.fate-doors-resolved .fate-door-face.is-faded {{
  position: absolute;
  top: 50%;
  transform: translateY(-50%) scale(0.86);
  opacity: 0.22;
  pointer-events: none;
  filter: grayscale(0.25);
  z-index: 1;
}}
.fate-doors-resolved.picked-A .fate-door-face.is-faded {{
  right: 4%;
  left: auto;
}}
.fate-doors-resolved.picked-B .fate-door-face.is-faded {{
  left: 4%;
  right: auto;
}}
@keyframes doorSettle {{
  from {{ opacity: 0.55; }}
  to {{ opacity: 1; }}
}}
.fate-door-face.is-pickable {{
  cursor: pointer;
  transition: border-color 0.25s ease, transform 0.25s ease, box-shadow 0.25s ease;
}}
/* 点选热区：透明按钮叠在门面上（由 render 注入 .st-key-door_* 细则） */

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
/* 选门后：C太太亲口作答（左像右文，同节点二） */
div[data-testid="stHorizontalBlock"]:has(.confession-avatar) {{
  align-items: flex-start !important;
  margin: 0.85rem 0 0.35rem;
}}
div[data-testid="column"]:has(.confession-avatar) {{
  display: flex !important;
  justify-content: center !important;
  align-items: flex-start !important;
  padding-top: 0.35rem !important;
}}
div[data-testid="column"]:has(.confession-dialogue) {{
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
}}
.confession-avatar {{
  width: 280px !important;
  margin: 0 auto !important;
}}
.confession-avatar img {{
  display: block !important;
  width: 280px !important;
  height: 280px !important;
  max-width: 280px !important;
  object-fit: cover !important;
  object-position: center top !important;
  border-radius: 50% !important;
  border: 2px solid rgba(196, 154, 69, 0.55) !important;
  box-shadow:
    0 8px 20px rgba(44, 36, 22, 0.14),
    inset 0 0 0 4px rgba(237, 232, 220, 0.65) !important;
  background: {IVORY} !important;
}}
.confession-avatar .avatar-caption {{
  display: block;
  margin-top: 0.5rem;
  text-align: center;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.7rem;
  letter-spacing: 0.12em;
  color: {SAGE};
}}
.confession-dialogue {{
  animation: confessionIn 0.4s ease;
  padding: 0.15rem 0 0.25rem;
}}
.confession-dialogue .beat-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  color: {SAGE};
  margin-bottom: 0.55rem;
}}
.confession-dialogue .confession-spoken {{
  margin: 0;
  font-size: 0.98rem;
  line-height: 1.85;
  color: #3A2F22;
  font-style: italic;
}}
@media (max-width: 720px) {{
  .confession-avatar {{
    width: 200px !important;
  }}
  .confession-avatar img {{
    width: 200px !important;
    height: 200px !important;
    max-width: 200px !important;
  }}
  .confession-dialogue {{
    text-align: center;
  }}
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
/* 节点二：C太太头像对话式听者确认（右文无独立卡片） */
div[data-testid="stHorizontalBlock"]:has(.whisper-avatar) {{
  align-items: center !important;
}}
div[data-testid="column"]:has(.whisper-avatar) {{
  display: flex !important;
  justify-content: center !important;
  align-items: center !important;
}}
div[data-testid="column"]:has(.whisper-copy) {{
  display: flex !important;
  flex-direction: column !important;
  justify-content: center !important;
}}
.whisper-avatar {{
  width: 280px !important;
  margin: 0.25rem auto !important;
}}
.whisper-avatar img {{
  display: block !important;
  width: 280px !important;
  height: 280px !important;
  max-width: 280px !important;
  object-fit: cover !important;
  object-position: center top !important;
  border-radius: 50% !important;
  border: 2px solid rgba(196, 154, 69, 0.55) !important;
  box-shadow:
    0 8px 20px rgba(44, 36, 22, 0.14),
    inset 0 0 0 4px rgba(237, 232, 220, 0.65) !important;
  background: {IVORY} !important;
}}
.whisper-avatar .avatar-caption {{
  display: block;
  margin-top: 0.5rem;
  text-align: center;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.7rem;
  letter-spacing: 0.12em;
  color: {SAGE};
}}
.whisper-copy {{
  padding-top: 0 !important;
  margin-bottom: 0.65rem;
}}
.whisper-copy .beat-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.72rem;
  letter-spacing: 0.16em;
  color: {SAGE};
  margin-bottom: 0.5rem;
}}
.whisper-copy .whisper-prompt {{
  margin: 0;
  font-size: 0.98rem;
  line-height: 1.75;
  color: #3A2F22;
}}
/* 按钮与提问文字左对齐，宽度随文字 */
.st-key-beat_whisper_1,
div[class*="st-key-beat_whisper_"] {{
  width: fit-content !important;
  max-width: 100% !important;
}}
.st-key-beat_whisper_1 div[data-testid="stButton"],
div[class*="st-key-beat_whisper_"] div[data-testid="stButton"],
.st-key-beat_whisper_1 .stButton,
div[class*="st-key-beat_whisper_"] .stButton {{
  width: fit-content !important;
}}
.st-key-beat_whisper_1 button,
div[class*="st-key-beat_whisper_"] button {{
  width: auto !important;
  min-width: unset !important;
  padding-left: 1.15rem !important;
  padding-right: 1.15rem !important;
}}
.whisper-echo {{
  margin: 0.85rem 0 1rem;
  padding-left: calc(40% + 0.6rem);
  font-size: 0.92rem;
  line-height: 1.75;
  font-style: italic;
  color: {BROWN};
}}
@media (max-width: 720px) {{
  .whisper-avatar {{
    width: 200px !important;
  }}
  .whisper-avatar img {{
    width: 200px !important;
    height: 200px !important;
    max-width: 200px !important;
  }}
  .whisper-copy {{
    text-align: center;
  }}
  .st-key-beat_whisper_1,
  div[class*="st-key-beat_whisper_"] {{
    margin-left: auto !important;
    margin-right: auto !important;
  }}
  .whisper-echo {{
    padding-left: 0;
    text-align: center;
  }}
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
  display: block;
  width: fit-content;
  max-width: min(42em, 100%);
  height: auto;
  box-sizing: border-box;
  margin: 1rem auto 0.5rem;
  padding: 1rem 1.25rem;
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
  white-space: normal;
  overflow-wrap: anywhere;
  word-break: break-word;
}}
.fate-echo .echo-you {{
  margin: 0 0 0.55rem;
  padding: 0;
  border: none;
  font-style: normal;
  font-size: 0.92rem;
  color: {BROWN};
}}
.fate-echo .echo-note {{
  margin-top: 0.55rem;
  padding-top: 0.55rem;
  border-top: 1px solid rgba(140, 43, 43, 0.18);
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

/* ---------- 画页展廊（双排横向滑动） ---------- */
.exhibit-wall {{
  max-width: 1100px;
  margin: 0 auto;
  animation: exhibitIn 0.35s ease;
}}
.exhibit-head {{
  text-align: center;
  margin: 0.15rem 0 0.45rem;
}}
.exhibit-head .exhibit-kicker {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.72rem;
  letter-spacing: 0.18em;
  color: {SAGE};
  margin-bottom: 0.25rem;
}}
.exhibit-head .exhibit-hint {{
  margin: 0;
  font-size: 0.78rem;
  letter-spacing: 0.06em;
  color: {BROWN};
  opacity: 0.78;
}}
.exhibit-rail {{
  overflow-x: auto;
  overflow-y: hidden;
  width: 100%;
  max-height: 520px;
  padding-bottom: 0.35rem;
  -webkit-overflow-scrolling: touch;
  scrollbar-color: rgba(196, 154, 69, 0.55) transparent;
  background: {CREAM};
  border: 1px solid rgba(196, 154, 69, 0.28);
  border-radius: 2px;
  box-shadow:
    inset 0 0 40px rgba(107, 74, 48, 0.04),
    0 10px 24px rgba(44, 36, 22, 0.08);
}}
.exhibit-rail::-webkit-scrollbar {{
  height: 8px;
}}
.exhibit-rail::-webkit-scrollbar-thumb {{
  background: rgba(196, 154, 69, 0.45);
  border-radius: 4px;
}}
.exhibit-board {{
  display: block;
  width: max-content;
  min-width: 100%;
  box-sizing: border-box;
  background: {CREAM};
  padding: 1.1rem 0.85rem 1.25rem;
}}
.exhibit-track {{
  display: flex;
  flex-direction: column;
  gap: 1.35rem;
  width: max-content;
  min-width: 100%;
  padding: 0.35rem 1.5rem 0.2rem;
  box-sizing: border-box;
  background: {CREAM};
}}
.exhibit-row {{
  display: flex;
  flex-direction: row;
  flex-wrap: nowrap;
  gap: 1.35rem;
  align-items: flex-start;
}}
.exhibit-row-even {{
  padding-left: 5.5rem;
}}
.exhibit-note {{
  position: relative;
  display: block;
  width: 100%;
  box-sizing: border-box;
  padding: 0.85rem 0.55rem 0.6rem;
  text-decoration: none !important;
  color: inherit !important;
  background: {IVORY};
  border: 1px solid rgba(196, 154, 69, 0.4);
  border-radius: 2px;
  box-shadow:
    0 6px 16px rgba(44, 36, 22, 0.12),
    inset 0 0 0 1px rgba(255, 255, 255, 0.35);
  cursor: pointer;
  transition: box-shadow 0.25s ease, border-color 0.25s ease;
}}
.exhibit-note::before {{
  content: "";
  position: absolute;
  top: -7px;
  left: 50%;
  width: 12px;
  height: 12px;
  margin-left: -6px;
  border-radius: 50%;
  background:
    radial-gradient(circle at 35% 30%, #b84a4a, {MADDER} 55%, #5c1a1a);
  box-shadow: 0 1px 3px rgba(44, 36, 22, 0.35);
  z-index: 2;
}}
.exhibit-note img {{
  display: block;
  width: 100%;
  height: 92px;
  object-fit: cover;
  border-radius: 1px;
  border: 1px solid rgba(168, 130, 72, 0.35);
  background: {PARCHMENT};
  margin-bottom: 0.4rem;
}}
.exhibit-note .note-clock {{
  display: block;
  font-family: "Playfair Display", Georgia, serif;
  font-size: 0.58rem;
  letter-spacing: 0.14em;
  color: {GOLD_BORDER};
  margin-bottom: 0.15rem;
}}
.exhibit-note .note-kicker {{
  display: block;
  font-size: 0.62rem;
  letter-spacing: 0.1em;
  color: {SAGE};
  margin-bottom: 0.1rem;
}}
.exhibit-note .note-title {{
  display: block;
  font-family: "Noto Serif SC", "Source Han Serif SC", serif;
  font-size: 0.78rem;
  font-weight: 700;
  line-height: 1.3;
  color: {CARBON};
  letter-spacing: 0.02em;
}}
/* Streamlit 展廊：容器横滑，两排同步 */
div[data-testid="stVerticalBlock"]:has(.exhibit-rail-host) {{
  overflow-x: auto !important;
  overflow-y: visible !important;
  max-height: none !important;
  background: {CREAM} !important;
  border: 1px solid rgba(196, 154, 69, 0.28);
  border-radius: 2px;
  box-shadow:
    inset 0 0 40px rgba(107, 74, 48, 0.04),
    0 10px 24px rgba(44, 36, 22, 0.08);
  padding: 1.1rem 0.75rem 1.25rem !important;
  -webkit-overflow-scrolling: touch;
  scrollbar-color: rgba(196, 154, 69, 0.55) transparent;
}}
div[data-testid="stVerticalBlock"]:has(.exhibit-rail-host) > div[data-testid="stHorizontalBlock"] {{
  flex-wrap: nowrap !important;
  width: max-content !important;
  min-width: 1520px !important;
  gap: 1.15rem !important;
  margin-bottom: 0.85rem !important;
}}
div[data-testid="stVerticalBlock"]:has(.exhibit-rail-host) > div[data-testid="stHorizontalBlock"]:has(.exhibit-row-even) {{
  padding-left: 4.5rem !important;
  margin-bottom: 0.25rem !important;
}}
div[data-testid="stVerticalBlock"]:has(.exhibit-rail-host) [data-testid="column"] {{
  min-width: 168px !important;
  width: 168px !important;
  flex: 0 0 168px !important;
}}
/* 便签热区：透明按钮叠在门面上 */
div[class*="st-key-exhibit_"] {{
  margin-top: -210px !important;
  margin-bottom: 0 !important;
  height: 210px !important;
  max-height: 210px !important;
  position: relative !important;
  z-index: 8 !important;
  overflow: hidden !important;
}}
div[class*="st-key-exhibit_"] div[data-testid="stButton"],
div[class*="st-key-exhibit_"] .stButton {{
  height: 210px !important;
  margin: 0 !important;
}}
div[class*="st-key-exhibit_"] button {{
  opacity: 0 !important;
  width: 100% !important;
  height: 210px !important;
  min-height: 210px !important;
  cursor: pointer !important;
  border: none !important;
  background: transparent !important;
  background-image: none !important;
  box-shadow: none !important;
  color: transparent !important;
  padding: 0 !important;
}}
div[data-testid="column"]:has([class*="st-key-exhibit_"]:hover) .exhibit-note {{
  border-color: rgba(196, 154, 69, 0.85) !important;
  box-shadow:
    0 10px 22px rgba(44, 36, 22, 0.16),
    inset 0 0 0 1px rgba(255, 255, 255, 0.4) !important;
}}
.reading-back-toc {{
  display: flex;
  justify-content: center;
  margin: 0 0 0.65rem;
}}
@keyframes exhibitIn {{
  from {{ opacity: 0.45; transform: translateY(8px); }}
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
/* 「回到目录」：窄铭牌、居中、精致一点 */
.st-key-btn_back_to_gallery {{
  display: flex !important;
  justify-content: center !important;
  width: 100% !important;
  margin: 0.15rem 0 0.35rem !important;
}}
.st-key-btn_back_to_gallery div[data-testid="stButton"],
.st-key-btn_back_to_gallery .stButton {{
  width: fit-content !important;
  margin: 0 auto !important;
}}
.st-key-btn_back_to_gallery button,
.st-key-btn_back_to_gallery button[kind="secondary"],
.st-key-btn_back_to_gallery button[kind="primary"] {{
  width: auto !important;
  min-width: unset !important;
  min-height: 2.05rem !important;
  height: auto !important;
  padding: 0.42rem 1.4rem !important;
  border-radius: 2px !important;
  border: 1px solid rgba(196, 154, 69, 0.7) !important;
  background-color: {IVORY} !important;
  background-image:
    linear-gradient(180deg, rgba(255,255,255,0.45) 0%, transparent 48%),
    linear-gradient(165deg, #F3EEE3 0%, {IVORY} 55%, #E4DCCE 100%) !important;
  color: {BROWN} !important;
  font-family: "Playfair Display", Georgia, "Noto Serif SC", serif !important;
  font-size: 0.78rem !important;
  font-weight: 500 !important;
  letter-spacing: 0.2em !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.55),
    inset 0 0 0 1px rgba(196, 154, 69, 0.18),
    0 2px 8px rgba(44, 36, 22, 0.08) !important;
  transition: border-color 0.3s ease, box-shadow 0.3s ease, color 0.3s ease, transform 0.3s ease !important;
}}
.st-key-btn_back_to_gallery button:hover,
.st-key-btn_back_to_gallery button[kind="secondary"]:hover,
.st-key-btn_back_to_gallery button[kind="primary"]:hover {{
  color: {CARBON} !important;
  border-color: rgba(196, 154, 69, 0.95) !important;
  background-color: rgba(237, 232, 220, 0.98) !important;
  background-image:
    linear-gradient(180deg, rgba(255,255,255,0.5) 0%, transparent 50%),
    linear-gradient(165deg, #F7F2E8 0%, {IVORY} 60%, #E8DFD0 100%) !important;
  box-shadow:
    inset 0 1px 0 rgba(255, 255, 255, 0.65),
    inset 0 0 0 1px rgba(196, 154, 69, 0.28),
    0 3px 12px rgba(44, 36, 22, 0.1),
    0 0 0 1px rgba(196, 154, 69, 0.2) !important;
  transform: translateY(-1px) !important;
  filter: none !important;
}}
.reading-nav-hint {{
  display: none;
}}
/* 左右翻页：视口两侧固定，不进内容栏 */
.st-key-flip_prev,
.st-key-flip_next {{
  position: fixed !important;
  top: 50% !important;
  transform: translateY(-50%) !important;
  z-index: 10000 !important;
  width: 44px !important;
  min-width: 44px !important;
  max-width: 44px !important;
  height: 0 !important;
  margin: 0 !important;
  padding: 0 !important;
  overflow: visible !important;
}}
.st-key-flip_prev {{
  left: 10px !important;
  right: auto !important;
}}
.st-key-flip_next {{
  right: 10px !important;
  left: auto !important;
}}
.st-key-flip_prev div[data-testid="stButton"],
.st-key-flip_next div[data-testid="stButton"],
.st-key-flip_prev .stButton,
.st-key-flip_next .stButton {{
  margin: 0 !important;
  width: 44px !important;
}}
.st-key-flip_prev button,
.st-key-flip_next button,
.st-key-flip_prev button[kind="primary"],
.st-key-flip_prev button[kind="secondary"],
.st-key-flip_next button[kind="primary"],
.st-key-flip_next button[kind="secondary"] {{
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
.st-key-flip_prev button:hover,
.st-key-flip_next button:hover {{
  background-color: rgba(196, 154, 69, 0.55) !important;
  color: {CARBON} !important;
  transform: none !important;
}}
.st-key-flip_prev button:disabled,
.st-key-flip_next button:disabled {{
  opacity: 0.4 !important;
}}
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
  left: 10px !important;
  right: auto !important;
}}
button.ebook-nav-pinned-right,
div[data-testid="stButton"] > button.ebook-nav-pinned-right {{
  right: 10px !important;
  left: auto !important;
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
  .st-key-flip_prev,
  button.ebook-nav-pinned-left,
  div[data-testid="stButton"] > button.ebook-nav-pinned-left {{
    left: 6px !important;
  }}
  .st-key-flip_next,
  button.ebook-nav-pinned-right,
  div[data-testid="stButton"] > button.ebook-nav-pinned-right {{
    right: 6px !important;
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
    """封面/画页/尾声与阅读共用画布米色背景，避免书桌色割裂。"""
    if view == "open_book":
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
            section.main,
            [data-testid="stMain"] {{
              overflow-x: hidden !important;
              overflow-y: auto !important;
            }}
            .main .block-container {{
              padding-top: 0.25rem !important;
              padding-bottom: 1rem !important;
              padding-left: 1.25rem !important;
              padding-right: 1.25rem !important;
              max-width: 1120px;
            }}
            .main .block-container::before {{
              display: none !important;
            }}
            .book-header {{
              margin: 0.05rem 0 0.35rem !important;
            }}
            .book-title {{
              color: {CARBON} !important;
              font-size: 18px !important;
              font-weight: 700 !important;
              letter-spacing: 0.08em !important;
              opacity: 1;
            }}
            .brush-underline {{
              display: block !important;
              width: min(360px, 80%) !important;
              margin: 6px auto 0 !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
    elif view in ("cover", "coda"):
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
              padding-left: 4rem !important;
              padding-right: 4rem !important;
              max-width: 980px;
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
            /* 翻页钮钉在视口左右缘，不随内容横移 */
            .st-key-flip_prev {{
              left: 10px !important;
              right: auto !important;
            }}
            .st-key-flip_next {{
              right: 10px !important;
              left: auto !important;
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


def render_confession(text: str, *, avatar: str | None = None) -> None:
    """即时展示独白；有 avatar 时左像右文，如 C 太太亲口作答。"""
    if not text:
        return
    body = _escape_multiline(text)
    if not avatar:
        st.markdown(
            f'<div class="confession-box">{body}</div>',
            unsafe_allow_html=True,
        )
        return

    avatar_src = _thumb_data_uri(avatar, 560)
    left_c, right_c = st.columns([1.05, 1.95], gap="medium")
    with left_c:
        st.markdown(
            f"""
            <div class="confession-avatar">
              <img src="{avatar_src}" alt="C太太"/>
              <span class="avatar-caption">C 太太</span>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right_c:
        st.markdown(
            f"""
            <div class="confession-dialogue">
              <span class="beat-kicker">C 太太 · 亲口作答</span>
              <div class="confession-spoken">{body}</div>
            </div>
            """,
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


def _exhibit_note_parts(card: dict, idx: int) -> tuple[str, str]:
    """拆出便签上的节点号与短标题。"""
    raw = (card.get("title") or f"节点{idx + 1}").strip()
    for sep in ("·", "：", ":"):
        if sep in raw:
            left, right = raw.split(sep, 1)
            return left.strip(), right.strip()
    return f"节点{idx + 1}", raw


def _exhibit_note_html(idx: int) -> str:
    """便签外观（非链接；点击由透明 Streamlit 按钮触发 goto_page）。"""
    card = SCENE_CARDS[idx]
    kicker, title = _exhibit_note_parts(card, idx)
    clock = SCENE_CLOCKS[idx] if idx < len(SCENE_CLOCKS) else "——"
    src = _thumb_data_uri(card.get("image"), 240)
    tilt = EXHIBIT_TILTS[idx % len(EXHIBIT_TILTS)]
    nudge = (-6, 4, -3, 7, -5, 3, -8, 5)[idx % 8]
    return (
        f'<div class="exhibit-note" '
        f'style="transform:rotate({tilt}deg) translateY({nudge}px);">'
        f'<img src="{src}" alt="{html.escape(kicker)}"/>'
        f'<span class="note-clock">{html.escape(clock)}</span>'
        f'<span class="note-kicker">{html.escape(kicker)}</span>'
        f'<span class="note-title">{html.escape(title)}</span>'
        f"</div>"
    )


def _render_exhibit_row(indices: list[int], *, even: bool = False) -> None:
    mark = "exhibit-row-even" if even else "exhibit-row-odd"
    st.markdown(f'<span class="{mark}"></span>', unsafe_allow_html=True)
    cols = st.columns(len(indices), gap="medium")
    for col, idx in zip(cols, indices):
        with col:
            st.markdown(_exhibit_note_html(idx), unsafe_allow_html=True)
            st.button(
                f"进入节点{idx + 1}",
                key=f"exhibit_{idx}",
                width="stretch",
                on_click=goto_page,
                args=(idx,),
            )


def render_open_book() -> None:
    """画页展廊：奇偶双排便签，横向滑动；点便签会话内进入对应节点。"""
    st.markdown(
        """
        <div class="exhibit-wall">
          <div class="exhibit-head">
            <span class="exhibit-kicker">GALLERY · 二十四小时展厅</span>
            <p class="exhibit-hint">点按便签进入该时辰</p>
          </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    back_l, back_m, back_r = st.columns([1.2, 0.8, 1.2])
    with back_m:
        st.button("返回封面", key="btn_back_cover", width="stretch", on_click=go_cover)

    with st.container():
        st.markdown(
            '<span class="exhibit-rail-host"></span>',
            unsafe_allow_html=True,
        )
        _render_exhibit_row(list(range(0, TOTAL_PAGES, 2)), even=False)
        _render_exhibit_row(list(range(1, TOTAL_PAGES, 2)), even=True)


def render_light_beat(beat: dict, scene_idx: int) -> None:
    """每隔数节点的轻交互：批注 / 对照 / 独白确认 / 时辰推进。"""
    if not beat:
        return
    kind = beat.get("type", "annotation")
    kicker = html.escape(beat.get("kicker", "节拍"))

    if kind == "whisper":
        prompt = html.escape(beat.get("prompt", ""))
        kicker_text = html.escape(beat.get("kicker", "听者 · 一句确认"))
        confirmed = bool(st.session_state.beats_confirmed.get(scene_idx))
        label = beat.get("confirm_label", "我愿意倾听")
        avatar_ref = beat.get("avatar")

        if avatar_ref:
            avatar_src = _thumb_data_uri(avatar_ref, 560)
            left_c, right_c = st.columns([1.05, 1.95], gap="medium")
            with left_c:
                st.markdown(
                    f"""
                    <div class="whisper-avatar">
                      <img src="{avatar_src}" alt="C太太"/>
                      <span class="avatar-caption">C 太太</span>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            with right_c:
                st.markdown(
                    f"""
                    <div class="whisper-copy">
                      <span class="beat-kicker">{kicker_text}</span>
                      <p class="whisper-prompt">{prompt}</p>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
                if st.button(
                    label if not confirmed else f"✓ {label}",
                    key=f"beat_whisper_{scene_idx}",
                    width="content",
                    disabled=confirmed,
                ):
                    st.session_state.beats_confirmed[scene_idx] = True
                    st.rerun()
        else:
            st.markdown(
                f"""
                <div class="beat-panel">
                  <span class="beat-kicker">{kicker_text}</span>
                  <p>{prompt}</p>
                </div>
                """,
                unsafe_allow_html=True,
            )
            if st.button(
                label if not confirmed else f"✓ {label}",
                key=f"beat_whisper_{scene_idx}",
                width="stretch",
                disabled=confirmed,
            ):
                st.session_state.beats_confirmed[scene_idx] = True
                st.rerun()

        if confirmed and beat.get("echo"):
            echo = html.escape(beat["echo"])
            if avatar_ref:
                st.markdown(
                    f'<p class="whisper-echo">{echo}</p>',
                    unsafe_allow_html=True,
                )
            else:
                st.markdown(
                    f'<div class="beat-panel"><p>{echo}</p></div>',
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


def _door_face_html(
    door: dict,
    voice: str = "",
    *,
    picked: bool = False,
    faded: bool = False,
    pickable: bool = False,
) -> str:
    """紧凑单行 HTML，避免 Streamlit markdown 拆坏嵌套标签导致泄漏 </div>。"""
    mood = html.escape(door.get("mood", "warm"))
    kicker = html.escape(door.get("kicker", ""))
    title = html.escape(door.get("title", ""))
    subtitle = html.escape(door.get("subtitle", ""))
    voice_html = (
        f'<p class="door-voice">{html.escape(voice)}</p>' if voice else ""
    )
    state = "is-picked" if picked else ("is-faded" if faded else "")
    if pickable:
        state = f"{state} is-pickable".strip()
    return (
        f'<div class="fate-door-face mood-{mood} {state}">'
        f'<span class="door-kicker">{kicker}</span>'
        f'<span class="door-title">{title}</span>'
        f'<p class="door-sub">{subtitle}</p>'
        f"{voice_html}"
        f"</div>"
    )


def render_door_choice_block(card: dict, scene_idx: int) -> None:
    """两扇门抉择：门面可视，透明按钮叠热区；选定后淡化另一扇并居中，再出独白与命运回响。"""
    doors = card.get("door_choice") or {}
    choices = card.get("choices") or {}
    voices = card.get("reader_voice") or {}
    door_a = doors.get("A") or {"title": "A", "subtitle": "", "mood": "warm", "kicker": ""}
    door_b = doors.get("B") or {"title": "B", "subtitle": "", "mood": "rain", "kicker": ""}

    prompt = card.get("choice_prompt", "")
    if prompt:
        st.markdown(
            f'<p class="choice-prompt">{html.escape(prompt)}</p>',
            unsafe_allow_html=True,
        )

    choice = st.session_state.choices.get(scene_idx)

    if not choice:
        key_a = f"door_{scene_idx}_A"
        key_b = f"door_{scene_idx}_B"
        # 440×660（2:3，相对原 220×330 放大至 200%）
        door_w = 440
        door_h = 660
        st.markdown(
            f"""
            <style>
            div[data-testid="stHorizontalBlock"]:has(.st-key-{key_a}) {{
              justify-content: center !important;
              gap: 0.85rem !important;
              max-width: 1120px !important;
              margin-left: auto !important;
              margin-right: auto !important;
            }}
            .st-key-{key_a},
            .st-key-{key_b} {{
              margin-top: -{door_h}px !important;
              margin-bottom: 0 !important;
              height: {door_h}px !important;
              max-height: {door_h}px !important;
              width: {door_w}px !important;
              max-width: {door_w}px !important;
              min-width: {door_w}px !important;
              position: relative !important;
              z-index: 8 !important;
              overflow: hidden !important;
              margin-left: auto !important;
              margin-right: auto !important;
              flex-shrink: 0 !important;
            }}
            .st-key-{key_a} div[data-testid="stButton"],
            .st-key-{key_b} div[data-testid="stButton"],
            .st-key-{key_a} .stButton,
            .st-key-{key_b} .stButton {{
              height: {door_h}px !important;
              margin: 0 !important;
              width: 100% !important;
            }}
            .st-key-{key_a} button,
            .st-key-{key_b} button {{
              opacity: 0 !important;
              width: 100% !important;
              height: {door_h}px !important;
              min-height: {door_h}px !important;
              max-height: {door_h}px !important;
              cursor: pointer !important;
              border: none !important;
              background: transparent !important;
              background-image: none !important;
              box-shadow: none !important;
              color: transparent !important;
              padding: 0 !important;
            }}
            .fate-door-face.is-pickable {{
              width: {door_w}px !important;
              max-width: {door_w}px !important;
              min-width: {door_w}px !important;
              height: {door_h}px !important;
              aspect-ratio: 2 / 3 !important;
              box-sizing: border-box !important;
              margin: 0 auto 0.35rem !important;
              overflow: hidden !important;
              flex-shrink: 0 !important;
              transform: none !important;
            }}
            div[data-testid="column"]:has(.st-key-{key_a}:hover) .fate-door-face.is-pickable,
            div[data-testid="column"]:has(.st-key-{key_b}:hover) .fate-door-face.is-pickable {{
              border-color: rgba(196, 154, 69, 0.92) !important;
              transform: translateY(-2px) !important;
              box-shadow:
                inset 0 0 0 5px rgba(237, 232, 220, 0.55),
                inset 0 0 0 6px rgba(196, 154, 69, 0.4),
                0 12px 26px rgba(44, 36, 22, 0.14) !important;
            }}
            </style>
            """,
            unsafe_allow_html=True,
        )
        st.markdown(
            '<p class="fate-door-hint">FATE DOORS · 点选一扇门</p>',
            unsafe_allow_html=True,
        )
        pad_l, col_a, col_b, pad_r = st.columns(
            [0.2, 1.5, 1.5, 0.2], gap="small"
        )
        with col_a:
            st.markdown(
                _door_face_html(door_a, voices.get("A", ""), pickable=True),
                unsafe_allow_html=True,
            )
            if st.button(
                f"推开 · {door_a.get('title', 'A')}",
                key=key_a,
                width="stretch",
            ):
                st.session_state.choices[scene_idx] = "A"
                st.rerun()
        with col_b:
            st.markdown(
                _door_face_html(door_b, voices.get("B", ""), pickable=True),
                unsafe_allow_html=True,
            )
            if st.button(
                f"推开 · {door_b.get('title', 'B')}",
                key=key_b,
                width="stretch",
            ):
                st.session_state.choices[scene_idx] = "B"
                st.rerun()
        st.markdown(
            f'<div class="choice-hint">{CHOICE_HINT}</div>',
            unsafe_allow_html=True,
        )
        return

    resolved = (
        f'<div class="fate-doors-resolved picked-{html.escape(str(choice))}">'
        f"{_door_face_html(door_a, picked=(choice == 'A'), faded=(choice != 'A'))}"
        f"{_door_face_html(door_b, picked=(choice == 'B'), faded=(choice != 'B'))}"
        f"</div>"
    )
    st.markdown(resolved, unsafe_allow_html=True)

    render_confession(
        card.get(f"feedback_{choice}", ""),
        avatar=card.get("feedback_avatar"),
    )

    picked_door = doors.get(choice) or {}
    picked_label = picked_door.get("title") or choices.get(choice, choice)
    note = card.get("author_note") or ""
    note_html = (
        f'<p class="echo-note">{html.escape(note)}</p>' if note else ""
    )
    echo = (
        f'<div class="fate-echo">'
        f'<span class="echo-kicker">命运回响 · 你以为自己推开了</span>'
        f'<p class="echo-you">你推开了 <em>{html.escape(str(choice))} · {html.escape(picked_label)}</em></p>'
        f"{note_html}"
        f"</div>"
    )
    st.markdown(echo, unsafe_allow_html=True)


def render_choice_block(card: dict, scene_idx: int) -> None:
    """伪分支抉择：有 door_choice 时走双门；否则保留按钮。"""
    if card.get("door_choice"):
        render_door_choice_block(card, scene_idx)
        return

    prompt = card.get("choice_prompt", "")
    if prompt:
        st.markdown(
            f'<p class="choice-prompt">{html.escape(prompt)}</p>',
            unsafe_allow_html=True,
        )

    choices = card.get("choices") or {"A": "选择理智", "B": "选择狂热"}
    voices = card.get("reader_voice") or {}
    already_chosen = st.session_state.choices.get(scene_idx) is not None

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
    note_html = (
        f'<p class="echo-note">{html.escape(note)}</p>' if note else ""
    )
    st.markdown(
        f"""
        <div class="fate-echo">
          <span class="echo-kicker">命运回响 · 你以为自己选择了</span>
          <p class="echo-you">你选了 <em>{html.escape(choice)} · {html.escape(picked_label)}</em></p>
          {note_html}
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
        # 仅节点十五保留滑动刮擦显影；其余节点直接显示
        render_soul_analysis(
            analysis,
            scene_idx,
            scratch=(scene_idx == TOTAL_PAGES - 1),
            light=False,
        )
    elif soul_gated:
        st.caption("请先确认「我愿意倾听」，再进入心灵解剖。")

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
    """钉住翻页按钮到视口左右缘，并监听 ← / →。"""
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
  var FLAG = "__ebookNavBridgeV3";
  if (doc[FLAG] && doc[FLAG].handler) {{
    doc.removeEventListener("keydown", doc[FLAG].handler, true);
  }}
  if (doc[FLAG] && doc[FLAG].timer) {{
    clearInterval(doc[FLAG].timer);
  }}

  function findBtn(keyClass) {{
    var wrap = doc.querySelector("." + keyClass);
    return wrap ? wrap.querySelector("button") : null;
  }}

  function pinOne(btn, side) {{
    if (!btn) return false;
    btn.classList.add("ebook-nav-pinned", side === "left" ? "ebook-nav-pinned-left" : "ebook-nav-pinned-right");
    btn.style.setProperty("position", "fixed", "important");
    btn.style.setProperty("top", "50%", "important");
    btn.style.setProperty("transform", "translateY(-50%)", "important");
    btn.style.setProperty("z-index", "10000", "important");
    btn.style.setProperty("width", "44px", "important");
    btn.style.setProperty("height", "44px", "important");
    if (side === "left") {{
      btn.style.setProperty("left", "10px", "important");
      btn.style.setProperty("right", "auto", "important");
    }} else {{
      btn.style.setProperty("right", "10px", "important");
      btn.style.setProperty("left", "auto", "important");
    }}
    var wrap = btn.closest("[class*='st-key-flip_']");
    if (wrap) {{
      wrap.style.setProperty("position", "fixed", "important");
      wrap.style.setProperty("top", "50%", "important");
      wrap.style.setProperty("transform", "translateY(-50%)", "important");
      wrap.style.setProperty("z-index", "10000", "important");
      if (side === "left") {{
        wrap.style.setProperty("left", "10px", "important");
        wrap.style.setProperty("right", "auto", "important");
      }} else {{
        wrap.style.setProperty("right", "10px", "important");
        wrap.style.setProperty("left", "auto", "important");
      }}
    }}
    return true;
  }}

  function pinButtons() {{
    var prev = findBtn("st-key-flip_prev");
    var next = findBtn("st-key-flip_next");
    var okPrev = pinOne(prev, "left");
    var okNext = pinOne(next, "right");
    return okPrev && okNext;
  }}

  function triggerNav(dir) {{
    if (dir === "next" && !canNext) return;
    try {{
      var url = new URL(win.location.href);
      url.searchParams.set("ebook_nav", dir);
      win.location.href = url.toString();
      return;
    }} catch (e1) {{}}
    var btn = findBtn(dir === "prev" ? "st-key-flip_prev" : "st-key-flip_next");
    if (btn && !btn.disabled) btn.click();
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
    """单节点阅读：‹ › 钉在视口左右缘；支持键盘翻页。"""
    consume_ebook_nav_param()

    ss = st.session_state
    page = ss.page
    card = SCENE_CARDS[page]
    need_choice = bool(card.get("has_choice")) and page not in ss.choices

    toc_l, toc_m, toc_r = st.columns([1.35, 1, 1.35])
    with toc_m:
        st.button(
            "回到目录",
            key="btn_back_to_gallery",
            width="content",
            on_click=go_open_book,
            help="返回二十四小时展厅",
        )

    st.markdown(
        f'<p class="reading-meta">纸页 {page + 1} / {TOTAL_PAGES}'
        f'<span style="opacity:0.55;font-size:0.85em;">'
        f' · 点击左侧边栏或键盘 ← → 可翻页</span></p>',
        unsafe_allow_html=True,
    )

    st.markdown('<span class="reading-mid-mark"></span>', unsafe_allow_html=True)
    render_scene_card(card, page)
    if need_choice:
        st.markdown(
            '<p class="flip-choice-hint">请先做出抉择，再点击右侧 › 或按 → 继续</p>',
            unsafe_allow_html=True,
        )

    # 翻页钮独立渲染，CSS/JS 钉到视口左右缘，避免进内容栏后横移
    st.button(
        "<",
        key="flip_prev",
        on_click=go_prev_page,
        help="上一节点（←）" if page > 0 else "返回画页（←）",
    )
    next_help = (
        "请先做出抉择"
        if need_choice
        else ("合上这一日（→）" if page >= TOTAL_PAGES - 1 else "下一节点（→）")
    )
    st.button(
        ">",
        key="flip_next",
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
        st.button("回到目录", width="stretch", on_click=go_open_book)
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
