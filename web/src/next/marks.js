// 기울임·밑줄·취소선 표시(TipTap 마크, 2026-10-19 사용자: 노션처럼 드래그해 꾸미기) — 공식 부품(@tiptap/extension-italic 등)은 설치돼 있지 않아
// 같은 뜻을 짧게 직접 만듦. .ecad에는 부분 서식 7번째 칸 deco('i'·'u'·'s')로 저장(ecadFormat.js `richTextToRuns`).
import { Mark } from '@tiptap/core'

const mark = (name, tags, tag, key) => Mark.create({
  name,
  parseHTML() { return tags.map(t => ({ tag: t })) },
  renderHTML() { return [tag, 0] },
  addKeyboardShortcuts() { return { [key]: () => this.editor.commands.toggleMark(this.name) } },
})

export const Italic = mark('italic', ['em', 'i'], 'em', 'Mod-i')
export const Underline = mark('underline', ['u'], 'u', 'Mod-u')
export const Strike = mark('strike', ['s', 'del'], 's', 'Mod-Shift-x')
