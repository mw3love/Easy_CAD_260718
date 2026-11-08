// 움직이는 카드 검사(2026-11-08) — AI가 만든 카드를 보이지 않는 칸에서 실제로 돌려 글자 잘림·겹침·스크립트 오류·빈 화면을 잰다(크레딧 없음).
// 카드 틀은 sandbox(same-origin 없음)라 바깥에서 안을 못 읽음 → 재는 스크립트를 카드 앞에 끼우고 결과만 postMessage로 받음(`MOTION_BRIDGE`와 같은 길).
// 잘못 잡으면 크레딧을 헛쓰므로 확실한 것만: 한 번 잰 뒤 조금 있다 또 재서 둘 다 나온 것만, 칸 밖에 통째로 있는 글(아직 안 나온 글)은 뺌.
import { LIVE_CSP, LIVE_H, LIVE_W, probeSrc } from './livecard.js'

const PROBE = String.raw`(function(){
var errs=[];addEventListener('error',function(e){var m=String(e.message||'');if(!/ResizeObserver/.test(m))errs.push(m.slice(0,120))});
var SKIP={SCRIPT:1,STYLE:1,NOSCRIPT:1,TEMPLATE:1,OPTION:1,TEXTAREA:1,TITLE:1,title:1,desc:1,defs:1,metadata:1,style:1,script:1};
function sleep(ms){return new Promise(function(r){setTimeout(r,ms)})}
function shown(el){for(var n=el,o=1;n&&n.nodeType===1;n=n.parentElement){if(SKIP[n.tagName])return false;var c=getComputedStyle(n);if(c.display==='none'||c.visibility==='hidden'||c.visibility==='collapse')return false;o*=+c.opacity;if(o<.1)return false}return true}
function turned(el){for(var n=el;n&&n.nodeType===1;n=n.parentElement){var t=getComputedStyle(n).transform;if(t&&t!=='none'){var m=new DOMMatrix(t);if(Math.abs(m.b)>.01||Math.abs(m.c)>.01)return true}if(n.getCTM&&n.tagName.toLowerCase()==='text'){var q=n.getCTM();if(q&&(Math.abs(q.b)>.01||Math.abs(q.c)>.01))return true}}return false}
function box(r){return{l:r.left,t:r.top,r:r.right,b:r.bottom,w:r.width,h:r.height}}
function texts(){var out=[],seen=new Set(),w=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
 while(w.nextNode()){var n=w.currentNode,s=n.nodeValue.replace(/\s+/g,' ').trim(),p=n.parentElement;if(!s||!p||!shown(p))continue;
  var svgT=p.closest&&p.closest('text');
  if(svgT){if(seen.has(svgT))continue;seen.add(svgT);var b=svgT.getBoundingClientRect();if(b.width>0&&b.height>0)out.push({s:svgT.textContent.replace(/\s+/g,' ').trim(),el:svgT,svg:true,rot:turned(svgT),b:box(b)});continue}
  var g=document.createRange();g.selectNodeContents(n);var rs=g.getClientRects(),rot=turned(p);for(var i=0;i<rs.length;i++)if(rs[i].width>1&&rs[i].height>1)out.push({s:s,el:p,svg:false,rot:rot,b:box(rs[i])})}
 return out}
function cutBy(b,f){var tolX=3,tolY=Math.max(3,b.h*.22);if(b.r<=f.l||b.l>=f.r||b.b<=f.t||b.t>=f.b)return false;return b.l<f.l-tolX||b.r>f.r+tolX||b.t<f.t-tolY||b.b>f.b+tolY}
function clipper(el,svg){for(var n=svg?el.ownerSVGElement:el;n&&n!==document.documentElement&&n!==document.body;n=n.parentElement){var c=getComputedStyle(n);if(/hidden|clip|auto|scroll/.test(c.overflow+c.overflowX+c.overflowY)||n.tagName.toLowerCase()==='svg')return n}return null}
function related(a,b){return a===b||a.contains(b)||b.contains(a)}
function look(){var ps={},add=function(p){ps[p.type+'|'+p.text+'|'+(p.other||'')]=p},t=texts(),V={l:0,t:0,r:innerWidth,b:innerHeight};
 t.forEach(function(x){if(cutBy(x.b,V)){add({type:'clip',text:x.s.slice(0,40)});return}var c=clipper(x.el,x.svg);if(c){var cb=box(c.getBoundingClientRect());if(cb.w>0&&cb.h>0&&cutBy(x.b,cb))add({type:'clip',text:x.s.slice(0,40)})}});
 var n=Math.min(t.length,400);for(var i=0;i<n;i++)for(var j=i+1;j<n;j++){var a=t[i],b=t[j];if(a.rot||b.rot||related(a.el,b.el))continue;
  var iw=Math.min(a.b.r,b.b.r)-Math.max(a.b.l,b.b.l),ih=Math.min(a.b.b,b.b.b)-Math.max(a.b.t,b.b.t);if(iw<5||ih<=0)continue;
  var minA=Math.min(a.b.w*a.b.h,b.b.w*b.b.h),minH=Math.min(a.b.h,b.b.h);if(iw*ih<minA*.2||ih<minH*.4)continue;
  if(a.s===b.s&&Math.abs(a.b.l-b.b.l)<3&&Math.abs(a.b.t-b.b.t)<3)continue;
  add({type:'overlap',text:a.s.slice(0,30),other:b.s.slice(0,30)})}
 var pics=[].slice.call(document.querySelectorAll('svg,canvas,img')).filter(function(e){if(!shown(e)||e.ownerSVGElement)return false;var r=e.getBoundingClientRect();return r.width>8&&r.height>8});
 return{ps:ps,any:t.length>0||pics.length>0}}
async function twice(wait){await sleep(wait);var a=look();await sleep(450);var b=look(),out=[];Object.keys(a.ps).forEach(function(k){if(b.ps[k])out.push(b.ps[k])});return{list:out,any:a.any||b.any}}
addEventListener('load',async function(){var res=[],empty=true,keep=function(r,step){if(r.any)empty=false;r.list.forEach(function(p){if(step)p.step=step;res.push(p)})};
 try{keep(await twice(1500),0);
  if(MOTION){if(typeof window.mbNext!=='function')errs.push('단계 넘기기 함수(mbNext)가 없음');else for(var s=1;s<8;s++){var more;try{more=window.mbNext()}catch(e){errs.push(String(e.message||e).slice(0,120));break}if(more===false||more===undefined)break;keep(await twice(1500),s)}}
 }catch(e){errs.push(String(e&&e.message||e).slice(0,120))}
 var seen={},out=[];res.forEach(function(p){var k=p.type+'|'+p.text+'|'+(p.other||'');if(!seen[k]){seen[k]=1;out.push(p)}});
 if(empty)out.unshift({type:'empty',text:''});errs.slice(0,3).forEach(function(m){out.unshift({type:'error',text:m})});
 parent.postMessage({mbCheck:TOKEN,problems:out.slice(0,12)},'*')});
})();`

export const checkSource = (html, token, motion) => probeSrc(`<script>var TOKEN=${token},MOTION=${motion ? 'true' : 'false'};${PROBE}</script>`, html)

/** 보이지 않는 칸에 카드를 띄워 결과를 받음 — 못 재면 null(문제 없음으로 치지 않고 그냥 넘어감). 칸은 화면 안에 투명하게(화면 밖이면 브라우저가 틀의 움직임을 멈춤) */
export function runCheck(src, w, h, token, csp, ms) {
  return new Promise(done => {
    const f = document.createElement('iframe')
    let timer = 0
    const end = v => { clearTimeout(timer); removeEventListener('message', on); f.remove(); done(v) }
    const on = e => { if (e.source === f.contentWindow && e.data?.mbCheck === token) end({ problems: Array.isArray(e.data.problems) ? e.data.problems : [] }) }
    addEventListener('message', on)
    timer = setTimeout(() => end(null), ms)
    f.setAttribute('sandbox', 'allow-scripts'); f.setAttribute('csp', csp); f.setAttribute('scrolling', 'no'); f.setAttribute('aria-hidden', 'true'); f.tabIndex = -1
    f.style.cssText = `position:fixed;left:0;top:0;width:${w}px;height:${h}px;border:0;opacity:0;pointer-events:none;z-index:-1`
    f.srcdoc = src
    document.body.appendChild(f)
  })
}

export function checkCard(html, { w = LIVE_W, h = LIVE_H, motion = false } = {}) {
  if (typeof document === 'undefined' || document.hidden || !html) return Promise.resolve(null)   // 뒤에 가려진 탭은 시계가 느려져 잴 수 없음
  const token = Math.floor(Math.random() * 1e9) + 1
  return runCheck(checkSource(html, token, motion), w, h, token, LIVE_CSP, motion ? 45_000 : 9_000)
}

/** 잰 결과 → 사람과 모델이 읽을 줄들 */
export function problemLines(problems) {
  return (problems || []).map(p => {
    const at = p.step ? `(${p.step + 1}번째 단계) ` : ''
    if (p.type === 'clip') return `${at}글자가 잘림: 「${p.text}」`
    if (p.type === 'overlap') return `${at}글자가 겹침: 「${p.text}」와 「${p.other}」`
    if (p.type === 'empty') return '화면이 비어 있음'
    return `스크립트 오류: ${p.text}`
  })
}
