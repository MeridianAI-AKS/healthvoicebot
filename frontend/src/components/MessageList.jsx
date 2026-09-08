import React, { useEffect, useRef } from 'react'

// Shown while a tool runs, so the demo audience can see the agent doing real
// work rather than guessing from a spinner.
const TOOL_LABELS = {
  search_catalogue: 'Searching the catalogue',
  get_package_details: 'Opening package details',
  check_pincode: 'Checking home collection coverage',
  get_available_slots: 'Checking collection slots',
  lookup_booking: 'Looking up the booking',
  get_report_status: 'Checking report status',
  create_booking: 'Creating the booking',
  escalate_to_human: 'Connecting a human agent',
}

// Tools whose answers come from demo fixtures rather than live systems.
const MOCK_TOOLS = new Set([
  'check_pincode',
  'get_available_slots',
  'lookup_booking',
  'get_report_status',
  'create_booking',
  'escalate_to_human',
])

function Bubble({ message, onSpeak, canSpeak }) {
  const classes = ['bubble']
  if (message.status === 'interim') classes.push('interim')
  if (message.guardrail) classes.push('guardrail')
  if (message.kind === 'error') classes.push('error')

  return (
    <div className={`row ${message.role === 'user' ? 'user' : 'agent'}`}>
      <div>
        <div className={classes.join(' ')}>
          {message.status === 'typing' ? (
            <span className="typing"><i /><i /><i /></span>
          ) : (
            message.content
          )}
        </div>

        {message.role === 'agent' && message.status !== 'typing' && (
          <div className="meta">
            {message.tools?.map((tool, index) => (
              <span
                key={`${tool}-${index}`}
                className={`tag ${MOCK_TOOLS.has(tool) ? 'mock' : ''}`}
              >
                {TOOL_LABELS[tool] || tool}
                {MOCK_TOOLS.has(tool) ? ' · demo data' : ''}
              </span>
            ))}
            {message.guardrail === 'emergency' && (
              <span className="tag mock">safety rule applied</span>
            )}
            {message.locale && <span>{message.locale}</span>}
            {canSpeak && message.speakable !== false && (
              <button type="button" className="speak" onClick={() => onSpeak(message)}>
                ▶ Listen
              </button>
            )}
            {message.speakable === false && <span>no voice for this language</span>}
          </div>
        )}
      </div>
    </div>
  )
}

export default function MessageList({ messages, activeTool, onSpeak, canSpeak }) {
  const endRef = useRef(null)

  useEffect(() => {
    endRef.current?.scrollIntoView({ behavior: 'smooth', block: 'end' })
  }, [messages, activeTool])

  return (
    <div className="transcript">
      {messages.map((message) => (
        <Bubble
          key={message.id}
          message={message}
          onSpeak={onSpeak}
          canSpeak={canSpeak}
        />
      ))}

      {activeTool && (
        <div className="row agent">
          <div className="meta">
            <span className={`tag ${MOCK_TOOLS.has(activeTool) ? 'mock' : ''}`}>
              {TOOL_LABELS[activeTool] || activeTool}…
            </span>
          </div>
        </div>
      )}

      <div ref={endRef} />
    </div>
  )
}
