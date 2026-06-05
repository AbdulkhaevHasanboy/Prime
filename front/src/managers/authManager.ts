/* ================================================================
   Auth Manager — session storage for the FastAPI Auth backend.

   "Remember device" decides WHERE we keep it:
     • checked   → localStorage  (survives closing the browser, ~30d)
     • unchecked → sessionStorage (cleared when the tab closes)

   Password logins hit the backend and give us a real JWT pair
   (access + refresh) which we store as-is. Google sign-in (when
   configured) gives us a GSI ID token we store the same way.
================================================================= */

export interface UserSession {
  name: string
  email: string
  avatar: string
  provider: 'google' | 'password' | 'telegram'
  role: 'student' | 'educator'
  /** The raw role string from the backend (e.g. 'student', 'teacher', 'admin'). */
  apiRole: string
}

interface StoredSession {
  user: UserSession
  token: string // access token
  refreshToken?: string
  exp: number // expiry, epoch ms
}

const KEY = 'prime.session'
const REMEMBER_TTL = 30 * 24 * 60 * 60 * 1000 // 30 days
const SESSION_TTL = 12 * 60 * 60 * 1000 // 12 hours

export function sessionTtl(remember: boolean): number {
  return remember ? REMEMBER_TTL : SESSION_TTL
}

/* ---------------- user helpers ---------------- */

function titleCase(s: string): string {
  return s.replace(/[._-]+/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())
}

/** Default avatar (initials) when the user hasn't set one. */
export function avatarFor(name: string): string {
  return `https://ui-avatars.com/api/?name=${encodeURIComponent(name)}&background=6366f1&color=fff&size=120`
}

/** Backend roles → the two roles the UI understands. */
export function mapApiRole(apiRole: string | undefined): 'student' | 'educator' {
  return ['teacher', 'educator', 'admin'].includes((apiRole ?? '').toLowerCase())
    ? 'educator'
    : 'student'
}

/** Build a UserSession from an email (Google sign-in / fallbacks). */
export function buildUser(
  email: string,
  provider: UserSession['provider'],
  name?: string,
  role: 'student' | 'educator' = 'student',
): UserSession {
  const display = name?.trim() || titleCase(email.split('@')[0] || 'User')
  return { name: display, email, avatar: avatarFor(display), provider, role, apiRole: role }
}

/** Build a UserSession from the backend's /auth/me (+ optional profile bits). */
export function buildApiUser(
  email: string,
  apiRole: string,
  opts: { name?: string; avatar?: string } = {},
): UserSession {
  const display = opts.name?.trim() || titleCase(email.split('@')[0] || 'User')
  return {
    name: display,
    email,
    avatar: opts.avatar?.trim() || avatarFor(display),
    provider: 'password',
    role: mapApiRole(apiRole),
    apiRole: apiRole || 'student',
  }
}

/* ---------------- mock JWT ---------------- */

function base64url(obj: unknown): string {
  return btoa(JSON.stringify(obj)).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

/** Build a real-shaped (unsigned) JWT for mocked logins. */
export function mintJwt(user: UserSession, ttlMs: number): string {
  const now = Date.now()
  const header = base64url({ alg: 'none', typ: 'JWT' })
  const payload = base64url({
    sub: user.email,
    name: user.name,
    provider: user.provider,
    role: user.role,
    iat: Math.floor(now / 1000),
    exp: Math.floor((now + ttlMs) / 1000),
  })
  return `${header}.${payload}.` // empty signature segment — demo only
}

/* ---------------- session storage ---------------- */

/** Persist the user + token(s). Remember → localStorage, else sessionStorage. */
export function setLocalSession(
  user: UserSession,
  token: string,
  remember: boolean,
  refreshToken?: string,
): void {
  const session: StoredSession = {
    user,
    token,
    refreshToken,
    exp: Date.now() + sessionTtl(remember),
  }
  // Drop any copy in the other store so we never restore a stale one.
  localStorage.removeItem(KEY)
  sessionStorage.removeItem(KEY)
  const store = remember ? localStorage : sessionStorage
  store.setItem(KEY, JSON.stringify(session))
}

/** Persist a backend login (access + refresh JWT pair). */
export function setApiSession(
  user: UserSession,
  accessToken: string,
  refreshToken: string,
  remember: boolean,
): void {
  setLocalSession(user, accessToken, remember, refreshToken)
}

/** Read the stored session object from whichever store holds it. */
function readStored(): { store: Storage; session: StoredSession } | null {
  for (const store of [localStorage, sessionStorage]) {
    const raw = store.getItem(KEY)
    if (!raw) continue
    try {
      return { store, session: JSON.parse(raw) as StoredSession }
    } catch {
      store.removeItem(KEY)
    }
  }
  return null
}

/** Patch the stored user (e.g. after a profile edit) without touching tokens. */
export function updateStoredUser(patch: Partial<UserSession>): UserSession | null {
  const found = readStored()
  if (!found) return null
  const user = { ...found.session.user, ...patch }
  found.store.setItem(KEY, JSON.stringify({ ...found.session, user }))
  return user
}

/** Mint a mock JWT for `user` and start a local session. Returns the token. */
export function startSession(user: UserSession, remember: boolean): string {
  const token = mintJwt(user, sessionTtl(remember))
  setLocalSession(user, token, remember)
  return token
}

/** Read a still-valid session's user, or null. Expired/corrupt entries are purged. */
export function loadSession(): UserSession | null {
  const raw = localStorage.getItem(KEY) ?? sessionStorage.getItem(KEY)
  if (!raw) return null
  try {
    const session = JSON.parse(raw) as StoredSession
    if (!session?.token || !session.user || typeof session.exp !== 'number' || Date.now() > session.exp) {
      clearSession()
      return null
    }
    return session.user
  } catch {
    clearSession()
    return null
  }
}

/** The raw access JWT, e.g. to send as an Authorization: Bearer header. */
export function getToken(): string | null {
  return readStored()?.session.token ?? null
}

/** The refresh JWT, for exchanging via /auth/refresh later. */
export function getRefreshToken(): string | null {
  return readStored()?.session.refreshToken ?? null
}

/** Sign out — wipe both stores. */
export function clearSession(): void {
  localStorage.removeItem(KEY)
  sessionStorage.removeItem(KEY)
}
