import Taro from '@tarojs/taro';
import { API_BASE, STORAGE_KEYS } from '@/config';
import type { SSEEvent } from '@/types';

interface SSEStreamOptions {
  url: string
  body: Record<string, unknown>
  onEvent: (ev: SSEEvent) => void
  onError?: (err: unknown) => void
  onComplete?: () => void
}

/**
 * SSE 流式请求封装(小程序专用):
 * - 使用 Taro.request + enableChunked 开启分块传输
 * - requestTask.onChunkReceived 增量接收数据
 * - 解析 SSE 事件块(event:/data: 多行)
 *
 * 兼容性:微信基础库 >= 2.20.2
 * 约定:end/report_done 事件触发完成
 */
export function streamChat(opts: SSEStreamOptions): { abort: () => void } {
  const { url, body, onEvent, onError, onComplete } = opts
  const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`
  const token = Taro.getStorageSync(STORAGE_KEYS.TOKEN)

  // 缓冲区:跨 chunk 的不完整事件块在此拼接
  let buffer = ''
  let finished = false

  // 看门狗:超过 SSE_IDLE_TIMEOUT 未收到任何 chunk 视为连接静默挂死
  // (服务端进程被杀但 TCP 未断时,既无 fail 也无 end,否则 sending 会永久卡死)
  const SSE_IDLE_TIMEOUT = 90_000
  let watchdog: ReturnType<typeof setTimeout> | null = null
  const clearWatchdog = () => {
    if (watchdog) {
      clearTimeout(watchdog)
      watchdog = null
    }
  }
  const resetWatchdog = () => {
    clearWatchdog()
    watchdog = setTimeout(() => {
      if (finished) return
      console.warn('[SSE] 空闲超时,主动断开')
      try {
        ;(requestTask as { abort?: () => void })?.abort?.()
      } catch (e) {
        /* ignore */
      }
      onError?.(new Error('连接超时，请重试'))
      finish()
    }, SSE_IDLE_TIMEOUT)
  }

  const finish = () => {
    if (finished) return
    finished = true
    clearWatchdog()
    onComplete?.()
  }

  // 解析缓冲区中所有完整事件块(以 \n\n 分隔)
  const parseBuffer = () => {
    let sepIndex: number
    while ((sepIndex = buffer.indexOf('\n\n')) !== -1) {
      const chunk = buffer.slice(0, sepIndex)
      buffer = buffer.slice(sepIndex + 2)
      const ev = parseEventBlock(chunk)
      if (ev) {
        onEvent(ev)
        // end/report_done 视为流结束
        if (ev.event === 'end' || ev.event === 'report_done') {
          // end 表示单轮结束,可能后续还有 report;report_done 才是真正完成
          if (ev.event === 'report_done') {
            finish()
          }
        }
      }
    }
  }

  const requestTask = Taro.request({
    url: fullUrl,
    method: 'POST',
    data: body,
    enableChunked: true,
    responseType: 'arraybuffer',
    header: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      Accept: 'text/event-stream',
    },
    success: () => {
      // 整个请求成功结束(此时所有 chunk 已通过 onChunkReceived 处理)
      // 处理缓冲区残余
      if (buffer.trim()) {
        const ev = parseEventBlock(buffer)
        if (ev) onEvent(ev)
        buffer = ''
      }
      finish()
    },
    fail: (err) => {
      console.error('[SSE] 请求失败', err)
      onError?.(err)
      finish()
    },
  })

  // 监听分块数据
  if (requestTask && typeof (requestTask as { onChunkReceived?: unknown }).onChunkReceived === 'function') {
    ;(requestTask as { onChunkReceived: (cb: (res: { data: ArrayBuffer }) => void) => void }).onChunkReceived((res) => {
      try {
        resetWatchdog()
        const text = arrayBufferToString(res.data)
        buffer += text
        parseBuffer()
      } catch (e) {
        console.error('[SSE] 解析 chunk 失败', e)
      }
    })
  } else {
    // 低版本不支持 enableChunked:回退提示用户
    console.warn('[SSE] 当前基础库不支持 enableChunked,无法流式接收')
    onError?.(new Error('当前微信版本过低,不支持流式问诊'))
  }

  return {
    abort: () => {
      try {
        ;(requestTask as { abort?: () => void })?.abort?.()
      } catch (e) {
        console.error('[SSE] abort 失败', e)
      }
      finish()
    },
  }
}

// 解析单个事件块为 SSEEvent
function parseEventBlock(block: string): SSEEvent | null {
  const lines = block.split('\n')
  let event = 'reply' as SSEEvent['event']
  const dataLines: string[] = []
  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim() as SSEEvent['event']
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).trimStart())
    }
  }
  if (dataLines.length === 0) return null
  return { event, data: dataLines.join('\n') }
}

// ArrayBuffer 转 UTF-8 字符串
function arrayBufferToString(buf: ArrayBuffer): string {
  // 优先用 TextDecoder(小程序新版本支持)
  try {
    if (typeof TextDecoder !== 'undefined') {
      return new TextDecoder('utf-8').decode(buf)
    }
  } catch (e) {
    // ignore
  }
  // 回退:手动按字节解析
  const bytes = new Uint8Array(buf)
  let result = ''
  for (let i = 0; i < bytes.length; i++) {
    result += String.fromCharCode(bytes[i])
  }
  try {
    return decodeURIComponent(escape(result))
  } catch (e) {
    return result
  }
}
