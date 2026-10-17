// 글 편집(2단계) — 칠판 위에 TipTap 편집기를 겹쳐 띄우고, 끝나면 .ecad 글(text + runs)로 돌려준다.
// 글 + runs ↔ TipTap 문서는 이미 시험된 규칙(ecadFormat.js runsToRichText/richTextToRuns) 그대로. 한글 조합 입력은 TipTap(ProseMirror)이 맡는다.
// Enter = 줄바꿈(데스크톱 글 상자와 같음), Esc·Ctrl+Enter·바깥 클릭 = 끝. Ctrl+B = 굵게.
import { useEffect, useRef } from 'react'
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
  addKeyboardShortcuts() { return { Escape: () => { this.options.onDone(); return true }, 'Mod-Enter': () => { this.options.onDone(); return true } } },
  addOptions() { return { onDone: () => {} } },
})

// spec: { left, top (화면 px — 문서 상자 왼쪽 위) 또는 center(화면 px — 도형 라벨 가운데), px(글자 px, 화면 배율 적용 전), zoom, family('app'|'board'), weight, color, align('left'|'center'),
//         rotation, origin(화면 px 회전 중심), text, runs } — onDone({ text, runs })
export function TextEditor({ spec, onDone }) {
  const host = useRef(null), ed = useRef(null), done = useRef(false)
  useEffect(() => {
    const finish = () => {
      if (done.current) return
      done.current = true
      const { text, runs } = richTextToRuns(ed.current.getJSON(), spec.weight || 400)
      onDone({ text, runs })
    }
    const editor = new Editor({
      element: host.current,
      extensions: [Document, Paragraph, Text, Bold, TextStyle, Color, BackgroundColor, FontWeight, UndoRedo, Finish.configure({ onDone: finish })],
      content: runsToRichText(spec.text || '', spec.runs, spec.weight && spec.weight !== 400 ? spec.weight : null),
      autofocus: 'end',
      editorProps: { attributes: { spellcheck: 'false' } },
    })
    ed.current = editor
    const onDown = e => { if (!host.current.contains(e.target)) finish() }
    setTimeout(() => window.addEventListener('pointerdown', onDown, true), 0)
    return () => { window.removeEventListener('pointerdown', onDown, true); finish(); editor.destroy() }
  }, [])   // eslint-disable-line
  const m = METRICS[spec.family === 'board' ? 'board' : 'app'], fs = spec.px * spec.zoom
  return <div ref={host} data-testid="text-editor" onPointerDown={e => e.stopPropagation()} onWheel={e => e.stopPropagation()}
    style={{ position: 'absolute', left: spec.center ? spec.center.x : spec.left, top: spec.center ? spec.center.y : spec.top, minWidth: 8, padding: TEXT_MARGIN * spec.zoom, boxSizing: 'border-box',
      transform: spec.center ? 'translate(-50%,-50%)' : spec.rotation ? `rotate(${spec.rotation}deg)` : undefined,   // center = 도형 라벨(가운데 기준)
      transformOrigin: !spec.center && spec.origin ? `${spec.origin.x - spec.left}px ${spec.origin.y - spec.top}px` : undefined,
      font: `${spec.weight || 400} ${fs}px ${spec.family === 'board' ? BOARD_FONT : APP_FONT}`, lineHeight: m.lineSpacing, color: spec.color, textAlign: spec.align || 'left',
      whiteSpace: 'pre', outline: '1.5px solid #89b4fa', background: 'rgba(255,255,255,.9)', zIndex: 20 }}>
    <style>{`[data-testid=text-editor] .ProseMirror{outline:none;white-space:pre}[data-testid=text-editor] p{margin:0}`}</style>
  </div>
}
