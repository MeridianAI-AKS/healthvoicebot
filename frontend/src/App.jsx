import React, { useCallback, useEffect, useRef, useState } from 'react'
import Header from './components/Header'
import MessageList from './components/MessageList'
import Composer from './components/Composer'
import { useVoiceRecognition } from './hooks/useVoiceRecognition'
import { useAudioPlayer } from './hooks/useAudioPlayer'
import {
  getHealth,
  getLanguages,
  startSession,
  streamChat,
  synthesizeSpeech,
} from './services/api'

// Demo prompts, one per language, so a live audience can see the agent switch
// without anyone having to type in a script they cannot read.
const SUGGESTIONS = [
  { label: 'Full body checkup price?', text: 'What is the price of a full body checkup?' },
  { label: 'हिन्दी — रिपोर्ट कब मिलेगी?', text: 'मेरी रिपोर्ट कब तक मिलेगी?' },
  { label: 'বাংলা — থাইরয়েড টেস্ট', text: 'থাইরয়েড টেস্টের দাম কত?' },
  { label: 'தமிழ் — வீட்டில் சேகரிப்பு', text: 'வீட்டில் இரத்த மாதிரி சேகரிப்பு இலவசமா?' },
  { label: 'Booking status (9800000002)', text: 'Check my booking, my number is 9800000002' },
  { label: 'Safety: read my report', text: 'My haemoglobin is 9.2, is that bad?' },
]

let idCounter = 0
const nextId = () => ++idCounter

export default function App() {
  const [messages, setMessages] = useState([])
  const [languages, setLanguages] = useState([])
  const [locale, setLocale] = useState('hi-IN')
  const [status, setStatus] = useState('ready')
  const [busy, setBusy] = useState(false)
  const [activeTool, setActiveTool] = useState(null)
  const [health, setHealth] = useState(null)

  const sessionRef = useRef(null)
  const localeRef = useRef(locale)
  const busyRef = useRef(false)
  const pipelineRef = useRef(null)
  const interimIdRef = useRef(null)

  const { play, stop: stopAudio } = useAudioPlayer()

  useEffect(() => { localeRef.current = locale }, [locale])
  useEffect(() => { busyRef.current = busy }, [busy])

  const addMessage = useCallback((message) => {
    const id = nextId()
    setMessages((prev) => [...prev, { id, ...message }])
    return id
  }, [])

  const patchMessage = useCallback((id, patch) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, ...patch } : m)))
  }, [])

  const dropMessage = useCallback((id) => {
    setMessages((prev) => prev.filter((m) => m.id !== id))
  }, [])

  // ── boot ──────────────────────────────────────────────────
  const begin = useCallback(async (startLocale) => {
    setMessages([])
    setActiveTool(null)
    setStatus('ready')
    try {
      const session = await startSession(startLocale)
      sessionRef.current = session.session_id
      addMessage({
        role: 'agent',
        content: session.reply,
        locale: session.locale,
        speakable: session.speakable,
      })
    } catch (err) {
      addMessage({ role: 'agent', kind: 'error', content: err.message })
      setStatus('error')
    }
  }, [addMessage])

  useEffect(() => {
    let cancelled = false
    ;(async () => {
      try {
        const [langs, healthPayload] = await Promise.all([getLanguages(), getHealth()])
        if (cancelled) return
        setLanguages(langs.languages)
        setHealth(healthPayload)
        const initial = langs.default || 'hi-IN'
        setLocale(initial)
        localeRef.current = initial
        await begin(initial)
      } catch (err) {
        if (!cancelled) {
          addMessage({
            role: 'agent',
            kind: 'error',
            content: `Cannot reach the backend: ${err.message}`,
          })
          setStatus('error')
        }
      }
    })()
    return () => { cancelled = true }
  }, [begin, addMessage])

  // ── speaking ──────────────────────────────────────────────
  const speak = useCallback(async (message) => {
    if (!health?.speech) return
    try {
      setStatus('speaking')
      const controller = new AbortController()
      const url = await synthesizeSpeech(message.content, message.locale, controller.signal)
      await play(url, controller.signal)
    } catch (err) {
      if (err?.name !== 'AbortError') console.warn('TTS failed:', err.message)
    } finally {
      setStatus((s) => (s === 'speaking' ? 'ready' : s))
    }
  }, [health, play])

  // ── a turn ────────────────────────────────────────────────
  const send = useCallback(async (text, { autoSpeak = false } = {}) => {
    if (!text.trim() || busyRef.current) return

    stopAudio()
    pipelineRef.current?.abort()
    const controller = new AbortController()
    pipelineRef.current = controller

    setBusy(true)
    setStatus('thinking')
    addMessage({ role: 'user', content: text })
    const typingId = addMessage({ role: 'agent', content: '', status: 'typing' })

    const toolsUsed = []
    let reply = ''
    let meta = {}

    try {
      for await (const event of streamChat(
        { message: text, sessionId: sessionRef.current, locale: localeRef.current },
        controller.signal,
      )) {
        if (event.type === 'meta') {
          meta = { ...meta, ...event }
          if (event.locale) {
            setLocale(event.locale)
            localeRef.current = event.locale
          }
        } else if (event.type === 'tool') {
          toolsUsed.push(event.name)
          setActiveTool(event.name)
        } else if (event.type === 'delta') {
          reply += event.text
        } else if (event.type === 'done') {
          reply = event.reply || reply
          meta = { ...meta, ...event }
        } else if (event.type === 'error') {
          throw new Error(event.detail || 'The assistant failed')
        }
      }

      setActiveTool(null)
      patchMessage(typingId, {
        content: reply,
        status: undefined,
        tools: toolsUsed,
        locale: meta.locale,
        speakable: meta.speakable,
        guardrail: meta.guardrail || undefined,
      })

      if (autoSpeak && meta.speakable !== false && health?.speech) {
        await speak({ content: reply, locale: meta.locale })
      }
      setStatus('ready')
    } catch (err) {
      setActiveTool(null)
      if (err?.name === 'AbortError') {
        dropMessage(typingId)
      } else {
        patchMessage(typingId, { content: err.message, status: undefined, kind: 'error' })
        setStatus('error')
      }
    } finally {
      setBusy(false)
      pipelineRef.current = null
    }
  }, [addMessage, patchMessage, dropMessage, speak, stopAudio, health])

  // ── voice ─────────────────────────────────────────────────
  const onInterim = useCallback((text) => {
    if (interimIdRef.current) {
      patchMessage(interimIdRef.current, { content: text })
    } else {
      interimIdRef.current = addMessage({ role: 'user', content: text, status: 'interim' })
    }
  }, [addMessage, patchMessage])

  const onResult = useCallback((text, detected) => {
    if (interimIdRef.current) {
      dropMessage(interimIdRef.current)
      interimIdRef.current = null
    }
    if (detected) localeRef.current = detected
    send(text, { autoSpeak: true })
  }, [dropMessage, send])

  const {
    isListening,
    error: micError,
    start: startMic,
    stop: stopMic,
  } = useVoiceRecognition({ onResult, onInterim, onLocale: setLocale })

  useEffect(() => {
    if (micError) {
      addMessage({ role: 'agent', kind: 'error', content: `Microphone: ${micError}` })
    }
  }, [micError, addMessage])

  useEffect(() => {
    if (isListening) setStatus((s) => (s === 'ready' ? 'listening' : s))
  }, [isListening])

  const onMicToggle = () => (isListening ? stopMic() : startMic())

  const onLocaleChange = (next) => {
    setLocale(next)
    localeRef.current = next
    begin(next)
  }

  const onReset = () => {
    stopMic()
    stopAudio()
    pipelineRef.current?.abort()
    begin(localeRef.current)
  }

  const degraded = health?.missing?.length ? health.missing : null

  return (
    <div className="app">
      <Header
        status={status}
        languages={languages}
        locale={locale}
        onLocaleChange={onLocaleChange}
        isListening={isListening}
        onMicToggle={onMicToggle}
        micAvailable={Boolean(health?.speech)}
        onReset={onReset}
      />

      {degraded && (
        <div className="banner">
          Running in degraded mode — not configured: {degraded.join('; ')}.
          {health?.retrieval_mode === 'keyword' &&
            ' Search is using keyword matching rather than embeddings.'}
        </div>
      )}

      <MessageList
        messages={messages}
        activeTool={activeTool}
        onSpeak={speak}
        canSpeak={Boolean(health?.speech)}
      />

      {messages.length <= 1 && (
        <div className="suggestions">
          {SUGGESTIONS.map((suggestion) => (
            <button
              key={suggestion.label}
              type="button"
              className="chip"
              onClick={() => send(suggestion.text)}
              disabled={busy}
            >
              {suggestion.label}
            </button>
          ))}
        </div>
      )}

      <Composer onSend={send} disabled={busy} />

      <div className="footnote">
        Prototype. Booking, report and coverage answers use demo data. Not medical advice.
      </div>
    </div>
  )
}
