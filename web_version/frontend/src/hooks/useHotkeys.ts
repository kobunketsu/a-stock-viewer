import { useEffect } from 'react'

export interface HotkeyBinding {
  combo: string
  handler: () => void
  description?: string
}

/**
 * 占位热键 Hook，暂未集成 KeyboardJS 等库。
 * 目前仅在控制台打印绑定信息，并在卸载时清理日志。
 */
export function useHotkeys(bindings: HotkeyBinding[], enabled = true): void {
  useEffect(() => {
    if (!enabled || bindings.length === 0) return

    bindings.forEach((binding) => {
      console.info(`[hotkey] 注册 ${binding.combo}${binding.description ? ` - ${binding.description}` : ''}`)
    })

    return () => {
      bindings.forEach((binding) => {
        console.info(`[hotkey] 注销 ${binding.combo}`)
      })
    }
  }, [bindings, enabled])
}
