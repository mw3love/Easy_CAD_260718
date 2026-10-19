// HTML 한 파일 공유(§8 항목61 ⓔ, 2026-10-18 — 방송본 고정·예비본) — 칠판 전체 그림 + 프레임 = 발표 장을 파일 하나에.
// 받는 사람은 앱·서버·인터넷 없이 브라우저로 연다(글꼴·스크립트 모두 안에). 데스크톱 「HTML로 공유」(`easycad/fileio/html_share.py`)와 같은 뜻.
// 전체 = 끌기·휠로 이동·확대, 발표 = 장마다 화면에 꽉 차게(→ · 스페이스 · 휠 = 다음, ← = 이전, Esc = 끝, F = 전체 화면) — 칠판 발표와 같은 손버릇.

const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' }[c]))

// overview = 전체 그림 svg 글, slides = [{ svg, name }], fonts = @font-face 글(한 번만), made = 만든 시각 글
export function buildHtml({ title, made, overview, slides = [], fonts = '' }) {
  const n = slides.length
  const slideDivs = slides.map((s, i) => `<div class="slide" data-i="${i}" data-name="${esc(s.name)}">${s.svg}</div>`).join('\n')
  return `<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>${esc(title)}</title>
<style>${fonts}
html,body{margin:0;height:100%;background:#f4f4f5;font:14px 'Pretendard','Malgun Gothic',sans-serif;color:#27272a;overflow:hidden}
#bar{position:fixed;left:0;right:0;top:0;height:44px;display:flex;align-items:center;gap:10px;padding:0 14px;background:#fff;border-bottom:1px solid #e4e4e7;z-index:5}
#bar b{font-size:15px}#bar .m{color:#71717a;font-size:12px}#bar .sp{flex:1}
#bar button{border:0;border-radius:6px;padding:6px 12px;background:rgba(218,119,86,.14);font:600 13px inherit;cursor:pointer;color:#27272a}
#bar button.on{background:#da7756;color:#fff}
#tabs{display:flex;gap:2px;padding:2px;border-radius:8px;background:#f4f4f5}#tabs button{background:transparent}#tabs button.cur{background:#fff;box-shadow:0 1px 2px rgba(0,0,0,.12)}
#ov{position:fixed;left:0;right:0;top:44px;bottom:0;overflow:hidden;cursor:grab}
#ovin{position:absolute;inset:0}#ovin svg{display:block;width:100%;height:100%}
#show{position:fixed;inset:0;background:#000;display:none;z-index:10}
#show .slide{position:absolute;inset:0;display:none;align-items:center;justify-content:center}
#show .slide svg{width:100%;height:100%;display:block}
#show .slide.cur{display:flex}
#nav{position:fixed;left:50%;bottom:14px;transform:translateX(-50%);display:flex;gap:4px;align-items:center;padding:4px;border-radius:10px;background:rgba(24,24,27,.86);color:#fff;z-index:11;opacity:0;transition:opacity .25s}
#show:hover #nav,#nav:hover{opacity:1}
#nav button{border:0;background:transparent;color:#fff;font:600 14px inherit;padding:6px 10px;border-radius:6px;cursor:pointer}
#nav span{font-size:12px;padding:0 8px}
</style></head><body>
<div id="bar"><b>${esc(title)}</b><span class="m">${esc(made)} 기준 고정본 · Magic Board</span><span class="sp"></span>
<div id="tabs"><button id="fit" class="cur" title="칠판 전체가 화면에 들어오게 맞춤 · 끌기 = 이동, 휠 = 확대">칠판</button>${n ? `<button id="play" title="프레임을 한 장씩 (Enter)">▶ 발표 (${n}장)</button>` : ''}</div></div>
<div id="ov"><div id="ovin">${overview}</div></div>
<div id="show">${slideDivs}<div id="nav"><button data-d="-1">◀</button><span id="no"></span><button data-d="1">▶</button><button id="end">끝 (Esc)</button></div></div>
<script>
(function(){
var ov=document.getElementById('ov'),inn=document.getElementById('ovin'),svg=inn.querySelector('svg');
var vb=svg?svg.viewBox.baseVal:{x:0,y:0,width:1000,height:700},X0=vb.x,Y0=vb.y,W=vb.width,H=vb.height,s=1,x=0,y=0;
if(svg){svg.removeAttribute('width');svg.removeAttribute('height');svg.setAttribute('preserveAspectRatio','xMinYMin meet')}
// 확대·이동 = svg viewBox(CSS transform 아래에선 크롬이 끼운 웹페이지를 안 그림 — 2026-10-19)
function put(){if(!svg)return;var r=ov.getBoundingClientRect();svg.setAttribute('viewBox',(X0-x/s)+' '+(Y0-y/s)+' '+(r.width/s)+' '+(r.height/s))}
function fit(){var r=ov.getBoundingClientRect();s=Math.min(r.width/W,r.height/H)*0.95;x=(r.width-W*s)/2;y=(r.height-H*s)/2;put()}
fit();window.addEventListener('resize',fit);document.getElementById('fit').onclick=fit;
ov.addEventListener('wheel',function(e){e.preventDefault();var r=ov.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top,k=e.deltaY<0?1.15:1/1.15,ns=Math.max(0.05,Math.min(40,s*k));k=ns/s;x=mx-(mx-x)*k;y=my-(my-y)*k;s=ns;put()},{passive:false});
var drag=null;ov.addEventListener('pointerdown',function(e){drag={x:e.clientX-x,y:e.clientY-y,sx:e.clientX,sy:e.clientY,t:e.target};ov.setPointerCapture(e.pointerId);ov.style.cursor='grabbing'});
ov.addEventListener('pointermove',function(e){if(!drag)return;x=e.clientX-drag.x;y=e.clientY-drag.y;put()});
ov.addEventListener('pointerup',function(e){var d=drag;drag=null;ov.style.cursor='grab';if(d&&Math.abs(e.clientX-d.sx)+Math.abs(e.clientY-d.sy)<5)webClick(d.t,e)});
// 웹 카드 누르기 — 몸통 = 그 자리에 실제 페이지(유튜브는 바로 재생, 인터넷이 없으면 그림 그대로), 위 띠·막는 사이트 = 새 탭
function webClick(t,e){var g=t&&t.closest&&t.closest('[data-web-url]');if(!g)return;var url=g.getAttribute('data-web-url'),src=g.getAttribute('data-web-src'),r=g.getBoundingClientRect(),head=+g.getAttribute('data-web-head')||0;
var yt=src&&src.indexOf('youtube.com/embed/')>=0;
// 유튜브는 내 PC에서 바로 연 파일(file://)이면 「오류 153」(어디서 왔는지 안 보냄 — 2026-10-19 확인) → 새 탭에서 재생
if(!src||(e.clientY-r.top)/r.height<head||(yt&&location.protocol==='file:')){window.open(url,'_blank','noopener');return}
if(g.querySelector('foreignObject')||navigator.onLine===false)return;
var b=g.getAttribute('data-web-box').split(',').map(Number),z=+g.getAttribute('data-web-zoom')||1;if(yt)src+=(src.indexOf('?')<0?'?':'&')+'autoplay=1';
var fo=document.createElementNS('http://www.w3.org/2000/svg','foreignObject');fo.setAttribute('x',b[0]);fo.setAttribute('y',b[1]);fo.setAttribute('width',b[2]);fo.setAttribute('height',b[3]);
var f=document.createElement('iframe');f.src=src;f.setAttribute('allow','autoplay; encrypted-media; picture-in-picture; fullscreen');f.setAttribute('allowfullscreen','');f.setAttribute('referrerpolicy','strict-origin-when-cross-origin');
f.style.cssText='border:0;display:block;background:#fff;width:'+100/z+'%;height:'+100/z+'%;transform-origin:0 0'+(z<1?';transform:scale('+z+')':'');fo.appendChild(f);g.appendChild(fo)}
var show=document.getElementById('show'),slides=show.querySelectorAll('.slide'),i=0,on=false,no=document.getElementById('no'),wheelAt=0;
show.addEventListener('click',function(e){webClick(e.target,e)});
function go(k){if(!slides.length)return;i=Math.max(0,Math.min(slides.length-1,k));for(var j=0;j<slides.length;j++)slides[j].classList.toggle('cur',j===i);var nm=slides[i].getAttribute('data-name');no.textContent=(i+1)+' / '+slides.length+(nm?' · '+nm:'')}
function start(){if(!slides.length)return;on=true;show.style.display='block';go(i);try{document.documentElement.requestFullscreen&&document.documentElement.requestFullscreen()}catch(e){}}
function end(){on=false;show.style.display='none';try{document.fullscreenElement&&document.exitFullscreen()}catch(e){}}
var play=document.getElementById('play');if(play)play.onclick=function(){i=0;start()};
document.getElementById('end').onclick=end;
Array.prototype.forEach.call(document.querySelectorAll('#nav [data-d]'),function(b){b.onclick=function(){go(i+ +b.getAttribute('data-d'))}});
document.addEventListener('keydown',function(e){if(!on){if(e.key==='Enter'&&slides.length)start();return}
if(['ArrowRight','ArrowDown','PageDown',' '].indexOf(e.key)>=0){e.preventDefault();go(i+1)}else if(['ArrowLeft','ArrowUp','PageUp','Backspace'].indexOf(e.key)>=0){e.preventDefault();go(i-1)}
else if(e.key==='Home')go(0);else if(e.key==='End')go(slides.length-1);else if(e.key==='Escape')end();else if(e.key==='f'||e.key==='F'){try{document.documentElement.requestFullscreen()}catch(err){}}});
var wacc=0,wt=0;show.addEventListener('wheel',function(e){e.preventDefault();var t=Date.now(),notch=Math.abs(e.deltaY)>=50;if(t-wt>200)wacc=0;wt=t;wacc+=e.deltaY;if(Math.abs(wacc)<100&&!notch)return;if(t-wheelAt<(notch?30:300)){wacc=0;return}wheelAt=t;wacc=0;go(i+(e.deltaY>0?1:-1))},{passive:false});
document.addEventListener('fullscreenchange',function(){if(!document.fullscreenElement&&on)end()});
})();
</script></body></html>`
}
