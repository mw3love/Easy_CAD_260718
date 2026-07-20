"""이미지→도면 초안 빌더 (Phase 5 — AI 이미지→도면).

Claude(이 세션의 네이티브 vision)가 이미지를 보고 이 빌더를 호출해 편집가능한 Easy CAD
도형으로 이루어진 `.ecad` 초안을 만든다. "완벽 복원"이 아니라 "고품질 초안 → 사용자 수동보정".

설계(deep-interview 2026-07-21):
- 앞단(이미지 이해)은 Claude가 담당 — 외부 API·게이트웨이 불필요(지속성).
- 뒷단(도형 생성)이 이 빌더. **순수 파이썬 — PyQt 비의존.** `document.py`가 쓰는 `.ecad` JSON
  스키마를 직접 만든다. 그래서 어떤 환경에서도 Qt 없이 돌아간다. 스키마가 어긋나면 로드 시
  `document.load_document`가 즉시 실패하므로(FORMAT 불일치→ValueError) 드리프트는 스모크가 잡는다.
- 좌표 = **이미지 픽셀 그대로**(캔버스 좌표). 사용자가 열어서 스케일·정리한다.
- 재사용: 기존 아이템 어휘 그대로 — box(rect)·ellipse·symbol(순서도 6종)·arrow(sarrow,
  지속연결 바인딩+직교 자동라우팅)·중앙/중점 라벨.

사용 예:
    from easycad.fileio.sketch_build import Sketch
    s = Sketch()
    a = s.symbol("terminal", 60, 40, 160, 70, "시작")
    b = s.symbol("decision", 90, 170, 120, 100, "조건?")
    c = s.box(280, 185, 160, 70, "처리 A")
    s.arrow(b, c, label="예")          # b→c 화살표(자동 직교 라우팅 + 지속연결)
    s.arrow(a, b)
    s.save("out.ecad")                 # 앱에서 Ctrl+O로 열면 편집가능 도형으로 뜬다
"""
import json

# document.py와 동일해야 하는 상수(그쪽은 PyQt를 import하므로 여기선 값만 복제 —
# 불일치 시 load_document가 ValueError로 걸러낸다).
FORMAT = "easycad-doc"
VERSION = 1

_DEFAULT_COLOR = "#000000"   # 복원 도면 기본은 검정(앱 기본 빨강과 다름 — 도면엔 검정이 자연스러움)
_DEFAULT_WIDTH = 6.0         # 앱 _DEFAULT_WIDTH와 동일(사용자 손그림과 두께 일관)
_DEFAULT_FONT = 16

# _SYMBOL_KINDS(annotator_core)와 동일한 순서도 심볼 어휘.
_SYMBOL_KINDS = ("decision", "terminal", "data", "prep", "document", "database")


def _argb(c: str) -> str:
    """색 문자열을 `.ecad`가 쓰는 `#AARRGGBB`(HexArgb, alpha 먼저)로 정규화.
    입력 `#RRGGBB`(6자리)면 불투명(alpha=ff) 부여, `#AARRGGBB`(8자리)면 그대로, `#RGB`(3자리)면 확장.
    ⚠ 8자리는 Qt 규약대로 alpha가 **앞**이다(RRGGBBAA 아님)."""
    s = c.strip().lstrip("#")
    if len(s) == 3:
        s = "ff" + "".join(ch * 2 for ch in s)
    elif len(s) == 6:
        s = "ff" + s
    elif len(s) != 8:
        raise ValueError(f"색 형식 오류: {c!r} (#RGB·#RRGGBB·#AARRGGBB 중 하나)")
    return "#" + s.lower()


class Node:
    """빌더가 반환하는 도형 핸들. arrow()가 이걸로 접속 포트를 계산한다.
    idx = 최종 items 배열에서의 위치(바인딩이 인덱스로 참조하므로 저장 순서 = 생성 순서)."""
    __slots__ = ("idx", "x", "y", "w", "h")

    def __init__(self, idx, x, y, w, h):
        self.idx, self.x, self.y, self.w, self.h = idx, float(x), float(y), float(w), float(h)

    @property
    def cx(self):
        return self.x + self.w / 2.0

    @property
    def cy(self):
        return self.y + self.h / 2.0

    def port(self, side):
        """지정한 변 중점(N·E·S·W) 좌표. 도형 pos=[0,0]·무회전이라 로컬좌표 == 씬좌표."""
        s = side.upper()
        if s == "N":
            return (self.cx, self.y)
        if s == "E":
            return (self.x + self.w, self.cy)
        if s == "S":
            return (self.cx, self.y + self.h)
        if s == "W":
            return (self.x, self.cy)
        raise ValueError(f"포트 방향 오류: {side!r} (N·E·S·W 중 하나)")

    def _port_facing(self, tx, ty):
        """상대 지점(tx,ty)을 향하는 변 중점(N·E·S·W) 하나 — 앱의 포트 모델과 일치."""
        return min((self.port(s) for s in "NESW"),
                   key=lambda p: (p[0] - tx) ** 2 + (p[1] - ty) ** 2)


class Sketch:
    """이미지 초안을 도형으로 조립하는 헤드리스 빌더. save()로 `.ecad`를 쓴다."""

    def __init__(self):
        self._items = []   # 생성 순서 = items 배열 순서 = 바인딩 인덱스 기준

    # ---- 공통 -------------------------------------------------------------
    def _common(self):
        z = len(self._items)   # 나중에 만든 것이 위(arrow가 box 위)
        return {"pos": [0.0, 0.0], "scale": 1.0, "rotation": 0.0,
                "z": float(z), "origin": [0.0, 0.0]}

    @staticmethod
    def _label_dict(text, color, font):
        return {"text": text, "color": _argb(color), "font": int(font), "bg": None}

    def _add_shape(self, type_, x, y, w, h, label, color, width, fill, extra=None):
        d = self._common()
        d.update(type=type_, rect=[float(x), float(y), float(w), float(h)],
                 pen=_argb(color), width=float(width),
                 fill=None if fill is None else _argb(fill))
        if extra:
            d.update(extra)
        if label:
            # 닫힌 도형(네모·원·심볼)은 중앙 라벨(_CenterLabelMixin) — 색=테두리색 관례를 따른다.
            d["label"] = self._label_dict(label, color, _DEFAULT_FONT)
        node = Node(len(self._items), x, y, w, h)
        self._items.append(d)
        return node

    # ---- 도형 -------------------------------------------------------------
    def box(self, x, y, w, h, label=None, *, color=_DEFAULT_COLOR,
            width=_DEFAULT_WIDTH, fill=None) -> Node:
        """직사각형(_RectItem). label이면 정중앙에 텍스트."""
        return self._add_shape("rect", x, y, w, h, label, color, width, fill)

    def ellipse(self, x, y, w, h, label=None, *, color=_DEFAULT_COLOR,
                width=_DEFAULT_WIDTH, fill=None) -> Node:
        """타원/원(_EllipseItem)."""
        return self._add_shape("ellipse", x, y, w, h, label, color, width, fill)

    def symbol(self, kind, x, y, w, h, label=None, *, color=_DEFAULT_COLOR,
               width=_DEFAULT_WIDTH, fill=None) -> Node:
        """순서도 심볼(_SymbolItem). kind ∈ decision·terminal·data·prep·document·database."""
        if kind not in _SYMBOL_KINDS:
            raise ValueError(f"알 수 없는 심볼 kind: {kind!r} (가능: {', '.join(_SYMBOL_KINDS)})")
        return self._add_shape("symbol", x, y, w, h, label, color, width, fill,
                               extra={"kind": kind})

    def text(self, x, y, s, *, color=_DEFAULT_COLOR, font=_DEFAULT_FONT) -> None:
        """자유 텍스트(_TextItem) — 제목·주석 등 도형에 안 붙는 글자."""
        d = self._common()
        d.update(type="text", text=s, color=_argb(color), font=int(font), bg=None)
        # 텍스트는 pos로 배치(rect 기반 아님).
        d["pos"] = [float(x), float(y)]
        self._items.append(d)

    # ---- 화살표 -----------------------------------------------------------
    def arrow(self, src: Node, dst: Node, label=None, *, head=True,
              from_side=None, to_side=None, channel_x=None, channel_y=None,
              color=_DEFAULT_COLOR, width=_DEFAULT_WIDTH) -> None:
        """src→dst 직선 화살표(_PolyArrowItem). 양 끝을 도형 변 중점 포트에 **지속연결**하고
        auto_route=True로 둬, 앱이 열릴 때 씬 신호로 직교 엘보를 자동 재계산한다(도형을 옮기면 추종).
        label이면 화살표 중점 위쪽에 텍스트.

        from_side/to_side(N·E·S·W)로 접속 변을 **명시**할 수 있다(생략 시 상대 도형을 향하는 최근접
        변). ⚠ 밀집 순서도에서 필요: ⓐ 정렬된 두 노드의 **피드백 루프**는 양끝을 같은 측면으로 빼야
        본선과 안 겹친다(예: 아래→위 루프에 from_side="E", to_side="E") ⓑ 한 노드에 여러 화살표가
        같은 변으로 들어와 겹칠 때 서로 다른 변으로 분산.

        channel_x/channel_y로 **외곽 채널 우회**를 준다(둘 중 하나만). 긴 루프백이 내부를 가로질러
        다른 화살표와 겹치는 걸 막으려, 자동 라우팅 대신 지정 좌표까지 빼서 도는 명시 경로를 쓴다.
        channel_x=X: 양끝을 x=X 세로 채널로(우회) → [p1,(X,p1y),(X,p2y),p2]. channel_y=Y: 가로 채널.
        ⚠ 코어 라우터는 다른 화살표를 장애물로 안 보므로(되먹임 위험), 긴 루프백은 이걸로 손수 우회한다.
        채널을 주면 auto_route=False(도형 이동 시 끝점만 추종, 채널 경로는 고정)."""
        if channel_x is not None and channel_y is not None:
            raise ValueError("channel_x와 channel_y는 동시에 줄 수 없다(둘 중 하나)")
        p1 = src.port(from_side) if from_side else src._port_facing(dst.cx, dst.cy)
        p2 = dst.port(to_side) if to_side else dst._port_facing(src.cx, src.cy)
        if channel_x is not None:
            pts = [[p1[0], p1[1]], [float(channel_x), p1[1]],
                   [float(channel_x), p2[1]], [p2[0], p2[1]]]
            auto = False
        elif channel_y is not None:
            pts = [[p1[0], p1[1]], [p1[0], float(channel_y)],
                   [p2[0], float(channel_y)], [p2[0], p2[1]]]
            auto = False
        else:
            pts = [[p1[0], p1[1]], [p2[0], p2[1]]]
            auto = True
        d = self._common()
        d.update(type="sarrow", pts=pts,
                 color=_argb(color), width=float(width), head=bool(head),
                 auto_route=auto,
                 bind1=src.idx, bind1_pt=[p1[0], p1[1]],   # 시작=idx0 → src 로컬 부착점(==씬)
                 bind2=dst.idx, bind2_pt=[p2[0], p2[1]])   # 끝=idx last → dst 로컬 부착점
        if label:
            d["label"] = self._label_dict(label, color, _DEFAULT_FONT)
        self._items.append(d)

    # ---- 출력 -------------------------------------------------------------
    def to_dict(self) -> dict:
        return {"format": FORMAT, "version": VERSION, "items": self._items}

    def save(self, path: str) -> int:
        """`.ecad`로 저장하고 아이템 수를 반환."""
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, ensure_ascii=False, indent=1)
        return len(self._items)
