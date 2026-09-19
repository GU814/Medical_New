import { request } from './api';
import type { SessionBrief, RecordListItem, RecordDetail, PagedResult } from '@/types';

// ==================== 问诊会话 ====================
export function createSession() {
  return request<SessionBrief>({ url: '/api/sessions', method: 'POST' })
}

export function getLatestSession() {
  return request<SessionBrief>({ url: '/api/sessions/latest' })
}

export function getSessionHistory(sessionId: string, cursor = 0, size = 20) {
  return request<{ items: { role: string; content: string }[]; next_cursor: number | null }>({
    url: `/api/sessions/${sessionId}/history?cursor=${cursor}&size=${size}`,
  })
}

export function resetSession(sessionId: string) {
  return request<SessionBrief>({
    url: `/api/sessions/${sessionId}/reset`,
    method: 'POST',
  })
}

// ==================== 历史记录 ====================
export function listRecords(page = 1, size = 10, start?: string, end?: string) {
  const params = new URLSearchParams()
  params.set('page', String(page))
  params.set('size', String(size))
  if (start) params.set('start', start)
  if (end) params.set('end', end)
  return request<PagedResult<RecordListItem>>({ url: `/api/records?${params.toString()}` })
}

export function getRecordDetail(id: number) {
  return request<RecordDetail>({ url: `/api/records/${id}` })
}

export function getRecordReport(id: number) {
  return request<{ report: string; visit_date: string }>({ url: `/api/records/${id}/report` })
}

export function createShare(recordId: number, ttlHours = 72) {
  return request<{ token: string; expires_at: string }>({
    url: '/api/share',
    method: 'POST',
    data: { record_id: recordId, ttl_hours: ttlHours },
  })
}

/**
 * 导出 PDF:小程序需用 Taro.downloadFile + openDocument
 */
export function exportRecordPdf(id: number) {
  return new Promise<void>((resolve, reject) => {
    import('@/config').then(({ API_BASE, STORAGE_KEYS }) => {
      import('@tarojs/taro').then((Taro) => {
        const token = Taro.getStorageSync(STORAGE_KEYS.TOKEN)
        Taro.downloadFile({
          url: `${API_BASE}/api/records/${id}/export?format=pdf`,
          header: { Authorization: `Bearer ${token}` },
          success: (res) => {
            if (res.statusCode === 200) {
              Taro.openDocument({
                filePath: res.tempFilePath,
                fileType: 'pdf',
                showMenu: true,
                success: () => resolve(),
                fail: (err) => {
                  console.error('[Export] openDocument 失败', err)
                  reject(err)
                },
              })
            } else {
              reject(new Error(`导出失败(${res.statusCode})`))
            }
          },
          fail: (err) => {
            console.error('[Export] downloadFile 失败', err)
            reject(err)
          },
        })
      })
    })
  })
}
