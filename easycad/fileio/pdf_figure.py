"""PDF 쪽에서 「그림 자리」 찾기 — 보드 그림 칸 자르기와 AI에게 알릴 「그림 있는 쪽」 목록이 같이 쓴다(§8 항목60, Qt 비의존).

논문은 그림이 사진 한 장이라 「가장 큰 그림 한 장」을 자르면 됐다. 장비 소개 슬라이드의 구성도는 작은 사진 여러 장(안테나·장비·카메라)에
선(벡터)과 글자 이름표가 얹힌 모양이라, 가장 큰 사진 한 장만 잘리고 위에 얹힌 글자가 반쯤 잘렸다(Leader 소개 자료, 실제 KAIROS).
가로 쪽(슬라이드)은 제목 줄·바닥 줄을 뺀 본문에서 사진·선을 모두 감싸고, 그 안·바로 옆의 이름표 글까지 넓힌 범위를 그림으로 본다.
"""
from __future__ import annotations

_MIN_IMG = 0.001   # 쪽 넓이 대비 — 이보다 작은 사진(점·아이콘)은 그림으로 안 본다(구성도의 안테나 사진이 0.002)
_MIN_FIG = 0.06    # 찾은 범위가 쪽 넓이의 이만큼도 안 되면 그림 없음
_HEAD, _FOOT = 0.16, 0.92   # 슬라이드 제목 줄 아래 · 바닥 줄 위(쪽 높이 비율)
_LABEL_GAP = 18.0  # 이름표로 볼 거리(pt) — 그림 범위에서 이만큼 안의 짧은 글


def _overlap(a, b) -> float:
    """a 넓이 중 b와 겹치는 비율(선처럼 납작한 것도 셈 — 높이 0은 1로)."""
    i = a & b
    if i.is_empty:
        return 0.0
    return (max(i.width, 1.0) * max(i.height, 1.0)) / (max(a.width, 1.0) * max(a.height, 1.0))


def _is_slide(page) -> bool:
    return page.rect.width > page.rect.height * 1.05


def figure_rect(page):
    """그림 자리(fitz.Rect) 또는 None. 세로 쪽(논문)은 가장 큰 사진, 가로 쪽(슬라이드)은 본문의 사진·선·이름표를 모두 감싼 범위."""
    import fitz
    r = page.rect
    area = r.width * r.height
    imgs = [fitz.Rect(i["bbox"]) & r for i in page.get_image_info()]
    if not _is_slide(page):
        big = [b for b in imgs if b.width * b.height > area * 0.04]
        return max(big, key=lambda b: b.width * b.height) if big else None
    body = fitz.Rect(r.x0, r.y0 + r.height * _HEAD, r.x1, r.y0 + r.height * _FOOT)
    # 가운데가 본문 안인 사진만 — 제목 줄 옆 장식(위성 아이콘)이 본문 위쪽에 살짝 걸쳐 범위를 제목까지 끌어올렸다
    parts = [b for b in imgs if b.width * b.height > area * _MIN_IMG and body.contains((b.tl + b.br) / 2)]
    texts = [(fitz.Rect(b[:4]), str(b[4]).strip()) for b in page.get_text("blocks")]
    paras = [tr for tr, t in texts if len(t) > 40]   # 문단(이름표가 아닌 긴 글)
    try:
        for d in page.get_drawings():   # 사진 사이를 잇는 선·상자(벡터)
            dr = fitz.Rect(d["rect"]) & r
            if dr.is_empty or dr.width * dr.height > area * 0.6 or not body.contains((dr.tl + dr.br) / 2):
                continue   # 쪽 전체 바탕 상자·제목 줄 장식은 빼고
            if any(_overlap(dr, p) >= 0.5 for p in paras):
                continue   # 문단 안 꾸밈(강조 상자·밑줄) — 2쪽 「STAY IN SYNC」 주황 상자가 범위를 문단까지 끌어내렸다
            if dr.height < 4 and dr.width > r.width * 0.6:   # 제목 밑 가로줄(쪽 폭을 가로지르는 얇은 줄)은 그림이 아니다
                continue
            if dr.width > 2 or dr.height > 2:
                parts.append(dr)
    except Exception:   # noqa: BLE001 — 선을 못 읽어도 사진만으로
        pass
    if not parts:
        return None
    box = fitz.Rect(parts[0])
    for p in parts[1:]:
        box |= p
    # 이름표 — 범위 안이나 바로 옆의 짧은 글 줄(긴 문단은 본문이라 넣지 않는다)
    for _ in range(2):
        near = fitz.Rect(box.x0 - _LABEL_GAP, box.y0 - _LABEL_GAP, box.x1 + _LABEL_GAP, box.y1 + _LABEL_GAP)
        grown = fitz.Rect(box)
        for br, t in texts:   # 제목 줄의 글은 빼고(걸친 글을 반만 자르지 않게 통째로 넣거나 뺀다)
            if br.intersects(near) and br.width < r.width * 0.45 and len(t) <= 40 and body.contains((br.tl + br.br) / 2):
                grown |= br
        if grown == box:
            break
        box = grown
    if box.width * box.height < area * _MIN_FIG:
        return None
    pad = 6.0
    return fitz.Rect(box.x0 - pad, box.y0 - pad, box.x1 + pad, box.y1 + pad) & r


def figure_labels(page, rect, limit: int = 80) -> str:
    """그림 자리 안 글(이름표)을 한 줄로 — AI가 어느 쪽이 무슨 그림인지 알게."""
    words = []
    for b in page.get_text("blocks"):
        import fitz
        br = fitz.Rect(b[:4])
        if rect.contains((br.tl + br.br) / 2):   # 가운데가 그림 안인 글만(걸친 바닥 줄 저작권 표시는 빼고)
            words.append(" ".join(str(b[4]).split()))
    s = " · ".join(w for w in words if w)
    return s[:limit]


def figure_pages(pdf_path, max_pages: int = 30) -> list:
    """[(쪽 번호, 이름표 글)] — 그림이 있는 쪽(앞에서부터 `max_pages`쪽까지)."""
    import fitz
    out = []
    with fitz.open(pdf_path) as doc:
        for i, page in enumerate(doc):
            if i >= max_pages:
                break
            rect = figure_rect(page)
            if rect is not None:
                out.append((i + 1, figure_labels(page, rect)))
    return out
