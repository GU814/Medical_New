import { request } from './api';
import type { WxacodeResult } from '@/types';

// ==================== 小程序码 ====================
// scene 最长 32 字符且只能是 ASCII,只放 token,不放中文

export function generateWxacode(scene: string, page?: string, width = 430) {
  return request<WxacodeResult>({
    url: '/api/wxacode',
    method: 'POST',
    data: { scene, page, width },
  });
}
