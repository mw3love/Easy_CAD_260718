// 단축키 글자를 기기에 맞게(2026-11-10 화면 검사 2단계 — 사용자 「맥이면 ⌘로」). 동작은 이미 Ctrl·⌘ 둘 다 받음(`e.ctrlKey || e.metaKey`), 여기는 보이는 글자만.
// 맥·아이폰·아이패드면 Ctrl → ⌘, Alt → ⌥, Shift → ⇧(맥 관례: 「⌘⇧X」처럼 붙여 씀). 윈도우·그 밖은 그대로.
const plat = () => { try { return navigator.userAgentData?.platform || navigator.platform || navigator.userAgent || '' } catch { return '' } }
export const IS_MAC = /Mac|iPhone|iPad|iPod/i.test(plat())
export function keyLabel(s, mac = IS_MAC) {
  if (!mac || typeof s !== 'string') return s
  return s.replace(/Ctrl\+/g, '⌘').replace(/Alt\+/g, '⌥').replace(/Shift\+/g, '⇧')
    .replace(/⌘⇧/g, '⇧⌘').replace(/⌘⌥/g, '⌥⌘')   // 맥 표기 순서 ⌥⇧⌘
    .replace(/\bCtrl\b/g, '⌘').replace(/\bAlt\b/g, '⌥')
}
