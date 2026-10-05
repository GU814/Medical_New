import Taro from '@tarojs/taro';
import { API_BASE, STORAGE_KEYS } from '@/config';

export interface RequestOptions<T = unknown> {
  url: string;
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  data?: Record<string, unknown> | unknown;
  auth?: boolean; // 是否注入 Bearer token,默认 true
  header?: Record<string, string>;
  /**
   * 预期内的错误状态码(如新用户查「最近未完成会话」必然 404)。
   * 命中时不打印 console.error 噪音,但仍以异常抛出,由调用方静默处理。
   */
  quietStatuses?: number[];
  /**
   * 内部使用:为 true 时,401 不触发静默重登 / 清登录态,仅抛出。
   * 用于静默重登自身的换 token 请求,避免递归与误清登录态。
   */
  noAuthGuard?: boolean;
}

/**
 * 预期内错误:用于区分「业务上正常的空结果」与「真故障」。
 * 只在日志层面静默,调用方的 try/catch 行为与普通 Error 完全一致。
 */
export class ExpectedError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'ExpectedError';
  }
}

/**
 * 静默重登(方案一):
 * wx.login 取 code -> POST /auth/wx-login 换新 token 并写入 storage。
 * 成功返回 true;失败(无 code / 换 token 异常)返回 false。
 * 仅在请求 401 时由 request 调用一次,不弹 UI、不跳页;失败交由上层按原逻辑处理。
 * 内部通过 noAuthGuard 调用换 token 接口,避免递归触发重登与误清登录态。
 */
async function trySilentRelogin(): Promise<boolean> {
  try {
    const { code } = await Taro.login()
    if (!code) return false
    const result = await request<{ token: string }>({
      url: '/auth/wx-login',
      method: 'POST',
      data: { code },
      auth: false,
      noAuthGuard: true,
    })
    if (!result?.token) return false
    Taro.setStorageSync(STORAGE_KEYS.TOKEN, result.token)
    return true
  } catch {
    return false
  }
}

/**
 * 统一请求封装:
 * - 自动注入 Authorization: Bearer <token>
 * - 401 时先尝试静默重登换新 token 并重试;仅当重登也失败才清除 token 并跳转登录页
 * - 统一错误处理
 */
export async function request<T = unknown>(
  opts: RequestOptions<T>,
  _attempt = 0,
): Promise<T> {
  const { url, method = 'GET', data, auth = true, header = {}, quietStatuses = [], noAuthGuard = false } = opts
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
      // 方案一:需鉴权的请求且尚未重试过时,先静默重登一次换新 token,再重试原请求,
      // 避免 token 过期即被强制登出、丢失登录记录。
      if (!noAuthGuard && auth !== false && _attempt === 0) {
        const refreshed = await trySilentRelogin()
        if (refreshed) {
          return request<T>({ ...opts, noAuthGuard: false }, _attempt + 1)
        }
      }
      // 静默重登失败 / 已重试过 / 内部请求:保持原行为,清登录态并跳登录页
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
      // 预期内错误(如「无未完成会话」404):仍抛出供调用方分支处理,但不刷红色日志
      if (quietStatuses.includes(res.statusCode)) {
        throw new ExpectedError(detail)
      }
      console.error(`[API] ${method} ${fullUrl} 失败: ${res.statusCode}`, res.data)
      throw new Error(detail)
    }

    return res.data as T
  } catch (err) {
    if (err instanceof ExpectedError) throw err
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
