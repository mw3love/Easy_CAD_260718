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
// Deep Mode 모양(2026-11-04 입구 합치기) — [메시지 kind, 이름, 설명]
export const SHAPES = [['deep', '📰 한 판', '신문 지면처럼 한 화면에 — 읽는 자료'], ['slides', '📖 여러 장', '작은 책·발표 자료 — 글 장·그림 장을 한 장씩']]
// 📽 발표 자료(§8 항목69, 2026-10-28) 질문지 — 같은 카드(`DeepAsk qs=`), 답은 서버 `slides.make_plan`이 그대로 지시문에
export const SLIDES_QS = [
  ['장 수', ['5장', '8장', '12장']],
  ['듣는 사람', ['처음 보는 사람', '아는 동료', '윗사람(보고)']],
  ['발표 시간', ['5분', '10분', '20분']],
  ['재료', ['고른 자료', '웹 검색', '둘 다']],
  ['그림 장', ['없음', '조금', '반쯤', '전부']],   // 장 전체가 그림 한 장(2026-11-04 사용자 「작은 책」 ① — 글 장과 그림 장 섞기, 서버 `slides.PLANNER` pic)
]
// 보낼 답 — 안 고른 것은 「알아서」, 여럿 고르기는 목록(없으면 「알아서」), 입력 칸 글 = 「더」
export const briefOf = (b = {}, more = '', qs = DEEP_QS) => ({ ...Object.fromEntries(qs.map(([q, , multi]) => [q, multi ? (b[q]?.length ? b[q] : AUTO) : b[q] || AUTO])), ...(more ? { 더: more } : {}) })
const SOURCE = { ai: 'AI 설명', web: '웹 검색', kr: '공공 데이터', image: '그림', board: '이 칠판' }
export const keptPlan = m => ({ ...m.plan, sections: (m.plan.sections || []).filter((_, i) => !(m.drop || []).includes(i)) })   // × 뺀 꼭지 빼고

// 질문지 — m = { topic, brief, done }. set(질문, 값) · go() = 「지면 계획 짜기」(입력 칸 글을 「더」로 같이)
// shape = 모양 바꾸기(한 판 ↔ 여러 장 — 2026-11-04 입구 합치기, 대화창 「+ › Deep Mode」에서 온 질문지만) — 누르면 그 모양의 질문지로
export function DeepAsk({ m, set, go, busy, css, qs = DEEP_QS, slides = false, shape = null }) {
  const b = m.brief || {}, lock = !!m.done || !!busy
  return <div data-testid="deep-ask" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    {shape && <div data-testid="deep-shape" style={{ display: 'flex', gap: 6 }}>
      {SHAPES.map(([k, name, tip]) => { const on = (slides ? 'slides' : 'deep') === k
        return <button key={k} data-v={k} aria-pressed={on} disabled={lock} onClick={() => !on && shape(k)} title={tip}
          style={{ ...(on ? css.pin : css.ghost), ...(on ? { background: 'rgba(218,119,86,.12)' } : null), flex: 1, padding: '6px 8px', display: 'flex', flexDirection: 'column', alignItems: 'flex-start', gap: 1, textAlign: 'left', cursor: lock ? 'default' : 'pointer' }}>
          <span style={{ fontWeight: 700 }}>{name}</span><span style={{ ...css.meta, fontWeight: 400, whiteSpace: 'normal' }}>{tip}</span></button> })}
    </div>}
    <div style={{ fontWeight: 700 }}>「{m.topic}」 — {slides ? '발표 자료를 짜기 전에 몇 가지만' : '한 판을 짜기 전에 몇 가지만'}</div>
    {slides && m.ctxCount > 0 && <span style={css.meta}>칠판에서 고른 것 {m.ctxCount}개를 재료로 같이 보내요</span>}
    {qs.map(([q, opts, multi]) => { const cur = b[q], on = v => (multi ? (cur || []).includes(v) : (cur || AUTO) === v)
      const pick = v => set(q, multi ? (on(v) ? (cur || []).filter(x => x !== v) : [...(cur || []), v]) : v)
      return <div key={q} data-q={q} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
        <span style={css.meta}>{q}{multi ? ' (여럿 · 안 고르면 알아서)' : ''}</span>
        <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {(multi ? opts : [AUTO, ...opts]).map(v => <button key={v} data-v={v} aria-pressed={on(v)} disabled={lock} onClick={() => pick(v)}
            style={{ ...(on(v) ? css.pin : css.ghost), ...(on(v) ? { background: 'rgba(218,119,86,.12)' } : null), opacity: lock && !on(v) ? 0.5 : 1, cursor: lock ? 'default' : 'pointer' }}>{v}</button>)}
        </div></div> })}
    {m.done ? <span style={css.meta}>{m.more ? `덧붙인 말: ${m.more} · ` : ''}이 답으로 {slides ? '장 계획' : '지면 계획'}을 짰어요</span>
      : <><span style={css.meta}>보기에 없는 말(꼭 넣을 것·빼 줄 것)은 아래 칸에 적고 Enter — 계획만 짜요({slides ? '약 10크레딧·15초' : '약 40크레딧·20초'}, 만들기는 계획을 보고 나서)</span>
        <button data-testid="deep-plan-go" style={{ ...css.pin, alignSelf: 'flex-start', padding: '4px 12px' }} disabled={!!busy} onClick={go}>{slides ? '장 계획 짜기' : '지면 계획 짜기'}</button></>}
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
        <span style={{ ...css.kind, flex: 'none', ...(s.size === '주인공' ? { color: 'var(--mb-accent)', background: 'rgba(218,119,86,.12)' } : null) }}>{s.shape}</span>
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

// 📽 발표 자료 장 계획(§8 항목69) — m = { plan: { title, slides: [{ title, point, source }] }, drop, estimate, built, frames, stale }. drop(i) · build() · show()
// 장의 그림 상태 — false = 글 장 · true = 그림 장 · 'both' = 글 장 + 아래 그림 판(작은 책 ② 갈래). m.pics = 🖼로 바꾼 장 {번호: 상태}
export const picOf = (m, i) => (m.pics && i in m.pics ? m.pics[i] : m.plan?.slides?.[i]?.pic || false)
export const nextPic = v => (v === false ? true : v === true ? 'both' : false)
export const keptSlides = m => ({ ...m.plan, slides: (m.plan.slides || []).map((s, i) => ({ ...s, pic: picOf(m, i) })).filter((_, i) => !(m.drop || []).includes(i)) })
const PIC_CREDITS = 12   // 그림 장 한 장(서버 `slides.PIC_CREDITS` — 2026-11-04 실측 11.22)
export function SlidesPlan({ m, flip, drop, build, show, busy, css }) {
  const sl = m.plan?.slides || [], dropped = new Set(m.drop || []), left = sl.length - dropped.size, lock = !!m.built || !!m.stale || !!busy
  const drawn = v => (v ? 1 : 0), extra = Object.keys(m.pics || {}).map(Number).filter(i => !dropped.has(i)).reduce((a, i) => a + (drawn(picOf(m, i)) - drawn(sl[i]?.pic)) * PIC_CREDITS, 0)   // 🖼 바꾼 만큼 어림을 고침
  const est = m.estimate && { ...m.estimate, credits: m.estimate.credits?.map(c => Math.max(0, c + extra)) }, rng = (a, u) => (Array.isArray(a) ? `${a[0]}~${a[1]}${u}` : '')
  const live = sl.map((_, i) => i).filter(i => !dropped.has(i)), pics = live.filter(i => picOf(m, i) === true).length, both = live.filter(i => picOf(m, i) === 'both').length
  return <div data-testid="slides-plan" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <div style={{ fontWeight: 700 }}>{m.plan?.title || '장 계획'}</div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {sl.map((s, i) => <div key={i} data-testid="slides-row" data-dropped={dropped.has(i) ? '1' : undefined} style={{ display: 'flex', gap: 6, alignItems: 'center', opacity: dropped.has(i) ? 0.4 : 1 }}>
        <span style={{ ...css.kind, flex: 'none', minWidth: 22, textAlign: 'center' }}>{i + 1}</span>
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: dropped.has(i) ? 'line-through' : 'none' }} title={s.point || s.title}>{s.title}</span>
        <span style={{ ...css.meta, flex: 'none' }}>{SOURCE[s.source] || ''}</span>
        {/* 🖼 = 누를 때마다 글 → 그림 → 글+그림(아래에 그림 판 — 작은 책 ② 갈래). 켜짐 = 코랄 테두리. 표지(첫 장)는 글 장만 */}
        {i > 0 && (v => <button data-testid="slides-pic" data-pic={String(v)} aria-pressed={!!v} disabled={lock || dropped.has(i)} onClick={() => flip(i)}
          title={v === true ? '그림 장 — 장 전체가 설명 그림 한 장(누르면 글+그림)' : v === 'both' ? '글+그림 — 글 장 아래에 같은 내용의 그림 판(발표 때 둘 다, 프레임 판에서 하나 끌 수 있어요 · 누르면 글 장)' : '글 장 — 누르면 그림 장(설명 그림 한 장, 약 12크레딧)'}
          style={{ ...(v ? css.pin : css.ghost), padding: '0 5px', flex: 'none', opacity: v ? 1 : 0.55, cursor: lock ? 'default' : 'pointer' }}>{v === 'both' ? '글+🖼' : '🖼'}</button>)(picOf(m, i))}
        {!lock && <button data-testid="slides-x" aria-label={dropped.has(i) ? `「${s.title}」 되살리기` : `「${s.title}」 빼기`} title={dropped.has(i) ? '되살리기' : '이 장 빼기'}
          disabled={!dropped.has(i) && left <= 2} onClick={() => drop(i)} style={{ ...css.ghost, padding: '0 6px', flex: 'none' }}>{dropped.has(i) ? '↺' : '×'}</button>}
      </div>)}
    </div>
    {m.built ? <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <button data-testid="slides-show" style={css.done} onClick={show}>✓ 프레임 {m.frames}장을 지었어요 — 보기</button>
        <span style={css.meta}>위 막대 「발표」로 바로 · 장마다 아래 회색 메모 = 발표자 메모(발표 화면엔 안 나옴)</span></div>
      : m.stale ? <span style={css.meta}>아래에 고친 계획이 있어요</span>
      : <><button data-testid="slides-build" style={{ ...css.pin, alignSelf: 'flex-start', padding: '4px 12px' }} disabled={!!busy} onClick={build}>
          이대로 만들기{est ? ` · 약 ${rng(est.credits, '크레딧')}` : ''}</button>
        <span style={css.meta}>{est?.seconds ? `${rng(est.seconds, '초')} 걸려요(추정) · ` : ''}{left}장{pics || both ? `(${[pics && `그림 장 ${pics}`, both && `글+그림 ${both}`].filter(Boolean).join(' · ')})` : ''} · 🖼 = 글 → 그림 → 글+그림 · 고칠 점은 아래 칸에 말하면 계획을 다시 짜요</span></>}
  </div>
}
