// 글 편집(2단계) — 칠판 위에 TipTap 편집기를 겹쳐 띄우고, 끝나면 .ecad 글(text + runs)로 돌려준다.
// 글 + runs ↔ TipTap 문서는 이미 시험된 규칙(ecadFormat.js runsToRichText/richTextToRuns) 그대로. 한글 조합 입력은 TipTap(ProseMirror)이 맡는다.
// Enter = 줄바꿈(데스크톱 글 상자와 같음), Esc·Ctrl+Enter·바깥 클릭 = 끝. Ctrl+B = 굵게.
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { Editor, Extension } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import Paragraph from '@tiptap/extension-paragraph'
import Text from '@tiptap/extension-text'
import Bold from '@tiptap/extension-bold'
import { BackgroundColor, Color, TextStyle } from '@tiptap/extension-text-style'
import { UndoRedo } from '@tiptap/extensions'
import { richTextToRuns, runsToRichText } from '../ecadFormat.js'
import { APP_FONT, BOARD_FONT, METRICS, TEXT_MARGIN } from './geom.js'

// 글 굵기(400·600·800) — textStyle 안에(데스크톱 weight·보드 글꼴 굵기)
const FontWeight = Extension.create({
  name: 'fontWeight',
  addGlobalAttributes() {
    return [{ types: ['textStyle'], attributes: { fontWeight: { default: null, parseHTML: el => el.style.fontWeight || null,
      renderHTML: a => (a.fontWeight ? { style: `font-weight: ${a.fontWeight}` } : {}) } } }]
  },
})
const Finish = Extension.create({
  name: 'finish',
  addKeyboardShortcuts() {
    const o = this.options
    const armed = () => !!o.isArmed?.()   // 표 칸 대기 중(보이지 않게 미리 띄운 편집기) — Esc·Enter 등은 칠판 글쇠가 맡음
    const keys = { Escape: () => { if (armed()) return false; (o.onCancel || o.onDone)(); return true }, 'Mod-Enter': () => { if (armed()) return false; o.onDone(); return true } }
    if (o.onMove) Object.assign(keys, { Enter: () => { if (!armed()) o.onMove([1, 0]); return true }, Tab: () => { if (!armed()) o.onMove([0, 1]); return true }, 'Shift-Tab': () => { if (!armed()) o.onMove([0, -1]); return true } })   // 표 칸(데스크톱 `_CellEditor`)
    return keys
  },
  addOptions() { return { onDone: () => {}, onCancel: null, onMove: null, isArmed: null } },
})

// 바로 포커스 + 커서를 끝으로 — TipTap focus 명령은 다음 그리기 때 돌아서(창이 가려지면 0.6초까지 늦음 — 2026-10-18 실측) 두 번 누르자마자 친 글자가 빠질 수 있음
const focusNow = editor => { try { editor.commands.setTextSelection(editor.state.doc.content.size); editor.view.focus() } catch { editor.commands.focus('end') } }

// spec: { left, top (화면 px — 문서 상자 왼쪽 위) 또는 center(화면 px — 도형 라벨 가운데), px(글자 px, 화면 배율 적용 전), zoom, family('app'|'board'), weight, color, align('left'|'center'),
//         rotation, origin(화면 px 회전 중심), text, runs, width(화면 px — 주면 그 폭에서 줄바꿈: 왼쪽 위 라벨), flat(테두리 없이 그 자리에 겹침), onChange(치는 동안 { text, runs }) } — onDone({ text, runs })
export function TextEditor({ spec, onDone }) {
  const host = useRef(null), ed = useRef(null), done = useRef(false), sp = useRef(spec), od = useRef(onDone), firstKey = useRef(spec.cellKey)
  sp.current = spec; od.current = onDone   // 표 칸은 같은 편집기를 다음 칸으로 옮겨 씀 — 늘 지금 칸의 값으로
  useLayoutEffect(() => {   // 그리기 전에 만들고 포커스 — 두 번 누르자마자 친 글자도 받게
    const finish = move => {
      if (sp.current.armed || done.current) return   // 대기 중 = 아직 고치기 전(바깥 클릭·사라질 때 빈 글로 덮지 않게)
      done.current = true
      try { ed.current.view.domObserver?.flush?.() } catch { /* 없어도 그만 */ }   // 방금 친 글자(화면엔 있고 아직 안 읽힌 것)를 먼저 읽음 — 빠르게 치고 Tab 하면 앞 글자가 빠졌음
      const s = sp.current, { text, runs } = richTextToRuns(ed.current.getJSON(), s.weight || 400)
      const nx = od.current({ text: s.cell ? text.replace(/\n/g, ' ') : text, runs, move: Array.isArray(move) ? move : null })   // 표 칸은 한 줄
      if (s.cell && nx) {   // 표 칸 Tab·Enter — 다시 그리기를 기다리지 않고 그 자리에서 다음 칸 내용으로(빠르게 이어 쳐도 안 섞임)
        firstKey.current = nx.key; done.current = false
        ed.current.commands.setContent(runsToRichText(nx.text, nx.runs, null), { emitUpdate: false }); focusNow(ed.current)
      }
    }
    const cancel = () => { if (sp.current.armed || done.current) return; done.current = true; od.current(null) }
    const editor = new Editor({
      element: host.current,
      extensions: [Document, Paragraph, Text, Bold, TextStyle, Color, BackgroundColor, FontWeight, UndoRedo, Finish.configure({ onDone: finish, onCancel: spec.cell ? cancel : null, onMove: spec.cell ? finish : null, isArmed: () => !!sp.current.armed })],
      content: runsToRichText(spec.text || '', spec.runs, spec.weight && spec.weight !== 400 ? spec.weight : null),
      autofocus: 'end',
      editorProps: { attributes: { spellcheck: 'false' }, handlePaste: () => !!sp.current.armed },   // 대기 중 Ctrl+V = 칠판 붙여넣기(편집기에 글이 숨어 들어가지 않게)
    })
    ed.current = editor
    focusNow(editor)   // 기본 autofocus는 한 박자 늦어 두 번 누르자마자 친 글자가 빠질 수 있음 — 바로
    if (spec.onChange) editor.on('update', () => sp.current.onChange?.(richTextToRuns(editor.getJSON(), sp.current.weight || 400)))   // 치는 동안 칠판에 바로(왼쪽 위 라벨 상자 높이)
    editor.on('update', () => { if (sp.current.armed && editor.getText()) sp.current.onArm?.() })   // 대기 중 글이 들어오면(띄어쓰기 등) 바로 고치기로
    if (spec.pxFor) editor.on('update', () => setPx(sp.current.pxFor(editor.getText())))   // 치는 동안 글자 크기(표 자동 크기 칸 — 칸에 맞춰 줄어듦)
    spec.onReady?.(editor)
    // 고치기를 끝낸 Esc가 칠판까지 가서 칸 고르기마저 풀지 않게(끝내면 그 칸을 고른 채로 — 엑셀). 누른 순간에 고치는 중이었는지로 판단 —
    // 편집기가 Esc를 처리한 뒤엔 화면이 이미 다시 그려져 「대기」로 바뀌어 있음(마이크로태스크 사이에 React가 그림)
    let escWhileEditing = null
    host.current.addEventListener('keydown', e => { if (e.key === 'Escape' && !sp.current.armed) escWhileEditing = e }, true)
    host.current.addEventListener('keydown', e => { if (e === escWhileEditing) e.stopPropagation() })
    const onDown = e => { if (!host.current.contains(e.target) && !e.target.closest?.('[data-keep-edit]')) finish() }   // 「글자」 카드를 누를 땐 계속
    setTimeout(() => window.addEventListener('pointerdown', onDown, true), 0)
    return () => { window.removeEventListener('pointerdown', onDown, true); finish(); spec.onReady?.(null); editor.destroy() }
  }, [])   // eslint-disable-line
  const [px, setPx] = useState(spec.px)
  const wasArmed = useRef(!!spec.armed)
  useLayoutEffect(() => {   // 표 칸 대기(엑셀처럼 칸을 고르면 보이지 않는 편집기가 미리 포커스 — 첫 키부터 한글 입력기가 켜져 있게, 2026-10-18 사용자: 「ㅎ」이 「g」로 들어감)
    const e = ed.current; if (!e) return
    if (spec.armed) { done.current = false; if (e.getText()) e.commands.setContent('', { emitUpdate: false }); focusNow(e) }
    else if (wasArmed.current) {   // 대기 → 고치기: 바로 친 글(fresh)은 그대로 이어 받고, Enter·F2·두 번 누르기는 있는 글을 불러옴
      if (!spec.fresh) { e.commands.setContent(runsToRichText(spec.text || '', spec.runs, spec.weight && spec.weight !== 400 ? spec.weight : null), { emitUpdate: false }); setPx(spec.px) }
      if (!e.view.hasFocus()) focusNow(e)
    }
    wasArmed.current = !!spec.armed
  }, [spec.armed, spec.cellKey])   // eslint-disable-line
  // 표 칸: Tab·Enter로 다음 칸 — 편집기를 새로 만들지 않고 내용만 바꿈(새로 만들면 포커스가 끊겨 바로 친 글자가 사라졌음, 2026-10-18 시험)
  useLayoutEffect(() => {   // 그리기 전에 바꿈 — 바로 이어 친 글자가 옛 칸 내용에 섞이지 않게
    if (!spec.cell || spec.cellKey === firstKey.current || !ed.current) return
    firstKey.current = spec.cellKey; done.current = false
    ed.current.commands.setContent(runsToRichText(spec.text || '', spec.runs, spec.weight && spec.weight !== 400 ? spec.weight : null), { emitUpdate: false })
    focusNow(ed.current); setPx(spec.px)
  }, [spec.cellKey])   // eslint-disable-line
  const m = METRICS[spec.family === 'board' ? 'board' : 'app'], fs = px * spec.zoom
  return <div ref={host} data-testid="text-editor" onPointerDown={e => e.stopPropagation()} onWheel={e => e.stopPropagation()}
    style={{ position: 'absolute', left: spec.center ? spec.center.x : spec.left, top: spec.center ? spec.center.y : spec.top, minWidth: 8, padding: TEXT_MARGIN * spec.zoom, boxSizing: 'border-box',
      transform: spec.center ? 'translate(-50%,-50%)' : spec.rotation ? `rotate(${spec.rotation}deg)` : undefined,   // center = 도형 라벨(가운데 기준)
      transformOrigin: !spec.center && spec.origin ? `${spec.origin.x - spec.left}px ${spec.origin.y - spec.top}px` : undefined,
      fontWeight: spec.weight || 400, fontSize: fs, fontFamily: spec.family === 'board' ? BOARD_FONT : APP_FONT, lineHeight: m.lineSpacing,   // 낱개로(한 줄짜리 font와 섞으면 다시 그릴 때 경고) color: spec.color, textAlign: spec.align || 'left',
      whiteSpace: spec.width && !spec.cell ? 'pre-wrap' : 'pre', width: spec.width, height: spec.height, display: spec.cell ? 'flex' : undefined, alignItems: spec.cell ? 'center' : undefined, justifyContent: spec.cell ? ({ left: 'flex-start', right: 'flex-end' }[spec.align] || 'center') : undefined, overflowWrap: spec.width ? 'anywhere' : undefined, outline: spec.flat || spec.armed ? 'none' : '1.5px solid #89b4fa', background: spec.bg || 'rgba(255,255,255,.9)', zIndex: 20, ...(spec.armed ? { opacity: 0, pointerEvents: 'none' } : {}) }}>
    {/* 고른 글의 색·형광펜이 고른 채로 보이게 — 브라우저 기본 선택은 글자색을 덮음(2026-10-18 사용자: 드래그를 풀어야 바뀐 색이 보임). 바탕만 옅게 */}
    <style>{`[data-testid=text-editor] .ProseMirror{outline:none;white-space:${spec.width ? 'pre-wrap' : 'pre'};overflow-wrap:${spec.width ? 'anywhere' : 'normal'}}[data-testid=text-editor] p{margin:0}[data-testid=text-editor] ::selection{background:rgba(137,180,250,.35)}`}</style>
  </div>
}
