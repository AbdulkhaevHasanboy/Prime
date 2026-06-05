/* ================================================================
   Fast text translation — NOT an LLM.

   Why not reuse the Gemini round-trip? Re-sending a whole index.html
   (inline CSS + JS + markup, often 30k+ tokens) to a language model
   just to translate the words is slow and expensive, and risks the
   model rewriting code. Instead we:
     1. parse the HTML in the browser,
     2. pull out ONLY the human-readable text (text nodes + a few
        user-facing attributes), never touching <script>/<style>,
     3. translate those short strings,
     4. drop the translations back into the same DOM and re-serialize.

   This sends a few hundred characters instead of the whole document
   and leaves all code byte-identical.

   Backends, in order of preference:
     1. The browser's built-in Translator API (Chrome 138+). On-device,
        free, offline, instant — no key, nothing leaves the machine.
        First use of a language pair may download a small model.
     2. Google Cloud Translation v2, if VITE_GOOGLE_TRANSLATE_API_KEY
        is set (reliable + quota-backed, good for production).
     3. The keyless public translate endpoint (works out of the box,
        fine for a demo).
   If every backend fails we keep the original text.
================================================================= */

export type LangCode = 'en' | 'ru' | 'uz'

const GT_KEY = import.meta.env.VITE_GOOGLE_TRANSLATE_API_KEY as string | undefined
const V2_URL = 'https://translation.googleapis.com/language/translate/v2'
const FREE_URL = 'https://translate.googleapis.com/translate_a/single'

/** Run `fn` over `items` with at most `limit` in flight, preserving order. */
async function mapPool<T, R>(items: T[], limit: number, fn: (x: T) => Promise<R>): Promise<R[]> {
  const res = new Array<R>(items.length)
  let cursor = 0
  async function worker() {
    while (cursor < items.length) {
      const i = cursor++
      res[i] = await fn(items[i]!)
    }
  }
  await Promise.all(Array.from({ length: Math.min(limit, items.length) }, worker))
  return res
}

/* ---------------- Browser-native Translator API ---------------- */

interface NativeTranslator {
  translate(text: string): Promise<string>
}

// One translator per source→target pair; creation (and any model download)
// happens once and is reused for the rest of the session.
const nativeCache = new Map<string, Promise<NativeTranslator | null>>()

function getNativeTranslator(source: LangCode, target: LangCode): Promise<NativeTranslator | null> {
  const key = `${source}->${target}`
  const cached = nativeCache.get(key)
  if (cached) return cached

  const created = (async (): Promise<NativeTranslator | null> => {
    const g = globalThis as any
    const opts = { sourceLanguage: source, targetLanguage: target }
    try {
      // Newer spec: global `Translator` with availability()/create().
      if (typeof g.Translator !== 'undefined') {
        const T = g.Translator
        if (typeof T.availability === 'function') {
          const status = await T.availability(opts)
          if (status === 'unavailable') return null
        }
        return (await T.create(opts)) as NativeTranslator
      }
      // Older experimental shape: self.translation.createTranslator().
      const legacy = g.translation
      if (legacy?.createTranslator) {
        if (typeof legacy.canTranslate === 'function') {
          const status = await legacy.canTranslate(opts)
          if (status === 'no') return null
        }
        return (await legacy.createTranslator(opts)) as NativeTranslator
      }
    } catch {
      return null
    }
    return null
  })()

  nativeCache.set(key, created)
  return created
}

/** Attributes whose values are shown to the user and so worth translating. */
const TRANSLATABLE_ATTRS = ['placeholder', 'title', 'alt', 'aria-label']
/** Tags whose text is code/markup, never prose. */
const SKIP_TAGS = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'CODE', 'PRE'])

/* ---------------- Translation backends ---------------- */

/** Official Google Cloud Translation v2 — batches up to ~128 strings/call. */
async function translateV2(texts: string[], target: LangCode, source?: LangCode): Promise<string[]> {
  const out: string[] = []
  // Stay well under the per-request segment/character limits.
  const CHUNK = 100
  for (let i = 0; i < texts.length; i += CHUNK) {
    const q = texts.slice(i, i + CHUNK)
    const res = await fetch(`${V2_URL}?key=${GT_KEY}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ q, target, source, format: 'text' }),
    })
    const data = await res.json().catch(() => ({}))
    if (!res.ok) throw new Error(`Translate API ${res.status}: ${data?.error?.message ?? res.statusText}`)
    const translations = data?.data?.translations as { translatedText: string }[] | undefined
    if (!translations) throw new Error('Translate API returned no translations.')
    for (let j = 0; j < q.length; j++) out.push(translations[j]?.translatedText ?? q[j]!)
  }
  return out
}

/** Keyless public endpoint — one string per request, run with limited concurrency. */
async function translateFree(texts: string[], target: LangCode, source?: LangCode): Promise<string[]> {
  const sl = source ?? 'auto'
  const results = new Array<string>(texts.length)
  const POOL = 8
  let cursor = 0

  async function worker() {
    while (cursor < texts.length) {
      const idx = cursor++
      const text = texts[idx]!
      try {
        const url = `${FREE_URL}?client=gtx&sl=${sl}&tl=${target}&dt=t&q=${encodeURIComponent(text)}`
        const res = await fetch(url)
        const data = await res.json()
        // Shape: [[["translated","original",...], ...], ...]
        const segs = (data?.[0] as [string][]) ?? []
        const joined = segs.map((s) => s?.[0] ?? '').join('')
        results[idx] = joined || text
      } catch {
        results[idx] = text // keep original on failure
      }
    }
  }

  await Promise.all(Array.from({ length: Math.min(POOL, texts.length) }, worker))
  return results
}

/**
 * Translate a list of plain strings into `target`. De-duplicates identical
 * strings so each unique phrase is sent once, and tries the on-device
 * Translator API before any network backend.
 */
export async function translateTexts(
  texts: string[],
  target: LangCode,
  source?: LangCode,
): Promise<string[]> {
  if (!texts.length || target === source) return texts.slice()

  const unique = [...new Set(texts)]
  let translatedUnique: string[] | null = null

  // 1. On-device browser translation (free, instant, offline). Needs a known
  //    source language; falls through if the pair isn't supported.
  if (source) {
    const native = await getNativeTranslator(source, target)
    if (native) {
      try {
        translatedUnique = await mapPool(unique, 6, (s) => native.translate(s))
      } catch {
        translatedUnique = null
      }
    }
  }

  // 2./3. Google Cloud (with key) or the keyless endpoint.
  if (!translatedUnique) {
    translatedUnique = GT_KEY
      ? await translateV2(unique, target, source)
      : await translateFree(unique, target, source)
  }

  const map = new Map<string, string>()
  unique.forEach((u, i) => map.set(u, translatedUnique![i] ?? u))
  return texts.map((t) => map.get(t) ?? t)
}

/* ---------------- HTML in-place translation ---------------- */

function collectTextNodes(root: Document): Text[] {
  const walker = root.createTreeWalker(root.documentElement, NodeFilter.SHOW_TEXT, {
    acceptNode(node) {
      const parent = node.parentElement
      if (!parent || SKIP_TAGS.has(parent.tagName)) return NodeFilter.FILTER_REJECT
      // Skip pure whitespace / symbol-only nodes (numbers, math, punctuation).
      const text = node.nodeValue ?? ''
      if (!text.trim() || !/[\p{L}]/u.test(text)) return NodeFilter.FILTER_REJECT
      return NodeFilter.FILTER_ACCEPT
    },
  })
  const nodes: Text[] = []
  let n: Node | null
  while ((n = walker.nextNode())) nodes.push(n as Text)
  return nodes
}

function collectAttrs(root: Document): { el: Element; name: string }[] {
  const hits: { el: Element; name: string }[] = []
  root.querySelectorAll('*').forEach((el) => {
    if (SKIP_TAGS.has(el.tagName)) return
    for (const name of TRANSLATABLE_ATTRS) {
      const v = el.getAttribute(name)
      if (v && /[\p{L}]/u.test(v)) hits.push({ el, name })
    }
    // Button-like inputs show their `value` to the user.
    if (el.tagName === 'INPUT') {
      const type = (el.getAttribute('type') ?? '').toLowerCase()
      if ((type === 'button' || type === 'submit' || type === 'reset') && el.getAttribute('value')) {
        hits.push({ el, name: 'value' })
      }
    }
  })
  return hits
}

/**
 * Translate every visible word in a self-contained index.html into `target`,
 * leaving all markup, CSS and JavaScript untouched. Fast (Google Translate,
 * only the visible strings are sent) and safe (code is never transmitted).
 *
 * NOTE: text that the page's own JavaScript injects at runtime is generated
 * in the page's original language; the live experience is created directly
 * in the chosen language, so this matters only when switching afterwards.
 */
export async function translateHtmlText(
  html: string,
  target: LangCode,
  source?: LangCode,
): Promise<string> {
  const doc = new DOMParser().parseFromString(html, 'text/html')

  const textNodes = collectTextNodes(doc)
  const attrs = collectAttrs(doc)

  const phrases = [
    ...textNodes.map((t) => t.nodeValue ?? ''),
    ...attrs.map(({ el, name }) => el.getAttribute(name) ?? ''),
  ]
  if (!phrases.length) return html

  // Translate trimmed phrases but preserve each node's leading/trailing space.
  const trimmed = phrases.map((p) => p.trim())
  const translated = await translateTexts(trimmed, target, source)

  let i = 0
  for (const node of textNodes) {
    const original = node.nodeValue ?? ''
    const lead = original.match(/^\s*/)?.[0] ?? ''
    const trail = original.match(/\s*$/)?.[0] ?? ''
    node.nodeValue = lead + (translated[i] ?? trimmed[i] ?? original) + trail
    i++
  }
  for (const { el, name } of attrs) {
    el.setAttribute(name, translated[i] ?? el.getAttribute(name) ?? '')
    i++
  }

  const doctype = doc.doctype ? '<!DOCTYPE html>\n' : ''
  return doctype + doc.documentElement.outerHTML
}
