/* ================================================================
   Live Client — Gemini Live websocket, TEXT received via transcription.

   The model itself is an AUDIO Live model (gemini-3.1-flash-live-preview —
   the only Live family this API key can reach). We don't want audio, so we
   enable output transcription and read the model's words as TEXT from
   `serverContent.outputTranscription.text` (and any `modelTurn.parts[].text`),
   while discarding the audio chunks entirely. This is the exact "text-only
   receive" pattern used in the Instagram project's live-responder.js.

   Trade-off (measured): because the model still synthesizes speech it never
   sends us, a Live turn is slower than a plain REST text call (~7s for a
   sentence). So we structure callers to hide that latency:
     • enhanceTopic()  — ONE short sentence; blocks generation (must be quick).
     • funFactsFor()   — several facts; NON-blocking, shown on the loading
                         screen while the (much longer) experience generates.
   Both reuse one persistent websocket; turns are serialized.

   Everything degrades gracefully: missing key, dead socket, or a slow turn →
   safe fallback (original topic / empty list) and the normal flow continues.

   Config (see .env):
     VITE_GEMINI_API_KEY        same key the REST client uses (client-side)
     VITE_GEMINI_LIVE_MODEL     live model id (default below)

   ⚠️ Like aiClient.ts, the VITE_ key ships to the browser — demo-grade.
================================================================= */

import { GoogleGenAI } from '@google/genai'

const API_KEY = import.meta.env.VITE_GEMINI_API_KEY as string | undefined
const LIVE_MODEL =
  (import.meta.env.VITE_GEMINI_LIVE_MODEL as string | undefined)?.trim() ||
  'gemini-3.1-flash-live-preview'

export interface ExtractedItem {
  value: string
  category: string
}

/** Flip on to trace the websocket lifecycle in the browser console. */
const DEBUG = true
const log = (...a: unknown[]) => DEBUG && console.debug('[live]', ...a)

/** True when a key is present, so callers can skip the helpers entirely. */
export const liveConfigured = Boolean(API_KEY)

/** Session/message shapes drift across @google/genai versions; keep them loose. */
type LiveSession = { sendClientContent: (req: unknown) => void; close?: () => void }
type LiveMessage = {
  setupComplete?: unknown
  serverContent?: {
    modelTurn?: { parts?: { text?: string }[] }
    outputTranscription?: { text?: string }
    turnComplete?: boolean
  }
}

class LiveTextClient {
  private client: GoogleGenAI | null
  private session: LiveSession | null = null
  private connecting: Promise<LiveSession> | null = null

  /** Set once the server sends `setupComplete` — only then is it safe to send. */
  private ready = false
  private readyResolve: (() => void) | null = null
  private readyPromise: Promise<void> | null = null

  /** Turns share one session, so they run one at a time — chain on this. */
  private queue: Promise<unknown> = Promise.resolve()

  /** State for the single in-flight turn. */
  private buffer = ''
  private resolveTurn: ((text: string) => void) | null = null
  private rejectTurn: ((err: unknown) => void) | null = null

  constructor() {
    // Default apiVersion (v1beta) — that's where this key's Live audio model lives.
    this.client = API_KEY ? new GoogleGenAI({ apiKey: API_KEY }) : null
  }

  /** Lazily open (and re-open) the websocket, then wait for setupComplete. */
  private async ensureSession(): Promise<LiveSession> {
    if (this.session && this.ready) return this.session
    if (this.connecting) return this.connecting
    if (!this.client) throw new Error('Live AI not configured (missing VITE_GEMINI_API_KEY).')

    this.ready = false
    this.readyPromise = new Promise<void>((res) => (this.readyResolve = res))

    const config = {
      // Audio model → we still must request AUDIO, but we read the transcript.
      responseModalities: ['AUDIO'],
      outputAudioTranscription: {},
      systemInstruction: {
        parts: [
          {
            text:
              'You are a fast text helper for an educational app. Treat every ' +
              'message as a fresh, independent request. Answer with ONLY the ' +
              'requested text — no preamble, no markdown, no surrounding quotes.',
          },
        ],
      },
    }

    this.connecting = this.client.live
      .connect({
        model: LIVE_MODEL,
        // Cast: config type drifts between SDK versions; the runtime accepts these.
        config: config as never,
        callbacks: {
          onopen: () => log('socket open'),
          onmessage: (msg: unknown) => this.handleMessage(msg as LiveMessage),
          onerror: (e: unknown) => {
            log('socket error', e)
            this.dropSession(e)
          },
          onclose: (e: unknown) => {
            log('socket closed', (e as { reason?: string })?.reason || '')
            this.dropSession(new Error('Live session closed'))
          },
        },
      })
      .then((s) => {
        this.session = s as unknown as LiveSession
        this.connecting = null
        return this.session
      })
      .catch((e: unknown) => {
        this.connecting = null
        log('connect failed', e)
        throw e
      })

    const session = await this.connecting
    // Wait for setupComplete, but don't hang forever if it never surfaces.
    await Promise.race([this.readyPromise, new Promise<void>((res) => setTimeout(res, 3000))])
    if (!this.ready) log('proceeding without observed setupComplete')
    return session
  }

  /**
   * Collect the model's words as TEXT (from transcription + any text parts),
   * ignore audio, and resolve the turn when the model says it's done.
   */
  private handleMessage(msg: LiveMessage): void {
    if (msg?.setupComplete) {
      log('setupComplete')
      this.ready = true
      this.readyResolve?.()
      this.readyResolve = null
      return
    }
    const content = msg?.serverContent
    const parts = content?.modelTurn?.parts
    if (Array.isArray(parts)) {
      for (const p of parts) if (typeof p?.text === 'string') this.buffer += p.text
    }
    if (typeof content?.outputTranscription?.text === 'string') {
      this.buffer += content.outputTranscription.text
    }
    if (content?.turnComplete) {
      const text = this.buffer.trim()
      this.buffer = ''
      log('turn complete', JSON.stringify(text.slice(0, 80)))
      const resolve = this.resolveTurn
      this.resolveTurn = null
      this.rejectTurn = null
      resolve?.(text)
    }
  }

  /** Tear down a broken session so the next turn reconnects cleanly. */
  private dropSession(err: unknown): void {
    this.session = null
    this.ready = false
    this.readyResolve = null
    this.readyPromise = null
    const reject = this.rejectTurn
    this.buffer = ''
    this.resolveTurn = null
    this.rejectTurn = null
    reject?.(err)
  }

  private async runTurn(prompt: string, timeoutMs: number): Promise<string> {
    const session = await this.ensureSession()
    return new Promise<string>((resolve, reject) => {
      let settled = false
      const finish = (fn: () => void) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        this.resolveTurn = null
        this.rejectTurn = null
        fn()
      }
      const timer = setTimeout(
        () =>
          finish(() => {
            this.buffer = ''
            reject(new Error('Live request timed out'))
          }),
        timeoutMs,
      )

      this.resolveTurn = (text) => finish(() => resolve(text))
      this.rejectTurn = (e) => finish(() => reject(e))
      this.buffer = ''

      try {
        log('send turn', JSON.stringify(prompt.slice(0, 60)))
        session.sendClientContent({
          turns: [{ role: 'user', parts: [{ text: prompt }] }],
          turnComplete: true,
        })
      } catch (e) {
        finish(() => reject(e))
      }
    })
  }

  /** Send one prompt; resolve with the model's text. Serialized over one session. */
  ask(prompt: string, timeoutMs = 16000): Promise<string> {
    const run = () => this.runTurn(prompt, timeoutMs)
    const result = this.queue.then(run, run)
    // Keep the queue alive regardless of this turn's outcome.
    this.queue = result.then(
      () => undefined,
      () => undefined,
    )
    return result
  }
}

const live = new LiveTextClient()

/** Drop stray markdown emphasis the spoken transcript occasionally includes. */
function clean(line: string): string {
  return line
    .replace(/[*_`]+/g, '')
    .replace(/^\s*(?:[-•]|\d+[.)])\s*/, '')
    .trim()
}

/**
 * Rewrite a student's raw request into one clear, specific, vivid sentence the
 * experience generator can build something richer from. SHORT → blocks
 * generation, so a tight-ish budget. Falls back to the original topic.
 */
export async function enhanceTopic(topic: string, language: string): Promise<string> {
  const t = topic.trim()
  if (!t || !liveConfigured) return t
  try {
    const out = await live.ask(
      `Rewrite this student's learning request into a single clear, specific, ` +
        `vivid sentence that an AI can turn into a great interactive lesson. ` +
        `Keep the original subject and intent — do not answer it, just sharpen it. ` +
        `Write it in ${language}. Reply with ONLY the rewritten sentence.\n\nRequest: ${t}`,
      14000,
    )
    return clean(out) || t
  } catch (e) {
    log('enhanceTopic failed', e)
    return t
  }
}

/* ================================================================
   LiveVisionClient — separate Live session configured for TEXT output.
   Used exclusively by extractConceptsViaLive() to analyze images.
   Reuses the same WebSocket infrastructure as LiveTextClient but with
   responseModalities: ['TEXT'] so inline image parts work correctly.
================================================================= */

type ImagePart = { text: string } | { inlineData: { mimeType: string; data: string } }

class LiveVisionClient {
  private client: GoogleGenAI | null
  private session: LiveSession | null = null
  private connecting: Promise<LiveSession> | null = null
  private ready = false
  private readyResolve: (() => void) | null = null
  private readyPromise: Promise<void> | null = null
  private queue: Promise<unknown> = Promise.resolve()
  private buffer = ''
  private resolveTurn: ((text: string) => void) | null = null
  private rejectTurn: ((err: unknown) => void) | null = null

  constructor() {
    this.client = API_KEY ? new GoogleGenAI({ apiKey: API_KEY }) : null
  }

  private async ensureSession(): Promise<LiveSession> {
    if (this.session && this.ready) return this.session
    if (this.connecting) return this.connecting
    if (!this.client) throw new Error('Live AI not configured (missing VITE_GEMINI_API_KEY).')

    this.ready = false
    this.readyPromise = new Promise<void>((res) => (this.readyResolve = res))

    const config = {
      // Same proven config as LiveTextClient: the model is an AUDIO Live model,
      // so we request AUDIO and read its words back as TEXT via transcription.
      responseModalities: ['AUDIO'],
      outputAudioTranscription: {},
      systemInstruction: {
        parts: [{
          text:
            'You are a precise image content extractor. ' +
            'Analyze ALL images provided and return ONLY a valid JSON array of extracted items. ' +
            'Never hallucinate. Never invent content not clearly visible. ' +
            'Each item: {"value": "...", "category": "Text|Formula|Diagram|Object/Concept"}.',
        }],
      },
    }

    this.connecting = this.client.live
      .connect({
        model: LIVE_MODEL,
        config: config as never,
        callbacks: {
          onopen: () => log('[vision] socket open'),
          onmessage: (msg: unknown) => this.handleMessage(msg as LiveMessage),
          onerror: (e: unknown) => { log('[vision] error', e); this.dropSession(e) },
          onclose: (e: unknown) => {
            log('[vision] closed', (e as { reason?: string })?.reason || '')
            this.dropSession(new Error('Vision session closed'))
          },
        },
      })
      .then((s) => {
        this.session = s as unknown as LiveSession
        this.connecting = null
        return this.session
      })
      .catch((e: unknown) => {
        this.connecting = null
        log('[vision] connect failed', e)
        throw e
      })

    const session = await this.connecting
    await Promise.race([this.readyPromise, new Promise<void>((res) => setTimeout(res, 5000))])
    if (!this.ready) log('[vision] proceeding without setupComplete')
    return session
  }

  private handleMessage(msg: LiveMessage): void {
    if (msg?.setupComplete) {
      log('[vision] setupComplete')
      this.ready = true
      this.readyResolve?.()
      this.readyResolve = null
      return
    }
    const content = msg?.serverContent
    const parts = content?.modelTurn?.parts
    if (Array.isArray(parts)) {
      for (const p of parts) if (typeof p?.text === 'string') this.buffer += p.text
    }
    if (typeof content?.outputTranscription?.text === 'string') {
      this.buffer += content.outputTranscription.text
    }
    if (content?.turnComplete) {
      const text = this.buffer.trim()
      this.buffer = ''
      log('[vision] turn complete, len=', text.length)
      const resolve = this.resolveTurn
      this.resolveTurn = null
      this.rejectTurn = null
      resolve?.(text)
    }
  }

  private dropSession(err: unknown): void {
    this.session = null
    this.ready = false
    this.readyResolve = null
    this.readyPromise = null
    const reject = this.rejectTurn
    this.buffer = ''
    this.resolveTurn = null
    this.rejectTurn = null
    reject?.(err)
  }

  private async runTurn(parts: ImagePart[], timeoutMs: number): Promise<string> {
    const session = await this.ensureSession()
    return new Promise<string>((resolve, reject) => {
      let settled = false
      const finish = (fn: () => void) => {
        if (settled) return
        settled = true
        clearTimeout(timer)
        this.resolveTurn = null
        this.rejectTurn = null
        fn()
      }
      const timer = setTimeout(
        () => finish(() => { this.buffer = ''; reject(new Error('Live vision request timed out')) }),
        timeoutMs,
      )

      this.resolveTurn = (text) => finish(() => resolve(text))
      this.rejectTurn = (e) => finish(() => reject(e))
      this.buffer = ''

      try {
        log('[vision] sending', parts.length, 'parts')
        session.sendClientContent({
          turns: [{ role: 'user', parts }],
          turnComplete: true,
        })
      } catch (e) {
        finish(() => reject(e))
      }
    })
  }

  askWithImages(parts: ImagePart[], timeoutMs = 45000): Promise<string> {
    const run = () => this.runTurn(parts, timeoutMs)
    const result = this.queue.then(run, run)
    this.queue = result.then(() => undefined, () => undefined)
    return result
  }
}

const liveVision = new LiveVisionClient()

/**
 * Send multiple images to Gemini Live (WebSocket) and extract all visible
 * text, formulas, diagrams, and concepts as a structured list.
 * Throws on failure — caller must fall back to the REST extractor.
 */
export async function extractConceptsViaLive(
  images: { mimeType: string; base64: string }[]
): Promise<ExtractedItem[]> {
  if (!liveConfigured) throw new Error('Live AI not configured (missing VITE_GEMINI_API_KEY).')

  // The model "speaks" its answer and we read the AUDIO transcript as text, so
  // JSON/punctuation transcribes badly. Like the mentor's funFactsFor(), we ask
  // for ONE item per line in a flat "Category | value" shape that reads cleanly.
  const promptText =
    `Look carefully at all ${images.length} image(s) and read EVERY clearly visible item: ` +
    `text, titles, notes, definitions, labels, math formulas, chemical equations, ` +
    `diagram annotations, and concepts. ` +
    `STRICT RULE: do NOT invent anything that is not clearly visible. ` +
    `List each item on its OWN line in this exact shape, nothing else:\n` +
    `Category | the extracted item\n` +
    `where Category is one of: Text, Formula, Diagram, Concept. For example:\n` +
    `Concept | Photosynthesis\n` +
    `Formula | 6CO2 plus 6H2O gives C6H12O6 plus 6O2\n` +
    `Text | The mitochondria is the powerhouse of the cell`

  const parts: ImagePart[] = [
    { text: promptText },
    ...images.map((img) => ({ inlineData: { mimeType: img.mimeType, data: img.base64 } })),
  ]

  const raw = await liveVision.askWithImages(parts, 45000)
  log('[vision] raw response len=', raw.length, raw.slice(0, 160))

  const CATS: Record<string, string> = {
    text: 'Text',
    formula: 'Formula',
    diagram: 'Diagram',
    concept: 'Object/Concept',
    object: 'Object/Concept',
  }

  // Try JSON first in case the model ignored us and returned a clean array.
  try {
    const cleaned = raw.trim().replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/i, '').trim()
    if (cleaned.startsWith('[')) {
      const parsed = JSON.parse(cleaned)
      if (Array.isArray(parsed) && parsed.length) {
        return parsed
          .filter((it): it is Record<string, unknown> => !!it && typeof it === 'object' && 'value' in it)
          .map((it) => ({
            value: String(it['value'] ?? '').trim(),
            category: String(it['category'] ?? 'Text').trim(),
          }))
          .filter((it) => it.value.length > 0)
      }
    }
  } catch {
    /* fall through to line parsing */
  }

  // Primary path: one "Category | value" per line from the transcript.
  return raw
    .split('\n')
    .map((line) => line.replace(/^[-*•\d.)\s]+/, '').trim())
    .filter((line) => line.length > 1)
    .map((line) => {
      const sep = line.indexOf('|')
      if (sep > -1) {
        const cat = line.slice(0, sep).trim().toLowerCase()
        const value = line.slice(sep + 1).trim()
        return { value, category: CATS[cat] || 'Text' }
      }
      return { value: line, category: 'Text' }
    })
    .filter((it) => it.value.length > 1 && it.value.length < 240)
}

/**
 * MANY short, distinct fun facts about the exact question, for the loading
 * screen. NON-blocking caller, so a generous budget. The caller calls this
 * repeatedly to keep the supply flowing while the experience generates.
 * Returns [] on failure so the caller keeps its generic rotation.
 */
export async function funFactsFor(
  topic: string,
  language: string,
  count = 18,
): Promise<string[]> {
  const t = topic.trim()
  if (!t || !liveConfigured) return []
  try {
    const out = await live.ask(
      `Tell me ${count} short, surprising, TRUE fun facts about: ${t}. ` +
        `Make each one genuinely different (a different angle each time), and write ` +
        `each as a single complete sentence on its OWN line, maximum 22 words. ` +
        `Write them in ${language}.`,
      22000,
    )
    // Transcription keeps newlines; fall back to sentence boundaries if it didn't.
    let lines = out.split('\n').map(clean).filter(Boolean)
    if (lines.length < 2) {
      lines = out
        .split(/(?<=[.!?])\s+/)
        .map(clean)
        .filter(Boolean)
    }
    return lines.slice(0, count)
  } catch (e) {
    log('funFactsFor failed', e)
    return []
  }
}
