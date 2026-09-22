import { request } from './api';
import type { SessionBrief, RecordListItem, RecordDetail, PagedResult } from '@/types';

// ==================== 问诊会话 ====================
export function createSession() {
  return request<SessionBrief>({ url: '/api/sessions', method: 'POST' })
}

/**
 * 获取「最近一条」会话(不论是否完成),供问诊页复用。
 * 后端已改为返回最近一条(不再限定 is_complete=0),因此只要用户有过会话,
 * 再次进入问诊页就会复用它并加载完整历史,而不是新建一个空会话。
 * 仅当该用户从未有过会话时才返回 404,属预期内结果(quiet,不刷红字)。
 */
export function getLatestSession() {
  return request<SessionBrief>({ url: '/api/sessions/latest', quietStatuses: [404] })
}

export interface SessionListItem {
  session_id: string
  stage: number
  is_complete: boolean
  created_at?: string
  updated_at?: string
  message_count: number
  title: string
}

/** 会话列表(最近更新优先),用于历史会话切换/回溯 */
export function listSessions(limit = 20) {
  return request<{ items: SessionListItem[] }>({
    url: `/api/sessions?limit=${limit}`,
  })
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

// ==================== 后台报告状态(轮询/断点续传) ====================
export interface ReportStatus {
  session_id: string
  report_status: 'none' | 'pending' | 'running' | 'done' | 'failed'
  report: string
  stage: number
  is_complete: boolean
}

/** 查询会话报告状态(报告由后端后台任务生成,前端轮询此接口拿取结果) */
export function getSessionReport(sessionId: string) {
  return request<ReportStatus>({ url: `/api/sessions/${sessionId}/report`, quietStatuses: [404] })
}

/** 重试后台报告生成(仅 failed 状态有效,其余状态后端原样返回) */
export function retryReport(sessionId: string) {
  return request<{ session_id: string; report_status: ReportStatus['report_status'] }>({
    url: `/api/sessions/${sessionId}/report/retry`,
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

/** 分享落地页:公开读取脱敏报告(无需登录) */
export function getShareView(token: string) {
  return request<{
    patient_age?: number;
    patient_gender?: string;
    report?: string;
    visit_date?: string;
    disclaimer?: string;
  }>({
    url: `/api/share/${token}`,
    method: 'GET',
    auth: false,
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
