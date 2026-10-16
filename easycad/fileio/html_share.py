"""「HTML로 공유」(§8 항목46, 2026-10-16) — 도면을 브라우저로 여는 파일 하나로. 받는 사람은 앱이 없어도 된다.

파일 하나에 다 들어 있다(외부 글꼴·스크립트 없음 — 사내망·인터넷 없이도 열림): 레이어마다 따로 그린 SVG를 겹친 도면 +
확대·이동(휠·끌기·손가락·＋/−/맞춤) + 레이어 켜고 끄기 + 상자에 올리면 강조·누르면 그 상자로 확대.
상자마다 위치·글자(`shapes`)를 함께 넣어 둔다 — 다음 「설명 페이지」(§8 항목47)가 "이 단계는 이 상자"를 강조하는 바탕.

그리기 규칙은 인쇄와 같다(`pdf_export`): 흰 종이·흰 잉크→검정, 선택 표시 없음. 레이어 SVG는 배경 없이 그려 겹친다.
"""
from __future__ import annotations

import html
import json
import re
import time

from PyQt6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, QSize, Qt
from PyQt6.QtGui import QBrush, QPainter
from PyQt6.QtSvg import QSvgGenerator

from easycad.fileio.pdf_export import _restore_swapped_colors, _swap_white_to_black_for_print
from easycad.fileio.safe_write import write_via_temp

PAD = 24.0


def _svg_inner(data: bytes) -> str:
    """QSvgGenerator 결과에서 바깥 `<svg>`·XML 머리를 걷고 안쪽만 — 한 `<svg>` 안에 레이어 `<g>`로 겹치려고."""
    text = data.decode("utf-8", errors="replace")
    m = re.search(r"<svg\b[^>]*>(.*)</svg>", text, re.S)
    inner = m.group(1) if m else text
    inner = re.sub(r"<title>.*?</title>|<desc>.*?</desc>", "", inner, flags=re.S)
    return inner.strip()


def render_layers(scene, groups, source: QRectF) -> list[str]:
    """`groups` = [(레이어 이름, 최상위 아이템 목록)] → 레이어마다 SVG 안쪽 문자열. 그리는 동안만 다른 레이어를 숨기고
    선택·배경·흰 잉크를 인쇄 규칙으로 바꿨다가 전부 되돌린다."""
    saved_sel = list(scene.selectedItems())
    scene.clearSelection()
    saved_bg = scene.backgroundBrush()
    scene.setBackgroundBrush(QBrush(Qt.BrushStyle.NoBrush))
    swapped = _swap_white_to_black_for_print(scene)
    tops = [it for it in scene.items() if it.parentItem() is None]
    was_visible = {it: it.isVisible() for it in tops}
    w, h = max(1, round(source.width())), max(1, round(source.height()))
    out = []
    try:
        for _name, items in groups:
            keep = set(items)
            for it in tops:
                it.setVisible(was_visible[it] and it in keep)
            ba = QByteArray()
            buf = QBuffer(ba)
            buf.open(QIODevice.OpenModeFlag.WriteOnly)
            gen = QSvgGenerator()
            gen.setOutputDevice(buf)
            gen.setSize(QSize(w, h))
            gen.setViewBox(QRectF(0, 0, w, h))
            p = QPainter(gen)
            p.setRenderHint(QPainter.RenderHint.Antialiasing)
            scene.render(p, QRectF(0, 0, w, h), source, Qt.AspectRatioMode.IgnoreAspectRatio)
            p.end()
            buf.close()
            out.append(_svg_inner(bytes(ba.data())))
    finally:
        for it, v in was_visible.items():
            it.setVisible(v)
        _restore_swapped_colors(swapped)
        scene.setBackgroundBrush(saved_bg)
        for it in saved_sel:
            it.setSelected(True)
    return out


def build_html(title: str, width: int, height: int, layers, shapes, made: str = "") -> str:
    """`layers` = [(이름, SVG 안쪽, 보임 여부)], `shapes` = [{"x","y","w","h","text"}](SVG 좌표) → HTML 문자열."""
    groups = "\n".join(
        f'<g class="layer" data-layer="{i}"{"" if vis else " style=\"display:none\""}>{svg}</g>'
        for i, (_n, svg, vis) in enumerate(layers))
    layer_list = [{"name": n, "visible": bool(v)} for n, _s, v in layers]
    return _TEMPLATE.replace("__TITLE__", html.escape(title)) \
        .replace("__MADE__", html.escape(made or time.strftime("%Y-%m-%d"))) \
        .replace("__W__", str(width)).replace("__H__", str(height)) \
        .replace("__GROUPS__", groups) \
        .replace("__LAYERS__", json.dumps(layer_list, ensure_ascii=False)) \
        .replace("__SHAPES__", json.dumps(shapes, ensure_ascii=False))


def export_html(scene, path: str, title: str, groups, shape_items) -> bool:
    """도면 전체를 HTML 한 파일로. `groups` = [(레이어 이름, 아이템 목록, 보임 여부)], `shape_items` = [(아이템, 글자)].
    내용이 없으면 False. 안전 저장(임시 파일 → 바꿔치기)."""
    source = scene.itemsBoundingRect()
    if source.isEmpty():
        return False
    source = source.adjusted(-PAD, -PAD, PAD, PAD)
    svgs = render_layers(scene, [(n, items) for n, items, _v in groups], source)
    layers = [(n, svg, v) for (n, _i, v), svg in zip(groups, svgs)]
    shapes = []
    for it, text in shape_items:
        r = it.sceneBoundingRect()
        shapes.append({"x": round(r.x() - source.x(), 1), "y": round(r.y() - source.y(), 1),
                       "w": round(r.width(), 1), "h": round(r.height(), 1), "text": text})
    doc = build_html(title, round(source.width()), round(source.height()), layers, shapes)
    data = doc.encode("utf-8")

    def _write(tmp):
        with open(tmp, "wb") as f:
            f.write(data)
    write_via_temp(path, _write)
    return True


_TEMPLATE = """<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="generator" content="Easy CAD">
<title>__TITLE__</title>
<style>
  :root { --bg:#eef1f4; --bar:#ffffff; --ink:#1b222b; --muted:#5d6876; --line:#d8dde3; --accent:#c25a37; --hl:rgba(218,119,86,.18); }
  @media (prefers-color-scheme: dark) { :root { --bg:#151a20; --bar:#1d242d; --ink:#e4e9ee; --muted:#97a2ae; --line:#2e3742; --accent:#e48867; } }
  * { box-sizing:border-box; }
  html, body { height:100%; margin:0; }
  body { background:var(--bg); color:var(--ink); font:14px/1.5 "Malgun Gothic","Apple SD Gothic Neo","Noto Sans KR",sans-serif;
         display:flex; flex-direction:column; }
  header { display:flex; align-items:center; gap:12px; padding:10px 16px; background:var(--bar); border-bottom:1px solid var(--line); flex-wrap:wrap; }
  header h1 { font-size:16px; margin:0; font-weight:700; flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .tools { display:flex; gap:6px; align-items:center; }
  button { font:inherit; border:1px solid var(--line); background:var(--bar); color:var(--ink); border-radius:7px; padding:4px 10px; cursor:pointer; }
  button:hover { border-color:var(--accent); }
  #zoom { min-width:52px; text-align:center; color:var(--muted); font-variant-numeric:tabular-nums; }
  main { flex:1 1 auto; position:relative; overflow:hidden; touch-action:none; cursor:grab; }
  main.dragging { cursor:grabbing; }
  svg#sheet { position:absolute; inset:0; width:100%; height:100%; }
  .paper { fill:#ffffff; filter:drop-shadow(0 1px 6px rgba(0,0,0,.18)); }
  .hit { fill:transparent; stroke:transparent; stroke-width:3; cursor:pointer; vector-effect:non-scaling-stroke; }
  .hit:hover, .hit.on { fill:var(--hl); stroke:#da7756; }
  aside { position:absolute; left:12px; bottom:12px; background:var(--bar); border:1px solid var(--line); border-radius:10px;
          padding:8px 12px; max-width:min(320px, calc(100% - 24px)); box-shadow:0 2px 10px rgba(0,0,0,.12); }
  aside h2 { font-size:12px; margin:0 0 4px; color:var(--muted); font-weight:600; }
  aside label { display:flex; gap:6px; align-items:center; cursor:pointer; }
  #tip { position:absolute; pointer-events:none; background:var(--bar); border:1px solid var(--line); border-radius:7px;
         padding:3px 8px; font-size:12px; display:none; white-space:pre-wrap; max-width:280px; box-shadow:0 2px 8px rgba(0,0,0,.15); }
  footer { padding:4px 16px; font-size:11px; color:var(--muted); background:var(--bar); border-top:1px solid var(--line); }
</style>
</head>
<body>
<header>
  <h1>__TITLE__</h1>
  <div class="tools">
    <button id="out" title="축소">−</button><span id="zoom">100%</span><button id="in" title="확대">＋</button>
    <button id="fit" title="전체 보기">맞춤</button>
  </div>
</header>
<main id="view">
  <svg id="sheet" xmlns="http://www.w3.org/2000/svg">
    <g id="cam">
      <rect class="paper" x="0" y="0" width="__W__" height="__H__"/>
      __GROUPS__
      <g id="hits"></g>
    </g>
  </svg>
  <aside id="layers" hidden><h2>레이어</h2><div id="layerList"></div></aside>
  <div id="tip"></div>
</main>
<footer>Easy CAD로 만든 도면 · __MADE__ · 휠·두 손가락으로 확대, 끌어서 이동, 상자를 누르면 그 상자로</footer>
<script>
(function () {
  var W = __W__, H = __H__;
  var LAYERS = __LAYERS__;
  var SHAPES = __SHAPES__;
  var view = document.getElementById("view"), cam = document.getElementById("cam");
  var zoomLbl = document.getElementById("zoom"), tip = document.getElementById("tip");
  var s = 1, tx = 0, ty = 0;
  function apply() { cam.setAttribute("transform", "translate(" + tx + "," + ty + ") scale(" + s + ")"); zoomLbl.textContent = Math.round(s * 100) + "%"; }
  function fitTo(x, y, w, h, pad) {
    var vw = view.clientWidth, vh = view.clientHeight; pad = pad || 24;
    s = Math.min((vw - pad * 2) / w, (vh - pad * 2) / h); s = Math.max(0.05, Math.min(s, 8));
    tx = vw / 2 - (x + w / 2) * s; ty = vh / 2 - (y + h / 2) * s; apply();
  }
  function fit() { fitTo(0, 0, W, H); }
  function zoomAt(f, cx, cy) {
    var ns = Math.max(0.05, Math.min(s * f, 20));
    tx = cx - (cx - tx) * (ns / s); ty = cy - (cy - ty) * (ns / s); s = ns; apply();
  }
  document.getElementById("fit").onclick = fit;
  document.getElementById("in").onclick = function () { zoomAt(1.25, view.clientWidth / 2, view.clientHeight / 2); };
  document.getElementById("out").onclick = function () { zoomAt(0.8, view.clientWidth / 2, view.clientHeight / 2); };
  view.addEventListener("wheel", function (e) {
    e.preventDefault(); var r = view.getBoundingClientRect();
    zoomAt(e.deltaY < 0 ? 1.15 : 1 / 1.15, e.clientX - r.left, e.clientY - r.top);
  }, { passive: false });
  var pts = {}, last = null, moved = false;
  view.addEventListener("pointerdown", function (e) { pts[e.pointerId] = { x: e.clientX, y: e.clientY }; last = null; moved = false; view.classList.add("dragging"); });
  window.addEventListener("pointerup", function (e) { delete pts[e.pointerId]; last = null; if (!Object.keys(pts).length) view.classList.remove("dragging"); });
  window.addEventListener("pointermove", function (e) {
    if (!pts[e.pointerId]) return;
    var ids = Object.keys(pts), r = view.getBoundingClientRect();
    if (ids.length === 1) {
      var dx = e.clientX - pts[e.pointerId].x, dy = e.clientY - pts[e.pointerId].y;
      if (Math.abs(dx) + Math.abs(dy) > 2) moved = true;
      tx += dx; ty += dy; apply();
    } else if (ids.length === 2) {
      var a = pts[ids[0]], b = pts[ids[1]];
      var o = ids[0] == e.pointerId ? b : a;
      var d0 = Math.hypot(a.x - b.x, a.y - b.y);
      var d1 = Math.hypot(e.clientX - o.x, e.clientY - o.y);
      if (d0 > 0) zoomAt(d1 / d0, (e.clientX + o.x) / 2 - r.left, (e.clientY + o.y) / 2 - r.top);
      moved = true;
    }
    pts[e.pointerId] = { x: e.clientX, y: e.clientY };
  });
  // 상자: 올리면 강조·글자, 누르면 그 상자로
  var hits = document.getElementById("hits"), NS = "http://www.w3.org/2000/svg";
  SHAPES.forEach(function (sh) {
    var r = document.createElementNS(NS, "rect");
    r.setAttribute("class", "hit"); r.setAttribute("x", sh.x); r.setAttribute("y", sh.y);
    r.setAttribute("width", sh.w); r.setAttribute("height", sh.h); r.setAttribute("rx", 3);
    r.addEventListener("pointerenter", function () { if (!sh.text) return; tip.textContent = sh.text; tip.style.display = "block"; });
    r.addEventListener("pointerleave", function () { tip.style.display = "none"; });
    r.addEventListener("pointermove", function (e) { var b = view.getBoundingClientRect(); tip.style.left = (e.clientX - b.left + 14) + "px"; tip.style.top = (e.clientY - b.top + 14) + "px"; });
    r.addEventListener("click", function () { if (moved) return; fitTo(sh.x, sh.y, sh.w, sh.h, Math.min(view.clientWidth, view.clientHeight) / 3); });
    hits.appendChild(r);
  });
  // 레이어
  if (LAYERS.length > 1) {
    var box = document.getElementById("layers"), list = document.getElementById("layerList"); box.hidden = false;
    LAYERS.forEach(function (ly, i) {
      var lab = document.createElement("label"), cb = document.createElement("input");
      cb.type = "checkbox"; cb.checked = ly.visible;
      cb.onchange = function () { document.querySelector('[data-layer="' + i + '"]').style.display = cb.checked ? "" : "none"; };
      lab.appendChild(cb); lab.appendChild(document.createTextNode(ly.name)); list.appendChild(lab);
    });
  }
  window.addEventListener("resize", fit);
  fit();
})();
</script>
</body>
</html>
"""
