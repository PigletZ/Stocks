/** 取消旧读取，并防止不支持取消的旧请求覆盖当前选择。缓存命中也走同一流程。 */
export function createLatestLoader<T>(handlers: {
  resolve: (value: T) => void
  reject?: (error: unknown) => void
  pending?: (value: boolean) => void
}) {
  let generation = 0
  let active: AbortController | null = null
  let disposed = false

  function cancel() {
    generation++
    active?.abort()
    active = null
    if (!disposed) handlers.pending?.(false)
  }

  async function load(fetcher: (signal: AbortSignal) => Promise<T>) {
    if (disposed) return
    active?.abort()
    const request = new AbortController()
    active = request
    const current = ++generation
    handlers.pending?.(true)
    try {
      const value = await fetcher(request.signal)
      if (!disposed && current === generation && !request.signal.aborted) handlers.resolve(value)
    } catch (error) {
      if (!disposed && current === generation && !request.signal.aborted) handlers.reject?.(error)
    } finally {
      if (!disposed && current === generation) {
        active = null
        handlers.pending?.(false)
      }
    }
  }

  function dispose() {
    cancel()
    disposed = true
  }

  return { load, cancel, dispose }
}
