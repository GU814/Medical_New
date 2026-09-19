import Taro from '@tarojs/taro';
import { request } from './api';
import { STORAGE_KEYS } from '@/config';
import type { WxLoginResult, UserProfile } from '@/types';

/**
 * 微信授权登录:
 * wx.login 取 code -> POST /auth/wx-login 换 token -> 存 storage
 */
export async function wxLogin(): Promise<WxLoginResult> {
  console.info('[Auth] 开始微信登录')
  const { code } = await Taro.login()
  if (!code) {
    throw new Error('微信登录失败:未获取到 code')
  }
  console.info('[Auth] 获取 code 成功,请求后端换 token')
  const result = await request<WxLoginResult>({
    url: '/auth/wx-login',
    method: 'POST',
    data: { code },
    auth: false,
  })
  // 持久化 token
  Taro.setStorageSync(STORAGE_KEYS.TOKEN, result.token)
  return result
}

export async function getProfile(): Promise<UserProfile> {
  const profile = await request<UserProfile>({ url: '/auth/me' })
  Taro.setStorageSync(STORAGE_KEYS.USER, profile)
  return profile
}

export async function updateProfile(data: Partial<UserProfile>): Promise<void> {
  await request({
    url: '/auth/profile',
    method: 'PUT',
    data: data as Record<string, unknown>,
  })
}

export function logout(): void {
  Taro.removeStorageSync(STORAGE_KEYS.TOKEN)
  Taro.removeStorageSync(STORAGE_KEYS.USER)
  Taro.removeStorageSync(STORAGE_KEYS.SESSION_ID)
  Taro.reLaunch({ url: '/pages/login/index' })
}

export function isLoggedIn(): boolean {
  return !!Taro.getStorageSync(STORAGE_KEYS.TOKEN)
}
