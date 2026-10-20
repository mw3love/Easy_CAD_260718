// 메모 고치기(§8 항목61 4-b ⑤ 1차) — 메모 자리에 TipTap을 겹쳐 띄움. 제목·글머리·번호·할 일·코드·인용 + 마크다운 입력(`# `·`- `·`1. `·`[] `·`> `·``` ```)은
// TipTap 확장의 입력 규칙 그대로(`---` = 구분선). 치수는 memo.js MEMO·MEMO_KIND와 render.jsx memoLayout과 같게(고치는 모습 = 결과). Esc·Ctrl+Enter·바깥 클릭 = 끝.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Editor, Extension } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import Paragraph from '@tiptap/extension-paragraph'
import Text from '@tiptap/extension-text'
import Bold from '@tiptap/extension-bold'
import Code from '@tiptap/extension-code'
import Heading from '@tiptap/extension-heading'
import Blockquote from '@tiptap/extension-blockquote'
import CodeBlock from '@tiptap/extension-code-block'
import HorizontalRule from '@tiptap/extension-horizontal-rule'
import { BulletList, ListItem, ListKeymap, OrderedList, TaskItem, TaskList } from '@tiptap/extension-list'
import { BackgroundColor, Color, TextStyle } from '@tiptap/extension-text-style'
import { UndoRedo } from '@tiptap/extensions'
import { Plugin } from '@tiptap/pm/state'
import { Decoration, DecorationSet } from '@tiptap/pm/view'
import { BOARD_FONT, METRICS, PT, TEXT_MARGIN, urlSpans } from './geom.js'
import { CODE_BAND, MONO_FONT } from './render.jsx'
import { LINE_KINDS, MEMO, MEMO_KIND, MUTED, caretLine, docToLines, lineBlocks, linesToDoc } from './memo.js'
import { Italic, Strike, Underline } from './marks.js'
import { FormatBar } from './formatbar.jsx'

const Finish = Extension.create({
  name: 'memoFinish',
  addOptions() { return { onDone: () => {}, onTurn: () => false } },
  // Esc = 끝내고 커서 줄 고르기(노션 — 그 상태에서 Ctrl+D·Del·Ctrl+/), Ctrl+Enter = 그냥 끝, Ctrl+/ = 전환 메뉴
  // Ctrl+Enter: 커서(또는 고른 글)가 할 일 줄이면 체크/해제(노션), 아니면 끝내기 — 2026-10-18 사용자 선택
  addKeyboardShortcuts() { return { Escape: () => { this.options.onDone(true); return true }, 'Mod-Enter': () => { if (!toggleTaskItems(this.editor)) this.options.onDone(false); return true }, 'Mod-/': () => this.options.onTurn() } },
})

// 고치는 중에도 주소는 파란 밑줄(어디까지가 주소인지 — 2026-10-18 사용자). 누르면 열리지는 않음(그냥 글), 코드 블록·「링크 끔」 줄은 칠하지 않음
const UrlPaint = Extension.create({
  name: 'memoUrl',
  addOptions() { return { off: new Set() } },
  addProseMirrorPlugins() {
    const off = this.options.off
    return [new Plugin({ props: { decorations: state => {
      const ds = []
      state.doc.descendants((n, pos) => {
        if (n.type.name === 'codeBlock') return false
        if (!n.isTextblock) return true
        if (off.has(n.textContent)) return false
        n.forEach((t, o) => { if (t.isText && !t.marks.some(m => m.type.name === 'code')) for (const [s, len] of urlSpans(t.text)) ds.push(Decoration.inline(pos + 1 + o + s, pos + 1 + o + s + len, { class: 'mb-url' })) })
        return false
      })
      return DecorationSet.create(state.doc, ds)
    } } })]
  },
})
// 고른 글에 걸친 할 일(또는 커서가 든 할 일) 체크/해제 — 하나라도 안 끝났으면 모두 끝, 모두 끝났으면 모두 풂. 할 일이 없으면 false
function toggleTaskItems(editor) {
  const { state, view } = editor, { from, to, $from } = state.selection, items = new Map()
  state.doc.nodesBetween(from, to, (n, pos) => { if (n.type.name === 'taskItem') items.set(pos, n) })
  for (let d = $from.depth; d > 0; d--) if ($from.node(d).type.name === 'taskItem') items.set($from.before(d), $from.node(d))
  if (!items.size) return false
  const all = [...items.values()].every(n => n.attrs.checked); let tr = state.tr
  for (const [pos, n] of items) tr = tr.setNodeMarkup(pos, undefined, { ...n.attrs, checked: !all })
  view.dispatch(tr); return true
}
// 전환(Ctrl+/) — 커서 줄 종류 바꾸기. 목록·인용에서 빠져나온 뒤 바꿈(clearNodes)
function turnInto(editor, k) {
  const c = editor.chain().focus().clearNodes()
  ;({ p: () => c, h1: () => c.setHeading({ level: 1 }), h2: () => c.setHeading({ level: 2 }), h3: () => c.setHeading({ level: 3 }), ul: () => c.toggleBulletList(), ol: () => c.toggleOrderedList(),
    todo: () => c.toggleTaskList(), code: () => c.setCodeBlock(), quote: () => c.setBlockquote() }[k] || (() => c))().run()
}

// spec: { left, top(화면 px — 메모 왼쪽 위), width(화면 px), zoom(칠판 배율 × 아이템 배율), fill(바탕 CSS), lines, caret?(처음 커서 줄), onChange(lines), onWheel(e) }
// onDone(lines, extra) — extra = { caret: 줄 번호 }(Esc — 그 줄 고르기) | { grab: { i, clientX, clientY } }(⠿를 눌러 끌기 시작) | { pick: { cur, clicked, range } }(단축키 + 다른 줄 클릭 = 줄 고르기) | null
const mayTake = host => { const a = document.activeElement; return !a || a === document.body || !!host?.contains(a) || !(/INPUT|TEXTAREA|SELECT/.test(a.tagName) || a.isContentEditable) }   // 대기 편집기가 다른 입력 칸의 포커스를 뺏지 않게(text.jsx와 같음)
export function MemoEditor({ spec, onDone }) {
  const box = useRef(null), host = useRef(null), ed = useRef(null), done = useRef(false), sp = useRef(spec), od = useRef(onDone)
  const [hov, setHov] = useState(null), [turn, setTurn] = useState(null), turnR = useRef(null)   // 손잡이를 띄울 줄 { i, y(칸 안 px) } · 전환 메뉴 { x, y, at }
  sp.current = spec; od.current = onDone; turnR.current = turn
  const finishR = useRef(null), turnOpenR = useRef(null), [edInst, setEdInst] = useState(null)   // 꾸미기 막대(2026-10-19)가 쓸 편집기·줄 종류 메뉴
  useLayoutEffect(() => {
    const finish = extra => { if (done.current) return; done.current = true; try { ed.current.view.domObserver?.flush?.() } catch { /* 없어도 그만 */ } od.current(docToLines(ed.current.getJSON()), extra || null) }
    finishR.current = finish
    const openTurn = () => {
      const v = ed.current.view, c = v.coordsAtPos(v.state.selection.from), b = box.current.getBoundingClientRect()
      setTurn({ x: c.left - b.left, y: c.bottom - b.top + 4, at: Math.max(0, LINE_KINDS.findIndex(([k]) => k === 'p')) }); return true
    }
    const editor = new Editor({
      element: host.current,
      extensions: [Document, Paragraph, Text, Bold, Italic, Underline, Strike, Code, TextStyle, Color, BackgroundColor, Heading.configure({ levels: [1, 2, 3] }), Blockquote, CodeBlock, HorizontalRule,
        BulletList, OrderedList, ListItem, TaskList, TaskItem.configure({ nested: true }), ListKeymap, UndoRedo, UrlPaint.configure({ off: new Set((spec.lines || []).filter(l => l.nolink).map(l => l.t)) }),
        Finish.configure({ onDone: sel => (turnR.current ? setTurn(null) : finish(sel ? { caret: caretLine(ed.current.state) } : null)), onTurn: openTurn })],
      content: linesToDoc(spec.lines),
      editorProps: {
        attributes: { spellcheck: 'false' },
        // 고치는 중 Shift+다른 줄 클릭 = 커서 줄부터 그 줄까지 줄 고르기, Ctrl·Alt+Shift 클릭 = 커서 줄 + 그 줄 따로(노션 — 2026-10-18 사용자). 같은 줄 Shift = 글자 고르기 그대로
        handleDOMEvents: { mousedown: (v, e) => {
          if (e.button !== 0) return false
          const range = e.shiftKey && !e.altKey, pick = ((e.ctrlKey || e.metaKey) && !e.shiftKey) || (e.altKey && e.shiftKey)
          if (!range && !pick) return false
          const hit = v.posAtCoords({ left: e.clientX, top: e.clientY }); if (!hit) return false
          const cur = caretLine(v.state), clicked = caretLine(v.state, hit.pos)
          if (range && clicked === cur) return false
          e.preventDefault(); finishR.current?.({ pick: { cur, clicked, range } }); return true
        } },
        handlePaste: () => !!sp.current.armed,   // 대기 중 Ctrl+V = 칠판 붙여넣기
        handleKeyDown: (_v, e) => {   // 전환 메뉴가 떠 있으면 ↑↓ Enter가 메뉴를 움직임
          if (sp.current.armed) return e.ctrlKey || e.metaKey || e.altKey || !(e.key.length === 1 || e.key === 'Process' || e.keyCode === 229)   // 대기 중 = 글자만 받고 Del·방향키·Enter·Ctrl+… 는 칠판이(메모 지우기·옮기기·고치기 시작)
          const t = turnR.current
          if (!t) { if (e.key === 'Escape') e.stopPropagation(); return false }   // 끝내며 고른 줄을 칠판의 Esc(= 고르기 풀기)가 바로 풀지 않게
          if (e.key === 'ArrowDown' || e.key === 'ArrowUp') { setTurn({ ...t, at: (t.at + (e.key === 'ArrowDown' ? 1 : LINE_KINDS.length - 1)) % LINE_KINDS.length }); return true }
          if (e.key === 'Enter') { turnInto(ed.current, LINE_KINDS[t.at][0]); setTurn(null); return true }
          if (e.key === 'Escape') { setTurn(null); return true }
          setTurn(null); return false
        },
      },
    })
    ed.current = editor; setEdInst(editor); turnOpenR.current = openTurn
    try {   // 커서 = 고른 줄 끝(Enter로 들어옴) 아니면 맨 끝
      const b = spec.caret != null ? lineBlocks(editor.state.doc)[spec.caret] : null, hit = spec.at && editor.view.posAtCoords({ left: spec.at.x, top: spec.at.y })   // 두 번 누른 자리가 먼저
      editor.commands.setTextSelection(hit ? hit.pos : b ? (b.node.isTextblock ? b.at + b.node.nodeSize - 1 : b.at) : editor.state.doc.content.size)
      if (!spec.armed || mayTake(host.current)) editor.view.focus()
    } catch { editor.commands.focus('end') }
    editor.on('update', () => { if (sp.current.armed) sp.current.onArm?.(); sp.current.onChange?.(docToLines(editor.getJSON())) })   // 치는 동안 메모 높이(칠판에 바로) · 대기 중 글이 들어오면(한글 조합 등) 바로 고치기로
    const onDown = e => { if (!sp.current.armed && e.button === 0 && box.current && !box.current.contains(e.target) && !e.target.closest?.('[data-keep-edit]')) finish() }
    const tm = setTimeout(() => window.addEventListener('pointerdown', onDown, true), 0)   // 0초 안에 닫히면(개발 모드 두 번 띄우기) 감시가 남아 오류를 쌓던 것 — 타이머도 지움
    // 치는 중에도 휠 = 칠판 확대(입력 칸은 배율 따라 같이 커짐 — 2026-10-18 사용자)
    const el = box.current, onWheel = e => { if (!sp.current.onWheel) return; e.preventDefault(); e.stopPropagation(); sp.current.onWheel(e) }
    el.addEventListener('wheel', onWheel, { passive: false })
    return () => { clearTimeout(tm); window.removeEventListener('pointerdown', onDown, true); el.removeEventListener('wheel', onWheel); if (!sp.current.armed) finish(); editor.destroy() }   // 대기만 하다 사라짐 = 고친 게 없음
  }, [])   // eslint-disable-line
  const z = spec.zoom, P = v => `${v * z}px`, fs = k => P(MEMO_KIND[k].pt * PT), ls = METRICS.board.lineSpacing, g = k => P(MEMO_KIND[k].gap ?? MEMO.GAP)
  // 치는 중에도 줄 손잡이 ⠿(2026-10-18 사용자) — 마우스가 올라간 줄의 첫 줄 높이에. 누르면 고치기를 끝내고 칠판의 손잡이 끌기·메뉴로 이어짐
  const HW = 16, HH = 22, inside = HW + 5 <= MEMO.LPAD * z, hx = inside ? MEMO.LPAD * z - HW - 3 : -HW - 4
  const onMove = e => {
    const editor = ed.current; if (!editor || turn) return
    const b = box.current.getBoundingClientRect(), y = e.clientY - b.top, seen = new Set(); let hit = null
    lineBlocks(editor.state.doc).forEach(({ at }, i) => {
      if (seen.has(at)) return; seen.add(at)
      const dom = editor.view.nodeDOM(at); if (!dom?.getBoundingClientRect) return
      const r = dom.getBoundingClientRect(), top = r.top - b.top, bot = r.bottom - b.top
      if (y >= top - MEMO.GAP * z && y <= bot) hit = { i, y: top + Math.min(r.height, (MEMO_KIND.p.pt * PT * ls + 2 * TEXT_MARGIN) * z) / 2 }
    })
    if (hit?.i !== hov?.i || hit?.y !== hov?.y) setHov(hit)
  }
  useEffect(() => { if (!spec.armed && ed.current && !ed.current.view.hasFocus()) ed.current.view.focus() }, [spec.armed])   // 대기 → 고치기(Enter 등) = 커서 그대로 보이게
  const S = '[data-testid=memo-editor]'
  // 블록 = 위아래 TEXT_MARGIN, 블록 사이 GAP(제목은 제 gap), 목록 들여쓰기 INDENT(깊이마다), 인용 = 왼쪽 막대 + QUOTE, 코드 = 고정폭 + 회색 바탕(이어진 줄 사이 여백 없음), 구분선 = 높이 HR*2 가운데 가는 줄
  const css = `${S} .ProseMirror{outline:none;white-space:pre-wrap;word-break:keep-all;overflow-wrap:anywhere;font-family:${BOARD_FONT};font-size:${fs('p')};line-height:${ls};color:#1f1f1f}
${S} p,${S} h1,${S} h2,${S} h3,${S} pre,${S} blockquote,${S} ul,${S} ol{margin:0}
${S} .ProseMirror>*+*,${S} li+li,${S} li>ul,${S} li>ol{margin-top:${g('p')}}
${S} p,${S} h1,${S} h2,${S} h3{padding:${P(TEXT_MARGIN)} 0}
${S} h1{font-size:${fs('h1')};font-weight:700}${S} h2{font-size:${fs('h2')};font-weight:700}${S} h3{font-size:${fs('h3')};font-weight:700}
${S} .ProseMirror>h1:not(:first-child){margin-top:${g('h1')}}${S} .ProseMirror>h2:not(:first-child){margin-top:${g('h2')}}${S} .ProseMirror>h3:not(:first-child){margin-top:${g('h3')}}
${S} ul,${S} ol{padding-left:${P(MEMO.INDENT)};list-style:none;counter-reset:n}${S} li{position:relative}
${S} ul:not([data-type=taskList])>li::before{content:'•';white-space:nowrap;position:absolute;right:calc(100% + ${P(6)});top:${P(TEXT_MARGIN)}}
${S} ol>li{counter-increment:n}${S} ol>li::before{content:counter(n) '.';white-space:nowrap;font-variant-numeric:tabular-nums;position:absolute;right:calc(100% + ${P(6)});top:${P(TEXT_MARGIN)}}
${S} ul[data-type=taskList]>li{display:flex}${S} ul[data-type=taskList]>li>label{position:absolute;right:calc(100% + ${P(MEMO.INDENT - 2 - MEMO_KIND.todo.pt * PT * 0.9)});top:${P(TEXT_MARGIN)};height:${P(MEMO_KIND.todo.pt * PT * ls)};display:flex;align-items:center}
${S} ul[data-type=taskList]>li>label input{margin:0;width:${P(MEMO_KIND.todo.pt * PT * 0.9)};height:${P(MEMO_KIND.todo.pt * PT * 0.9)};accent-color:#2f80ed}
${S} ul[data-type=taskList]>li>div{flex:1}${S} ul[data-type=taskList]>li[data-checked=true]>div{color:${MUTED};text-decoration:line-through}
${S} blockquote{border-left:${P(3)} solid #d4d4d8;padding:${P(TEXT_MARGIN)} 0 ${P(TEXT_MARGIN)} ${P(MEMO.QUOTE - 3)};color:#52525b}${S} blockquote p{padding:0}${S} blockquote p+p{margin-top:0}
${S} pre{white-space:pre;overflow-x:auto;scrollbar-width:none;font-family:${MONO_FONT};font-size:${fs('code')};background:${CODE_BAND};padding:${P(TEXT_MARGIN)} 0;line-height:${ls}}${S} pre code{font:inherit;background:none}
${S} hr{border:0;margin:0;height:${P(MEMO.HR * 2)};position:relative;overflow:visible}${S} hr::after{content:'';position:absolute;left:0;right:0;top:50%;border-top:1px solid #d4d4d8}
${S} hr.ProseMirror-selectednode{background:rgba(137,180,250,.25)}
${S} .mb-url{color:#2f80ed;text-decoration:underline}${S} code{font-family:${MONO_FONT};font-size:inherit;background:${CODE_BAND}}${S} ::selection{background:rgba(137,180,250,.35)}`
  const item = { all: 'unset', boxSizing: 'border-box', display: 'block', width: '100%', padding: '5px 10px', borderRadius: 5, cursor: 'pointer' }
  // 바탕은 투명 — 칠판이 고치는 메모의 바탕(채움·테두리)만 그려 줌(겹쳐 칠하면 투명한 채움이 진해졌음 — 2026-10-18)
  if (spec.armed) return <div ref={box} data-testid="memo-armed" style={{ position: 'absolute', left: spec.left, top: spec.top, width: spec.width, boxSizing: 'border-box', padding: `${P(MEMO.PAD)} ${P(MEMO.PAD)} ${P(MEMO.PAD)} ${P(MEMO.LPAD)}`, opacity: 0, pointerEvents: 'none', zIndex: 20 }}><style>{css.replaceAll(S, '[data-testid=memo-armed]')}</style><div ref={host} /></div>   // 메모만 고른 대기 — 보이지 않게 미리 띄워 첫 글자(한글 조합 포함)를 받음. 같은 host라 고치기로 바뀌어도 편집기는 그대로
  return <div ref={box} data-testid="memo-editor" onPointerDown={e => { e.stopPropagation(); if (e.button === 1) sp.current.onPan?.(e) }} onMouseDown={e => { if (e.button === 1) e.preventDefault() }} onWheel={e => e.stopPropagation()} onMouseMove={onMove} onMouseLeave={() => setHov(null)}
    style={{ position: 'absolute', left: spec.left, top: spec.top, width: spec.width, boxSizing: 'border-box', padding: `${P(MEMO.PAD)} ${P(MEMO.PAD)} ${P(MEMO.PAD)} ${P(MEMO.LPAD)}`, background: 'transparent', borderRadius: P(10), outline: '1.5px solid #89b4fa', zIndex: 20, colorScheme: 'light' }}>
    <style>{css}</style>
    <div ref={host} />
    {hov && !turn && <div data-testid="memo-edit-handle" title="끌기 = 옮기기 · 누르기 = 메뉴"
      onPointerDown={e => { e.preventDefault(); e.stopPropagation(); finishR.current?.({ grab: { i: hov.i, clientX: e.clientX, clientY: e.clientY } }) }}
      style={{ position: 'absolute', left: hx, top: hov.y - HH / 2, width: HW, height: HH, borderRadius: 4, background: 'rgba(127,127,127,.16)', cursor: 'grab', display: 'grid', placeItems: 'center', color: '#8a8f98', font: '700 12px sans-serif', lineHeight: 1, userSelect: 'none' }}>⠿</div>}
    {!turn && <FormatBar ed={edInst} onTurn={() => turnOpenR.current?.()} />}
    {turn && <div data-testid="memo-turn" onMouseDown={e => e.preventDefault()}
      style={{ position: 'absolute', left: turn.x, top: turn.y, zIndex: 2, minWidth: 170, background: 'var(--mb-card)', color: 'var(--mb-ink)', border: '1px solid var(--mb-line)', borderRadius: 8, padding: 4, boxShadow: '0 6px 18px rgba(0,0,0,.22)', font: "400 12.5px 'Pretendard', sans-serif", colorScheme: 'normal' }}>
      <div style={{ padding: '3px 10px 5px', color: 'var(--mb-muted)', fontSize: 11 }}>전환 · ↑↓ Enter</div>
      {LINE_KINDS.map(([k, name], j) => <button key={k} onClick={() => { turnInto(ed.current, k); setTurn(null) }} onMouseEnter={() => setTurn(t => ({ ...t, at: j }))}
        style={{ ...item, background: j === turn.at ? 'rgba(218,119,86,.14)' : 'transparent' }}>{name}</button>)}
    </div>}
  </div>
}
