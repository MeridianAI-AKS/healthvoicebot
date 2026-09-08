/**
 * API base resolution:
 *   1. window.__API_BASE__  (public/config.js, set only on the deployed site)
 *   2. VITE_API_BASE_URL    (build-time)
 *   3. /api                 (local Vite proxy)
 */
function normalizeBase(url) {
  const trimmed = (url || '/api').trim().replace(/\/$/, '')
  return trimmed || '/api'
}

export const API_BASE =
  typeof window !== 'undefined' && window.__API_BASE__
    ? normalizeBase(window.__API_BASE__)
    : normalizeBase(import.meta.env.VITE_API_BASE_URL)

const CLIENT_KEY = import.meta.env.VITE_CLIENT_KEY || ''

function apiUrl(path) {
  return `${API_BASE}${path.startsWith('/') ? path : `/${path}`}`
}

function headers(extra = {}) {
  const base = { 'Content-Type': 'application/json', ...extra }
  if (CLIENT_KEY) base['X-Client-Key'] = CLIENT_KEY
  return base
}

async function failure(res, fallback) {
  const body = await res.json().catch(() => ({}))
  throw new Error(body.detail || `${fallback} (${res.status})`)
}

export async function getHealth() {
  const res = await fetch(apiUrl('/health'))
  if (!res.ok) await failure(res, 'Health check failed')
  return res.json()
}

export async function getLanguages() {
  const res = await fetch(apiUrl('/languages'))
  if (!res.ok) await failure(res, 'Could not load languages')
  return res.json()
}

export async function startSession(locale, signal) {
  const res = await fetch(apiUrl('/session/start'), {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ locale }),
    signal,
  })
  if (!res.ok) await failure(res, 'Could not start session')
  return res.json()
}

/** Yields the backend's NDJSON events: meta | tool | delta | done | error. */
export async function* streamChat({ message, sessionId, locale }, signal) {
  const res = await fetch(apiUrl('/chat/stream'), {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ message, session_id: sessionId, locale }),
    signal,
  })
  if (!res.ok) await failure(res, 'Chat failed')

  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buffer += decoder.decode(value, { stream: true })
    const lines = buffer.split('\n')
    buffer = lines.pop() || ''
    for (const line of lines) {
      if (line.trim()) yield JSON.parse(line)
    }
  }
  if (buffer.trim()) yield JSON.parse(buffer)
}

export async function synthesizeSpeech(text, locale, signal) {
  const res = await fetch(apiUrl('/tts'), {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ text, locale }),
    signal,
  })
  if (!res.ok) await failure(res, 'Speech synthesis failed')
  return URL.createObjectURL(await res.blob())
}

export async function getSpeechToken() {
  const res = await fetch(apiUrl('/stt-token'), { headers: headers() })
  if (!res.ok) await failure(res, 'Could not get speech token')
  return res.json()
}
