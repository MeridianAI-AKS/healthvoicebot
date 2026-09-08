import React from 'react'

const STATUS_TEXT = {
  ready: 'Ready',
  thinking: 'Looking that up…',
  listening: 'Listening…',
  speaking: 'Speaking…',
  error: 'Something went wrong',
}

const STATUS_DOT = {
  ready: 'ok',
  thinking: 'busy',
  listening: 'busy',
  speaking: 'busy',
  error: 'err',
}

export default function Header({
  status,
  languages,
  locale,
  onLocaleChange,
  isListening,
  onMicToggle,
  micAvailable,
  onReset,
}) {
  return (
    <header className="header">
      <div className="brand">
        <div className="avatar" aria-hidden="true">HW</div>
        <div>
          <div className="brand-name">Hindustan Wellness — Help Desk</div>
          <div className="status">
            <span className={`dot ${STATUS_DOT[status] || ''}`} />
            {STATUS_TEXT[status] || 'Ready'}
          </div>
        </div>
      </div>

      <label className="visually-hidden" htmlFor="lang">Language</label>
      <select
        id="lang"
        value={locale}
        onChange={(e) => onLocaleChange(e.target.value)}
        title="Starting language — the agent follows whatever language you actually use"
      >
        {languages.map((lang) => (
          <option key={lang.locale} value={lang.locale}>
            {lang.native_name}
            {lang.speakable ? '' : ' (text only)'}
          </option>
        ))}
      </select>

      <button
        type="button"
        className={`btn mic ${isListening ? 'on' : ''}`}
        onClick={onMicToggle}
        disabled={!micAvailable}
        title={
          micAvailable
            ? 'Speak — the language is detected automatically'
            : 'Voice needs Azure Speech credentials'
        }
      >
        {isListening ? '● Stop' : '🎤 Speak'}
      </button>

      <button type="button" className="btn" onClick={onReset} title="Start over">
        Reset
      </button>
    </header>
  )
}
