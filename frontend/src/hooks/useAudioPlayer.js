import { useCallback, useEffect, useRef } from 'react'

/** Plays one TTS clip at a time; stop() cancels playback and frees the blob URL. */
export function useAudioPlayer() {
  const audioRef = useRef(null)
  const urlRef = useRef(null)

  const release = useCallback(() => {
    if (urlRef.current) {
      URL.revokeObjectURL(urlRef.current)
      urlRef.current = null
    }
  }, [])

  const stop = useCallback(() => {
    const audio = audioRef.current
    if (audio) {
      audio.pause()
      audio.src = ''
      audioRef.current = null
    }
    release()
  }, [release])

  const play = useCallback(
    (url, signal) =>
      new Promise((resolve, reject) => {
        stop()
        if (signal?.aborted) {
          URL.revokeObjectURL(url)
          const abort = new Error('aborted')
          abort.name = 'AbortError'
          reject(abort)
          return
        }

        const audio = new Audio(url)
        audioRef.current = audio
        urlRef.current = url

        const finish = (fn, arg) => {
          signal?.removeEventListener('abort', onAbort)
          release()
          fn(arg)
        }
        const onAbort = () => {
          audio.pause()
          const abort = new Error('aborted')
          abort.name = 'AbortError'
          finish(reject, abort)
        }

        audio.onended = () => finish(resolve)
        audio.onerror = () => finish(reject, new Error('Audio playback failed'))
        signal?.addEventListener('abort', onAbort, { once: true })

        audio.play().catch((err) => finish(reject, err))
      }),
    [release, stop],
  )

  useEffect(() => stop, [stop])

  return { play, stop }
}
