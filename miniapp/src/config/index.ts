// 全局配置
// API 基础地址:生产部署需 HTTPS 且在小程序后台配置 request 合法域名
// 可通过构建环境变量 VITE_API_BASE 覆盖
// 本地联调默认用 127.0.0.1 而非 localhost:
// 部分机器 localhost 会优先解析到 IPv6 的 ::1,而后端 uvicorn 只监听 IPv4,
// 结果请求直接 ERR_CONNECTION_REFUSED(开发者工具里表现为 request:fail)。
export const API_BASE =
  (process.env.VITE_API_BASE as string) || 'http://127.0.0.1:8000'

// storage 键
export const STORAGE_KEYS = {
  TOKEN: 'mb_token',
  USER: 'mb_user',
  SESSION_ID: 'mb_session_id',
}

// 问诊阶段定义
export const STAGES = [
  { value: 1, label: '基本信息' },
  { value: 2, label: '主诉现病史' },
  { value: 3, label: '既往史' },
  { value: 4, label: '系统回顾' },
  { value: 5, label: '完成报告' },
] as const

export function getStageLabel(stage: number): string {
  return STAGES.find((s) => s.value === stage)?.label || '问诊中'
}
