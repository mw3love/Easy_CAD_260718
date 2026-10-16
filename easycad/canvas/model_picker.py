"""모델 고르기 버튼(§8 항목56, 2026-10-16) — 가운데 칸과 보드 막대가 같이 쓴다.

버튼 글: 「기본 · gpt-6.1-sol ▾」(체크 없음 = 기본 하나) · 「gemini-3.8-flash ▾」(다른 것 하나) · 「gpt-6.1-sol 외 1개 ▾」(여러 개 →
흐름도·보드는 모델마다 하나씩 만들어 나란히). 펼치면 GPT·Gemini·Claude 차례로 회사마다 3개(`gw.featured_models` — 옛 모델은 걸러짐),
가격은 숫자(100만 토큰당 $ 입력 / 출력, 사용자: "주관적 표현 말고 숫자로"), 줄마다 「기본」 표시 또는 「기본으로」 버튼. 나머지는
「모델 더 보기」. 고른 것은 관리 객체(`_AIController.picks`)가 들고 있어 두 버튼이 같이 바뀐다.

목록 줄은 QWidgetAction(체크 상자) — 눌러도 메뉴가 닫히지 않아 여러 개를 연달아 고를 수 있다.
"""
from __future__ import annotations

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QCheckBox, QHBoxLayout, QLabel, QMenu, QToolButton, QWidget, QWidgetAction

from easycad.ai import gateway as gw

_VENDOR_LABEL = {"gpt": "GPT", "gemini": "Gemini", "claude": "Claude"}


def picker_text(ctrl) -> str:
    picks = ctrl.picks()
    default = ctrl.default_model()
    if len(picks) > 1:
        return f"{picks[0]} 외 {len(picks) - 1}개 ▾"
    if picks[0] == default:
        return f"기본 · {default} ▾"
    return f"{picks[0]} ▾"


class _ModelRow(QWidget):
    """목록 한 줄 — [체크] 모델 이름 · 가격 · 「기본」/「기본으로」."""

    def __init__(self, picker, info: dict, checked: bool, is_default: bool):
        super().__init__()
        self.model_id = info["id"]
        lay = QHBoxLayout(self)
        lay.setContentsMargins(10, 2, 8, 2)
        lay.setSpacing(8)
        self.check = QCheckBox(self.model_id, self)
        self.check.setChecked(checked)
        self.check.toggled.connect(lambda on, m=self.model_id: picker.toggle_model(m, on))
        lay.addWidget(self.check, 1)
        price = QLabel(gw.price_text(info), self)
        price.setMinimumWidth(92)
        price.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        price.setStyleSheet("color:#8a96a3; font-size:11px;")
        lay.addWidget(price)
        if is_default:
            self.default_btn = None
            tag = QLabel("기본", self)
            tag.setFixedWidth(62)
            tag.setAlignment(Qt.AlignmentFlag.AlignCenter)
            tag.setStyleSheet("background:#da7756; color:#1b120d; border-radius:4px; font-size:11px; font-weight:600;")
            lay.addWidget(tag)
        else:
            self.default_btn = QToolButton(self)
            self.default_btn.setText("기본으로")
            self.default_btn.setFixedWidth(62)
            self.default_btn.setToolTip("다음부터 이 모델로 만들어요(버튼에 「기본 · 이름」)")
            self.default_btn.setStyleSheet("QToolButton { border:1px solid rgba(128,128,128,140); border-radius:4px;"
                                           " font-size:11px; padding:1px 4px; }"
                                           "QToolButton:hover { background:rgba(128,128,128,50); }")
            self.default_btn.clicked.connect(lambda _c=False, m=self.model_id: picker.make_default(m))
            lay.addWidget(self.default_btn)


class _ModelPickerButton(QToolButton):
    def __init__(self, ctrl, parent=None):
        super().__init__(parent)
        self._ctrl = ctrl
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setToolTip("AI 모델 — 여러 개 고르면 흐름도·보드를 모델마다 만들어 나란히 비교해요. 가격은 100만 토큰당 $(입력 / 출력)")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.menu_ = QMenu(self)
        self.menu_.aboutToShow.connect(self.fill)
        self.setMenu(self.menu_)
        self.rows: list = []
        ctrl.picks_changed.connect(self.sync)
        self.sync()

    def sync(self):
        try:
            self.setText(picker_text(self._ctrl))
        except RuntimeError:   # 버튼이 지워진 뒤 늦게 온 시그널
            pass

    def _picked(self) -> list:
        return list(self._ctrl._picks) or [self._ctrl.default_model()]

    def fill(self):
        menu = self.menu_
        menu.clear()
        self.rows = []
        ctrl = self._ctrl
        info = ctrl.model_info()
        if not info or any("created" not in m for m in info):
            ctrl.fetch_models()   # 처음이거나 옛 형식(등록일 없음) — 새로 받아 둔다
        if not info:
            wait = menu.addAction("모델 목록·가격을 받아 오는 중… (KAIROS 키가 있어야 해요)")
            wait.setEnabled(False)
            return
        head = menu.addAction("여러 개 고르면 나란히 비교 — 100만 토큰당 $ (입력 / 출력)")
        head.setEnabled(False)
        picked, default = self._picked(), ctrl.default_model()
        feat = gw.featured_models(info)
        shown = set()
        for v in gw.MODEL_VENDORS:
            if not feat.get(v):
                continue
            menu.addSection(_VENDOR_LABEL[v])
            for m in feat[v]:
                self._add_row(menu, m, m["id"] in picked, m["id"] == default)
                shown.add(m["id"])
        rest = [m for m in info if m["id"] not in shown]
        if rest:
            more = menu.addMenu(f"모델 더 보기 — 옛 모델 포함 ({len(rest)})")
            rest.sort(key=lambda m: (gw.MODEL_VENDORS.index(gw.model_vendor(m["id"])) if gw.model_vendor(m["id"]) else 9,
                                     -(m.get("output") or 0.0), m["id"]))
            for m in rest:
                self._add_row(more, m, m["id"] in picked, m["id"] == default)
        n = len(picked)
        note = menu.addAction(f"{n}개 고름 — 흐름도·보드는 모델마다 하나씩 나란히, 크레딧도 각각" if n > 1
                              else "심볼·베끼기는 첫 모델 하나로 만들어요")
        note.setEnabled(False)

    def _add_row(self, menu, info, checked, is_default):
        row = _ModelRow(self, info, checked, is_default)
        act = QWidgetAction(menu)
        act.setDefaultWidget(row)
        menu.addAction(act)
        self.rows.append(row)

    def toggle_model(self, mid: str, on: bool):
        picked = self._picked()
        if on and mid not in picked:
            picked.append(mid)
        elif not on and mid in picked:
            picked.remove(mid)
        if not picked:   # 하나도 없으면 기본 하나로
            picked = [self._ctrl.default_model()]
        self._ctrl.set_picks([] if picked == [self._ctrl.default_model()] else picked)
        self._sync_checks()

    def make_default(self, mid: str):
        self._ctrl.set_model_choice(mid)
        if self._ctrl._picks == [mid]:
            self._ctrl.set_picks([])
        self.menu_.close()

    def _sync_checks(self):
        picked = self._picked()
        for row in self.rows:
            if row.check.isChecked() != (row.model_id in picked):
                row.check.blockSignals(True)
                row.check.setChecked(row.model_id in picked)
                row.check.blockSignals(False)
