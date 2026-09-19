import Taro from '@tarojs/taro';
import { API_BASE, STORAGE_KEYS } from '@/config';

export interface RequestOptions<T = unknown> {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: Record<string, unknown> | unknown;
  auth?: boolean; // 是否注入 Bearer token,默认 true
  header?: Record<string, string>;
}

/**
 * 统一请求封装:
 * - 自动注入 Authorization: Bearer <token>
 * - 401 时清除 token 并跳转登录页
 * - 统一错误处理
 */
export async function request<T = unknown>(opts: RequestOptions<T>): Promise<T> {
  const { url, method = 'GET', data, auth = true, header = {} } = opts
  const fullUrl = url.startsWith('http') ? url : `${API_BASE}${url}`

  const finalHeader: Record<string, string> = {
    'Content-Type': 'application/json',
    ...header,
  }

  if (auth) {
    const token = Taro.getStorageSync(STORAGE_KEYS.TOKEN)
    if (token) {
      finalHeader.Authorization = `Bearer ${token}`
    }
  }

  console.info(`[API] ${method} ${fullUrl}`)
  try {
    const res = await Taro.request({
      url: fullUrl,
      method,
      data: data as Record<string, unknown>,
      header: finalHeader,
      timeout: 60000,
    })

    if (res.statusCode === 401) {
      console.warn('[API] 401 未授权,清除登录态')
      Taro.removeStorageSync(STORAGE_KEYS.TOKEN)
      Taro.removeStorageSync(STORAGE_KEYS.USER)
      Taro.removeStorageSync(STORAGE_KEYS.SESSION_ID)
      Taro.reLaunch({ url: '/pages/login/index' })
      throw new Error('登录已过期,请重新登录')
    }

    if (res.statusCode >= 400) {
      const detail =
        (res.data as { detail?: string })?.detail || `请求失败(${res.statusCode})`
      console.error(`[API] ${method} ${fullUrl} 失败: ${res.statusCode}`, res.data)
      throw new Error(detail)
    }

    return res.data as T
  } catch (err) {
    console.error(`[API] ${method} ${fullUrl} 异常:`, err)
    // Taro.request 失败时抛出的是带 errMsg 的对象(不是 Error),转成可读错误便于定位
    if (err instanceof Error) throw err
    const errMsg = (err as { errMsg?: string })?.errMsg || ''
    if (errMsg.includes('url not in domain list') || errMsg.includes('domain')) {
      throw new Error(
        '请求被拦截:请关闭开发者工具「详情-本地设置」中的域名校验(urlCheck),或改用已配置的 HTTPS 合法域名'
      )
    }
    // 连接被拒绝/超时:绝大多数情况是后端没启动,不要把裸 request:fail 抛给上层
    if (
      errMsg.includes('ERR_CONNECTION_REFUSED') ||
      errMsg.includes('CONNECTION_REFUSED') ||
      errMsg === 'request:fail' ||
      errMsg.includes('request:fail')
    ) {
      throw new Error(
        `无法连接后端服务 ${API_BASE}:请先双击项目根目录 start-api.bat 启动服务,再重新编译预览`
      )
    }
    if (errMsg.includes('timeout')) {
      throw new Error('请求超时:后端可能正在加载模型,请稍后重试')
    }
    throw new Error(errMsg || '网络请求失败,请检查后端服务是否已启动')
  }
}

export default { request }
