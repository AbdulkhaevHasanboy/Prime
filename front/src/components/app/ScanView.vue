<script setup lang="ts">
import { ref, computed, onUnmounted } from 'vue'
import { useI18n } from 'vue-i18n'
import { useToast } from '../../composables/useToast'
import { extractDataFromImages, generateExperience, aiConfigured } from '../../managers/aiClient'
import type { ExtractedItem } from '../../managers/aiClient'
import { extractConceptsViaLive, liveConfigured } from '../../managers/liveClient'
import { aiLanguageName, type LocaleCode } from '../../i18n'

const { t, tm, locale } = useI18n()
const { showToast } = useToast()

interface UploadedImage {
  name: string
  base64: string
  previewUrl: string
  mimeType: string
}

// AI Engine selection
const models = [
  { id: 'gemini-3.1-flash-live-preview', name: 'Gemini 3.1 Live' },
  { id: 'gemini-3.5-flash', name: 'Gemini 3.5 Flash' }
]
const selectedModel = ref('gemini-3.1-flash-live-preview')

const genres = [
  { id: 'arcade', name: 'Arcade Challenge', icon: '🎮', desc: 'Fast-paced matching, catching, or sorting game' },
  { id: 'sandbox', name: 'Interactive Sandbox', icon: '🧪', desc: 'Variable controls, sliders, and visual simulations' },
  { id: 'quest', name: 'Adventure Quest', icon: '🗺️', desc: 'Choice-driven interactive story and scenario solving' },
  { id: 'trivia', name: 'Card Battler / Quiz Arena', icon: '🃏', desc: 'Concept-based deck battling or deck quiz' }
]
const selectedGenre = ref('arcade')

// State variables
const uploadedImages = ref<UploadedImage[]>([])
const isDragging = ref(false)
const isScanning = ref(false)
const isGenerating = ref(false)
const extractedConcepts = ref<ExtractedItem[]>([])
const selectedConcepts = ref<string[]>([])
const generatedHtml = ref('')
const currentStep = ref(0)
const currentFact = ref('')

// Timers for game generation progress
let factTimer: ReturnType<typeof setInterval> | null = null
let stepTimer: ReturnType<typeof setInterval> | null = null

const loadingSteps = computed(() => tm('loadingSteps') as unknown as string[])
const funFacts = computed(() => tm('funFacts') as unknown as string[])

// File handling
const fileInput = ref<HTMLInputElement | null>(null)

function triggerUpload() {
  fileInput.value?.click()
}

function handleFileChange(e: Event) {
  const target = e.target as HTMLInputElement
  if (target.files) {
    addFiles(target.files)
  }
}

function onDragOver(e: DragEvent) {
  e.preventDefault()
  isDragging.value = true
}

function onDragLeave() {
  isDragging.value = false
}

function onDrop(e: DragEvent) {
  e.preventDefault()
  isDragging.value = false
  if (e.dataTransfer?.files) {
    addFiles(e.dataTransfer.files)
  }
}

function addFiles(files: FileList) {
  for (let i = 0; i < files.length; i++) {
    const file = files[i]!
    if (!file.type.startsWith('image/')) {
      showToast(t('auth.toasts.generic'), 'error')
      continue
    }
    
    const previewUrl = URL.createObjectURL(file)
    const reader = new FileReader()
    reader.readAsDataURL(file)
    reader.onload = () => {
      const base64 = (reader.result as string).split(',')[1]!
      uploadedImages.value.push({
        name: file.name,
        base64,
        previewUrl,
        mimeType: file.type
      })
    }
  }
}

function removeImage(index: number) {
  const img = uploadedImages.value[index]
  if (img) {
    URL.revokeObjectURL(img.previewUrl)
    uploadedImages.value.splice(index, 1)
  }
}

function clearAllImages() {
  uploadedImages.value.forEach(img => URL.revokeObjectURL(img.previewUrl))
  uploadedImages.value = []
}

// Phase 1: Scan & Extract Text/Concepts using Gemini
// Live model selected → WebSocket (extractConceptsViaLive)
// REST model selected → HTTPS fetch (extractDataFromImages)
async function startScanning() {
  if (uploadedImages.value.length === 0) return
  isScanning.value = true
  extractedConcepts.value = []
  selectedConcepts.value = []

  try {
    const isLive = selectedModel.value.toLowerCase().includes('live')
    let results: ExtractedItem[] = []

    if (isLive && liveConfigured) {
      // Try Live WebSocket first; if it returns nothing or errors, fall back
      // to the reliable REST vision endpoint so the user always gets data.
      try {
        results = await extractConceptsViaLive(uploadedImages.value)
      } catch (liveErr) {
        console.warn('Live extraction failed, falling back to REST:', liveErr)
      }
      if (!results || results.length === 0) {
        results = await extractDataFromImages(uploadedImages.value)
      }
    } else {
      results = await extractDataFromImages(uploadedImages.value, selectedModel.value)
    }

    if (results && results.length > 0) {
      extractedConcepts.value = results
      // Pre-select all by default
      selectedConcepts.value = results.map(r => r.value)
      showToast(t('toasts.ready'), 'success')
    } else {
      showToast(t('scan.extractedEmpty'), 'warning')
    }
  } catch (err) {
    console.error('Scan failed:', err)
    showToast(t('toasts.hiccup'), 'error')
    // Fallback Mock data for testing/offline mode
    extractedConcepts.value = [
      { value: 'Photosynthesis', category: 'Object/Concept' },
      { value: 'Chlorophyll pigment', category: 'Object/Concept' },
      { value: '6CO2 + 6H2O -> C6H12O6 + 6O2', category: 'Formula' },
      { value: 'Sunlight energy conversion', category: 'Object/Concept' },
      { value: 'Carbon dioxide gas', category: 'Text' },
      { value: 'Water molecules absorption', category: 'Text' },
      { value: 'Glucose output energy storage', category: 'Formula' },
      { value: 'Oxygen release byproduct', category: 'Diagram' }
    ]
    selectedConcepts.value = extractedConcepts.value.map(r => r.value)
  } finally {
    isScanning.value = false
  }
}

// Flat concept list — 'Text' items merged into 'Object/Concept'
const flatConcepts = computed(() =>
  extractedConcepts.value.map(item => ({
    ...item,
    category: item.category === 'Text' ? 'Object/Concept' : item.category
  }))
)

// Two-item mode: special one-or-both selection UX
const isTwoItemMode = computed(() => flatConcepts.value.length === 2)

/** Select only this concept (deselect the other) — used in two-item mode */
function selectOnly(concept: string) {
  selectedConcepts.value = [concept]
}

const isAllSelected = computed(() => {
  return extractedConcepts.value.length > 0 && selectedConcepts.value.length === extractedConcepts.value.length
})

function toggleSelectAll() {
  if (isAllSelected.value) {
    selectedConcepts.value = []
  } else {
    selectedConcepts.value = extractedConcepts.value.map(r => r.value)
  }
}

function toggleConcept(concept: string) {
  const idx = selectedConcepts.value.indexOf(concept)
  if (idx > -1) {
    selectedConcepts.value.splice(idx, 1)
  } else {
    selectedConcepts.value.push(concept)
  }
}

// Phase 2: Personalized strategy from localStorage
function getPersonalizedScanExtension(): string {
  const savedExtra = localStorage.getItem('prime_profile_extra')
  if (!savedExtra) return ''
  try {
    const extra = JSON.parse(savedExtra)
    const edu = extra.education_class || ''
    const subject = extra.favorite_subject || ''
    const custom = extra.custom_subject || ''
    let ageGroup = 'general student', difficulty = 'easy-medium', themeInstruction = ''
    if (edu === 'PRE_SCHOOL') { ageGroup = 'pre-school child (4-6 years old)'; difficulty = 'extremely easy'; themeInstruction = 'Use super simple wording, cute cartoon styling, no complex formulas.' }
    else if (edu === 'ELEMENTARY') { ageGroup = 'elementary school student (7-10 years old)'; difficulty = 'easy'; themeInstruction = 'Use simple concepts, colorful adventure mechanics, avoid college-level math.' }
    else if (edu === 'HIGH_SCHOOL') { ageGroup = 'high school student (14-18 years old)'; difficulty = 'medium'; themeInstruction = 'Use high school curriculum level, structured challenges, basic equations.' }
    else if (edu === 'UNI') { ageGroup = 'university student'; difficulty = 'medium-hard'; themeInstruction = 'Use advanced concepts, academic terminology, deep simulation mechanics.' }
    else if (edu === 'GRADUATED') { ageGroup = 'graduated adult learner'; difficulty = 'medium-hard'; themeInstruction = 'Use professional design aesthetics, deep analytical tools.' }
    const favSubName = subject === 'OTHER' ? custom : subject
    const subjectHook = favSubName ? `\n- Favorite subject is ${favSubName}. Use hooks or analogies referencing this subject where relevant.` : ''
    return `\n\nPERSONALIZED LEARNING STRATEGY (ENABLED):\n- Target Audience: ${ageGroup}\n- Difficulty: ${difficulty}\n- Theme: ${themeInstruction}${subjectHook}\n- Adapt layout, language complexity, and gameplay to match this grade level.`
  } catch { return '' }
}

// Phase 3: Create educational game from selected concepts
const PROMPT_TEMPLATE = (import.meta.env.VITE_AI_SYSTEM_PROMPT as string | undefined) ?? ''
const TAILWIND_REQUIREMENT =
  `\n\nSTYLING REQUIREMENT — USE TAILWIND CSS, NOT HAND-WRITTEN CSS:\n` +
  `• Load Tailwind exactly once in <head> via the Play CDN: ` +
  `<script src="https://cdn.tailwindcss.com"><\/script>\n` +
  `• Style EVERYTHING with Tailwind utility classes directly on the elements — ` +
  `layout (flex/grid), spacing, sizing, colors, typography, rounded corners, borders, ` +
  `shadows, and interactive states. Use a dark, modern look (e.g. bg-slate-900 text-slate-100).\n` +
  `• Rely on utility classes.`

const NO_DIALOGS_REQUIREMENT =
  `\n\nNO BROWSER DIALOGS: Never call alert(), confirm(), or prompt() — show all feedback ` +
  `directly on the page.`

async function createGame() {
  if (selectedConcepts.value.length === 0) {
    showToast(t('scan.noSelection'), 'warning')
    return
  }

  isGenerating.value = true
  generatedHtml.value = ''
  currentStep.value = 0
  
  // Start loading animation timers
  currentFact.value = funFacts.value[Math.floor(Math.random() * funFacts.value.length)] || ''
  factTimer = setInterval(() => {
    currentFact.value = funFacts.value[Math.floor(Math.random() * funFacts.value.length)] || ''
  }, 4000)
  stepTimer = setInterval(() => {
    if (currentStep.value < loadingSteps.value.length - 1) {
      currentStep.value++
    }
  }, 1200)

  // Construct prompt strictly enforcing selected concepts only
  const conceptListText = selectedConcepts.value.join(', ')
  
  let genreDescription = ''
  if (selectedGenre.value === 'arcade') {
    genreDescription = `\nGAME GENRE SPECIFICATION:
Generate a fast-paced arcade-style interactive challenge (such as catching correct concepts falling down, matching concept tiles, or popping correct bubbles). Include elements of score, feedback, lives, or a timer. Keep it highly action-oriented and creative.`
  } else if (selectedGenre.value === 'sandbox') {
    genreDescription = `\nGAME GENRE SPECIFICATION:
Generate an interactive visual sandbox simulation. Include sliders to adjust inputs, switches to toggle options, and real-time canvas or DOM-based animations showing the consequences. Make it an experimental playground where they discover relationships.`
  } else if (selectedGenre.value === 'quest') {
    genreDescription = `\nGAME GENRE SPECIFICATION:
Generate a choices-matter text-adventure or RPG-style quest. The player encounters scenarios where they must apply the selected concepts to progress, gain inventory items, or solve challenges. Include multiple paths, a story description, and success/failure endings.`
  } else if (selectedGenre.value === 'trivia') {
    genreDescription = `\nGAME GENRE SPECIFICATION:
Generate a card-battler or trivia arena. The player plays cards representing the concepts (each card describes a concept) to defeat an opponent or answer challenging questions to level up their stats. Include visual cards, stats, and a simple card play interface.`
  }

  const strictBrief = `You must build an interactive educational game EXCLUSIVELY teaching and demonstrating the following concepts: ${conceptListText}.
${genreDescription}
STRICT EXCLUSIVITY RULE: DO NOT HALLUCINATE OR ADD ANY OTHER TOPICS, THEORIES, OR CONCEPTS. Only use this exact data: [${conceptListText}]. Do not add anything except these concepts. All parts of the game (such as the hook, prediction, exploration, and plain-words explanation) must build EXCLUSIVELY on this exact list. No other information should be added.`

  const lang = aiLanguageName(locale.value as LocaleCode)
  const basePrompt = PROMPT_TEMPLATE.replace('{{MODE}}', 'game').replace('{{STUDENT_THOUGHTS}}', strictBrief)
  const prompt = (
    `${basePrompt}${TAILWIND_REQUIREMENT}${NO_DIALOGS_REQUIREMENT}` +
    `\n\nLANGUAGE REQUIREMENT: Write ALL human-readable text on the page ` +
    `(instructions, headings, labels, buttons, explanations, messages shown by JavaScript) ` +
    `in ${lang}. Keep all code, identifiers, HTML attribute names and math symbols unchanged.` +
    getPersonalizedScanExtension()
  )

  try {
    if (aiConfigured) {
      // Live models are WebSocket-only — REST game generation always uses the
      // default REST model from env (VITE_GEMINI_MODEL).
      const genModel = selectedModel.value.toLowerCase().includes('live')
        ? undefined
        : selectedModel.value
      generatedHtml.value = await generateExperience(prompt, genModel)
    } else {
      // Offline fallback
      await new Promise(resolve => setTimeout(resolve, 4000))
      generatedHtml.value = buildMockGame(selectedConcepts.value)
    }
    showToast(t('toasts.ready'), 'success')
  } catch (err) {
    console.error('Game generation failed:', err)
    showToast(t('toasts.hiccup'), 'error')
    generatedHtml.value = buildMockGame(selectedConcepts.value)
  } finally {
    isGenerating.value = false
    stopTimers()
  }
}

function stopTimers() {
  if (factTimer) clearInterval(factTimer)
  if (stepTimer) clearInterval(stepTimer)
  factTimer = null
  stepTimer = null
}

onUnmounted(stopTimers)

// Sandbox setup
const SANDBOX_SHIM = `<script>(function(){if(window.__dlgShim)return;window.__dlgShim=1;
function toast(msg){try{var h=document.getElementById('__dlg_toasts');if(!h){h=document.createElement('div');h.id='__dlg_toasts';h.style.cssText='position:fixed;left:50%;bottom:18px;transform:translateX(-50%);z-index:2147483647;display:flex;flex-direction:column;gap:8px;align-items:center;pointer-events:none;font-family:system-ui,-apple-system,Segoe UI,Roboto,sans-serif';(document.body||document.documentElement).appendChild(h);}var e=document.createElement('div');e.textContent=String(msg);e.style.cssText='max-width:80vw;padding:10px 16px;border-radius:12px;background:rgba(17,24,39,.92);color:#fff;font-size:14px;line-height:1.4;box-shadow:0 8px 24px rgba(0,0,0,.25);opacity:0;transform:translateY(8px);transition:opacity .25s,transform .25s';h.appendChild(e);requestAnimationFrame(function(){e.style.opacity='1';e.style.transform='none';});setTimeout(function(){e.style.opacity='0';e.style.transform='translateY(8px)';setTimeout(function(){e.remove();},300);},2600);}catch(_){try{console.log('[alert]',msg);}catch(__){}}}
window.alert=function(m){toast(m);};window.confirm=function(m){if(m!=null)toast(m);return true;};window.prompt=function(m,d){if(m!=null)toast(m);return d!=null?d:'';};})();<\/script>`

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
}

function resetScanner() {
  clearAllImages()
  extractedConcepts.value = []
  selectedConcepts.value = []
  generatedHtml.value = ''
}

function copyCode() {
  if (!generatedHtml.value) return
  navigator.clipboard.writeText(generatedHtml.value)
    .then(() => showToast(t('toasts.copied'), 'success'))
    .catch(() => showToast(t('toasts.copyFail'), 'error'))
}

// Mock fallback game if AI is unavailable or fails
function buildMockGame(concepts: string[]): string {
  const conceptItems = concepts.map((c, i) => `{ id: ${i}, term: "${c.replace(/"/g, '\\"')}", matched: false }`).join(', ')
  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>Concept Matcher Game</title>
  <script src="https://cdn.tailwindcss.com"><\/script>
  <style>
    body { background-color: #0f172a; color: #f1f5f9; min-height: 100vh; font-family: sans-serif; }
  </style>
</head>
<body class="flex flex-col p-6">
  <div class="max-w-4xl mx-auto w-full flex-1 flex flex-col gap-6">
    <div class="bg-indigo-950/40 border border-indigo-500/20 p-4 rounded-xl">
      <h2 class="text-indigo-400 font-bold text-sm uppercase tracking-wider mb-1">Interactive Game</h2>
      <h1 class="text-2xl font-black text-white">Concept Discovery Board</h1>
      <p class="text-slate-400 text-sm mt-1">Strict Rules Applied: Build exclusively on scanned data. Match terms with their correct definitions.</p>
    </div>

    <div class="grid grid-cols-1 md:grid-cols-2 gap-6 flex-1 items-start">
      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl">
        <h3 class="font-bold text-lg mb-4 text-emerald-400">💡 Scanned Terms</h3>
        <div class="flex flex-col gap-3" id="terms-list"></div>
      </div>

      <div class="bg-slate-900 border border-slate-800 rounded-xl p-5 shadow-xl flex flex-col gap-4">
        <h3 class="font-bold text-lg text-indigo-400">🎮 Interactive Matcher</h3>
        <p class="text-slate-400 text-sm">Tap a term and select its matching description to clear it from the board.</p>
        <div class="p-4 bg-slate-950 rounded-lg border border-slate-800 flex flex-col items-center justify-center min-h-[180px] text-center" id="play-area">
          <div class="text-3xl mb-3">🔍</div>
          <p class="text-slate-500 text-sm">Select a term from the left to start matching!</p>
        </div>
      </div>
    </div>
  </div>

  <script>
    const concepts = [${conceptItems}];
    let selectedId = null;

    function renderList() {
      const list = document.getElementById('terms-list');
      list.innerHTML = '';
      concepts.forEach(c => {
        const btn = document.createElement('button');
        btn.className = \`w-full p-4 text-left rounded-lg border transition-all duration-200 flex items-center justify-between \${
          c.matched 
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400 cursor-not-allowed opacity-60' 
            : selectedId === c.id 
              ? 'bg-indigo-500/20 border-indigo-500 text-white font-bold scale-[1.02] shadow-lg shadow-indigo-500/10' 
              : 'bg-slate-800/40 border-slate-700/50 hover:bg-slate-800 text-slate-300 hover:border-slate-600'
        }\`;
        btn.disabled = c.matched;
        btn.onclick = () => selectConcept(c.id);
        
        const label = document.createElement('span');
        label.textContent = c.term;
        btn.appendChild(label);

        if (c.matched) {
          const check = document.createElement('span');
          check.textContent = '✓';
          check.className = 'font-bold text-emerald-500';
          btn.appendChild(check);
        }
        list.appendChild(btn);
      });
    }

    function selectConcept(id) {
      selectedId = id;
      renderList();
      const item = concepts.find(c => c.id === id);
      const playArea = document.getElementById('play-area');
      playArea.innerHTML = \`
        <div class="w-full text-left">
          <span class="text-xs font-bold text-indigo-400 uppercase tracking-wider">Active Concept</span>
          <h4 class="text-xl font-black text-white mt-1 mb-4">\${item.term}</h4>
          <p class="text-slate-400 text-sm mb-4">Is this a core part of the scanned material?</p>
          <div class="flex gap-3">
            <button class="flex-1 py-2.5 px-4 bg-emerald-600 hover:bg-emerald-500 text-white font-bold rounded-lg transition-colors" onclick="matchSuccess(\${id})">Yes, match concept</button>
            <button class="py-2.5 px-4 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg transition-colors" onclick="cancelSelection()">Cancel</button>
          </div>
        </div>
      \`;
    }

    function matchSuccess(id) {
      const item = concepts.find(c => c.id === id);
      if (item) {
        item.matched = true;
        selectedId = null;
        renderList();
        
        const playArea = document.getElementById('play-area');
        const allMatched = concepts.every(c => c.matched);
        if (allMatched) {
          playArea.innerHTML = \`
            <div class="text-center">
              <div class="text-4xl mb-3">🎉</div>
              <h4 class="text-xl font-black text-emerald-400">Excellent Work!</h4>
              <p class="text-slate-400 text-sm mt-1">You matched all concepts extracted strictly from your scanned files.</p>
            </div>
          \`;
        } else {
          playArea.innerHTML = \`
            <div class="text-center">
              <div class="text-3xl mb-3">✓</div>
              <h4 class="text-lg font-bold text-emerald-400">Matched: \${item.term}</h4>
              <p class="text-slate-500 text-sm mt-1">Select another concept from the list.</p>
            </div>
          \`;
        }
      }
    }

    function cancelSelection() {
      selectedId = null;
      renderList();
      const playArea = document.getElementById('play-area');
      playArea.innerHTML = \`
        <div class="text-center">
          <div class="text-3xl mb-3">🔍</div>
          <p class="text-slate-500 text-sm">Select a term from the left to start matching!</p>
        </div>
      \`;
    }

    renderList();
  <\/script>
</body>
</html>`
}
</script>

<template>
  <div class="h-full overflow-y-auto relative">
    <!-- Animated background blooms -->
    <div class="pointer-events-none fixed inset-0 overflow-hidden -z-10">
      <div class="blob blob-indigo"></div>
      <div class="blob blob-purple"></div>
    </div>

    <div class="max-w-[1200px] mx-auto px-8 pt-8 pb-14 max-[620px]:px-[18px] max-[620px]:pt-6 max-[620px]:pb-12 flex flex-col gap-6">
      
      <!-- Top Header -->
      <div class="flex justify-between items-center gap-4 flex-wrap border-b border-solid border-slate-200/50 pb-5">
        <div>
          <h1 class="font-display text-[1.9rem] font-extrabold bg-gradient-to-r from-indigo-600 to-violet-600 bg-clip-text text-transparent">
            {{ t('scan.title') }}
          </h1>
          <p class="text-ink-soft mt-1 text-[0.95rem]">{{ t('scan.subtitle') }}</p>
        </div>
        
        <div class="flex items-center gap-3 flex-wrap">
          <!-- AI Engine selector -->
          <div class="flex items-center gap-1.5 bg-slate-100/80 p-1 rounded-2xl border border-slate-200/60 shadow-inner">
            <span class="text-xs font-bold text-slate-500 uppercase px-2">AI Engine</span>
            <button 
              v-for="m in models" 
              :key="m.id" 
              @click="selectedModel = m.id"
              class="py-1.5 px-3.5 rounded-xl text-xs font-bold transition-all duration-200 cursor-pointer"
              :class="[
                selectedModel === m.id 
                  ? 'bg-white text-indigo-700 shadow-sm border border-slate-200/40' 
                  : 'text-slate-500 hover:text-slate-700'
              ]"
            >
              {{ m.name }}
            </button>
          </div>

          <button 
            v-if="generatedHtml || extractedConcepts.length"
            @click="resetScanner"
            class="flex items-center gap-2 bg-slate-100 hover:bg-slate-200 border border-slate-200 text-ink-soft hover:text-ink py-2 px-5 rounded-full font-body text-[0.88rem] font-semibold transition-all duration-200 cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>
            {{ t('scan.reset') }}
          </button>
        </div>
      </div>

      <!-- Main Stages -->
      <div class="w-full">
        <!-- Stage 1: Upload and Analyze Images -->
        <div v-if="!extractedConcepts.length && !generatedHtml" class="flex flex-col gap-6">
          <div 
            @dragover="onDragOver"
            @dragleave="onDragLeave"
            @drop="onDrop"
            class="flex flex-col items-center justify-center border-2 border-dashed rounded-3xl p-10 text-center transition-all duration-300 min-h-[260px] cursor-pointer"
            :class="[
              isDragging 
                ? 'border-indigo-500 bg-indigo-500/[0.04]' 
                : 'border-slate-300 bg-white/60 hover:bg-slate-50/50 hover:border-slate-400'
            ]"
            @click="triggerUpload"
          >
            <input 
              type="file" 
              ref="fileInput" 
              class="hidden" 
              multiple 
              accept="image/*" 
              @change="handleFileChange" 
            />
            
            <div class="w-16 h-16 rounded-2xl bg-indigo-50/10 flex items-center justify-center text-indigo-600 mb-4 shadow-sm">
              <svg xmlns="http://www.w3.org/2000/svg" width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"/><polyline points="17 8 12 3 7 8"/><line x1="12" y1="3" x2="12" y2="15"/></svg>
            </div>
            
            <h3 class="text-lg font-bold text-ink mb-1">{{ t('scan.uploadTitle') }}</h3>
            <p class="text-sm text-ink-soft max-w-md mx-auto mb-4">
              Drag and drop your photos, worksheets, or textbook pages here, or click to browse files.
            </p>
            
            <button class="bg-gradient-to-r from-indigo-500 to-violet-500 text-white font-bold py-2.5 px-6 rounded-full text-sm shadow-md shadow-indigo-500/20 hover:scale-[1.02] active:scale-100 transition-all duration-200 pointer-events-none">
              {{ t('scan.uploadBtn') }}
            </button>
          </div>

          <!-- Previews of uploaded images -->
          <div v-if="uploadedImages.length > 0" class="flex flex-col gap-4">
            <div class="flex justify-between items-center">
              <h4 class="font-bold text-ink text-sm uppercase tracking-wider">
                Selected Images ({{ uploadedImages.length }})
              </h4>
              <button @click="clearAllImages" class="text-red-500 hover:text-red-600 text-sm font-semibold transition-colors duration-200 cursor-pointer">
                {{ t('scan.clearBtn') }}
              </button>
            </div>
            
            <div class="grid grid-cols-4 gap-4 max-[860px]:grid-cols-2 max-[480px]:grid-cols-1">
              <div 
                v-for="(img, idx) in uploadedImages" 
                :key="idx" 
                class="relative rounded-2xl overflow-hidden border border-slate-200 bg-white group aspect-[4/3] shadow-sm"
              >
                <!-- Pulsing Scan Laser Line Overlay when scanning -->
                <div v-if="isScanning" class="absolute inset-0 z-10 pointer-events-none overflow-hidden">
                  <div class="w-full h-1 bg-gradient-to-r from-indigo-400 via-cyan-400 to-indigo-400 opacity-80 absolute animate-laser"></div>
                  <div class="absolute inset-0 bg-indigo-500/10 animate-pulse"></div>
                </div>

                <img :src="img.previewUrl" :alt="img.name" class="w-full h-full object-cover" />
                <button 
                  @click.stop="removeImage(idx)" 
                  class="absolute top-2 right-2 bg-slate-900/70 hover:bg-slate-900 text-white rounded-full w-8 h-8 flex items-center justify-center transition-all duration-200 shadow-md border border-white/10 cursor-pointer"
                >
                  <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/></svg>
                </button>
              </div>
            </div>

            <!-- Analyze Action Button -->
            <button 
              @click="startScanning"
              :disabled="isScanning"
              class="w-full py-4 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-bold rounded-2xl shadow-lg shadow-indigo-500/20 hover:scale-[1.01] active:scale-100 hover:shadow-xl transition-all duration-200 flex items-center justify-center gap-3 disabled:opacity-50 cursor-pointer"
            >
              <span v-if="isScanning" class="w-5 h-5 border-2 border-white/20 border-t-white rounded-full animate-spin"></span>
              <svg v-else xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><path d="m15 9-6 6"/><path d="m9 9 6 6"/></svg>
              <span>{{ isScanning ? t('scan.loadingScan') : t('scan.scanBtn') }}</span>
            </button>
          </div>
        </div>

        <!-- Stage 2: Options/Checkbox selection of extracted terms -->
        <div v-else-if="extractedConcepts.length && !generatedHtml && !isGenerating" class="bg-white/80 backdrop-blur-[12px] border border-slate-200/60 rounded-3xl p-6 shadow-xl flex flex-col gap-6">
          <div class="flex justify-between items-start gap-4 flex-wrap border-b border-slate-100 pb-4">
            <div>
              <h3 class="text-xl font-bold text-ink">{{ t('scan.selectTitle') }}</h3>
              <p class="text-sm text-amber-600 font-medium mt-1 flex items-center gap-1.5">
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
                {{ t('scan.strictRule') }}
              </p>
            </div>
            
            <button 
              v-if="!isTwoItemMode"
              @click="toggleSelectAll"
              class="text-indigo-600 hover:text-indigo-700 font-bold text-sm transition-colors duration-200 bg-indigo-50 hover:bg-indigo-100 py-1.5 px-4 rounded-full cursor-pointer"
            >
              {{ isAllSelected ? 'Deselect All' : 'Select All' }}
            </button>
          </div>

          <!-- Two-item mode: choose one or both -->
          <div v-if="isTwoItemMode" class="flex flex-col gap-4">
            <p class="text-[0.88rem] text-ink-soft">Two items detected — choose one to focus on, or use both:</p>
            <div class="grid grid-cols-2 gap-4 max-[480px]:grid-cols-1">
              <button
                v-for="item in flatConcepts"
                :key="item.value"
                @click="selectOnly(item.value)"
                class="p-4 rounded-2xl border-2 border-solid text-left transition-all duration-200 cursor-pointer flex flex-col gap-1.5 hover:-translate-y-0.5"
                :class="[
                  selectedConcepts.length === 1 && selectedConcepts.includes(item.value)
                    ? 'bg-gradient-to-br from-indigo-500 to-violet-500 border-transparent text-white shadow-lg shadow-indigo-500/20'
                    : 'bg-white border-slate-200 text-ink hover:bg-slate-50 hover:border-indigo-300'
                ]"
              >
                <span class="text-[0.7rem] font-bold uppercase tracking-widest" :class="selectedConcepts.length === 1 && selectedConcepts.includes(item.value) ? 'text-indigo-200' : 'text-indigo-500'">{{ item.category }}</span>
                <span class="font-bold text-[0.95rem] leading-snug">{{ item.value }}</span>
              </button>
            </div>
            <button
              @click="toggleSelectAll"
              class="self-center font-bold text-sm py-2 px-5 rounded-full transition-all duration-200 cursor-pointer border"
              :class="isAllSelected ? 'bg-indigo-600 text-white border-indigo-600' : 'bg-indigo-50 text-indigo-600 border-indigo-200 hover:bg-indigo-100'"
            >
              {{ isAllSelected ? '✓ Using both concepts' : 'Use both concepts' }}
            </button>
          </div>

          <!-- Normal mode: flat chip list -->
          <div v-else class="flex flex-wrap gap-2.5 my-1">
            <button 
              v-for="item in flatConcepts" 
              :key="item.value"
              @click="toggleConcept(item.value)"
              class="py-2.5 px-4 rounded-xl border border-solid font-body text-[0.88rem] font-semibold transition-all duration-200 flex items-center gap-2 cursor-pointer hover:-translate-y-px"
              :class="[
                selectedConcepts.includes(item.value)
                  ? 'bg-gradient-to-r from-indigo-500 to-violet-500 border-transparent text-white shadow-md shadow-indigo-500/10'
                  : 'bg-white border-slate-200 text-ink-soft hover:bg-slate-50 hover:text-ink'
              ]"
            >
              <span class="w-3.5 h-3.5 rounded-full flex items-center justify-center border flex-shrink-0" :class="[selectedConcepts.includes(item.value) ? 'bg-white text-indigo-600 border-white' : 'border-slate-300']">
                <svg v-if="selectedConcepts.includes(item.value)" xmlns="http://www.w3.org/2000/svg" width="8" height="8" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round"><polyline points="20 6 9 17 4 12"/></svg>
              </span>
              <span>{{ item.value }}</span>
              <span v-if="item.category !== 'Object/Concept'" class="text-[0.65rem] opacity-60 font-normal">{{ item.category }}</span>
            </button>
          </div>

          <!-- Game Style / Genre Selector -->
          <div class="border-t border-slate-100 pt-5 flex flex-col gap-3">
            <div>
              <h4 class="font-bold text-ink text-[0.95rem] flex items-center gap-1.5">
                <span>🎨</span> Creative Game Genre
              </h4>
              <p class="text-xs text-ink-soft mt-0.5">Select the format of the educational game you want the AI to generate.</p>
            </div>
            
            <div class="grid grid-cols-2 gap-3 max-[580px]:grid-cols-1">
              <button 
                v-for="genre in genres" 
                :key="genre.id"
                @click="selectedGenre = genre.id"
                class="p-3.5 rounded-2xl border border-solid text-left transition-all duration-200 cursor-pointer flex gap-3 hover:-translate-y-px"
                :class="[
                  selectedGenre === genre.id
                    ? 'bg-indigo-50/60 border-indigo-400 shadow-sm'
                    : 'bg-white border-slate-200 hover:bg-slate-50'
                ]"
              >
                <span class="text-2xl mt-0.5 leading-none">{{ genre.icon }}</span>
                <div class="flex flex-col">
                  <span class="font-bold text-xs text-indigo-950">{{ genre.name }}</span>
                  <span class="text-[0.68rem] text-slate-500 mt-0.5 leading-snug">{{ genre.desc }}</span>
                </div>
              </button>
            </div>
          </div>

          <!-- Create Game Action Button -->
          <button 
            @click="createGame"
            class="w-full py-4 bg-gradient-to-r from-indigo-600 to-violet-600 text-white font-bold rounded-2xl shadow-lg shadow-indigo-500/20 hover:scale-[1.01] active:scale-100 transition-all duration-200 flex items-center justify-center gap-2 cursor-pointer"
          >
            <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
            <span>{{ t('scan.gameBtn') }}</span>
          </button>
        </div>

        <!-- Stage 3: Game Generation Loading screen -->
        <div v-else-if="isGenerating" class="bg-white/80 backdrop-blur-[12px] border border-slate-200/60 rounded-3xl p-10 shadow-xl flex flex-col items-center justify-center text-center min-h-[360px] gap-4">
          <div class="relative w-16 h-16 mb-2">
            <span class="absolute inset-0 border-4 border-solid border-slate-100 rounded-full"></span>
            <span class="absolute inset-0 border-4 border-solid border-t-indigo-500 border-transparent rounded-full animate-spin"></span>
          </div>
          
          <h3 class="text-xl font-bold text-ink flex items-center gap-2 justify-center">
            {{ loadingSteps[currentStep] }}
          </h3>
          
          <div class="max-w-md bg-slate-50 border border-slate-100 rounded-2xl p-5 shadow-inner mt-2">
            <p class="text-sm text-indigo-700 font-bold uppercase tracking-wider mb-2">Did You Know?</p>
            <p class="text-[0.9rem] text-ink-soft leading-[1.5] italic">
              "{{ currentFact }}"
            </p>
          </div>
        </div>

        <!-- Stage 4: Play Generated Game (Interactive Iframe) -->
        <div v-else-if="generatedHtml" class="flex flex-col gap-4">
          <!-- Game utilities toolbar -->
          <div class="flex justify-between items-center gap-3 bg-white/70 backdrop-blur-[8px] border border-slate-200/50 p-3 rounded-2xl shadow-sm">
            <div class="flex items-center gap-2">
              <span class="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse"></span>
              <span class="text-xs font-bold text-ink-soft uppercase tracking-wider">Play Mode</span>
            </div>
            
            <div class="flex gap-2">
              <button 
                @click="copyCode" 
                class="flex items-center gap-1.5 bg-slate-50 hover:bg-slate-100 border border-slate-200 text-ink-soft hover:text-ink py-1.5 px-3 rounded-xl font-body text-[0.8rem] font-semibold transition-all duration-200 cursor-pointer"
                title="Copy Game HTML Code"
              >
                <svg xmlns="http://www.w3.org/2000/svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><rect x="9" y="9" width="13" height="13" rx="2" ry="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                Copy Code
              </button>
            </div>
          </div>

          <!-- Iframe -->
          <div class="rounded-3xl overflow-hidden border border-solid border-slate-200 bg-white shadow-lg flex-1 min-h-[580px] flex">
            <iframe
              data-experience
              class="w-full h-full min-h-[580px] border-none block bg-slate-950"
              :srcdoc="withSandboxShim(generatedHtml)"
              sandbox="allow-scripts allow-pointer-lock"
              @load="handleFrameLoad"
            ></iframe>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Animated laser scanning line style */
.animate-laser {
  animation: scanning 2s ease-in-out infinite;
}

@keyframes scanning {
  0% {
    top: 0%;
  }
  50% {
    top: 100%;
  }
  100% {
    top: 0%;
  }
}

/* Floating backdrop bloom circles */
.blob {
  position: absolute;
  border-radius: 9999px;
  filter: blur(80px);
  opacity: 0.22;
  will-change: transform;
  width: 400px;
  height: 400px;
}
.blob-indigo {
  top: -100px;
  left: -100px;
  background: radial-gradient(circle, rgba(99, 102, 241, 0.4), transparent 70%);
  animation: float-a 20s ease-in-out infinite;
}
.blob-purple {
  bottom: -150px;
  right: -100px;
  background: radial-gradient(circle, rgba(168, 85, 247, 0.45), transparent 70%);
  animation: float-b 24s ease-in-out infinite;
}

@keyframes float-a {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(40px, 30px) scale(1.1); }
}
@keyframes float-b {
  0%, 100% { transform: translate(0, 0) scale(1); }
  50% { transform: translate(-30px, 40px) scale(1.05); }
}
</style>
