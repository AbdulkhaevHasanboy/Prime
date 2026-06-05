/* ================================================================
   AI Client — talks to Google Gemini (generateContent REST API).

   The studio sends the composed prompt (built in MentorView.vue from
   VITE_AI_SYSTEM_PROMPT) and gets back ONE self-contained index.html
   that we render live in the preview iframe.

   Robustness (why a single fetch isn't enough):
   A full interactive page can be long. If the model hits its output
   token cap it stops mid-stream — the HTML never reaches </html>, the
   <script> is cut in half, and the "game" is broken. So we:
     1. ask for a large output budget,
     2. detect truncation (finishReason === 'MAX_TOKENS') and CONTINUE
        the generation until the document is closed,
     3. sanitize + repair the result so it's always valid, closed HTML.

   Config (see .env):
     VITE_GEMINI_API_KEY     your Generative Language API key
     VITE_GEMINI_MODEL       model id (default: gemini-3.5-flash)
     VITE_GEMINI_MAX_TOKENS  output cap per call (default: 32768)

   ⚠️ Security note: a VITE_ key is bundled into the browser and is
   visible to anyone using the app. Fine for a demo / hackathon. For
   production, move this call behind a tiny backend proxy so the key
   never ships to the client.
================================================================= */

const API_KEY = import.meta.env.VITE_GEMINI_API_KEY as string | undefined
const MODEL = (import.meta.env.VITE_GEMINI_MODEL as string | undefined)?.trim() || 'gemini-3.5-flash'
const MAX_TOKENS = Number(import.meta.env.VITE_GEMINI_MAX_TOKENS) || 32768
const MAX_CONTINUATIONS = 4
const BASE = 'https://generativelanguage.googleapis.com/v1beta/models'

/** True when a key is present, so the UI can decide whether to call the API. */
export const aiConfigured = Boolean(API_KEY)

/** Which model we're calling — handy for logs / the UI badge. */
export const aiModel = MODEL

interface Part {
  text?: string
  inlineData?: {
    mimeType: string
    data: string
  }
}
interface Content {
  role: 'user' | 'model'
  parts: Part[]
}
interface GeminiResponse {
  candidates?: { content?: { parts?: Part[] }; finishReason?: string }[]
  promptFeedback?: { blockReason?: string }
  error?: { message?: string }
}

/** Strip ```html ... ``` fences the model sometimes adds despite instructions. */
function stripFences(raw: string): string {
  return raw
    .trim()
    .replace(/^```[a-zA-Z]*\s*\n?/, '')
    .replace(/\n?```\s*$/, '')
    .trim()
}

/** Pull the document out of the response and guarantee it's closed. */
function sanitizeHtml(raw: string): string {
  let t = stripFences(raw).trim()

  // Drop any chatter before the document starts.
  const start = t.search(/<!doctype html|<html[\s>]/i)
  if (start > 0) t = t.slice(start)

  // Cut anything the model rambled after the document ends.
  const close = t.toLowerCase().lastIndexOf('</html>')
  if (close !== -1) {
    t = t.slice(0, close + '</html>'.length)
  } else {
    // Truncated despite continuation — best-effort repair so it still renders.
    if (/<body[\s>]/i.test(t) && !/<\/body>/i.test(t)) t += '\n</body>'
    t += '\n</html>'
  }
  return t.trim()
}

export interface ExtractedItem {
  value: string
  category: string
}

/** One round-trip to the model. Returns the text and why it stopped. */
async function callGemini(contents: Content[], modelName?: string): Promise<{ text: string; finish: string }> {
  const activeModel = modelName || MODEL
  const res = await fetch(`${BASE}/${activeModel}:generateContent?key=${API_KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents,
      generationConfig: {
        // High temperature → a fresh, different experience every time.
        temperature: 1.0,
        topP: 0.95,
        maxOutputTokens: MAX_TOKENS,
        // Flash models "think" before answering by default, which adds
        // several seconds of latency. We just need clean HTML, so turn the
        // thinking step off for a much faster first byte. (Ignored by models
        // that don't support thinking, so it's safe to always send.)
        thinkingConfig: { thinkingBudget: 0 },
      },
    }),
  })

  const data = (await res.json().catch(() => ({}))) as GeminiResponse

  if (!res.ok) {
    throw new Error(`Gemini API ${res.status}: ${data.error?.message ?? res.statusText}`)
  }
  const blocked = data.promptFeedback?.blockReason
  if (blocked) {
    throw new Error(`Gemini blocked the prompt (${blocked}).`)
  }

  const candidate = data.candidates?.[0]
  const text = (candidate?.content?.parts ?? []).map((p) => p.text ?? '').join('')
  return { text, finish: candidate?.finishReason ?? 'STOP' }
}

/**
 * Run a conversation to completion, continuing the generation whenever the
 * model hits its output cap mid-document, so we always get a closed </html>.
 * `contents` is mutated as the back-and-forth grows.
 */
async function runToCompletion(contents: Content[], modelName?: string): Promise<string> {
  let full = ''

  for (let attempt = 0; attempt <= MAX_CONTINUATIONS; attempt++) {
    const { text, finish } = await callGemini(contents, modelName)
    full += text

    const looksDone = /<\/html>/i.test(full)
    if (finish !== 'MAX_TOKENS' || looksDone) break

    // Truncated — ask the model to pick up exactly where it stopped.
    contents.push({ role: 'model', parts: [{ text }] })
    contents.push({
      role: 'user',
      parts: [
        {
          text: 'Continue the HTML exactly where you stopped. Do NOT repeat any earlier content, do NOT add explanations or code fences — output only the remaining raw HTML, and finish the document with </html>.',
        },
      ],
    })
  }

  return full
}

/**
 * Send the composed prompt to Gemini and return a COMPLETE index.html.
 * Continues the generation if the model runs out of room, then repairs
 * the final document. Throws on missing key / API error / empty result —
 * the caller is expected to catch and fall back to the local mock.
 */
export async function generateExperience(prompt: string, modelName?: string): Promise<string> {
  if (!API_KEY) {
    throw new Error('Missing VITE_GEMINI_API_KEY — add it to .env to enable live AI generation.')
  }

  const contents: Content[] = [{ role: 'user', parts: [{ text: prompt }] }]
  const html = sanitizeHtml(await runToCompletion(contents, modelName))
  if (!html || !/<html[\s>]/i.test(html)) {
    throw new Error('Gemini returned no usable HTML.')
  }
  return html
}

/**
 * Sends multiple base64-encoded images to Gemini and extracts all text, formulas,
 * concepts, and objects as a clean list of categorized options (JSON array) without hallucinating.
 */
export async function extractDataFromImages(
  images: { mimeType: string; base64: string }[],
  modelName?: string
): Promise<ExtractedItem[]> {
  if (!API_KEY) {
    throw new Error('Missing VITE_GEMINI_API_KEY — add it to .env to enable image analysis.')
  }

  const activeModel = modelName || MODEL

  const promptText = `Analyze these images.
1. Extract ALL text, written words, titles, notes, math formulas, equations, definitions, labels, diagrams, or objects present in the images.
2. Be extremely precise and strict. Do NOT hallucinate. Do NOT add any extra information, comments, or assumptions. Only extract what is clearly visible or written in the images.
3. Group and structure the extracted items into brief, clean, distinct topics or data points.
4. Categorize each item into exactly one of these types: "Text" (for written words, sentences, notes, definitions), "Formula" (for mathematical formulas, chemical equations), "Diagram" (for labels on graphs/diagrams/illustrations), or "Object/Concept" (for visual objects, shapes, main concepts).
5. Output the result ONLY as a JSON array of objects, where each object has "value" (string) and "category" (string, either "Text", "Formula", "Diagram", or "Object/Concept").
Example format:
[
  {"value": "Photosynthesis", "category": "Object/Concept"},
  {"value": "6CO2 + 6H2O -> C6H12O6 + 6O2", "category": "Formula"},
  {"value": "Chloroplast structure diagram", "category": "Diagram"}
]
Do NOT wrap it in markdown code blocks. Do NOT include any other text before or after the JSON.`

  const parts: Part[] = [
    { text: promptText },
    ...images.map(img => ({
      inlineData: {
        mimeType: img.mimeType,
        data: img.base64
      }
    }))
  ]

  const contents: Content[] = [{ role: 'user', parts }]

  const res = await fetch(`${BASE}/${activeModel}:generateContent?key=${API_KEY}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      contents,
      generationConfig: {
        temperature: 0.1,
        topP: 0.95,
        maxOutputTokens: 2048,
        responseMimeType: "application/json"
      }
    })
  })

  const data = (await res.json().catch(() => ({}))) as GeminiResponse

  if (!res.ok) {
    throw new Error(`Gemini API ${res.status}: ${data.error?.message ?? res.statusText}`)
  }

  const candidate = data.candidates?.[0]
  const text = (candidate?.content?.parts ?? []).map((p) => p.text ?? '').join('')
  
  try {
    const cleanText = text.trim().replace(/^```json\s*/, '').replace(/```\s*$/, '').trim()
    const parsed = JSON.parse(cleanText)
    if (Array.isArray(parsed)) {
      return parsed.map(item => {
        if (typeof item === 'object' && item !== null && 'value' in item) {
          return {
            value: String(item.value).trim(),
            category: String(item.category || 'Text').trim()
          }
        }
        return {
          value: String(item).trim(),
          category: 'Text'
        }
      }).filter(item => item.value)
    }
  } catch (err) {
    console.error('Failed to parse Gemini JSON output:', text, err)
  }

  // Fallback parsing: split by lines or bullets if JSON parsing failed
  return text
    .split('\n')
    .map(line => line.replace(/^[-*•\d.\s]+/, '').trim())
    .filter(line => line.length > 0 && line.length < 100)
    .map(val => ({ value: val, category: 'Text' }))
}
