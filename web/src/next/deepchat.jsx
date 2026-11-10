// 딥모드 대화창 카드(§8 항목66 3-2, 2026-10-25) — ① 질문지 한 장 ② 지면 계획 카드. 상태는 대화 기록의 답 하나(`kind: 'deep'`)에 — 다시 열어도 그대로.
// 질문지는 한 번에 한 장(항목64가 버린 「여러 번 묻기」의 예외: 몇 분짜리 비싼 일이라 묻는 값이 쌈) — 2026-11-06부터 질문은 서버가 주제 글을 읽고 맞춤(`brief_ask`, 몇 초), 못 하면 고정 질문. 보기에 없는 말은 기존 입력 칸.
// 계획 카드 = 꼭지(× 빼기) · 예상 크레딧(톤은 만든 뒤 속성 카드 — 2026-10-25 처음 고르기 없앰) → 「이대로 만들기」 전엔 비싼 생성 없음. 말로 고치기 = 입력 칸(chat.jsx가 계획을 다시 짜게 보냄)
import { useEffect, useState } from 'react'

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
export const SHAPES = [['deep', '📰 한 판', '신문 지면처럼 한 화면에 — 읽는 자료'], ['slides', '📖 여러 장', '작은 책·슬라이드 — 글 장·그림 장을 한 장씩']]
// 📽 발표 자료(§8 항목69, 2026-10-28) 질문지 — 같은 카드(`DeepAsk qs=`), 답은 서버 `slides.make_plan`이 그대로 지시문에
export const SLIDES_QS = [
  ['내용', ['설명', '이야기']],   // 이야기 = 동화처럼 장면이 이어지는 책 — 그림 장이 첫 그림을 참고로 같은 인물·장소(작은 책 ⑤, 서버 `slides.is_story` — 그림 값 약 2배)
  ['장 수', ['5장', '8장', '12장']],
  ['듣는 사람', ['처음 보는 사람', '아는 동료', '윗사람(보고)']],
  ['발표 시간', ['5분', '10분', '20분']],
  ['재료', ['고른 자료', '웹 검색', '둘 다']],
  ['그림 장', ['없음', '조금', '반쯤', '전부']],   // 장 전체가 그림 한 장(2026-11-04 사용자 「작은 책」 ① — 글 장과 그림 장 섞기, 서버 `slides.PLANNER` pic · 알아서 = 표지 빼고 모두, 2026-11-06)
]
// 보낼 답 — 안 고른 것은 「알아서」, 여럿 고르기는 목록(없으면 「알아서」), 입력 칸 글 = 「더」
export const briefOf = (b = {}, more = '', qs = DEEP_QS) => ({ ...Object.fromEntries(qs.map(([q, , multi]) => [q, multi ? (b[q]?.length ? b[q] : AUTO) : b[q] || AUTO])), ...(more ? { 더: more } : {}) })
// 맞춤 질문(2026-11-06 사용자 「프롬프트를 읽고 맞춤으로 — 대상을 썼는데 또 물음」) — 서버 `brief_ask`가 주제 글을 읽고 { known, audience, questions }.
// 화면 = 알아들은 것(회색 칩) + 맞춤 질문 + 아래 설정(코드가 값으로 쓰는 것 — 장 수·그림 장·재료·내용·깊이). 못 만들면 옛 고정 질문(`DEEP_QS`·`SLIDES_QS`)
export const DEEP_SET = DEEP_QS.filter(([q]) => ['깊이', '재료'].includes(q))
export const SLIDES_SET = SLIDES_QS.filter(([q]) => ['내용', '장 수', '재료', '그림 장'].includes(q))
export const askQs = (m, slides) => (m.ai?.questions?.length ? [...m.ai.questions.map(x => [x.q, x.options, !!x.multi, x.h]), ...(slides ? SLIDES_SET : DEEP_SET)] : m.asking ? (slides ? SLIDES_SET : DEEP_SET) : slides ? SLIDES_QS : DEEP_QS)   // 정리하는 동안 = 설정만(고정 질문이 떴다 바뀌지 않게) · 넷째 = 탭 이름(맞춤 질문만)
// 서버에 보낼 답 = 질문 답 + 알아들은 것(「누구에게」 = 딥모드 본문이 독자로 읽음 — 질문으로 물었으면 그 답이 이김)
export const askBrief = (m, more, slides) => { const b = briefOf(m.brief, more, askQs(m, slides)), ai = m.ai
  if (!ai) return b
  return { ...(ai.known?.length ? { '주제에서 알아들은 것': ai.known.map(k => `${k.label}: ${k.value}`).join(' · ') } : {}), ...(ai.audience ? { 누구에게: ai.audience } : {}), ...b } }
const SOURCE = { ai: 'AI 설명', web: '웹 검색', kr: '공공 데이터', image: '그림', board: '이 칠판' }
export const keptPlan = m => ({ ...m.plan, sections: (m.plan.sections || []).filter((_, i) => !(m.drop || []).includes(i)) })   // × 뺀 꼭지 빼고

// 질문지 — m = { topic, brief, done }. set(질문, 값) · go() = 「지면 계획 짜기」(입력 칸 글을 「더」로 같이)
// shape = 모양 바꾸기(한 판 ↔ 여러 장 — 2026-11-04 입구 합치기, 대화창 「+ › Deep Mode」에서 온 질문지만) — 누르면 그 모양의 질문지로
// 2026-11-07 대화창 디자인 1~3라운드 확정(사용자 — Claude Code 질문창처럼, 설명 문구 없이 「질문이 가장 잘, 다음이 선택지」):
// 위 탭 = 맞춤 질문(이름 = AI가 준 짧은 이름) + ⚙ 설정(코드가 값으로 쓰는 것) + ✓ 확인 · 지금 탭의 질문 하나만 · 하나 고르기는 고르면 다음 탭 ·
// 끝 칸 「직접 적기」(하나 고르기 = 그 글이 답, 여럿 = 고른 것 + 글) · 고른 것 = 회색 채움 ✓, 단추만 코랄 채움(K1) · 「계획 짜기」는 늘 보임(다 알아서면 바로)
const PICK = { background: 'var(--mb-pick)', border: '1px solid transparent', color: 'var(--mb-ink)', fontWeight: 700 }
export const GO = { all: 'unset', cursor: 'pointer', alignSelf: 'flex-start', background: 'var(--mb-accent)', color: '#fff', font: "700 12.5px 'Pretendard', sans-serif", padding: '5px 14px', borderRadius: 7 }
const answerText = (v) => (Array.isArray(v) ? (v.length ? v.join(', ') : AUTO) : v || AUTO)
export function DeepAsk({ m, set, go, busy, css, slides = false, shape = null, cost = '' }) {   // m.pic = 인포그래픽 질문지(2026-11-08 — 대화창 「한 판」 대신 그림 한 장), cost = KAIROS 기능 표 어림(`/api/models` features)
  const b = m.brief || {}, lock = !!m.done || !!busy, qs = askQs(m, slides)
  const setNames = new Set((slides ? SLIDES_SET : DEEP_SET).map(([q]) => q))
  const content = qs.filter(([q]) => !setNames.has(q)), settings = qs.filter(([q]) => setNames.has(q))
  const tabs = [...content.map(([q, , , h]) => ({ id: q, label: h || q })), ...(settings.length ? [{ id: 'set', label: '⚙ 설정' }] : []), { id: 'review', label: '✓ 확인' }]
  const [tab, setTab] = useState(0), cur = tabs[Math.min(tab, tabs.length - 1)], next = () => setTab(t => Math.min(t + 1, tabs.length - 1))
  useEffect(() => { setTab(0) }, [slides])   // 한 판 ↔ 여러 장 = 첫 탭부터
  const answered = q => { const v = b[q]; return Array.isArray(v) ? v.length > 0 : !!v && v !== AUTO }
  if (m.done) return <div data-testid="deep-ask" style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
    {qs.filter(([q]) => answered(q)).map(([q, , , h]) => <div key={q} style={{ display: 'flex', gap: 8, fontSize: 12.5 }}><span style={{ ...css.meta, fontSize: 12, flex: 'none' }}>{h || q}</span><b>{answerText(b[q])}</b></div>)}
    <span style={css.meta}>{m.more ? `덧붙인 말: ${m.more} · ` : ''}{m.pic ? '이 답으로 조사해서 그림을 그렸어요' : `이 답으로 ${slides ? '장 계획' : '지면 계획'}을 짰어요`}</span></div>
  const chip = (q, v, on, onClick) => <button key={v} data-v={v} aria-pressed={on} disabled={lock} onClick={onClick}
    style={{ ...css.ghost, ...(on ? PICK : null), cursor: lock ? 'default' : 'pointer' }}>{on ? `✓ ${v}` : v}</button>
  // 질문 하나 — rows = 번호 줄(맞춤 질문) / 칩(설정)
  const question = ([q, opts, multi], rows) => {
    const v = b[q], picks = multi ? (v || []).filter(x => opts.includes(x)) : v, own = multi ? (v || []).filter(x => !opts.includes(x)).join(', ') : v && v !== AUTO && !opts.includes(v) ? v : ''
    const isOn = x => (multi ? picks.includes(x) : (v || AUTO) === x)
    const pick = x => { if (multi) set(q, isOn(x) ? (v || []).filter(y => y !== x) : [...(v || []), x]); else { set(q, x); if (rows) next() } }
    const all = multi ? opts : [AUTO, ...opts]
    if (!rows) return <div key={q} data-q={q} style={{ display: 'flex', flexDirection: 'column', gap: 3 }}><span style={css.meta}>{q}</span>
      <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>{all.map(x => chip(q, x, isOn(x), () => pick(x)))}</div></div>
    return <div key={q} data-q={q} style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
      <div style={{ font: "800 15px/1.4 'Pretendard', sans-serif" }}>{q}{multi && <span style={{ ...css.meta, marginLeft: 6 }}>여럿</span>}</div>
      {all.map((x, i) => <button key={x} data-v={x} aria-pressed={isOn(x)} disabled={lock} onClick={() => pick(x)} className="mb-mi"
        style={{ all: 'unset', cursor: lock ? 'default' : 'pointer', display: 'flex', gap: 8, alignItems: 'baseline', padding: '6px 9px', borderRadius: 7, font: "400 13.5px 'Pretendard', sans-serif", ...(isOn(x) ? { background: 'var(--mb-pick)', fontWeight: 700 } : null) }}>
        <span style={{ ...css.meta, fontWeight: 700, width: 14, flex: 'none' }}>{i + 1}</span>{isOn(x) ? `✓ ${x}` : x}</button>)}
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', padding: '2px 9px' }}><span style={{ ...css.meta, fontWeight: 700, width: 14, flex: 'none' }}>{all.length + 1}</span>
        <input data-testid="ask-own" className="mb-field" key={q} defaultValue={own} disabled={lock} placeholder="직접 적기…" aria-label={`${q} — 직접 적기`}
          onChange={e => { const t = e.target.value.trim(); set(q, multi ? [...picks, ...(t ? [t] : [])] : t || AUTO) }}
          onKeyDown={e => { if (e.key === 'Enter') { e.preventDefault(); e.stopPropagation(); next() } }}
          style={{ flex: 1, minWidth: 0, font: "400 13px 'Pretendard', sans-serif", color: 'var(--mb-ink)', background: 'transparent', border: 0, borderBottom: '1px solid var(--mb-line)', padding: '3px 0', outline: 'none' }} /></div>
      {multi && <button data-testid="ask-next" style={{ ...css.ghost, alignSelf: 'flex-start' }} disabled={lock} onClick={next}>다음</button>}
    </div>
  }
  return <div data-testid="deep-ask" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <style>{'.mb-mi:hover:not(:disabled){background:var(--mb-seg)}@keyframes mb-spin{to{transform:rotate(360deg)}}'}</style>
    {shape && <div data-testid="deep-shape" style={{ display: 'flex', gap: 6 }}>
      {SHAPES.map(([k, name]) => { const on = (slides ? 'slides' : 'deep') === k
        return <button key={k} data-v={k} aria-pressed={on} disabled={lock} onClick={() => !on && shape(k)} style={{ ...css.ghost, ...(on ? PICK : null), flex: 1, cursor: lock ? 'default' : 'pointer' }}>{name}</button> })}
    </div>}
    {m.ctxCount > 0 && <span style={css.meta}>칠판에서 고른 것 {m.ctxCount}개를 재료로 같이 보내요</span>}
    {m.asking && <div data-testid="deep-asking" style={{ ...css.meta, display: 'flex', gap: 6, alignItems: 'center' }}><span style={{ display: 'inline-block', width: 10, height: 10, borderRadius: '50%', border: '2px solid currentColor', borderTopColor: 'transparent', animation: 'mb-spin .8s linear infinite' }} />질문 정리 중…</div>}
    {m.askFail && <span data-testid="deep-ask-fallback" hidden />}
    <div role="tablist" style={{ display: 'flex', gap: 2, flexWrap: 'wrap', borderBottom: '1px solid var(--mb-line)', paddingBottom: 6 }}>
      {tabs.map((t, i) => { const now = t === cur, done = t.id !== 'set' && t.id !== 'review' && answered(t.id)
        return <button key={t.id} role="tab" data-testid="ask-tab" data-tab={t.id} aria-selected={now} onClick={() => setTab(i)} className="mb-mi"
          style={{ all: 'unset', cursor: 'pointer', display: 'flex', gap: 4, alignItems: 'center', font: "600 11.5px 'Pretendard', sans-serif", padding: '3px 8px', borderRadius: 6, color: now ? 'var(--mb-ink)' : 'var(--mb-muted)', ...(now ? { background: 'var(--mb-pick)' } : null) }}>
          {t.id !== 'set' && t.id !== 'review' && <span aria-hidden style={{ width: 9, height: 9, borderRadius: 3, border: '1.5px solid currentColor', ...(done ? { background: 'currentColor' } : null) }} />}{t.label}</button> })}
    </div>
    {cur.id === 'set' ? settings.map(x => question(x, false))
      : cur.id === 'review' ? <div data-testid="ask-review" style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
          {[...content, ...settings].map(([q, , , h]) => <div key={q} style={{ display: 'flex', gap: 8, fontSize: 12.5 }}><span style={{ ...css.meta, fontSize: 12, width: 72, flex: 'none' }}>{h || q}</span><b>{answerText(b[q])}</b></div>)}</div>
      : question(content.find(([q]) => q === cur.id), true)}
    <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
      <button data-testid="deep-plan-go" style={{ ...GO, ...(busy || m.asking ? { opacity: 0.5, cursor: 'default' } : null) }} disabled={!!busy || !!m.asking} onClick={go}>{m.pic ? '그림 만들기' : slides ? '장 계획 짜기' : '지면 계획 짜기'}</button>
      <span style={css.meta}>{cost || (slides ? '약 10크레딧' : '약 40크레딧')}</span></div>
  </div>
}

// 만들기 전 크레딧 확인(계획 ④, 2026-11-08 사용자 「크레딧을 기반으로 거꾸로 — 여유 있으면 여러 장, 아니면 한 장으로 압축」).
// need = 이 계획 어림의 높은 쪽, credits = /api/credits(이 요청의 키 — 「🔑 내 키」면 그 사람 것), fixes = [[이름, 줄인 뒤 어림, 함수]](맞는 것만), one = 한 장으로 압축(인포그래픽 질문지)
// 어림은 「약」이라 넘쳐도 「이대로 만들기」는 막지 않음(KAIROS Estimate는 그림·영상만 — 대화 모델은 실측 어림)
export function CreditFit({ need, credits, mine, fixes = [], one, oneCost = '', css }) {
  if (!credits || need == null) return null
  const left = Math.floor(credits.remaining), who = mine ? '내 키' : '서버 키'
  if (need <= left) return <span data-testid="credit-ok" style={css.meta}>남은 크레딧 {left.toLocaleString('ko-KR')}({who}) — 충분해요</span>
  return <div data-testid="credit-short" style={{ display: 'flex', flexDirection: 'column', gap: 5, padding: '7px 9px', borderRadius: 8, background: 'rgba(220,38,38,.07)', border: '1px solid rgba(220,38,38,.25)' }}>
    <span style={{ fontSize: 12.5 }}>남은 크레딧 <b>{left.toLocaleString('ko-KR')}</b>({who})이 이 계획(약 {need})보다 적어요 — 줄이거나 한 장으로 압축해요</span>
    <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
      {fixes.map(([label, after, fn]) => <button key={label} data-testid="credit-fix" style={css.ghost} onClick={fn}>{label} · 약 {after}</button>)}
      {one && <button data-testid="credit-one" style={css.ghost} onClick={one}>한 장으로 압축 (인포그래픽{oneCost ? ` · ${oneCost}` : ''})</button>}
    </div></div>
}
// 끝에서부터 빼서 room 안에 들게 — items = [{ i, c, fixed }](차례대로), keep = 남길 최소 수. 들게 되면 뺄 번호들, 안 되면 null
export function fitDrop(items, room, keep) {
  let sum = items.reduce((a, x) => a + x.c, 0), n = items.length; const out = []
  for (let k = items.length - 1; k >= 0 && sum > room && n > keep; k--) { if (items[k].fixed) continue; sum -= items[k].c; n--; out.push(items[k].i) }
  return sum <= room && out.length ? { out, sum } : null
}

// 지면 계획 — m = { plan, drop, estimate: { credits: [lo, hi], seconds: [lo, hi] }, built, pages, stale }
// drop(i) · build() · show() = 지은 판으로
export function DeepPlan({ m, drop, build, show, busy, css, credits = null, mine = false, setDrop = null, one = null, oneCost = '' }) {   // credits·setDrop·one = 만들기 전 크레딧 확인(④)
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
      : <><button data-testid="deep-build" style={GO} disabled={!!busy} onClick={build}>
          이대로 만들기{est ? ` · 약 ${rng(est.credits, '크레딧')}` : ''}</button>
        <span style={css.meta}>{est?.seconds ? `${rng(est.seconds, '초')} 걸려요(추정) · ` : ''}꼭지 {left}개 · 고칠 점은 아래 칸에 말하면 계획을 다시 짜요</span>
        {(() => { const hi = Array.isArray(est?.credits) ? est.credits[1] : null; if (hi == null || !credits) return null
          const per = hi / Math.max(1, left), f = fitDrop(secs.map((_, i) => ({ i, c: per })).filter(x => !dropped.has(x.i)), credits.remaining, 3)   // 꼭지마다 비슷하게 — 3개는 남김(× 빼기와 같은 하한)
          return <CreditFit need={Math.round(hi)} credits={credits} mine={mine} css={css} one={one} oneCost={oneCost}
            fixes={f && setDrop ? [[`끝에서 꼭지 ${f.out.length}개 빼기`, Math.round(f.sum), () => setDrop([...dropped, ...f.out])]] : []} /> })()}</>}
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
// 줄 번호 = 그 장이 될 프레임 번호(2026-11-06 사용자 「계획 번호와 프레임 번호가 안 맞아 헷갈림」) — 칠판에 이미 있는 프레임 뒤(base)부터, 글+그림 = 두 번호, 뺀 장 = –.
// 지은 뒤엔 칠판이 실제로 매긴 번호(`m.nos`, 그림을 못 받아 판이 빠지면 그만큼 당겨짐). 이 기능 전에 지은 계획은 옛 번호(1부터)
export const slideNos = (m, base = 1) => {
  const sl = m.plan?.slides || [], dropped = new Set(m.drop || [])
  if (m.built && !m.nos) return sl.map((_, i) => [i + 1])
  let n = base, j = 0
  return sl.map((_, i) => { if (dropped.has(i)) return null
    const got = m.built ? m.nos[j++] : null; if (got) return got
    const k = picOf(m, i) === 'both' ? [n, n + 1] : [n]; n += k.length; return k })
}
export function SlidesPlan({ m, flip, drop, build, show, busy, css, base = 1, credits = null, mine = false, setPics = null, setDrop = null, one = null, oneCost = '' }) {   // credits·setPics·setDrop·one = 만들기 전 크레딧 확인(④)
  const sl = m.plan?.slides || [], dropped = new Set(m.drop || []), left = sl.length - dropped.size, lock = !!m.built || !!m.stale || !!busy, nos = slideNos(m, base)
  const per = PIC_CREDITS * (m.brief?.['내용'] === '이야기' ? 2 : 1)   // 이야기 책 = 참고 그림을 같이 보내 약 2배(서버 `slides.estimate`)
  const drawn = v => (v ? 1 : 0), extra = Object.keys(m.pics || {}).map(Number).filter(i => !dropped.has(i)).reduce((a, i) => a + (drawn(picOf(m, i)) - drawn(sl[i]?.pic)) * per, 0)   // 🖼 바꾼 만큼 어림을 고침
  const est = m.estimate && { ...m.estimate, credits: m.estimate.credits?.map(c => Math.max(0, c + extra)) }, rng = (a, u) => (Array.isArray(a) ? `${a[0]}~${a[1]}${u}` : '')
  const live = sl.map((_, i) => i).filter(i => !dropped.has(i)), pics = live.filter(i => picOf(m, i) === true).length, both = live.filter(i => picOf(m, i) === 'both').length
  return <div data-testid="slides-plan" style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
    <div style={{ fontWeight: 700 }}>{m.plan?.title || '장 계획'}</div>
    <div style={{ display: 'flex', flexDirection: 'column', gap: 3 }}>
      {sl.map((s, i) => <div key={i} data-testid="slides-row" data-dropped={dropped.has(i) ? '1' : undefined} style={{ display: 'flex', gap: 6, alignItems: 'center', opacity: dropped.has(i) ? 0.4 : 1 }}>
        <span data-testid="slides-no" style={{ ...css.kind, flex: 'none', minWidth: 22, textAlign: 'center' }} title={nos[i]?.length > 1 ? '글 장 + 아래 그림 판 = 프레임 두 개' : '프레임 번호'}>{nos[i] ? nos[i].join('·') : '–'}</span>
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', textDecoration: dropped.has(i) ? 'line-through' : 'none' }} title={s.point || s.title}>{s.title}</span>
        <span style={{ ...css.meta, flex: 'none' }}>{SOURCE[s.source] || ''}</span>
        {/* 🖼 = 누를 때마다 글 → 그림 → 글+그림(아래에 그림 판 — 작은 책 ② 갈래). 켜짐 = 회색 채움(2026-11-07 K1). 표지(첫 장)는 글 장만 */}
        {i > 0 && (v => <button data-testid="slides-pic" data-pic={String(v)} aria-pressed={!!v} disabled={lock || dropped.has(i)} onClick={() => flip(i)}
          title={v === true ? '그림 장 — 장 전체가 설명 그림 한 장(누르면 글+그림)' : v === 'both' ? '글+그림 — 글 장 아래에 같은 내용의 그림 판(발표 때 둘 다, 프레임 판에서 하나 끌 수 있어요 · 누르면 글 장)' : '글 장 — 누르면 그림 장(설명 그림 한 장, 약 12크레딧)'}
          style={{ ...css.ghost, ...(v ? PICK : null), padding: '0 5px', flex: 'none', opacity: v ? 1 : 0.55, cursor: lock ? 'default' : 'pointer' }}>{v === 'both' ? '글+🖼' : '🖼'}</button>)(picOf(m, i))}
        {!lock && <button data-testid="slides-x" aria-label={dropped.has(i) ? `「${s.title}」 되살리기` : `「${s.title}」 빼기`} title={dropped.has(i) ? '되살리기' : '이 장 빼기'}
          disabled={!dropped.has(i) && left <= 2} onClick={() => drop(i)} style={{ ...css.ghost, padding: '0 6px', flex: 'none' }}>{dropped.has(i) ? '↺' : '×'}</button>}
      </div>)}
    </div>
    {m.built ? <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
        <button data-testid="slides-show" style={css.done} onClick={show}>✓ 프레임 {m.frames}장을 지었어요 — 보기</button>
        <span style={css.meta}>위 막대 「발표」로 바로 · 장마다 아래 회색 메모 = 발표자 메모(발표 화면엔 안 나옴)</span></div>
      : m.stale ? <span style={css.meta}>아래에 고친 계획이 있어요</span>
      : <><button data-testid="slides-build" style={GO} disabled={!!busy} onClick={build}>
          이대로 만들기{est ? ` · 약 ${rng(est.credits, '크레딧')}` : ''}</button>
        <span style={css.meta}>{est?.seconds ? `${rng(est.seconds, '초')} 걸려요(추정) · ` : ''}{left}장{pics || both ? `(${[pics && `그림 장 ${pics}`, both && `글+그림 ${both}`].filter(Boolean).join(' · ')})` : ''} · 🖼 = 글 → 그림 → 글+그림 · 고칠 점은 아래 칸에 말하면 계획을 다시 짜요</span>
        {(() => { const hi = Array.isArray(est?.credits) ? est.credits[1] : null; if (hi == null || !credits) return null
          const room = credits.remaining, drawnN = live.filter(i => drawn(picOf(m, i))).length, perText = Math.max(0, hi - drawnN * per) / Math.max(1, live.length)
          const cost = i => perText + (drawn(picOf(m, i)) ? per : 0), fixes = []
          const offs = fitDrop(live.filter(i => drawn(picOf(m, i))).map(i => ({ i, c: per })), room - live.reduce((a, i) => a + perText, 0), 0)   // 그림 장을 끝에서부터 글 장으로
          if (offs && setPics) fixes.push([`그림 장 ${offs.out.length}개를 글 장으로`, Math.round(offs.sum + live.length * perText), () => setPics(Object.fromEntries(offs.out.map(i => [i, false])))])
          const cut = fitDrop(live.map(i => ({ i, c: cost(i), fixed: i === 0 })), room, 2)   // 장을 끝에서부터 빼기 — 표지는 남김
          if (cut && setDrop) fixes.push([`끝에서 ${cut.out.length}장 빼기`, Math.round(cut.sum), () => setDrop([...dropped, ...cut.out])])
          return <CreditFit need={Math.round(hi)} credits={credits} mine={mine} css={css} one={one} oneCost={oneCost} fixes={fixes} /> })()}</>}
  </div>
}
