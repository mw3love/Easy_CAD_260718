// .ecad 도형을 웹 칠판에서 그대로 보이게 하는 도형들.
// - 기본 글(text)·상자(geo): tldraw 것 그대로 쓰되, meta.ecad에 담긴 정확한 색·크기·굵기를 getCustomDisplayValues로 입힌다
//   (tldraw 기본은 정해진 13색·s/m/l/xl 크기뿐이라 보드 디자인이 깨진다).
// - esym: 데스크톱 순서도·안테나 심볼(symbols.json, tools/export_web_symbols.py가 뽑음)과 자유 경로.
// - eboard: 보드 틀(16:9 바탕색) — 안에 놓인 것이 같이 움직이는 frame 성격.
import {
  BaseBoxShapeUtil, BaseFrameLikeShapeUtil, GeoShapeUtil, HTMLContainer, RichTextLabel, Rectangle2d, SVGContainer, T,
  TextShapeUtil, getTipTapDefaultExtensions, resizeBox, toRichText,
} from 'tldraw'
import { Extension } from '@tiptap/core'
import { BackgroundColor, Color, TextStyle } from '@tiptap/extension-text-style'
import SYMBOLS from './symbols.json'

export const BOARD_FONT = "'Pretendard', sans-serif"
export const LINE_HEIGHT = 1.3

// 글 굵기(400·600·800) — tldraw 글 상자는 굵기 표시값을 화면에 안 쓰므로 글 안 textStyle에 담는다(편집·재기·저장 모두 같이 감)
const FontWeight = Extension.create({
  name: 'fontWeight',
  addGlobalAttributes() {
    return [{ types: ['textStyle'], attributes: { fontWeight: {
      default: null, parseHTML: el => el.style.fontWeight || null,
      renderHTML: a => (a.fontWeight ? { style: `font-weight: ${a.fontWeight}` } : {}) } } }]
  },
})
// 글 편집기: tldraw 기본 + 글자 색·글자 배경(형광펜)·굵기 — .ecad `runs`의 부분 색·형광펜을 담는다
export const textOptions = { tipTapConfig: { extensions: [...getTipTapDefaultExtensions(), TextStyle, Color, BackgroundColor, FontWeight] } }

const ec = s => s.meta?.ecad

// 잉크 색 바꿔 그리기 — 데스크톱 어두운 화면에서 그린 흰 선·글자는 밝은 칠판에서 안 보인다(PDF 출력의 "흰 잉크→검정"과 같은 규칙,
// easycad/fileio/pdf_export.py). 어두운 칠판에선 반대로 검정 잉크를 흰색으로. 보드 안은 보드 바탕을 따르므로 그대로.
const near = (c, v) => { const m = /^#([0-9a-f]{6})$/i.exec(c || ''); if (!m) return false
  const n = parseInt(m[1], 16), r = n >> 16, g = (n >> 8) & 255, b = n & 255; return v ? r >= 250 && g >= 250 && b >= 250 : r <= 40 && g <= 40 && b <= 40 }
export function ink(editor, shape, c, mode) {
  if (!c) return c
  const onBoard = editor.getShapeAncestors(shape).some(a => a.type === 'eboard')
  if (onBoard) return c
  mode = mode ?? editor.getColorMode()
  if (mode === 'light' && near(c, true)) return '#1f1f1f'
  if (mode === 'dark' && near(c, false)) return '#f2f2f2'
  return c
}
export const EText = TextShapeUtil.configure({
  showTextOutline: false,   // 글자 둘레 흰 외곽선 — 형광펜 칠한 구절에 테두리처럼 보였다(데스크톱엔 없음)
  getCustomDisplayValues(e, s, _t, mode) {
    const m = ec(s); if (!m) return {}
    return { color: ink(e, s, m.color, mode), fontSize: m.px, fontFamily: m.family ? BOARD_FONT : undefined, fontWeight: String(m.weight ?? 400), lineHeight: LINE_HEIGHT }
  },
})
export const EGeo = GeoShapeUtil.configure({
  getCustomDisplayValues(e, s, _t, mode) {
    const m = ec(s); if (!m) return {}
    const v = { strokeColor: ink(e, s, m.stroke, mode), fillColor: m.fill ?? 'transparent', strokeWidth: m.sw, strokeRoundness: 0 }
    if (m.label) Object.assign(v, { labelColor: ink(e, s, m.label.color, mode), labelFontSize: m.label.px, labelLineHeight: LINE_HEIGHT, labelPadding: m.label.pad ?? 4,   // pad: 대화 카드(chat.jsx)만 넉넉히
      labelEdgeMargin: 0,
      labelFontFamily: m.label.family ? BOARD_FONT : undefined })
    return Object.fromEntries(Object.entries(v).filter(([, x]) => x !== undefined))
  },
})

// 경로 d를 상자(w,h)에 맞춰 늘리기 — fit: stretch(그냥 늘림) / keep(비율 지키고 가운데) / rect(시작/끝·지연: 상자 비율로 다시 그림)
function symbolPath(kind, d, fit, vw, vh, w, h) {
  if (kind === 'terminal') { const r = Math.min(h, w) / 2; return `M${r},0 H${w - r} A${r},${r} 0 0 1 ${w - r},${h} H${r} A${r},${r} 0 0 1 ${r},0 Z` }
  if (kind === 'delay') { const r = Math.min(h / 2, w); return `M0,0 H${w - r} A${r},${r} 0 0 1 ${w - r},${h} H0 Z` }
  return { d, transform: fit === 'keep'
    ? (() => { const k = Math.min(w / vw, h / vh); return `translate(${(w - vw * k) / 2},${(h - vh * k) / 2}) scale(${k})` })()
    : `scale(${w / vw},${h / vh})` }
}

export class ESymUtil extends BaseBoxShapeUtil {
  static type = 'esym'
  static props = { w: T.number, h: T.number, kind: T.string, d: T.string, vw: T.number, vh: T.number,
    stroke: T.string, fill: T.string, sw: T.number, richText: T.any, labelColor: T.string, labelPx: T.number, labelFamily: T.boolean }
  getDefaultProps() { return { w: 120, h: 60, kind: 'process', d: '', vw: 100, vh: 100, stroke: '#1e2b45', fill: 'transparent', sw: 2,
    richText: toRichText(''), labelColor: '#1f1f1f', labelPx: 18, labelFamily: false } }
  canEdit() { return true }
  onResize(s, info) { return resizeBox(s, info) }
  getGeometry(s) { return new Rectangle2d({ width: s.props.w, height: s.props.h, isFilled: s.props.fill !== 'transparent' || !!s.props.d }) }
  component(s) {
    const p = s.props, sym = SYMBOLS[p.kind]
    const path = symbolPath(p.kind, p.d || sym?.d || `M0,0 H100 V100 H0 Z`, p.d ? 'stretch' : sym?.fit, p.d ? p.vw : 100, p.d ? p.vh : 100, p.w, p.h)
    const stroke = ink(this.editor, s, p.stroke)
    const shapeEl = typeof path === 'string'
      ? <path d={path} fill={p.fill} stroke={stroke} strokeWidth={p.sw} />
      : <path d={path.d} transform={path.transform} fill={p.fill} stroke={stroke} strokeWidth={p.sw} vectorEffect="non-scaling-stroke" />
    const isSelected = s.id === this.editor.getOnlySelectedShapeId()
    return <>
      <SVGContainer>{shapeEl}</SVGContainer>
      <RichTextLabel shapeId={s.id} type="esym" fontFamily={p.labelFamily ? BOARD_FONT : 'var(--tl-font-sans)'} fontSize={p.labelPx}
        lineHeight={LINE_HEIGHT} textAlign="center" verticalAlign="middle" richText={p.richText} labelColor={ink(this.editor, s, p.labelColor)}
        isSelected={isSelected} wrap padding={6} bounds={this.editor.getShapeGeometry(s).bounds} />
    </>
  }
  getIndicatorPath(s) { const r = new Path2D(); r.rect(0, 0, s.props.w, s.props.h); return r }
}

export class EBoardUtil extends BaseFrameLikeShapeUtil {
  static type = 'eboard'
  static props = { w: T.number, h: T.number, bg: T.string, name: T.string }
  getDefaultProps() { return { w: 1920, h: 1080, bg: '#ffffff', name: '보드' } }
  canEdit() { return false }
  onResize(s, info) { return resizeBox(s, info) }
  component(s) {
    return <HTMLContainer style={{ background: s.props.bg, boxShadow: '0 1px 10px rgba(0,0,0,.15)', borderRadius: 4 }} />
  }
  getIndicatorPath(s) { const r = new Path2D(); r.rect(0, 0, s.props.w, s.props.h); return r }
}

export const shapeUtils = [EText, EGeo, ESymUtil, EBoardUtil]
