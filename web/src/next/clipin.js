// 바깥에서 복사한 것 붙여넣기(2026-10-21 사용자: 클립보드 글을 바로 칠판에) — 글 생김새를 보고 앱이 모양을 고름. 사용자는 고르지 않는다.
// 짧은 한 줄 = 글자 · 여러 줄 = 메모(마크다운) · 탭 표 = 진짜 표 · 웹·AI 답을 긁은 것(text/html) = 꾸밈 살린 메모 · 엑셀·한글 표 = 진짜 표 · VS Code = 코드 칸.
// 칠판에 넣기는 Editor `pasteOutside`. 여기는 판단만(글 규칙은 순수 — `npm test`, HTML은 브라우저 DOMParser·TipTap).
import { generateJSON } from '@tiptap/core'
import Document from '@tiptap/extension-document'
import Paragraph from '@tiptap/extension-paragraph'
import Text from '@tiptap/extension-text'
import Bold from '@tiptap/extension-bold'
import Code from '@tiptap/extension-code'
import Heading from '@tiptap/extension-heading'
import Blockquote from '@tiptap/extension-blockquote'
import CodeBlock from '@tiptap/extension-code-block'
import HorizontalRule from '@tiptap/extension-horizontal-rule'
import { BulletList, ListItem, OrderedList, TaskItem, TaskList } from '@tiptap/extension-list'
import { Italic, Strike, Underline } from './marks.js'
import { docToLines } from './memo.js'

export const LINE_MAX = 80   // 이보다 짧은 한 줄 = 글자 상자(쪽지). 길면 메모

// 탭으로 나뉜 줄들(엑셀·한글 표 글) → 칸 목록. 표가 아니면 null — 줄 2개 이상 또는 칸 2개 이상, 모든 줄 칸 수가 같아야
export function tsvRows(text) {
  const ls = String(text || '').replace(/\r\n?/g, '\n').replace(/\n+$/, '').split('\n')
  if (!ls.length || !ls.every(l => l.includes('\t'))) return null
  const rows = ls.map(l => l.split('\t').map(c => c.trim())), n = rows[0].length
  return rows.every(r => r.length === n) && n >= 2 ? rows : null
}

// 마크다운 표시가 있나(제목 #·목록·번호·인용·코드 울타리·**굵게**·| 표 |) — AI 웹 「복사」 버튼 글
export const looksMarkdown = text => /^\s{0,3}(#{1,6}\s|[-*]\s|\d+[.)]\s|>\s?|```|\|.*\|\s*$)/m.test(text || '') || /\*\*[^*\n]+\*\*/.test(text || '')

// 글만 있을 때 모양 — 'empty' | 'tsv' | 'line' | 'memo'
export function textKind(text) {
  const t = String(text || '').replace(/\r\n?/g, '\n').trim()
  if (!t) return 'empty'
  if (tsvRows(text)) return 'tsv'
  if (!t.includes('\n') && t.length <= LINE_MAX && !looksMarkdown(t)) return 'line'
  return 'memo'
}

// ── text/html(브라우저 안에서만) ──
// 웹 페이지 색·글꼴은 버린다(어두운 화면 ChatGPT의 흰 글이 메모에서 안 보이지 않게) — 꾸밈은 굵게·기울임·밑줄·취소선·코드·제목·목록만
const EXT = [Document, Paragraph, Text, Bold, Italic, Underline, Strike, Code, Heading.configure({ levels: [1, 2, 3] }), Blockquote, CodeBlock, HorizontalRule,
  BulletList, OrderedList, ListItem, TaskList, TaskItem.configure({ nested: true })]
const MONO = /font-family:[^;"']*(consolas|monospace|courier|menlo|cascadia|d2coding|fira code)/i

// 클립보드 HTML → { tables: [{ rows, header }], lines: 메모 줄(없으면 []), code: 코드 칸으로 볼지 }.
// 글 생김새(꾸밈 태그)가 없으면 null — 그땐 글(text/plain) 규칙으로
export function htmlPlan(html) {
  if (!html || typeof DOMParser === 'undefined') return null
  const d = new DOMParser().parseFromString(html, 'text/html'), body = d.body
  body.querySelectorAll('script,style,meta,link,title').forEach(n => n.remove())
  const tables = []
  for (const tb of [...body.querySelectorAll('table')].filter(t => !t.parentElement?.closest('table'))) {   // 바깥 표만(표 안 표는 칸 글로)
    const rows = [...tb.rows].map(r => [...r.cells].map(c => c.textContent.replace(/\s+/g, ' ').trim()))
    const cols = Math.max(0, ...rows.map(r => r.length))
    if (rows.length * cols >= 2) tables.push({ rows: rows.map(r => Array.from({ length: cols }, (_, i) => r[i] || '')), header: !!tb.querySelector('th') })
    tb.remove()
  }
  const rest = body.textContent.trim()
  if (!rest) return tables.length ? { tables, lines: [], code: false } : null
  const rich = /<(h[1-6]|li|strong|b|em|i|u|s|del|pre|blockquote|code|hr)[\s>]/i.test(body.innerHTML)
  if (MONO.test(html) && !/<(h[1-6]|li|p)[\s>]/i.test(body.innerHTML)) return { tables, lines: [], code: true }   // VS Code 등 = 글 그대로 코드 칸
  if (!rich && !tables.length) return null
  body.querySelectorAll('br').forEach(b => b.replaceWith(d.createTextNode('\n')))
  const lines = docToLines(generateJSON(body.innerHTML, EXT)).filter((l, i, a) => l.t || l.k === 'hr' || (i > 0 && a[i - 1].t))   // 빈 줄은 하나만
  while (lines.length && !lines[lines.length - 1].t && lines[lines.length - 1].k !== 'hr') lines.pop()
  return { tables, lines, code: false }
}
