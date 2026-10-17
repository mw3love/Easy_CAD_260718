// 세 후보가 똑같이 그리는 한 장 보드 내용(공정 비교용)
export const TITLE = 'Transformer — 어텐션만으로 충분하다'
export const CARDS = [
  [['어텐션', true], [': 모든 단어가 서로를 ', false], ['한 번에', true], [' 본다', false]],
  [['병렬 처리', true], [': 순서대로 안 읽어 학습이 빠르다', false]],
  [['결과', true], [': BLEU ', false], ['28.4', true], [' — 기존 최고보다 높다', false]],
]
export const plain = runs => runs.map(r => r[0]).join('')
// 좌표(보드 1600x900 기준)
export const BOARD = { x: 0, y: 0, w: 1600, h: 900 }
export const CARD_POS = [[80, 200], [580, 200], [1080, 200]]
export const CARD_SIZE = [440, 180]
export const FIG = { x: 600, y: 480, w: 400, h: 250 }
