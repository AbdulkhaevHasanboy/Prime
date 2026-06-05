/* ================================================================
   API Client — talks to the FastAPI Auth backend.

   Endpoints used (see /docs on the server):
     POST /auth/register          email + password → ApiUser
     POST /auth/login             OAuth2 form (username/password) → TokenPair
     POST /auth/login/mfa         email + 6-digit code → TokenPair
     POST /auth/forgot-password   email → 200 (always, to avoid enumeration)
     GET  /auth/me                Bearer token → ApiUser
     GET  /auth/profile           Bearer token → ApiProfile
     PUT  /auth/profile           Bearer token + fields → ApiProfile

   Telegram, Google OAuth and history endpoints are intentionally NOT
   wired up here — they aren't configured on the backend yet.

   Base URL comes from VITE_AUTH_API_URL, falling back to the demo host.
================================================================= */

const BASE =
  (import.meta.env.VITE_AUTH_API_URL as string | undefined)?.replace(/\/+$/, '') ||
  'https://testapi-1hhm.onrender.com'

export interface ApiUser {
  id: number
  email: string
  role: string
  is_active: boolean
  is_superuser: boolean
  mfa_enabled: boolean
}

export interface TokenPair {
  access_token: string
  refresh_token: string
  /** 'bearer' on success, 'mfa_required' when a second factor is needed. */
  token_type: string
}

export interface ApiProfile {
  first_name: string | null
  last_name: string | null
  bio: string | null
  avatar_url: string | null
  id: number
  user_id: number
}

export interface ProfileUpdate {
  first_name?: string
  last_name?: string
  bio?: string
  avatar_url?: string
}

/** Turn FastAPI's error shapes into a single readable message. */
function errorMessage(data: unknown, status: number, statusText: string): string {
  const detail = (data as { detail?: unknown })?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    const msg = detail
      .map((d) => (d && typeof d === 'object' ? (d as { msg?: string }).msg : null))
      .filter(Boolean)
      .join('; ')
    if (msg) return msg
  }
  return `${status} ${statusText}`.trim()
}

/** Parse a response as JSON and throw a clean Error on non-2xx. */
async function handle<T>(res: Response): Promise<T> {
  const data = await res.json().catch(() => ({}))
  if (!res.ok) throw new Error(errorMessage(data, res.status, res.statusText))
  return data as T
}

function authHeader(token: string): HeadersInit {
  return { Authorization: `Bearer ${token}` }
}

/* ---------------- auth ---------------- */

export async function register(email: string, password: string): Promise<ApiUser> {
  const res = await fetch(`${BASE}/auth/register`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, password }),
  })
  return handle<ApiUser>(res)
}

/** OAuth2 password flow — body must be x-www-form-urlencoded. */
export async function login(email: string, password: string): Promise<TokenPair> {
  const body = new URLSearchParams({ grant_type: 'password', username: email, password })
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
    body,
  })
  return handle<TokenPair>(res)
}

/**
 * Ensure an account exists for `email`, then log in — used for Google
 * sign-in, where we manage a derived password the user never types.
 * A pre-existing account is fine; we just proceed to log in. Any other
 * registration error is ignored here and surfaces from login() instead.
 */
export async function registerOrLogin(email: string, password: string): Promise<TokenPair> {
  try {
    await register(email, password)
  } catch {
    /* already registered (or transient) — fall through to login */
  }
  return login(email, password)
}

export async function loginMfa(email: string, code: string): Promise<TokenPair> {
  const res = await fetch(`${BASE}/auth/login/mfa`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email, code }),
  })
  return handle<TokenPair>(res)
}

/** Always resolves (server returns 200 even for unknown emails). */
export async function forgotPassword(email: string): Promise<void> {
  const res = await fetch(`${BASE}/auth/forgot-password`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ email }),
  })
  await handle(res)
}

/* ---------------- profile ---------------- */

export async function getMe(token: string): Promise<ApiUser> {
  return handle<ApiUser>(await fetch(`${BASE}/auth/me`, { headers: authHeader(token) }))
}

export async function getProfile(token: string): Promise<ApiProfile> {
  return handle<ApiProfile>(await fetch(`${BASE}/auth/profile`, { headers: authHeader(token) }))
}

export async function updateProfile(token: string, data: ProfileUpdate): Promise<ApiProfile> {
  const res = await fetch(`${BASE}/auth/profile`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify(data),
  })
  return handle<ApiProfile>(res)
}

/* ---------------- MFA Setup & Verification ---------------- */

export interface MfaSetupResponse {
  secret: string
  uri: string
}

export async function setupMfa(token: string): Promise<MfaSetupResponse> {
  const res = await fetch(`${BASE}/auth/mfa/setup`, {
    method: 'POST',
    headers: authHeader(token),
  })
  return handle<MfaSetupResponse>(res)
}

export async function verifyMfa(token: string, code: string): Promise<void> {
  const res = await fetch(`${BASE}/auth/mfa/verify?code=${encodeURIComponent(code)}`, {
    method: 'POST',
    headers: authHeader(token),
  })
  await handle<void>(res)
}

/* ---------------- User History ---------------- */

export interface ApiUserHistory {
  id: number
  user_id: number
  question: string | null
  data: string[] | null
  answer: string | null
  correct_answer: string | null
  favorite: boolean | null
  created_at: string
  is_correct: boolean | null
}

export interface HistoryCreate {
  question?: string
  data?: string[]
  answer?: string
  correct_answer?: string
  favorite?: boolean
}

export async function createHistory(token: string, data: HistoryCreate): Promise<ApiUserHistory> {
  const res = await fetch(`${BASE}/auth/history`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify(data),
  })
  return handle<ApiUserHistory>(res)
}

export async function getHistory(
  token: string,
  start = 0,
  end = 10,
  sort = 'newest'
): Promise<ApiUserHistory[]> {
  const params = new URLSearchParams({
    start: String(start),
    end: String(end),
    sort,
  })
  return handle<ApiUserHistory[]>(
    await fetch(`${BASE}/auth/history?${params}`, { headers: authHeader(token) })
  )
}

/* ---------------- Comics & Reviews ---------------- */

export interface ApiComic {
  id: number
  author_id: number
  title: string
  description: string | null
  images: string[]
  is_public: boolean | null
  created_at: string
}

export interface ComicCreate {
  title: string
  description?: string
  images: string[]
  is_public?: boolean
}

export interface ApiReview {
  id: number
  comic_id: number
  user_id: number
  rating: number
  review_text: string | null
  created_at: string
}

export interface ReviewCreate {
  rating: number
  review_text?: string
}

export async function createComic(token: string, data: ComicCreate): Promise<ApiComic> {
  const res = await fetch(`${BASE}/auth/comics`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify(data),
  })
  return handle<ApiComic>(res)
}

export async function getComics(limit = 10, offset = 0): Promise<ApiComic[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  return handle<ApiComic[]>(await fetch(`${BASE}/auth/comics?${params}`))
}

export async function getMyComics(token: string, limit = 10, offset = 0): Promise<ApiComic[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  return handle<ApiComic[]>(
    await fetch(`${BASE}/auth/comics/my?${params}`, { headers: authHeader(token) })
  )
}

export async function createReview(
  token: string,
  comicId: number,
  data: ReviewCreate
): Promise<ApiReview> {
  const res = await fetch(`${BASE}/auth/comics/${comicId}/reviews`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...authHeader(token) },
    body: JSON.stringify(data),
  })
  return handle<ApiReview>(res)
}

export async function getReviews(comicId: number, limit = 10, offset = 0): Promise<ApiReview[]> {
  const params = new URLSearchParams({
    limit: String(limit),
    offset: String(offset),
  })
  return handle<ApiReview[]>(await fetch(`${BASE}/auth/comics/${comicId}/reviews?${params}`))
}
