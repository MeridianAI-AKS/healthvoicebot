import React, { useRef, useState } from 'react'

export default function Composer({ onSend, disabled }) {
  const [value, setValue] = useState('')
  const textareaRef = useRef(null)

  const submit = () => {
    const text = value.trim()
    if (!text || disabled) return
    onSend(text)
    setValue('')
    if (textareaRef.current) textareaRef.current.style.height = 'auto'
  }

  const onKeyDown = (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      submit()
    }
  }

  const grow = (e) => {
    setValue(e.target.value)
    e.target.style.height = 'auto'
    e.target.style.height = `${Math.min(e.target.scrollHeight, 130)}px`
  }

  return (
    <div className="composer">
      <textarea
        ref={textareaRef}
        rows={1}
        value={value}
        onChange={grow}
        onKeyDown={onKeyDown}
        placeholder="Ask in Hindi, English, Bengali, Tamil, Telugu or Marathi…"
        aria-label="Message"
      />
      <button
        type="button"
        className="btn primary"
        onClick={submit}
        disabled={disabled || !value.trim()}
      >
        Send
      </button>
    </div>
  )
}
