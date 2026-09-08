import { useCallback, useRef, useState } from 'react'
import { getSpeechToken } from '../services/api'

/**
 * Continuous speech recognition with continuous language identification.
 *
 * The FixFeels reference pinned recognition to hi-IN. Here the candidate list
 * comes from the backend and Azure decides per utterance, so a caller can
 * switch from Hindi to Tamil mid-conversation and be understood.
 *
 * Azure limits continuous LID to 10 candidate locales and cannot switch
 * language *within* one sentence — code-mixed Hinglish resolves to whichever
 * language dominates the utterance, which is why hi-IN leads the list.
 *
 * The Speech SDK is ~460 kB and is only needed once someone presses the mic,
 * so it is imported on demand rather than at page load.
 */
export function useVoiceRecognition({ onResult, onInterim, onLocale }) {
  const [isListening, setIsListening] = useState(false)
  const [error, setError] = useState(null)
  const recognizerRef = useRef(null)
  const startingRef = useRef(false)

  const callbacks = useRef({ onResult, onInterim, onLocale })
  callbacks.current = { onResult, onInterim, onLocale }

  const stop = useCallback(() => {
    const recognizer = recognizerRef.current
    recognizerRef.current = null
    startingRef.current = false
    setIsListening(false)
    if (recognizer) recognizer.stopContinuousRecognitionAsync(() => {}, () => {})
  }, [])

  const start = useCallback(async () => {
    if (recognizerRef.current || startingRef.current) return
    startingRef.current = true
    setError(null)

    try {
      const SDK = await import('microsoft-cognitiveservices-speech-sdk')
      const { token, region, candidates } = await getSpeechToken()
      const speechConfig = SDK.SpeechConfig.fromAuthorizationToken(token, region)

      speechConfig.setProperty(
        SDK.PropertyId.SpeechServiceConnection_LanguageIdMode,
        'Continuous',
      )
      speechConfig.setProperty(
        SDK.PropertyId.SpeechServiceConnection_EndSilenceTimeoutMs,
        '900',
      )
      speechConfig.setProperty(
        SDK.PropertyId.Speech_SegmentationSilenceTimeoutMs,
        '700',
      )
      speechConfig.setProperty(
        SDK.PropertyId.SpeechServiceConnection_InitialSilenceTimeoutMs,
        '15000',
      )

      const autoDetect = SDK.AutoDetectSourceLanguageConfig.fromLanguages(
        candidates && candidates.length ? candidates : ['hi-IN', 'en-IN'],
      )
      const audioConfig = SDK.AudioConfig.fromDefaultMicrophoneInput()
      const recognizer = SDK.SpeechRecognizer.FromConfig(
        speechConfig,
        autoDetect,
        audioConfig,
      )
      recognizerRef.current = recognizer

      recognizer.recognizing = (_s, e) => {
        const text = e.result?.text?.trim()
        if (text) callbacks.current.onInterim?.(text)
      }

      recognizer.recognized = (_s, e) => {
        if (e.result.reason !== SDK.ResultReason.RecognizedSpeech) return
        const text = e.result.text?.trim()
        if (!text) return

        let locale = null
        try {
          locale = SDK.AutoDetectSourceLanguageResult.fromResult(e.result)?.language
        } catch {
          locale = null
        }
        if (locale) callbacks.current.onLocale?.(locale)
        callbacks.current.onResult?.(text, locale)
      }

      recognizer.canceled = (_s, e) => {
        recognizerRef.current = null
        startingRef.current = false
        setIsListening(false)
        if (e.errorCode !== SDK.CancellationErrorCode.NoError) {
          setError(e.errorDetails || String(e.errorCode))
        }
      }

      recognizer.sessionStopped = () => {
        recognizerRef.current = null
        startingRef.current = false
        setIsListening(false)
      }

      recognizer.startContinuousRecognitionAsync(
        () => {
          startingRef.current = false
          setIsListening(true)
        },
        (err) => {
          startingRef.current = false
          setIsListening(false)
          setError(`Could not start the microphone: ${err}`)
        },
      )
    } catch (err) {
      startingRef.current = false
      setError(err.message || 'Microphone unavailable')
    }
  }, [])

  return { isListening, error, start, stop }
}
