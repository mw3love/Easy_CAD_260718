"""웹 칠판 PDF 보기 카드(§8 항목61, 2026-10-21 사용자: 휠로 쭉 보다가 Alt+드래그로 칠판에 오려 오기) — 서버 쪽 계산.

PDF 원본은 데이터 폴더 `<칠판>.pdf/<번호>.pdf`에 두고 칠판엔 주소만(칠판 파일이 가벼움). 브라우저는 쪽 그림을 그때그때 받는다 —
크롬 PDF 보기 화면은 칠판이 안을 들여다볼 수 없어 오려 낼 수 없음. 그리기는 데스크톱 「PDF 열기」와 같은 PyMuPDF(`fileio/pdf_import.py`).
Qt·네트워크 없음 — `web/server.py`가 부른다.
"""
from __future__ import annotations

import base64
import re


def _tidy(t: str) -> str:
    """PDF 글 — 줄 끝 빈칸·여러 빈 줄을 한 줄로(쪽 배치대로 뽑으면 줄 사이가 빈 줄 여럿)."""
    return re.sub(r"\n{2,}", "\n", re.sub(r"[ \t]+\n", "\n", t)).strip()

THUMB_W = 320          # 카드가 서버 없이 보일 때(내보내기·HTML 공유·데스크톱) 첫 쪽 작은 그림
TEXT_MAX = 30_000      # 찾기·대화 재료로 칠판에 같이 넣는 글(긴 PDF는 앞부분만)
CLIP_DPI = 200         # 오려 오기 — 화면 캡처보다 선명하게 다시 그림


def _open(path: str):
    import pymupdf
    return pymupdf.open(path)


def info(path: str) -> dict:
    """{pages, sizes: [[w, h] pt], thumb: data:image/jpeg, text} — 올릴 때 한 번."""
    import pymupdf
    with _open(path) as d:
        sizes = [[round(p.rect.width, 1), round(p.rect.height, 1)] for p in d]
        thumb = ""
        if len(d):
            p0 = d[0]
            pix = p0.get_pixmap(matrix=pymupdf.Matrix(THUMB_W / p0.rect.width, THUMB_W / p0.rect.width), alpha=False)
            thumb = "data:image/jpeg;base64," + base64.b64encode(pix.tobytes("jpeg", jpg_quality=70)).decode()
        text, n = [], 0
        for i, p in enumerate(d):
            t = _tidy(p.get_text("text", sort=True))
            if t:
                text.append(f"[{i + 1}쪽] {t}")
                n += len(t)
            if n > TEXT_MAX:
                break
        return {"pages": len(sizes), "sizes": sizes, "thumb": thumb, "text": "\n".join(text)[:TEXT_MAX]}


def page_jpeg(path: str, i: int, width: int) -> bytes:
    """i쪽(0부터)을 폭 width px JPEG로 — 카드 안 보기."""
    import pymupdf
    width = max(100, min(2400, int(width)))
    with _open(path) as d:
        p = d[i]
        k = width / p.rect.width
        return p.get_pixmap(matrix=pymupdf.Matrix(k, k), alpha=False).tobytes("jpeg", jpg_quality=90)   # 82는 작은 글자 둘레가 번짐(2026-10-21)


def _clip_rect(p, r):
    """r = 쪽 안 비율 [x0, y0, x1, y1](0~1) → PDF 좌표 사각형(쪽 밖은 잘라 냄)."""
    import pymupdf
    x0, y0, x1, y1 = (max(0.0, min(1.0, float(v))) for v in r)
    W, H = p.rect.width, p.rect.height
    return pymupdf.Rect(min(x0, x1) * W, min(y0, y1) * H, max(x0, x1) * W, max(y0, y1) * H)


def clip_png(path: str, i: int, r) -> bytes:
    """i쪽의 r 부분만 PNG로(칠판 이미지 = PNG — 데스크톱도 그대로 열림)."""
    import pymupdf
    with _open(path) as d:
        p = d[i]
        rc = _clip_rect(p, r)
        if rc.is_empty or rc.width < 1 or rc.height < 1:
            raise ValueError("빈 영역")
        k = CLIP_DPI / 72
        return p.get_pixmap(matrix=pymupdf.Matrix(k, k), clip=rc, alpha=False).tobytes("png")


def clip_text(path: str, i: int, r) -> str:
    """i쪽의 r 부분 글 — 줄 차례대로(「글로」). 스캔 PDF처럼 글이 없으면 ""."""
    with _open(path) as d:
        p = d[i]
        return _tidy(p.get_text("text", clip=_clip_rect(p, r), sort=True))


def lines(path: str, i: int) -> list:
    """i쪽 글 줄마다 [x0, y0, x1, y1(쪽 안 비율), 글] — 카드 위 보이지 않는 글 층(끌어 고르기·복사, 2026-10-21 사용자: 「글로」 단추 대신).
    가로줄만(논문 옆 세로 글씨 등은 고를 일이 드묾 — 겹쳐 놓으면 오히려 고르기를 방해)."""
    with _open(path) as d:
        p = d[i]
        W, H = p.rect.width, p.rect.height
        out = []
        for b in p.get_text("dict")["blocks"]:
            for ln in b.get("lines", []):
                dx, dy = ln.get("dir", (1, 0))
                t = "".join(s["text"] for s in ln["spans"]).rstrip()
                if abs(dy) > 0.01 or dx <= 0 or not t.strip():
                    continue
                x0, y0, x1, y1 = ln["bbox"]
                out.append([round(x0 / W, 5), round(y0 / H, 5), round(x1 / W, 5), round(y1 / H, 5), t])
        return out
