/* ================================================================
   Pre-made interactive projects (TEST MODE).

   When VITE_TEST=true, clicking one of the 6 simulation cards in the
   "Simulyatsiyalar" page plays a hand-built interactive experience
   keyed to that subject — instead of calling the live AI. A random
   3–7s "generating" delay is shown first so it feels produced live.

   Each experience is a single self-contained HTML document rendered
   inside the chat iframe. Text is written in Uzbek (the platform's
   primary language); the language-switch translator can still
   translate them on the fly.
================================================================= */

// The Solar System experience is a full, self-contained document authored as
// a standalone .html file (not the shared `shell()`), imported raw at build time.
import solarHtml from './premade/solar.html?raw'
// "Ildiz Ovchisi" — square-root catcher math game; replaces the heart experience.
import mathRootsHtml from './premade/math-roots.html?raw'

/** True when the app is running in pre-made / demo mode. */
export const testMode = String(import.meta.env.VITE_TEST).toLowerCase() === 'true'

/** Language the pre-made experiences are authored in. */
export const PREMADE_LOCALE = 'uz' as const

/** Random "playing" delay between 3 and 7 seconds (ms). */
export function premadeDelayMs(): number {
  return Math.round(3000 + Math.random() * 4000)
}

/* Shared polished dark shell so every experience looks consistent. */
function shell(o: { tag: string; title: string; accent: string; css: string; body: string }): string {
  return `<!DOCTYPE html>
<html lang="uz"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Segoe UI',system-ui,sans-serif;background:radial-gradient(circle at 30% 8%,#1e1b4b,#070a14 72%);color:#f8fafc;min-height:100vh;padding:22px;display:flex;flex-direction:column;gap:16px;}
.tag{font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;color:${o.accent};font-weight:800;}
h1{font-size:1.4rem;line-height:1.2;}
.sub{opacity:.6;font-size:.88rem;margin-top:4px;}
.panel{background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:16px;display:flex;flex-direction:column;gap:14px;}
.row{display:flex;align-items:center;gap:12px;}
.row label{width:150px;font-size:.85rem;opacity:.85;}
.row input[type=range]{flex:1;accent-color:${o.accent};}
.row .val{width:64px;text-align:right;font-weight:700;color:${o.accent};}
.readout{display:flex;gap:10px;flex-wrap:wrap;}
.stat{flex:1;min-width:110px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:12px 14px;}
.stat b{display:block;font-size:1.5rem;color:${o.accent};}
.stat span{font-size:.66rem;opacity:.6;text-transform:uppercase;letter-spacing:.08em;}
button{font-family:inherit;}
${o.css}
</style></head>
<body>
<div><span class="tag">${o.tag}</span><h1>${o.title}</h1><p class="sub">SIMULINK · oldindan tayyorlangan interaktiv tajriba</p></div>
${o.body}
</body></html>`
}

/* 1) FOTOSINTEZ — sunlight/water/CO₂ → O₂ */
function photosynthesis(): string {
  const accent = '#4ade80'
  return shell({
    accent,
    tag: 'Biologiya · Fotosintez',
    title: '🌱 Fotosintez jarayoni',
    css: `
.stage{display:flex;align-items:center;justify-content:center;min-height:200px;background:linear-gradient(#0b1024,#0f2027);border:1px solid rgba(255,255,255,.1);border-radius:16px;position:relative;overflow:hidden;}
#leaf{font-size:90px;transition:transform .3s,filter .3s;}
.bubble{position:absolute;bottom:20px;font-size:14px;color:#7dd3fc;animation:rise 2.4s linear forwards;}
@keyframes rise{to{transform:translateY(-180px);opacity:0;}}
.bar{height:10px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden;}
.bar i{display:block;height:100%;width:0;background:${accent};transition:width .3s;}
.formula{text-align:center;font-size:.95rem;opacity:.85;}`,
    body: `
<div class="stage"><div id="leaf">🌿</div></div>
<div class="readout">
  <div class="stat"><b id="o2">0</b><span>Kislorod O₂ /s</span></div>
  <div class="stat"><b id="glu">0</b><span>Glyukoza /s</span></div>
</div>
<div class="panel">
  <div class="row"><label>☀️ Quyosh nuri</label><input id="sun" type="range" min="0" max="100" value="70"><span class="val" id="sunV">70%</span></div>
  <div class="row"><label>💧 Suv (H₂O)</label><input id="water" type="range" min="0" max="100" value="60"><span class="val" id="waterV">60%</span></div>
  <div class="row"><label>🌫️ CO₂</label><input id="co2" type="range" min="0" max="100" value="50"><span class="val" id="co2V">50%</span></div>
  <div class="bar"><i id="rateBar"></i></div>
  <p class="formula">6CO₂ + 6H₂O + ☀️ → C₆H₁₂O₆ + 6O₂</p>
</div>
<script>
var stage=document.querySelector('.stage'),leaf=document.getElementById('leaf');
function v(id){return parseInt(document.getElementById(id).value,10);}
['sun','water','co2'].forEach(function(id){document.getElementById(id).oninput=function(){document.getElementById(id+'V').textContent=v(id)+'%';update();};});
var rate=0;
function update(){
  rate=Math.round(Math.min(v('sun'),v('water'),v('co2'))*0.92);
  document.getElementById('o2').textContent=rate;
  document.getElementById('glu').textContent=Math.round(rate/6);
  document.getElementById('rateBar').style.width=rate+'%';
  leaf.textContent=rate>15?'🌿':'🍂';
  leaf.style.filter='brightness('+(0.5+rate/100)+')';
  leaf.style.transform='scale('+(0.85+rate/220)+')';
}
update();
setInterval(function(){
  if(rate<10)return;
  var b=document.createElement('div');b.className='bubble';b.textContent='O₂';
  b.style.left=(35+Math.random()*30)+'%';stage.appendChild(b);
  setTimeout(function(){b.remove();},2400);
},Math.max(180,900-rate*7));
<\/script>`,
  })
}

/* 2) NYUTON — F = m·a */
function newton(): string {
  const accent = '#38bdf8'
  return shell({
    accent,
    tag: 'Fizika · Nyuton qonunlari',
    title: '🧲 Kuch, massa va tezlanish (F = m·a)',
    css: `
canvas{width:100%;height:200px;background:linear-gradient(#0b1024,#131c44);border:1px solid rgba(255,255,255,.1);border-radius:16px;display:block;}`,
    body: `
<canvas id="c"></canvas>
<div class="readout">
  <div class="stat"><b id="acc">0.0</b><span>Tezlanish a (m/s²)</span></div>
  <div class="stat"><b id="spd">0.0</b><span>Tezlik v (m/s)</span></div>
</div>
<div class="panel">
  <div class="row"><label>💪 Kuch F (N)</label><input id="f" type="range" min="0" max="100" value="40"><span class="val" id="fV">40</span></div>
  <div class="row"><label>📦 Massa m (kg)</label><input id="m" type="range" min="1" max="20" value="5"><span class="val" id="mV">5</span></div>
</div>
<script>
var cv=document.getElementById('c'),x=cv.getContext('2d');
function fit(){cv.width=cv.clientWidth;cv.height=cv.clientHeight;}fit();addEventListener('resize',fit);
var fEl=document.getElementById('f'),mEl=document.getElementById('m');
fEl.oninput=function(){document.getElementById('fV').textContent=fEl.value;};
mEl.oninput=function(){document.getElementById('mV').textContent=mEl.value;};
var pos=0,vel=0;
function loop(){
  var F=parseFloat(fEl.value),m=parseFloat(mEl.value),a=F/m;
  vel+=a*0.016;pos+=vel*0.016;
  if(pos>cv.width-60){pos=cv.width-60;vel=-vel*0.6;}
  if(pos<0){pos=0;vel=Math.abs(vel)*0.6;}
  document.getElementById('acc').textContent=a.toFixed(1);
  document.getElementById('spd').textContent=Math.abs(vel).toFixed(1);
  x.clearRect(0,0,cv.width,cv.height);
  var gY=cv.height-40;
  x.fillStyle='rgba(255,255,255,.12)';x.fillRect(0,gY+34,cv.width,6);
  var size=24+m*2;
  x.fillStyle='#38bdf8';x.fillRect(pos,gY-size+34,size,size);
  x.fillStyle='#fff';x.font='20px serif';x.fillText('📦',pos+size/2-12,gY+24);
  requestAnimationFrame(loop);
}
loop();
<\/script>`,
  })
}

/* 3) KIMYOVIY REAKSIYALAR — combine atoms */
function reactions(): string {
  const accent = '#c084fc'
  return shell({
    accent,
    tag: 'Kimyo · Reaksiyalar',
    title: '⚗️ Atomlarni biriktiring',
    css: `
.flask{font-size:1.6rem;min-height:64px;background:rgba(255,255,255,.05);border:1px dashed rgba(255,255,255,.2);border-radius:16px;display:flex;align-items:center;justify-content:center;padding:14px;}
.atoms{display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:10px;}
.atoms button{padding:14px;border:none;border-radius:12px;background:rgba(255,255,255,.08);color:#fff;font-size:1rem;font-weight:700;cursor:pointer;}
.atoms button:active{background:${accent};}
.go{display:flex;gap:10px;}
.go button{flex:1;padding:14px;border:none;border-radius:12px;font-weight:800;cursor:pointer;}
#react{background:${accent};color:#fff;}#clr{background:rgba(255,255,255,.08);color:#fff;}
#out{min-height:60px;border-radius:14px;padding:14px;font-size:.95rem;line-height:1.5;background:rgba(192,132,252,.08);border:1px solid rgba(192,132,252,.3);color:#e9d5ff;}`,
    body: `
<div class="flask" id="flask">atomlarni qo'shish uchun bosing…</div>
<div class="atoms">
  <button data-s="H">H 💧</button><button data-s="O">O 🅾️</button><button data-s="C">C ⚫</button>
  <button data-s="Na">Na 🧂</button><button data-s="Cl">Cl 🟢</button>
</div>
<div class="go"><button id="react">⚗️ Reaksiya!</button><button id="clr">Tozalash</button></div>
<div id="out">Sinab ko'ring: <b>H + H + O</b>, <b>C + O + O</b> yoki <b>Na + Cl</b>…</div>
<script>
var counts={};
var recipes=[
 {k:{H:2,O:1},n:'💧 Suv (H₂O)',f:'Ikki vodorod bitta kislorodni ushlaydi — barcha tirik organizmlar uchun zarur molekula.'},
 {k:{C:1,O:2},n:'🌫️ Karbonat angidrid (CO₂)',f:'Bir uglerod, ikki kislorod — biz nafas chiqaradigan, o\\'simliklar yutadigan gaz.'},
 {k:{Na:1,Cl:1},n:'🧂 Osh tuzi (NaCl)',f:'Faol metall + zaharli gaz birikib, dasturxon tuzini hosil qiladi.'},
 {k:{C:1,H:4},n:'🔥 Metan (CH₄)',f:'Bir uglerod to\\'rtta vodorodni quchadi — tabiiy gaz.'}];
function render(){var s='';for(var k in counts){if(counts[k])s+=k+(counts[k]>1?'<sub>'+counts[k]+'</sub>':'')+' ';}
  document.getElementById('flask').innerHTML=s||'atomlarni qo\\'shish uchun bosing…';}
document.querySelectorAll('.atoms button').forEach(function(b){b.onclick=function(){var s=b.getAttribute('data-s');counts[s]=(counts[s]||0)+1;render();};});
document.getElementById('clr').onclick=function(){counts={};render();document.getElementById('out').innerHTML='Tozalandi. Boshqa birikmani sinang!';};
document.getElementById('react').onclick=function(){
  var match=null;
  recipes.forEach(function(r){var ok=true,keys={};for(var k in r.k)keys[k]=1;for(var c in counts)if(counts[c])keys[c]=1;
    for(var k in keys)if((counts[k]||0)!==(r.k[k]||0))ok=false;if(ok)match=r;});
  var out=document.getElementById('out');
  if(match){out.innerHTML='<b style="color:#34d399">'+match.n+'</b><br>'+match.f;}
  else{out.innerHTML='🤔 Bu atomlar barqaror molekula hosil qilmaydi. Maslahat: H₂O uchun <b>ikkita</b> H kerak.';}
};
render();
<\/script>`,
  })
}

/* 4) QUYOSH TIZIMI — orbiting planets (full standalone experience) */
function solar(): string {
  return solarHtml
}

/* 5) "Yurak Qon Aylanishi" slot now plays the √ Ildiz Ovchisi math game
   (square-root catcher) — a full standalone document imported raw. */
function mathRoots(): string {
  return mathRootsHtml
}

/* 6) ELEKTR TO'KI — Ohm's law */
function circuit(): string {
  const accent = '#fbbf24'
  return shell({
    accent,
    tag: 'Fizika · Elektr toki',
    title: '💡 Ohm qonuni (I = U / R)',
    css: `
.stage{display:flex;align-items:center;justify-content:center;min-height:180px;background:linear-gradient(#0b1024,#1a1604);border:1px solid rgba(255,255,255,.1);border-radius:16px;}
#bulb{font-size:90px;transition:filter .2s,transform .2s;}`,
    body: `
<div class="stage"><div id="bulb">💡</div></div>
<div class="readout">
  <div class="stat"><b id="cur">0.0</b><span>Tok I (A)</span></div>
  <div class="stat"><b id="pow">0.0</b><span>Quvvat P (W)</span></div>
</div>
<div class="panel">
  <div class="row"><label>🔋 Kuchlanish U (V)</label><input id="u" type="range" min="0" max="24" value="12"><span class="val" id="uV">12</span></div>
  <div class="row"><label>🧱 Qarshilik R (Ω)</label><input id="r" type="range" min="1" max="20" value="6"><span class="val" id="rV">6</span></div>
</div>
<script>
var uEl=document.getElementById('u'),rEl=document.getElementById('r'),bulb=document.getElementById('bulb');
function update(){
  var U=parseFloat(uEl.value),R=parseFloat(rEl.value),I=U/R;
  document.getElementById('uV').textContent=U;
  document.getElementById('rV').textContent=R;
  document.getElementById('cur').textContent=I.toFixed(2);
  document.getElementById('pow').textContent=(U*I).toFixed(1);
  var br=Math.min(2.2,0.3+I/3);
  bulb.style.filter='brightness('+br+') drop-shadow(0 0 '+(I*6)+'px #fde047)';
  bulb.style.transform='scale('+(0.9+I/14)+')';
  bulb.textContent=I>0.3?'💡':'🔌';
}
uEl.oninput=update;rEl.oninput=update;update();
<\/script>`,
  })
}

/* id → builder. Keys match the sim ids in SimulationsView.vue.
   In test mode ONLY these two play a hand-built experience; every other
   simulation (photosynthesis, newton, reactions, circuit) falls through to
   the live AI. The remaining builders below are kept for reference/reuse. */
const BUILDERS: Record<string, () => string> = {
  solar,
  mathRoots,
}

// Referenced so the unused-but-kept builders don't trip linters.
void photosynthesis
void newton
void reactions
void circuit

/** Returns the pre-made HTML for a simulation id, or null if there isn't one. */
export function getPremade(id: string): string | null {
  const build = BUILDERS[id]
  return build ? build() : null
}
