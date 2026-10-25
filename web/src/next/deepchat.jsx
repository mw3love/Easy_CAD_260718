// 딥모드 대화창 카드(§8 항목66 3-2, 2026-10-25) — ① 질문지 한 장 ② 지면 계획 카드. 상태는 대화 기록의 답 하나(`kind: 'deep'`)에 — 다시 열어도 그대로.
// 질문지는 서버를 안 부름(왕복 없이 한 번 — 항목64가 버린 「여러 번 묻기」의 예외: 몇 분짜리 비싼 일이라 묻는 값이 쌈). 보기에 없는 말은 기존 입력 칸.
// 계획 카드 = 꼭지(× 빼기) · 예상 크레딧(톤은 만든 뒤 속성 카드 — 2026-10-25 처음 고르기 없앰) → 「이대로 만들기」 전엔 비싼 생성 없음. 말로 고치기 = 입력 칸(chat.jsx가 계획을 다시 짜게 보냄)
import { useState } from 'react'

// [질문, 보기, 여럿 고르기] — 답 꼴은 `tools/deepmode_probe.py` ANSWERS와 같게(3-3 서버가 그대로 지시문에)
export const DEEP_QS = [
  ['누구에게', ['처음 보는 사람', '아는 동료', '윗사람(보고)']],
  ['무엇에', ['공부·교육', '발표', '보고·결정']],
  ['깊이', ['핵심만', '보통', '자세히']],
  ['꼭 넣을 것', ['숫자·그래프', '원리 단계', '직접 눌러 보기', '용어 풀이', '확인 문제'], true],
  ['재료', ['웹 검색', '이 칠판', '둘 다']],
]
export const AUTO = '알아서'
// 보낼 답 — 안 고른 것은 「알아서」, 여럿 고르기는 목록(없으면 「알아서」), 입력 칸 글 = 「더」
export const briefOf = (b = {}, more = '') => ({ ...Object.fromEntries(DEEP_QS.map(([q, , multi]) => [q, multi ? (b[q]?.length ? b[q] : AUTO) : b[q] || AUTO])), ...(more ? { 더: more } : {}) })
const SOURCE = { ai: 'AI 설명', web: '웹 검색', kr: '공공 데이터', image: '그림', board: '이 칠판' }
export const keptPlan = m => ({ ...m.plan, sections: (m.plan.sections || []).filter((_, i) => !(m.drop || []).includes(i)) })   // × 뺀 꼭지 빼고

// 질문지 — m = { topic, brief, done }. set(질문, 값) · go() = 「지면 계획 짜기」(입력 칸 글을 「더」로 같이)
export function DeepAsk({ m, set, go, busy, css }) {
  const b = m.brief || {}, lock = !!m.done || !!busy
  return <div data-testid="deep-ask" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <div style={{ fontWeight: 700 }}>「{m.topic}」 — 한 판을 짜기 전에 몇 가지만</div>
    {DEEP_QS.map(([q, opts, multi]) => { const cur = b[q], on = v => (multi ? (cur || []).includes(v) : (cur || AUTO) === v)
      const pick = v => set(q, multi ? (on(v) ? (cur || []).filter(x => x !== v) : [...(cur || []), v]) : v)
      return <div key={q} data-q={q} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={css.meta}>{q}{multi ? ' (여럿 · 안 고르면 알아서)' : ''}</span>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {(multi ? opts : [AUTO, ...opts]).map(v => <button key={v} data-v={v} aria-pressed={on(v)} disabled={lock} onClick={() => pick(v)}
            style={{ ...(on(v) ? css.pin : css.ghost), ...(on(v) ? { background: 'rgba(218,119,86,.12)' } : null), opacity: lock && !on(v) ? 0.5 : 1, cursor: lock ? 'default' : 'pointer' }}>{v}</button>)}
        </div></div> })}
    {m.done ? <span style={css.meta}>{m.more ? `덧붙인 말: ${m.more} · ` : ''}이 답으로 지면 계획을 짰어요</span>
      : <><span style={css.meta}>보기에 없는 말(꼭 넣을 것·빼 줄 것)은 아래 칸에 적고 Enter — 계획만 짜요(약 40크레딧·20초, 만들기는 계획을 보고 나서)</span>
        <button data-testid="deep-plan-go" style={{ ...css.pin, alignSelf: 'flex-start', padding: '4px 12px' }} disabled={!!busy} onClick={go}>지면 계획 짜기</button></>}
  </div>
}

// 지면 계획 — m = { plan, drop, estimate: { credits: [lo, hi], seconds: [lo, hi] }, built, pages, stale }
// drop(i) · build() · show() = 지은 판으로
export function DeepPlan({ m, drop, build, show, busy, css }) {
  const secs = m.plan?.sections || [], dropped = new Set(m.drop || []), left = secs.length - dropped.size, lock = !!m.built || !!m.stale || !!busy
  const est = m.estimate, rng = (a, u) => (Array.isArray(a) ? (a[0] === a[1] ? `${a[0]}${u}` : `${a[0]}~${a[1]}${u}`) : a != null ? `${a}${u}` : '')
  return <div data-testid="deep-plan" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <div><div style={{ fontWeight: 700 }}>{m.plan?.title || '지면 계획'}</div>{m.plan?.headline && <div style={css.meta}>{m.plan.headline}</div>}</div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {secs.map((s, i) => <div key={i} data-testid="deep-sec" data-dropped={dropped.has(i) ? '1' : undefined} style={{ display: 'flex', gap: 6, alignItems: 'center', opacity: dropped.has(i) ? 0.4 : 1 }}>
        <span style={{ ...css.kind, flex: 'none', ...(s.size === '주인공' ? { color: '#da7756', background: 'rgba(218,119,86,.12)' } : null) }}>{s.shape}</span>
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: dropped.has(i) ? 'line-through' : 'none' }} title={s.question || s.title}>{s.title}</span>
        <span style={{ ...css.meta, flex: 'none' }}>{s.shape === '출처 카드' ? '모은 출처' : s.shape === '요약 그림' ? 'AI 그림 · 판 내용으로' : SOURCE[s.source] || s.source || ''}</span>
        {!lock && <button data-testid="deep-sec-x" aria-label={dropped.has(i) ? `「${s.title}」 되살리기` : `「${s.title}」 빼기`} title={dropped.has(i) ? '되살리기' : '이 꼭지 빼기'}
          disabled={!dropped.has(i) && left <= 3} onClick={() => drop(i)} style={{ ...css.ghost, padding: '0 6px', flex: 'none' }}>{dropped.has(i) ? '↺' : '×'}</button>}
      </div>)}
    </div>
    {m.built ? <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <button data-testid="deep-show" style={css.done} onClick={show}>✓ 칠판에 지었어요{m.pages > 1 ? ` · ${m.pages}장` : ''} — 보기</button>
        <span style={css.meta}>판을 고르면 톤(색)·꼭지 모양을 바꿀 수 있어요</span>
        {m.missing && <span data-testid="deep-missing" style={css.meta}>그대로 둔 꼭지(못 씀): {m.missing.join(', ')} — 그 꼭지를 골라 다시 쓸 수 있어요</span>}</div>
      : m.stale ? <span style={css.meta}>아래에 고친 계획이 있어요</span>
      : <><button data-testid="deep-build" style={{ ...css.pin, alignSelf: 'flex-start', padding: '4px 12px' }} disabled={!!busy} onClick={build}>
          이대로 만들기{est ? ` · 약 ${rng(est.credits, '크레딧')}` : ''}</button>
        <span style={css.meta}>{est?.seconds ? `${rng(est.seconds, '초')} 걸려요(추정) · ` : ''}꼭지 {left}개 · 고칠 점은 아래 칸에 말하면 계획을 다시 짜요</span></>}
  </div>
}

// 꼭지 다시 쓰기(5단계) — 판 꼭지를 고른 채 이런 말 = 그 꼭지만 다시(묻는 말은 보통 대화 — 질문 하나에 꼭지가 바뀌면 안 됨). 「정리해」는 정리 문서·정돈 길이라 뺌
export const REDO_RE = /자세히|자세하게|바꿔|바꾸|고쳐|고치|다시|넣어|추가|더해|보태|빼|지워|없애|줄여|늘려|채워|쉽게|짧게|길게|간단|단순|표로|그래프로|숫자로|예시|더\s|덜\s/

// 덮어쓰기 확인 — m = { titles, ask, done }. 판을 손으로 고친 뒤면 다시 지을 때 덮어써서, 크레딧을 쓰기 전에 한 번 물음(속성 카드 「디자인」과 같은 생각)
export function DeepConfirm({ m, busy, css, yes, no }) {
  return <div data-testid="deep-confirm-chat" style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
    <span>이 판에 손으로 고친 것이 있어요. {m.titles.map(t => `「${t}」`).join(' ')}를 다시 쓰면 판을 다시 지어서 손으로 고친 것을 덮어써요(Ctrl+Z로 되돌릴 수 있어요).</span>
    {m.done ? <span style={css.meta}>{m.done === 'no' ? '그대로 뒀어요' : '덮어쓰고 다시 썼어요'}</span>
      : <div style={{ display: 'flex', gap: 6 }}>
        <button data-testid="deep-confirm-chat-yes" style={css.pin} disabled={!!busy} onClick={yes}>덮어쓰고 다시 쓰기</button>
        <button style={css.ghost} disabled={!!busy} onClick={no}>그대로</button></div>}
  </div>
}

// 꼭지 다시 쓰기 전·후(2026-10-25 사용자 「바로 교체라 비교가 어려움」) — 판을 그 자리에서 원래 것 ↔ 바꾼 것으로 번갈아 다시 지음(Editor `deepFlip`).
// 그 판의 마지막 다시 쓰기 답에만, 이 창에서 다시 쓴 것만(새로고침하면 기억이 없어 안 보임). 지금 어느 쪽인지는 누를 때마다 판에서 다시 봄(Ctrl+Z와 섞여도 맞게)
export function DeepFlip({ ed, root, last, css }) {
  const [, tick] = useState(0), [note, setNote] = useState('')
  const now = last ? ed.current?.deepFlipState?.(root) : null
  if (!now) return null
  const go = () => { const r = ed.current?.deepFlip(root); setNote(r === 'edited' ? '판을 손으로 고친 뒤라 안 바꿨어요(Ctrl+Z로 되돌려요)' : ''); tick(n => n + 1) }
  return <div style={{ display: 'flex', gap: 6, alignItems: 'center', marginTop: 6, flexWrap: 'wrap' }}>
    <button data-testid="deep-flip" data-now={now} style={css.pin} onClick={go} title="판을 그 자리에서 다시 지어 원래 것과 바꾼 것을 번갈아 봐요(크레딧 없음)">
      {now === 'after' ? '↺ 원래대로 보기' : '↻ 바꾼 것 보기'}</button>
    <span style={css.meta}>{note || (now === 'after' ? '지금 칠판 = 바꾼 것' : '지금 칠판 = 원래 것')}</span>
  </div>
}
