// 메모 고치기(§8 항목61 4-b ⑤ 1차) — 메모 자리에 TipTap을 겹쳐 띄움. 제목·글머리·번호·할 일·코드·인용 + 마크다운 입력(`# `·`- `·`1. `·`[] `·`> `·``` ```)은
// TipTap 확장의 입력 규칙 그대로. 치수는 memo.js MEMO·MEMO_KIND와 render.jsx memoLayout과 같게(고치는 모습 = 결과). Esc·Ctrl+Enter·바깥 클릭 = 끝.
import { useLayoutEffect, useRef } from 'react'
import { Editor, Extension } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import Paragraph from '@tiptap/extension-paragraph'
import Text from '@tiptap/extension-text'
import Bold from '@tiptap/extension-bold'
import Code from '@tiptap/extension-code'
import Heading from '@tiptap/extension-heading'
import Blockquote from '@tiptap/extension-blockquote'
import CodeBlock from '@tiptap/extension-code-block'
import { BulletList, ListItem, ListKeymap, OrderedList, TaskItem, TaskList } from '@tiptap/extension-list'
import { BackgroundColor, Color, TextStyle } from '@tiptap/extension-text-style'
import { UndoRedo } from '@tiptap/extensions'
import { BOARD_FONT, METRICS, PT, TEXT_MARGIN } from './geom.js'
import { CODE_BAND, MONO_FONT } from './render.jsx'
import { MEMO, MEMO_KIND, MUTED, docToLines, linesToDoc } from './memo.js'

const Finish = Extension.create({
  name: 'memoFinish',
  addOptions() { return { onDone: () => {} } },
  addKeyboardShortcuts() { return { Escape: () => { this.options.onDone(); return true }, 'Mod-Enter': () => { this.options.onDone(); return true } } },
})

// spec: { left, top(화면 px — 메모 왼쪽 위), width(화면 px), zoom(칠판 배율 × 아이템 배율), fill(바탕 CSS), lines, onChange(lines) } — onDone(lines)
export function MemoEditor({ spec, onDone }) {
  const host = useRef(null), ed = useRef(null), done = useRef(false), sp = useRef(spec), od = useRef(onDone)
  sp.current = spec; od.current = onDone
  useLayoutEffect(() => {
    const finish = () => { if (done.current) return; done.current = true; try { ed.current.view.domObserver?.flush?.() } catch { /* 없어도 그만 */ } od.current(docToLines(ed.current.getJSON())) }
    const editor = new Editor({
      element: host.current,
      extensions: [Document, Paragraph, Text, Bold, Code, TextStyle, Color, BackgroundColor, Heading.configure({ levels: [1, 2, 3] }), Blockquote, CodeBlock,
        BulletList, OrderedList, ListItem, TaskList, TaskItem.configure({ nested: true }), ListKeymap, UndoRedo, Finish.configure({ onDone: finish })],
      content: linesToDoc(spec.lines),
      editorProps: { attributes: { spellcheck: 'false' } },
    })
    ed.current = editor
    try { editor.commands.setTextSelection(editor.state.doc.content.size); editor.view.focus() } catch { editor.commands.focus('end') }
    editor.on('update', () => sp.current.onChange?.(docToLines(editor.getJSON())))   // 치는 동안 메모 높이(칠판에 바로)
    const onDown = e => { if (!host.current.contains(e.target) && !e.target.closest?.('[data-keep-edit]')) finish() }
    setTimeout(() => window.addEventListener('pointerdown', onDown, true), 0)
    return () => { window.removeEventListener('pointerdown', onDown, true); finish(); editor.destroy() }
  }, [])   // eslint-disable-line
  const z = spec.zoom, P = v => `${v * z}px`, fs = k => P(MEMO_KIND[k].pt * PT), ls = METRICS.board.lineSpacing, g = k => P(MEMO_KIND[k].gap ?? MEMO.GAP)
  const S = '[data-testid=memo-editor]'
  // 블록 = 위아래 TEXT_MARGIN, 블록 사이 GAP(제목은 제 gap), 목록 들여쓰기 INDENT(깊이마다), 인용 = 왼쪽 막대 + QUOTE, 코드 = 고정폭 + 회색 바탕(이어진 줄 사이 여백 없음)
  const css = `${S} .ProseMirror{outline:none;white-space:pre-wrap;word-break:keep-all;overflow-wrap:anywhere;font-family:${BOARD_FONT};font-size:${fs('p')};line-height:${ls};color:#1f1f1f}
${S} p,${S} h1,${S} h2,${S} h3,${S} pre,${S} blockquote,${S} ul,${S} ol{margin:0}
${S} .ProseMirror>*+*,${S} li+li,${S} li>ul,${S} li>ol{margin-top:${g('p')}}
${S} p,${S} h1,${S} h2,${S} h3{padding:${P(TEXT_MARGIN)} 0}
${S} h1{font-size:${fs('h1')};font-weight:700}${S} h2{font-size:${fs('h2')};font-weight:700}${S} h3{font-size:${fs('h3')};font-weight:700}
${S} .ProseMirror>h1:not(:first-child){margin-top:${g('h1')}}${S} .ProseMirror>h2:not(:first-child){margin-top:${g('h2')}}${S} .ProseMirror>h3:not(:first-child){margin-top:${g('h3')}}
${S} ul,${S} ol{padding-left:${P(MEMO.INDENT)};list-style:none;counter-reset:n}${S} li{position:relative}
${S} ul:not([data-type=taskList])>li::before{content:'•';white-space:nowrap;position:absolute;right:calc(100% + ${P(6)});top:${P(TEXT_MARGIN)}}
${S} ol>li{counter-increment:n}${S} ol>li::before{content:counter(n) '.';white-space:nowrap;position:absolute;right:calc(100% + ${P(6)});top:${P(TEXT_MARGIN)}}
${S} ul[data-type=taskList]>li{display:flex}${S} ul[data-type=taskList]>li>label{position:absolute;right:calc(100% + ${P(MEMO.INDENT - 2 - MEMO_KIND.todo.pt * PT * 0.9)});top:${P(TEXT_MARGIN)};height:${P(MEMO_KIND.todo.pt * PT * ls)};display:flex;align-items:center}
${S} ul[data-type=taskList]>li>label input{margin:0;width:${P(MEMO_KIND.todo.pt * PT * 0.9)};height:${P(MEMO_KIND.todo.pt * PT * 0.9)};accent-color:#2f80ed}
${S} ul[data-type=taskList]>li>div{flex:1}${S} ul[data-type=taskList]>li[data-checked=true]>div{color:${MUTED};text-decoration:line-through}
${S} blockquote{border-left:${P(3)} solid #d4d4d8;padding:${P(TEXT_MARGIN)} 0 ${P(TEXT_MARGIN)} ${P(MEMO.QUOTE - 3)};color:#52525b}${S} blockquote p{padding:0}${S} blockquote p+p{margin-top:0}
${S} pre{font-family:${MONO_FONT};font-size:${fs('code')};background:${CODE_BAND};padding:${P(TEXT_MARGIN)} 0;line-height:${ls}}${S} pre code{font:inherit;background:none}
${S} code{font-family:${MONO_FONT};font-size:inherit;background:${CODE_BAND}}${S} ::selection{background:rgba(137,180,250,.35)}`
  return <div ref={host} data-testid="memo-editor" onPointerDown={e => e.stopPropagation()} onWheel={e => e.stopPropagation()}
    style={{ position: 'absolute', left: spec.left, top: spec.top, width: spec.width, boxSizing: 'border-box', padding: P(MEMO.PAD), background: spec.fill || '#fff', borderRadius: P(10), outline: '1.5px solid #89b4fa', zIndex: 20 }}>
    <style>{css}</style>
  </div>
}
