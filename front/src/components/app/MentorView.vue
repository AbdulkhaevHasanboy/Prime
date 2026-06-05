<script setup lang="ts">
import { ref, computed, onUnmounted, watch, nextTick, onMounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'
import { generateExperience, aiConfigured, aiModel } from '../../managers/aiClient'
import { createHistory, getHistory, type ApiUserHistory } from '../../managers/apiClient'
import { enhanceTopic, funFactsFor, liveConfigured } from '../../managers/liveClient'
import { translateHtmlText } from '../../managers/translate'
import { testMode, getPremade, premadeDelayMs, PREMADE_LOCALE } from '../../managers/premadeProjects'
import { aiLanguageName, currentLocaleCode, type LocaleCode } from '../../i18n'
import { getToken } from '../../managers/authManager'

const props = defineProps<{
  seed: string
  seedId?: string
}>()

const emit = defineEmits<{
  (e: 'seed-consumed'): void
  (e: 'topic', topic: string): void
}>()

const { showToast } = useToast()
const { t, tm, locale } = useI18n()

/* ---------- Chat state ---------- */
let msgId = 0
interface ChatMessage {
  id: number
  role: 'assistant' | 'user'
  type: 'text' | 'loading' | 'experience'
  text?: string
  html?: string
  htmlLocale?: LocaleCode
}

const messages = ref<ChatMessage[]>([{ id: msgId++, role: 'assistant', type: 'text', text: t('mentor.greeting') }])
const draft = ref('')
const isGenerating = ref(false)
const chatScroll = ref<HTMLElement | null>(null)

// Show the popular-topic chips until the student has interacted.
const showTopics = computed(() => messages.value.every((m) => m.role !== 'user'))
const popularTopics = computed(() => tm('mentor.topics') as unknown as string[])

// Recent topics (right panel) — seeded, then prepended with real submissions.
const recentTopics = ref<string[]>([])
const historyRecords = ref<ApiUserHistory[]>([])

async function loadTopicHistory(topic: string) {
  const record = historyRecords.value.find(r => r.question?.toLowerCase().trim() === topic.toLowerCase().trim())
  if (record && record.data && record.data[0]) {
    problemText.value = topic
    messages.value.push({ id: msgId++, role: 'user', type: 'text', text: topic })
    messages.value.push({
      id: msgId++,
      role: 'assistant',
      type: 'experience',
      html: record.data[0],
      htmlLocale: currentLocaleCode()
    })
    scrollToEnd()
  } else {
    submit(topic)
  }
}

onMounted(async () => {
  const token = getToken()
  if (!token) return
  try {
    const list = await getHistory(token, 0, 20)
    historyRecords.value = list
    const unique = new Set<string>()
    for (const r of list) {
      if (r.question) unique.add(r.question)
    }
    if (unique.size > 0) {
      recentTopics.value = Array.from(unique).slice(0, 6)
    }
  } catch (err) {
    console.error('[Failed to load history]', err)
  }
})

function pushRecent(topic: string) {
  const next = [topic, ...recentTopics.value.filter((t2) => t2.toLowerCase() !== topic.toLowerCase())]
  recentTopics.value = next.slice(0, 6)
}

async function scrollToEnd() {
  await nextTick()
  const el = chatScroll.value
  if (el) el.scrollTop = el.scrollHeight
}

/* ----------------------------------------------------------------
   Subject detection — mirrors the AI's own reasoning so the mock
   fallback can pick a fitting interactive experience.
----------------------------------------------------------------- */
const problemText = ref('')

interface SubjectRule {
  id: string
  label: string
  emoji: string
  keywords: string[]
}

const subjectRules: SubjectRule[] = [
  { id: 'math', label: 'Mathematics', emoji: '🧮', keywords: ['math', 'pi', 'π', '3.14', '3,14', 'equation', 'algebra', 'algebraic', 'tenglama', 'calculus', 'geometry', 'fraction', 'derivative', 'integral', 'trig', 'sin', 'cos', 'theorem', 'angle', 'percent'] },
  { id: 'biology', label: 'Biology', emoji: '🧬', keywords: ['cell', 'dna', 'organism', 'photosynthesis', 'fotosintez', 'biology', 'gene', 'evolution', 'mitochondria', 'plant', 'animal', 'enzyme', 'protein', 'organ', 'blood', 'yurak', 'heart'] },
  { id: 'chemistry', label: 'Chemistry', emoji: '⚗️', keywords: ['atom', 'molecule', 'reaction', 'reaksiya', 'chemistry', 'kimyo', 'acid', 'base', 'periodic', 'bond', "bog'lanish", 'element', 'ion', 'compound', 'mole'] },
  { id: 'physics', label: 'Physics', emoji: '🔭', keywords: ['force', 'gravity', 'velocity', 'physics', 'fizika', 'energy', 'quantum', 'motion', 'newton', 'nyuton', 'momentum', 'electric', 'elektr', 'voltage', 'wave', 'light', 'mass'] },
  { id: 'history', label: 'History', emoji: '📜', keywords: ['war', 'urush', 'history', 'tarix', 'revolution', 'ancient', 'empire', 'century', 'king', 'queen', 'treaty', 'dynasty', 'colony', 'jahon'] },
  { id: 'languages', label: 'Languages', emoji: '🗣️', keywords: ['grammar', 'language', 'verb', 'tense', 'vocabulary', 'english', 'spanish', 'essay', 'writing', 'noun', 'pronoun', 'sentence', 'spelling'] },
  { id: 'coding', label: 'Coding', emoji: '💻', keywords: ['code', 'coding', 'javascript', 'python', 'function', 'loop', 'programming', 'variable', 'array', 'recursion', 'class', 'bug', 'html', 'css'] },
  { id: 'geography', label: 'Geography', emoji: '🌍', keywords: ['country', 'capital', 'geography', 'river', 'mountain', 'climate', 'continent', 'map', 'ocean', 'population', 'tectonic'] },
]

const detectedSubject = computed<SubjectRule | null>(() => {
  const text = problemText.value.toLowerCase()
  if (!text.trim()) return null
  let best: SubjectRule | null = null
  let bestScore = 0
  for (const rule of subjectRules) {
    let score = 0
    for (const kw of rule.keywords) if (text.includes(kw)) score++
    if (score > bestScore) {
      bestScore = score
      best = rule
    }
  }
  return bestScore > 0 ? best : null
})

function subjectName(id?: string) {
  return id ? t(`subjects.${id}`) : t('subjects.fallback')
}
const subjectLabel = computed(() => subjectName(detectedSubject.value?.id))

/* ----------------------------------------------------------------
   Prompt assembly — the real prompt lives in .env.
----------------------------------------------------------------- */
const PROMPT_TEMPLATE = (import.meta.env.VITE_AI_SYSTEM_PROMPT as string | undefined) ?? ''
/* Forcing Tailwind on the generated page keeps the output short: the model
   styles with utility classes instead of emitting a big hand-written <style>
   block, which cuts generated code (and generation time/tokens) substantially
   and avoids truncation/continuation rounds. */
const TAILWIND_REQUIREMENT =
  `\n\nSTYLING REQUIREMENT — USE TAILWIND CSS, NOT HAND-WRITTEN CSS:\n` +
  `• Load Tailwind exactly once in <head> via the Play CDN: ` +
  `<script src="https://cdn.tailwindcss.com"><\/script>\n` +
  `• Style EVERYTHING with Tailwind utility classes directly on the elements — ` +
  `layout (flex/grid), spacing, sizing, colors, typography, rounded corners, borders, ` +
  `shadows, and interactive states (hover: focus: active: disabled:) and responsive ` +
  `prefixes (sm: md:). Use a dark, modern look (e.g. bg-slate-900 text-slate-100 with an accent color).\n` +
  `• Do NOT write a large <style> block. Only add a tiny <style> for the few things ` +
  `utilities cannot express (custom @keyframes, or making a <canvas> fill its parent).\n` +
  `• This is mandatory: keep the document compact by relying on utility classes.`

/* The preview runs in a sandboxed iframe WITHOUT allow-modals, so the native
   dialog functions are blocked. Tell the model to show feedback in the page
   instead — otherwise win/lose messages silently fail. */
const NO_DIALOGS_REQUIREMENT =
  `\n\nNO BROWSER DIALOGS: Never call alert(), confirm(), or prompt() — the page ` +
  `runs in a sandbox where they do nothing. Show all feedback (scores, win/lose, ` +
  `hints) in on-page elements you create and update with the DOM.`

const usePersonalizedStrategy = ref(true)

function getPersonalizedPromptExtension(): string {
  if (!usePersonalizedStrategy.value) return ''
  const savedExtra = localStorage.getItem('prime_profile_extra')
  if (!savedExtra) return ''
  try {
    const extra = JSON.parse(savedExtra)
    const edu = extra.education_class || ''
    const subject = extra.favorite_subject || ''
    const custom = extra.custom_subject || ''
    
    let ageGroup = 'general student'
    let difficulty = 'easy-medium'
    let themeInstruction = ''
    
    if (edu === 'PRE_SCHOOL') {
      ageGroup = 'pre-school child (4-6 years old)'
      difficulty = 'extremely easy'
      themeInstruction = 'Use super simple wording, highly gamified mechanics, cute animal or cartoon styling, and no complex formulas. Keep instructions to single sentences.'
    } else if (edu === 'ELEMENTARY') {
      ageGroup = 'elementary school student (7-10 years old)'
      difficulty = 'easy'
      themeInstruction = 'Use simple concepts, colorful adventure/gamified mechanics, basic instructions, and avoid college-level math. Show visual guides.'
    } else if (edu === 'HIGH_SCHOOL') {
      ageGroup = 'high school student (14-18 years old)'
      difficulty = 'medium'
      themeInstruction = 'Use standard high school science/math curriculum level, structured challenges, clear goals, and basic equations.'
    } else if (edu === 'UNI') {
      ageGroup = 'university student'
      difficulty = 'medium-hard'
      themeInstruction = 'Use advanced university level concepts, academic terminology, deep simulation mechanics, and interactive variables.'
    } else if (edu === 'GRADUATED') {
      ageGroup = 'graduated adult learner'
      difficulty = 'medium-hard'
      themeInstruction = 'Use mature, professional design aesthetics, deep analytical tools, and comprehensive data visualization.'
    }

    const favSubName = subject === 'OTHER' ? custom : subject
    const subjectHook = favSubName ? `\n- The user's favorite subject is ${favSubName}. If possible, use creative hooks or analogies referencing this subject to explain the core concept.` : ''
    
    return (
      `\n\nPERSONALIZED LEARNING STRATEGY (ENABLED):` +
      `\n- Target Audience: ${ageGroup}` +
      `\n- Game/Experience Difficulty: ${difficulty}` +
      `\n- Theme & Styling Instruction: ${themeInstruction}` +
      subjectHook +
      `\n- Adapt the layout, language complexity, interaction model, and overall gameplay to match this grade level.`
    )
  } catch {
    return ''
  }
}

const composedPrompt = computed(() => {
  const base = PROMPT_TEMPLATE.replace('{{MODE}}', 'game').replace('{{STUDENT_THOUGHTS}}', problemText.value.trim())
  const lang = aiLanguageName(locale.value as LocaleCode)
  return (
    `${base}${TAILWIND_REQUIREMENT}${NO_DIALOGS_REQUIREMENT}` +
    `\n\nLANGUAGE REQUIREMENT: Write ALL human-readable text on the page ` +
    `(instructions, headings, labels, buttons, explanations, and any messages shown by the JavaScript) ` +
    `in ${lang}. Keep all code, identifiers, HTML attribute names and math symbols unchanged.` +
    getPersonalizedPromptExtension()
  )
})

/* The generated page lives inside the sandboxed preview iframe
   (`<iframe class="w-full h-[560px]" sandbox="allow-scripts allow-pointer-lock">`).
   The exact height is fixed by that `h-[560px]` class. */
const SANDBOX_HEIGHT = 560

/** The EXACT inner size of the preview sandbox the experience will render in. */
function sandboxSize(): { w: number; h: number } {
  // Prefer measuring a real rendered preview iframe — that's the exact sandbox.
  const frames = chatScroll.value?.querySelectorAll<HTMLIFrameElement>('iframe[data-experience]')
  const frame = frames && frames.length ? frames[frames.length - 1] : null
  if (frame && frame.clientWidth > 0) {
    return { w: Math.round(frame.clientWidth), h: Math.round(frame.clientHeight) }
  }
  // No frame yet (first generation): compute the exact width from the chat
  // column. The iframe is full-width inside its row, so subtract the fixed
  // chrome around it: horizontal padding (2×26) + avatar (32) + gap (10) +
  // container border (2) = 96px. Height is the fixed 560 from the class.
  const col = chatScroll.value?.clientWidth ?? window.innerWidth
  return { w: Math.max(1, Math.round(col - 96)), h: SANDBOX_HEIGHT }
}

function deviceContext(): string {
  const vw = window.innerWidth
  const vh = window.innerHeight
  const dpr = Math.round((window.devicePixelRatio || 1) * 100) / 100
  const { w: rw, h: rh } = sandboxSize()
  const orientation = rw >= rh ? 'landscape' : 'portrait'
  const form = vw < 600 ? 'mobile phone' : vw < 1024 ? 'tablet' : 'desktop'
  const twoCol = rw >= 720
  return (
    `\n\nTARGET SANDBOX & RENDER AREA: The page renders inside a sandboxed iframe ` +
    `(sandbox="allow-scripts allow-pointer-lock") that is EXACTLY ${rw}px wide × ${rh}px tall ` +
    `on a ${form} (full device viewport ${vw}×${vh}px, ${dpr}× pixel density, ${orientation}). ` +
    `Design specifically for THIS exact size: everything must fit and be fully usable with NO ` +
    `horizontal scrolling and NO vertical overflow beyond ${rh}px; size every canvas/interactive ` +
    `element from this area (not a hard-coded width); use large, touch-friendly targets. ` +
    (twoCol
      ? `There is room for the two-column layout (game left, controls right).`
      : `This is narrow — use a single-column layout optimized for ${orientation} ${form}, with controls below or beside the game as space allows; do NOT force two columns.`)
  )
}

/* ---------- Loading copy (localized) ---------- */
const funFacts = computed(() => tm('funFacts') as unknown as string[])
const loadingSteps = computed(() => tm('loadingSteps') as unknown as string[])
const currentFact = ref('')
const currentStep = ref(0)
// Topic-specific fun facts streamed from Gemini Live for the current question.
// When non-empty the loading rotation cycles these instead of the generic list.
const aiFacts = ref<string[]>([])
let factTimer: ReturnType<typeof setInterval> | null = null
let stepTimer: ReturnType<typeof setInterval> | null = null

function randomFact(): string {
  const pool = aiFacts.value.length ? aiFacts.value : funFacts.value
  return pool[Math.floor(Math.random() * pool.length)] ?? ''
}

function stopTimers() {
  if (factTimer) clearInterval(factTimer)
  if (stepTimer) clearInterval(stepTimer)
  factTimer = null
  stepTimer = null
}

/* ================================================================
   Mock generator — STAND-IN for the real AI until a key is wired up.
   Each builder is a different interactive mini-app; we pick one from
   the detected subject and shuffle so regenerating stays fresh.
================================================================= */
function escapeHtml(str: string): string {
  return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function shell(o: { tag: string; title: string; accent: string; css: string; body: string }): string {
  const safeTopic = escapeHtml(problemText.value.trim() || `the basics of ${subjectLabel.value}`)
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="UTF-8" /><meta name="viewport" content="width=device-width, initial-scale=1.0" />
<style>
*{box-sizing:border-box;margin:0;padding:0;}
body{font-family:'Segoe UI',system-ui,sans-serif;background:radial-gradient(circle at 30% 8%,#1e1b4b,#070a14 72%);color:#f8fafc;min-height:100vh;padding:22px;display:flex;flex-direction:column;gap:16px;}
.tag{font-size:.74rem;letter-spacing:.14em;text-transform:uppercase;color:${o.accent};font-weight:800;}
h1{font-size:1.45rem;line-height:1.2;}
.sub{opacity:.65;font-size:.9rem;margin-top:4px;}
button{font-family:inherit;}
${o.css}
</style></head>
<body>
<div><span class="tag">${o.tag}</span><h1>${o.title}</h1><p class="sub">Built from your words: <em>${safeTopic}</em></p></div>
${o.body}
</body></html>`
}

function buildRocket(accent: string): string {
  return shell({
    accent,
    tag: 'Physics · Flight Lab',
    title: '🚀 Fly the rocket — feel velocity, gravity &amp; drag',
    css: `
canvas{width:100%;flex:1;min-height:280px;background:linear-gradient(#0b1024,#131c44);border:1px solid rgba(255,255,255,.1);border-radius:16px;touch-action:none;}
.hud{display:flex;gap:10px;flex-wrap:wrap;}
.stat{flex:1;min-width:100px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:10px 12px;}
.stat b{display:block;font-size:1.3rem;color:${accent};}
.stat span{font-size:.68rem;opacity:.6;text-transform:uppercase;letter-spacing:.08em;}
.ctl{display:flex;flex-direction:column;gap:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:14px;}
.row{display:flex;align-items:center;gap:12px;}
.row label{width:84px;font-size:.82rem;opacity:.85;}
.row input{flex:1;accent-color:${accent};}
.thrust{width:100%;padding:16px;border:none;border-radius:14px;background:${accent};color:#fff;font-size:1.05rem;font-weight:800;cursor:pointer;user-select:none;}
.thrust:active{filter:brightness(1.3);}`,
    body: `
<canvas id="c"></canvas>
<div class="hud">
  <div class="stat"><b id="alt">0</b><span>Altitude (m)</span></div>
  <div class="stat"><b id="vel">0.0</b><span>Velocity (m/s)</span></div>
  <div class="stat"><b id="net">0.0</b><span>Net accel</span></div>
</div>
<div class="ctl">
  <div class="row"><label>Gravity</label><input id="g" type="range" min="0" max="40" value="18"></div>
  <div class="row"><label>Air drag</label><input id="d" type="range" min="0" max="20" value="6"></div>
  <button class="thrust" id="t">HOLD TO FIRE THRUSTERS 🔥</button>
</div>
<script>
var cv=document.getElementById('c'),x=cv.getContext('2d');
function fit(){cv.width=cv.clientWidth;cv.height=cv.clientHeight;}fit();addEventListener('resize',fit);
var y=0,vy=0,thr=false;
var gEl=document.getElementById('g'),dEl=document.getElementById('d'),t=document.getElementById('t');
function on(e){if(e)e.preventDefault();thr=true;}function off(){thr=false;}
t.addEventListener('mousedown',on);t.addEventListener('touchstart',on,{passive:false});
addEventListener('mouseup',off);addEventListener('touchend',off);
function step(){
  var g=parseFloat(gEl.value)/10,dr=parseFloat(dEl.value)/900,thrust=thr?4.6:0;
  var net=thrust-g-(vy*Math.abs(vy)*dr);
  vy+=net*0.16;y+=vy*0.16;if(y<0){y=0;if(vy<0)vy=0;}
  document.getElementById('alt').textContent=Math.round(y);
  document.getElementById('vel').textContent=vy.toFixed(1);
  document.getElementById('net').textContent=net.toFixed(1);
  draw();requestAnimationFrame(step);
}
function draw(){
  x.clearRect(0,0,cv.width,cv.height);
  var gY=cv.height-26;
  x.fillStyle='rgba(255,255,255,.12)';x.fillRect(0,gY,cv.width,26);
  var px=cv.width/2,py=gY-22-Math.min(y*1.3,cv.height-100);
  if(thr){x.fillStyle='#ff8a00';x.beginPath();x.moveTo(px-8,py+22);x.lineTo(px+8,py+22);x.lineTo(px,py+40+Math.random()*12);x.closePath();x.fill();}
  x.font='30px serif';x.textAlign='center';x.fillText('🚀',px,py+22);
}
step();
<\/script>`,
  })
}

function buildPi(accent: string): string {
  return shell({
    accent,
    tag: 'Mathematics · Reveal',
    title: '➗ Unroll a circle — meet π for real',
    css: `
canvas{width:100%;flex:1;min-height:240px;background:#0b1024;border:1px solid rgba(255,255,255,.1);border-radius:16px;}
.ctl{display:flex;flex-direction:column;gap:12px;background:rgba(255,255,255,.04);border:1px solid rgba(255,255,255,.1);border-radius:16px;padding:14px;}
.row{display:flex;align-items:center;gap:12px;}
.row label{width:120px;font-size:.85rem;opacity:.85;}
.row input{flex:1;accent-color:${accent};}
.eq{font-size:1.15rem;text-align:center;}
.eq b{color:${accent};}
#roll{width:100%;padding:15px;border:none;border-radius:14px;background:${accent};color:#fff;font-weight:800;font-size:1rem;cursor:pointer;}
#s{min-height:24px;text-align:center;font-size:.95rem;}`,
    body: `
<canvas id="c"></canvas>
<p class="eq">C = π × d = <b><span id="cval">0</span></b> &nbsp;(diameter = <span id="dval">0</span>)</p>
<div class="ctl">
  <div class="row"><label>Diameter (d)</label><input id="d" type="range" min="40" max="150" value="90"></div>
  <button id="roll">▶ Roll the circle once</button>
</div>
<p id="s"></p>
<script>
var ACC='${accent}';
var cv=document.getElementById('c'),x=cv.getContext('2d'),dEl=document.getElementById('d'),anim=null;
function fit(){cv.width=cv.clientWidth;cv.height=cv.clientHeight;}fit();addEventListener('resize',fit);
function dia(){return parseInt(dEl.value,10);}
function circ(){return Math.PI*dia();}
function show(){document.getElementById('cval').textContent=circ().toFixed(2);document.getElementById('dval').textContent=dia();draw(0);}
dEl.oninput=function(){if(anim)cancelAnimationFrame(anim);document.getElementById('s').textContent='';show();};
function draw(dist){
  x.clearRect(0,0,cv.width,cv.height);
  var R=dia()/2,baseY=cv.height*0.66,startX=34,d=dia();
  x.strokeStyle='rgba(255,255,255,.25)';x.lineWidth=2;x.beginPath();x.moveTo(startX,baseY);x.lineTo(cv.width-8,baseY);x.stroke();
  x.fillStyle='rgba(255,255,255,.55)';x.font='11px sans-serif';
  for(var k=1;k<=3;k++){var tx=startX+d*k;if(tx<cv.width-8){x.fillRect(tx,baseY-7,1,14);x.fillText(k+'d',tx-7,baseY+18);}}
  x.strokeStyle=ACC;x.lineWidth=5;x.beginPath();x.moveTo(startX,baseY);x.lineTo(startX+dist,baseY);x.stroke();
  var cx=startX+dist,cy=baseY-R,ang=dist/R;
  x.strokeStyle='#fff';x.lineWidth=2;x.beginPath();x.arc(cx,cy,R,0,Math.PI*2);x.stroke();
  x.fillStyle=ACC;x.beginPath();x.arc(cx+R*Math.sin(ang),cy+R*Math.cos(ang),5,0,Math.PI*2);x.fill();
}
document.getElementById('roll').onclick=function(){
  if(anim)cancelAnimationFrame(anim);var C=circ(),start=null;
  function f(ts){if(!start)start=ts;var p=Math.min((ts-start)/2200,1);draw(C*p);if(p<1)anim=requestAnimationFrame(f);
    else document.getElementById('s').innerHTML='<b style="color:#34d399">One roll = '+C.toFixed(2)+' = π × '+dia()+'. So π is just "how many diameters fit around the circle" ≈ 3.14. Always.</b>';}
  anim=requestAnimationFrame(f);
};
show();
<\/script>`,
  })
}

function buildReaction(accent: string): string {
  return shell({
    accent,
    tag: 'Chemistry · Lab Bench',
    title: '⚗️ Mix atoms — build a real molecule',
    css: `
.flask{font-size:1.6rem;min-height:64px;background:rgba(255,255,255,.05);border:1px dashed rgba(255,255,255,.2);border-radius:16px;display:flex;align-items:center;justify-content:center;padding:14px;letter-spacing:.05em;}
.atoms{display:grid;grid-template-columns:repeat(auto-fit,minmax(70px,1fr));gap:10px;}
.atoms button{padding:14px;border:none;border-radius:12px;background:rgba(255,255,255,.08);color:#fff;font-size:1rem;font-weight:700;cursor:pointer;}
.atoms button:active{background:${accent};}
.go{display:flex;gap:10px;}
.go button{flex:1;padding:14px;border:none;border-radius:12px;font-weight:800;cursor:pointer;}
#react{background:${accent};color:#fff;}#clr{background:rgba(255,255,255,.08);color:#fff;}
#out{min-height:60px;border-radius:14px;padding:14px;font-size:.95rem;line-height:1.5;background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.25);color:#fcd34d;}`,
    body: `
<div class="flask" id="flask">tap atoms to drop them in…</div>
<div class="atoms">
  <button data-s="H">H 💧</button><button data-s="O">O 🅾️</button><button data-s="C">C ⚫</button>
  <button data-s="Na">Na 🧂</button><button data-s="Cl">Cl 🟢</button>
</div>
<div class="go"><button id="react">⚗️ React!</button><button id="clr">Clear</button></div>
<div id="out">Try <b>H + H + O</b>, or <b>C + O + O</b>, or <b>Na + Cl</b>…</div>
<script>
var counts={};
var recipes=[
 {k:{H:2,O:1},n:'💧 Water (H₂O)',f:'Two hydrogens grab one oxygen — the molecule every living thing runs on.'},
 {k:{C:1,O:2},n:'🌫️ Carbon dioxide (CO₂)',f:'One carbon, two oxygens — what you breathe out and plants drink in.'},
 {k:{Na:1,Cl:1},n:'🧂 Table salt (NaCl)',f:'A reactive metal + a poison gas bond into the salt on your fries.'},
 {k:{C:1,H:4},n:'🔥 Methane (CH₄)',f:'One carbon hugging four hydrogens — natural gas, and cow burps.'}];
function render(){var s='';for(var k in counts){if(counts[k])s+=k+(counts[k]>1?'<sub>'+counts[k]+'</sub>':'')+' ';}
  document.getElementById('flask').innerHTML=s||'tap atoms to drop them in…';}
document.querySelectorAll('.atoms button').forEach(function(b){b.onclick=function(){var s=b.getAttribute('data-s');counts[s]=(counts[s]||0)+1;render();};});
document.getElementById('clr').onclick=function(){counts={};render();document.getElementById('out').innerHTML='Cleared. Try another combo!';};
document.getElementById('react').onclick=function(){
  var match=null;
  recipes.forEach(function(r){var ok=true,keys={};for(var k in r.k)keys[k]=1;for(var c in counts)if(counts[c])keys[c]=1;
    for(var k in keys)if((counts[k]||0)!==(r.k[k]||0))ok=false;if(ok)match=r;});
  var out=document.getElementById('out');
  if(match){out.innerHTML='<b style="color:#34d399">'+match.n+'</b><br>'+match.f;}
  else{out.innerHTML='🤔 Those atoms won\\'t form a stable molecule. Hint: count carefully — H₂O needs <b>two</b> H.';}
};
render();
<\/script>`,
  })
}

function buildLoop(accent: string): string {
  return shell({
    accent,
    tag: 'Coding · Trace It',
    title: '💻 Step through a loop, watch it think',
    css: `
pre{background:#0b1024;border:1px solid rgba(255,255,255,.1);border-radius:14px;padding:16px;font-family:ui-monospace,monospace;font-size:.95rem;line-height:1.7;overflow:auto;}
.hi{background:${accent};color:#fff;padding:0 4px;border-radius:4px;}
.row{display:flex;align-items:center;gap:12px;}
.row label{font-size:.85rem;opacity:.85;}
.row input{flex:1;accent-color:${accent};}
.go{display:flex;gap:10px;}
.go button{flex:1;padding:14px;border:none;border-radius:12px;font-weight:800;cursor:pointer;}
#step{background:${accent};color:#fff;}#reset{background:rgba(255,255,255,.08);color:#fff;}
.out{min-height:48px;background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.1);border-radius:12px;padding:14px;font-family:ui-monospace,monospace;}
.out b{color:${accent};}`,
    body: `
<div class="row"><label>Repeat n =</label><input id="n" type="range" min="2" max="8" value="5"><span id="nv">5</span></div>
<pre id="code"></pre>
<div class="out">output: [ <span id="arr"></span>]</div>
<div class="go"><button id="step">▶ Run next step</button><button id="reset">↻ Reset</button></div>
<script>
var ACC='${accent}';
var nEl=document.getElementById('n'),i=0,started=false,out=[];
function n(){return parseInt(nEl.value,10);}
function code(active){
  var line='for (let i = 0; i < '+n()+'; i++) {';
  if(active)line=line.replace('i < '+n(),'i < '+n()+'   // i = '+i);
  return line+'\\n  output.push(i);\\n}';
}
function render(running){
  document.getElementById('nv').textContent=n();
  var c=code(running);
  if(running)c=c.replace('output.push(i);','<span class="hi">output.push('+i+');</span>');
  document.getElementById('code').innerHTML=c;
  document.getElementById('arr').textContent=out.join(', ')+(out.length?' ':'');
}
nEl.oninput=function(){i=0;out=[];started=false;render(false);};
document.getElementById('step').onclick=function(){
  if(i>=n()){document.getElementById('arr').innerHTML=out.join(', ')+' &nbsp;<b style="color:#34d399">✓ loop finished — it ran '+n()+' times</b>';return;}
  out.push(i);render(true);i++;
};
document.getElementById('reset').onclick=function(){i=0;out=[];render(false);};
render(false);
<\/script>`,
  })
}

function buildCellCity(accent: string): string {
  return shell({
    accent,
    tag: 'Biology · Gamified Quest',
    title: '🧪 Cell City — tap each building to learn its job',
    css: `
.score{font-size:1.05rem;font-weight:700;}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin-top:12px;}
.cell{cursor:pointer;background:${accent};border:none;color:#fff;border-radius:14px;padding:16px;font-size:.95rem;font-weight:700;text-align:left;transition:transform .15s,box-shadow .15s;}
.cell:hover{transform:translateY(-3px);box-shadow:0 10px 24px rgba(0,0,0,.4);}
.cell small{display:block;font-weight:400;opacity:.9;margin-top:6px;}
.fact{background:rgba(251,191,36,.1);border:1px solid rgba(251,191,36,.3);border-radius:14px;padding:16px;font-size:.95rem;color:#fde68a;}
.done{color:#34d399;font-weight:700;}`,
    body: `
<div class="score">Discovered: <span id="score">0</span> / 4 🏆</div>
<div class="grid">
  <button class="cell" data-fact="The nucleus is City Hall — it stores the master plans (DNA) and bosses everyone around.">🏛️ Nucleus <small>Tap to reveal</small></button>
  <button class="cell" data-fact="Mitochondria are the power plants — they burn fuel to make ATP energy. (The powerhouse of the cell.)">⚡ Mitochondria <small>Tap to reveal</small></button>
  <button class="cell" data-fact="Ribosomes are tiny factories stamping out proteins from the nucleus's blueprints.">🏭 Ribosomes <small>Tap to reveal</small></button>
  <button class="cell" data-fact="The membrane is the city wall with smart gates — it decides what gets in and out.">🚪 Membrane <small>Tap to reveal</small></button>
</div>
<div class="fact">🤯 If you uncoiled all the DNA in your body it would stretch ~10 billion miles — Pluto and back.</div>
<p id="status" style="opacity:.7;">Tap all four buildings to complete the quest!</p>
<script>
var found=0,seen=new Set();
document.querySelectorAll('.cell').forEach(function(b){b.addEventListener('click',function(){
  if(!seen.has(b)){seen.add(b);found++;document.getElementById('score').textContent=found;}
  b.querySelector('small').textContent=b.dataset.fact;
  if(found===4)document.getElementById('status').innerHTML='<span class="done">🎉 Quest complete! You just toured a living city.</span>';
});});
<\/script>`,
  })
}

function buildGeneric(accent: string): string {
  const safe = escapeHtml(problemText.value.trim() || `the basics of ${subjectLabel.value}`)
  const subj = escapeHtml(subjectLabel.value)
  return shell({
    accent,
    tag: subj + ' · Memory Hooks',
    title: '🃏 Flip the cards until it clicks',
    css: `
.bar{height:8px;background:rgba(255,255,255,.08);border-radius:99px;overflow:hidden;}
.bar i{display:block;height:100%;width:0;background:${accent};transition:width .4s;}
.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;}
.card{height:160px;perspective:900px;cursor:pointer;}
.inner{position:relative;width:100%;height:100%;transition:transform .55s;transform-style:preserve-3d;}
.card.flip .inner{transform:rotateY(180deg);}
.face{position:absolute;inset:0;backface-visibility:hidden;border-radius:16px;padding:16px;display:flex;align-items:center;justify-content:center;text-align:center;}
.front{background:${accent};color:#fff;font-weight:800;font-size:1.05rem;}
.back{background:rgba(255,255,255,.06);border:1px solid rgba(255,255,255,.14);transform:rotateY(180deg);font-size:.88rem;line-height:1.5;}
#s{min-height:24px;}.done{color:#34d399;font-weight:700;}`,
    body: `
<p style="opacity:.85">Flip each card. Tap it again when it finally makes sense — <span id="n">0</span>/3 locked in 🔓</p>
<div class="bar"><i id="p"></i></div>
<div class="cards">
  <div class="card"><div class="inner">
    <div class="face front">🤔 What is it, really?</div>
    <div class="face back">Strip the jargon from «${safe}» — at its core it's one simple pattern in ${subj} you can picture in your head.</div>
  </div></div>
  <div class="card"><div class="inner">
    <div class="face front">🔗 Why does it matter?</div>
    <div class="face back">This idea shows up everywhere in ${subj}. Once it clicks, the next ten things you learn lean on it.</div>
  </div></div>
  <div class="card"><div class="inner">
    <div class="face front">🧠 How to remember it</div>
    <div class="face back">Tie it to something you already know. Explain «${safe}» out loud in one sentence — if you can, you've got it.</div>
  </div></div>
</div>
<p id="s"></p>
<script>
var locked=new Set();
document.querySelectorAll('.card').forEach(function(c){c.addEventListener('click',function(){
  c.classList.toggle('flip');
  if(c.classList.contains('flip'))locked.add(c);
  document.getElementById('n').textContent=locked.size;
  document.getElementById('p').style.width=(locked.size/3*100)+'%';
  if(locked.size===3)document.getElementById('s').innerHTML='<span class="done">🎉 All three flipped — you just rebuilt the idea in your own words.</span>';
});});
<\/script>`,
  })
}

const ACCENTS = ['#6366f1', '#a855f7', '#ec4899', '#06b6d4', '#22c55e', '#f59e0b', '#fb7185']
const EXPERIENCES: Record<string, ((accent: string) => string)[]> = {
  physics: [buildRocket],
  math: [buildPi],
  chemistry: [buildReaction],
  coding: [buildLoop],
  biology: [buildCellCity],
}

function buildExperience(): string {
  const accent = ACCENTS[Math.floor(Math.random() * ACCENTS.length)] ?? '#6366f1'
  const id = detectedSubject.value?.id
  const matched = id ? EXPERIENCES[id] : undefined
  const pool = matched ? [...matched, buildGeneric] : [buildGeneric, buildRocket, buildPi, buildReaction, buildLoop, buildCellCity]
  const pick = pool[Math.floor(Math.random() * pool.length)] ?? buildGeneric
  return pick(accent)
}

/* ---------- Submit / generate ---------- */
async function submit(rawTopic?: string, premadeKey?: string) {
  const topic = (rawTopic ?? draft.value).trim()
  if (!topic || isGenerating.value) return

  problemText.value = topic
  draft.value = ''
  pushRecent(topic)
  emit('topic', topic)

  messages.value.push({ id: msgId++, role: 'user', type: 'text', text: topic })
  const loadingMsg: ChatMessage = { id: msgId++, role: 'assistant', type: 'loading' }
  messages.value.push(loadingMsg)
  scrollToEnd()

  isGenerating.value = true
  currentStep.value = 0
  aiFacts.value = []
  currentFact.value = randomFact()

  const genLocale = locale.value as LocaleCode
  const aiLang = aiLanguageName(genLocale)

  const calcInterval = (text: string) => {
    const wordCount = text.split(/\s+/).length
    return Math.max(2000, (wordCount / 2) * 1200)
  }
  const factPoolSize = () => (aiFacts.value.length ? aiFacts.value.length : funFacts.value.length)
  const changeFact = () => {
    let next = currentFact.value
    while (next === currentFact.value && factPoolSize() > 1) next = randomFact()
    currentFact.value = next
    if (factTimer) clearInterval(factTimer)
    factTimer = setInterval(changeFact, calcInterval(next))
  }
  factTimer = setInterval(changeFact, calcInterval(currentFact.value))
  stepTimer = setInterval(() => {
    if (currentStep.value < loadingSteps.value.length - 1) currentStep.value++
  }, 900)

  // TEST MODE: a known simulation card plays its hand-built experience
  // after a random 3–7s "playing" delay, instead of calling the AI.
  const premade = testMode && premadeKey ? getPremade(premadeKey) : null

  // Sharpen the student's raw words into a richer brief (Gemini Live, text via
  // transcription). SHORT and BLOCKING — the brief must reach the generator. It
  // runs first on the shared session so it doesn't wait behind the facts turn.
  let refinedBrief = ''
  if (!premade && aiConfigured && liveConfigured) {
    refinedBrief = await enhanceTopic(topic, aiLang)
  }

  // Topic-specific fun facts (Gemini Live), AFTER the rewrite. NON-blocking and
  // continuous: keep pulling fresh batches (deduped) while the experience
  // generates, so the loading rotation never runs dry. Stops when the page is
  // ready, a batch fails, or no new facts come back.
  if (!premade && aiConfigured && liveConfigured) {
    void (async () => {
      const seen = new Set<string>()
      while (isGenerating.value) {
        const facts = await funFactsFor(topic, aiLang, 18)
        if (!isGenerating.value || !facts.length) break
        const before = aiFacts.value.length
        for (const f of facts) {
          const key = f.toLowerCase()
          if (!seen.has(key)) {
            seen.add(key)
            aiFacts.value.push(f)
          }
        }
        // The moment the first AI facts land, switch the rotation onto them.
        if (before === 0 && aiFacts.value.length > 0) {
          currentFact.value = aiFacts.value[0] ?? currentFact.value
          if (factTimer) clearInterval(factTimer)
          factTimer = setInterval(changeFact, calcInterval(currentFact.value))
        }
        if (aiFacts.value.length === before) break // batch added nothing new
      }
    })()
  }

  await nextTick()
  let prompt = composedPrompt.value + deviceContext()
  if (refinedBrief && refinedBrief.toLowerCase().trim() !== topic.toLowerCase()) {
    prompt +=
      `\n\nREFINED BRIEF (an AI-clarified restatement of the student's request — ` +
      `use it to make the experience more specific and engaging while keeping ` +
      `their original intent): ${refinedBrief}`
  }
  console.debug(`[AI prompt → ${aiModel}]\n`, prompt)

  try {
    let html: string
    let htmlLang: LocaleCode = genLocale
    if (premade) {
      await new Promise((resolve) => setTimeout(resolve, premadeDelayMs()))
      html = premade
      htmlLang = PREMADE_LOCALE
    } else if (aiConfigured) {
      html = await generateExperience(prompt)
    } else {
      await new Promise((resolve) => setTimeout(resolve, 4200))
      html = buildExperience()
    }
    stopTimers()
    replaceLoading(loadingMsg.id, html, htmlLang)
    showToast(t('toasts.ready'), 'success')

    const token = getToken()
    if (token) {
      try {
        const saved = await createHistory(token, {
          question: topic,
          data: [html]
        })
        historyRecords.value.unshift(saved)
        pushRecent(topic)
      } catch (err) {
        console.error('[Failed to save history]', err)
      }
    }
  } catch (err) {
    stopTimers()
    console.error('[AI generation failed]', err)
    replaceLoading(loadingMsg.id, buildExperience(), genLocale)
    showToast(t('toasts.hiccup'), 'error')
  } finally {
    isGenerating.value = false
    scrollToEnd()
  }
}

function replaceLoading(id: number, html: string, htmlLocale: LocaleCode) {
  const idx = messages.value.findIndex((m) => m.id === id)
  if (idx === -1) return
  messages.value[idx] = { id, role: 'assistant', type: 'experience', html, htmlLocale }
}

/* ---------- Instant translation of the latest live experience ---------- */
watch(locale, async (code) => {
  const target = code as LocaleCode
  if (isGenerating.value) return
  // Translate the most recent experience message in place.
  for (let i = messages.value.length - 1; i >= 0; i--) {
    const m = messages.value[i]!
    if (m.type !== 'experience' || !m.html) continue
    const from = m.htmlLocale ?? currentLocaleCode()
    if (from === target) return
    const source = m.html
    try {
      const translated = await translateHtmlText(source, target, from)
      if (messages.value[i]?.html !== source) return
      messages.value[i] = { ...m, html: translated, htmlLocale: target }
      showToast(t('toasts.translated', { lang: target.toUpperCase() }), 'success')
    } catch (err) {
      console.error('[translation failed]', err)
      showToast(t('toasts.translateFail'), 'error')
    }
    return
  }
})

/* ---------- Live preview iframe sizing ---------- */
/* ---------- Sandbox dialog shim ----------
   The preview iframe is sandboxed WITHOUT `allow-modals`, so any
   alert()/confirm()/prompt() the generated game calls is silently ignored by
   the browser (and spams the console). Rather than allow blocking modals — a
   game's win/lose alert in a requestAnimationFrame loop would freeze the page —
   we inject a tiny script that turns those dialogs into non-blocking in-frame
   toasts. Works for AI, premade, and fallback HTML alike. */
const SANDBOX_SHIM = `<script>(function(){if(window.__dlgShim)return;window.__dlgShim=1;
function toast(msg){try{var h=document.getElementById('__dlg_toasts');if(!h){h=document.createElement('div');h.id='__dlg_toasts';h.style.cssText='position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:2147483647;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif';(document.body||document.documentElement).appendChild(h);}var e=document.createElement('div');e.textContent=String(msg);e.style.cssText='max-width:80vw;padding:10px 16px;border-radius:12px;background:rgba(17,24,39,.92);color:#fff;font-size:14px;line-height:1.4;box-shadow:0 8px 24px rgba(0,0,0,.25);opacity:0;transform:translateY(8px);transition:opacity .25s,transform .25s';h.appendChild(e);requestAnimationFrame(function(){e.style.opacity='1';e.style.transform='none';});setTimeout(function(){e.style.opacity='0';e.style.transform='translateY(8px)';setTimeout(function(){e.remove();},300);},2600);}catch(_){try{console.log('[alert]',msg);}catch(__){}}}
window.alert=function(m){toast(m);};window.confirm=function(m){if(m!=null)toast(m);return true;};window.prompt=function(m,d){if(m!=null)toast(m);return d!=null?d:'';};})();<\/script>`

/** Inject SANDBOX_SHIM as early as possible so it overrides the dialog
 *  functions before any game script runs. Uses a function replacer so `$`
 *  sequences in the HTML are never treated as replacement patterns. */
function withSandboxShim(html?: string): string {
  if (!html) return ''
  const anchor = html.match(/<head[^>]*>/i) || html.match(/<html[^>]*>/i) || html.match(/<body[^>]*>/i)
  if (anchor) return html.replace(anchor[0], (m) => m + SANDBOX_SHIM)
  return SANDBOX_SHIM + html
}

function handleFrameLoad(e: Event) {
  const f = e.target as HTMLIFrameElement
  const nudge = () => {
    const h = Math.max(1, f.clientHeight)
    f.style.height = h - 1 + 'px'
    requestAnimationFrame(() => {
      f.style.height = ''
    })
  }
  requestAnimationFrame(nudge)
  setTimeout(nudge, 200)
  setTimeout(nudge, 600)
}

/* ---------- Textarea behaviour ---------- */
function autoResize(event: Event) {
  const target = event.target as HTMLTextAreaElement
  target.style.height = 'auto'
  target.style.height = Math.min(target.scrollHeight, 140) + 'px'
}

function onKeydown(e: KeyboardEvent) {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault()
    submit()
  }
}

/* ---------- React to a seed topic coming from Home/Simulations ---------- */
watch(
  () => props.seed,
  (val) => {
    if (val && val.trim()) {
      submit(val, props.seedId)
      emit('seed-consumed')
    }
  },
  { immediate: true },
)

onUnmounted(stopTimers)
</script>

<template>
  <div class="h-full flex flex-col overflow-hidden">
    <!-- Header -->
    <header class="flex justify-between items-center py-[14px] px-[26px] border-b border-solid border-slate-200 bg-white shadow-sm flex-shrink-0 max-[600px]:py-3 max-[600px]:px-4">
      <div class="flex items-center gap-3">
        <span class="w-[42px] h-[42px] rounded-xl flex items-center justify-center text-white bg-gradient-to-br from-indigo-500 to-violet-500">
          <svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>
        </span>
        <div class="flex flex-col leading-[1.25]">
          <span class="font-bold text-base text-ink">{{ t('mentor.name') }}</span>
          <span class="inline-flex items-center gap-1.5 text-[0.78rem] text-green-400"><i class="w-[7px] h-[7px] rounded-full bg-green-400 shadow-[0_0_8px_#4ade80]"></i>{{ t('mentor.online') }}</span>
        </div>
      </div>
      <span class="inline-flex items-center gap-1.5 text-[0.78rem] font-semibold text-indigo-700 bg-indigo-500/[0.12] border border-solid border-indigo-400/30 py-1.5 px-[13px] rounded-full">
        <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="m12 3-1.9 5.8a2 2 0 0 1-1.3 1.3L3 12l5.8 1.9a2 2 0 0 1 1.3 1.3L12 21l1.9-5.8a2 2 0 0 1 1.3-1.3L21 12l-5.8-1.9a2 2 0 0 1-1.3-1.3z"/></svg>
        {{ t('mentor.powered') }}
      </span>
    </header>

    <div class="flex-1 flex min-h-0">
      <!-- Chat column -->
      <div class="flex-1 flex flex-col min-w-0">
        <div class="flex-1 overflow-y-auto py-6 px-[26px] flex flex-col gap-4 max-[600px]:py-[18px] max-[600px]:px-4" ref="chatScroll">
          <template v-for="m in messages" :key="m.id">
            <!-- Assistant text -->
            <div v-if="m.role === 'assistant' && m.type === 'text'" class="flex gap-2.5 max-w-full items-start">
              <span class="w-8 h-8 flex-shrink-0 rounded-[9px] flex items-center justify-center text-white bg-gradient-to-br from-indigo-500 to-violet-500">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>
              </span>
              <div class="bg-white border border-solid border-slate-200 rounded-[4px_16px_16px_16px] py-[13px] px-[17px] text-[0.92rem] leading-[1.55] text-ink max-w-[640px]">{{ m.text }}</div>
            </div>

            <!-- User text -->
            <div v-else-if="m.role === 'user'" class="flex gap-2.5 max-w-full justify-end">
              <div class="rounded-[16px_4px_16px_16px] py-[13px] px-[17px] text-[0.92rem] leading-[1.55] max-w-[640px] bg-gradient-to-br from-indigo-500 to-[#8b5cf6] text-white">{{ m.text }}</div>
            </div>

            <!-- Loading -->
            <div v-else-if="m.type === 'loading'" class="flex gap-2.5 max-w-full items-start">
              <span class="w-8 h-8 flex-shrink-0 rounded-[9px] flex items-center justify-center text-white bg-gradient-to-br from-indigo-500 to-violet-500">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>
              </span>
              <div class="bg-white border border-solid border-slate-200 rounded-[4px_16px_16px_16px] py-[13px] px-[17px] text-[0.92rem] leading-[1.55] text-ink max-w-[640px] flex flex-col gap-2 min-w-[240px]">
                <div class="flex items-center gap-2.5"><span class="w-[18px] h-[18px] border-2 border-solid border-slate-200 border-t-indigo-500 rounded-full animate-[spin_0.8s_linear_infinite] flex-shrink-0"></span><strong>{{ loadingSteps[currentStep] }}</strong></div>
                <p class="text-[0.85rem] text-ink-soft leading-[1.5]">{{ currentFact }}</p>
              </div>
            </div>

            <!-- Experience -->
            <div v-else-if="m.type === 'experience'" class="flex gap-2.5 max-w-full items-start">
              <span class="w-8 h-8 flex-shrink-0 rounded-[9px] flex items-center justify-center text-white bg-gradient-to-br from-indigo-500 to-violet-500">
                <svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 8V4H8"/><rect width="16" height="12" x="4" y="8" rx="2"/><path d="M2 14h2M20 14h2M15 13v2M9 13v2"/></svg>
              </span>
              <div class="flex-1 min-w-0 rounded-[16px] overflow-hidden border border-solid border-slate-200 bg-white shadow-sm">
                <iframe
                  :key="m.id + ':' + m.htmlLocale"
                  data-experience
                  class="w-full h-[560px] border-none block bg-white"
                  :srcdoc="withSandboxShim(m.html)"
                  sandbox="allow-scripts allow-pointer-lock"
                  @load="handleFrameLoad"
                ></iframe>
              </div>
            </div>
          </template>

          <!-- Popular topics (only before any interaction) -->
          <div v-if="showTopics" class="mt-1">
            <span class="text-[0.82rem] text-ink-mute">{{ t('mentor.popularLabel') }}</span>
            <div class="flex flex-wrap gap-2.5 mt-3">
              <button v-for="(topic, i) in popularTopics" :key="i" class="py-[9px] px-[18px] rounded-full border border-solid border-indigo-400/30 bg-indigo-400/[0.08] text-violet-700 font-body text-[0.86rem] font-semibold cursor-pointer transition-all duration-200 hover:bg-indigo-500/15 hover:border-indigo-400/50 hover:-translate-y-px" @click="loadTopicHistory(topic)">
                {{ topic }}
              </button>
            </div>
          </div>

          <!-- Recent topics (only before any interaction) -->
          <div v-if="showTopics && recentTopics.length" class="mt-6">
            <span class="text-[0.82rem] text-ink-mute">{{ t('mentor.recentTitle') }}</span>
            <div class="flex flex-wrap gap-2.5 mt-3">
              <button v-for="(topic, i) in recentTopics" :key="i" class="py-[9px] px-[18px] rounded-full border border-solid border-slate-200 bg-slate-50 text-slate-700 font-body text-[0.86rem] font-semibold cursor-pointer transition-all duration-200 hover:bg-slate-100 hover:border-slate-300 hover:-translate-y-px" @click="loadTopicHistory(topic)">
                {{ topic }}
              </button>
            </div>
          </div>
        </div>

        <!-- Input (round, transparent) -->
        <div class="flex-shrink-0 pt-4 px-[26px] pb-[22px] max-[600px]:pt-3 max-[600px]:px-4 max-[600px]:pb-[18px] flex flex-col gap-2.5">
          <!-- Personalized learning toggle button -->
          <div class="flex items-center justify-between px-3">
            <button 
              type="button"
              @click="usePersonalizedStrategy = !usePersonalizedStrategy"
              class="inline-flex items-center gap-2 text-[0.8rem] font-semibold transition-all duration-200 cursor-pointer bg-transparent border-none outline-none select-none"
              :class="usePersonalizedStrategy ? 'text-indigo-600' : 'text-slate-400'"
            >
              <!-- Toggle Switch icon -->
              <span class="relative inline-flex h-4 w-7 items-center rounded-full transition-colors duration-200" :class="usePersonalizedStrategy ? 'bg-indigo-600' : 'bg-slate-200'">
                <span class="inline-block h-2.5 w-2.5 transform rounded-full bg-white transition-transform duration-200" :style="{ transform: usePersonalizedStrategy ? 'translateX(14px)' : 'translateX(3px)' }" />
              </span>
              <span>{{ usePersonalizedStrategy ? t('mentor.strategyActive') : t('mentor.strategyInactive') }}</span>
            </button>
          </div>

          <div class="flex items-end gap-2.5 bg-white border border-solid border-slate-200 shadow-sm rounded-[26px] pt-3.5 pr-4 pb-3.5 pl-5 transition-all duration-200 focus-within:border-indigo-500 focus-within:bg-slate-100">
            <textarea
              v-model="draft"
              rows="1"
              class="flex-1 bg-transparent border-none outline-none resize-none text-ink font-body text-[0.95rem] leading-[1.5] max-h-[140px] min-h-[22px] placeholder:text-ink-mute"
              :placeholder="t('mentor.placeholder')"
              @input="autoResize"
              @keydown="onKeydown"
            ></textarea>
            <button class="w-[42px] h-[42px] flex-shrink-0 border-none rounded-full bg-gradient-to-br from-indigo-500 to-violet-500 text-white cursor-pointer flex items-center justify-center transition-all duration-200 enabled:hover:scale-[1.06] enabled:hover:shadow-[0_6px_16px_rgba(99,102,241,0.25)] disabled:opacity-40 disabled:cursor-not-allowed" :disabled="!draft.trim() || isGenerating" @click="submit()">
              <svg v-if="!isGenerating" xmlns="http://www.w3.org/2000/svg" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M14.536 21.686a.5.5 0 0 0 .937-.024l6.5-19a.496.496 0 0 0-.635-.635l-19 6.5a.5.5 0 0 0-.024.937l7.93 3.18a2 2 0 0 1 1.112 1.11z"/><path d="m21.854 2.147-10.94 10.939"/></svg>
              <span v-else class="w-[18px] h-[18px] border-2 border-solid border-white/[0.18] border-t-white rounded-full animate-[spin_0.8s_linear_infinite] flex-shrink-0"></span>
            </button>
          </div>
        </div>
      </div>

      <!-- Right panel — live 3D AI mentor (iframe) -->
      <aside class="w-[380px] flex-shrink-0 border-l border-solid border-slate-200 bg-slate-50 flex flex-col max-[900px]:hidden">
        <div class="flex items-center gap-2 py-3 px-4 border-b border-solid border-slate-200 bg-white flex-shrink-0">
          <span class="inline-flex items-center gap-1.5 text-[0.72rem] font-semibold text-indigo-700">
            <i class="w-[7px] h-[7px] rounded-full bg-green-400 shadow-[0_0_8px_#4ade80]"></i>
            {{ t('mentor.name') }}
          </span>
        </div>
        <div class="flex-1 min-h-0 relative">
          <iframe
            src="https://vmrchat.vercel.app/"
            title="3D AI mentor"
            class="absolute inset-0 w-full h-full border-none block bg-slate-900"
            allow="microphone; camera; autoplay; clipboard-write; fullscreen; xr-spatial-tracking"
            allowfullscreen
          ></iframe>
        </div>
      </aside>
    </div>
  </div>
</template>

<style scoped>
/* Custom keyframe referenced by the spinner via animate-[spin_0.8s_linear_infinite].
   Kept here because the arbitrary animation utility needs the `spin` keyframe defined. */
@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}
</style>
