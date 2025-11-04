import { useCallback, useRef } from 'react'

/**
 * 占位音频提醒 Hook。后续可加载真实 WAV 并控制音量/播放限制。
 */
export function useAudioAlert(src?: string) {
  const audioRef = useRef<HTMLAudioElement | null>(src ? new Audio(src) : null)

  const play = useCallback(() => {
    if (!audioRef.current) {
      console.info('[audio] 播放占位提示')
      return
    }
    audioRef.current.currentTime = 0
    audioRef.current
      .play()
      .catch((err) => console.warn('Audio playback failed (placeholder)', err))
  }, [])

  return { play }
}
