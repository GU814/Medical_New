import Taro from '@tarojs/taro';
import { request } from './api';
import { SUBSCRIBE_TEMPLATES } from '@/config';
import type { ReminderItem } from '@/types';

/**
 * 问诊完成场景:请求订阅消息授权并上报后端。
 * 模板 ID 未配置(SUBSCRIBE_TEMPLATES.consult_done 为空)时直接跳过(dev/未申请)。
 */
export async function requestConsultDoneSubscribe(): Promise<void> {
  const tmplId = SUBSCRIBE_TEMPLATES.consult_done;
  if (!tmplId) return;
  try {
    await Taro.requestSubscribeMessage({ tmplIds: [tmplId] });
    await request({
      url: '/api/subscribe/authorize',
      method: 'POST',
      data: { template_id: tmplId, scene: 'consult_done' },
    });
  } catch (err) {
    // 用户拒绝或接口异常都不阻断主流程
    console.warn('[subscribe] 授权/上报失败', err);
  }
}

export function createReminder(
  templateId: string,
  data: Record<string, unknown>,
  scheduledAt?: string
) {
  return request<{ id: number }>({
    url: '/api/subscribe/reminders',
    method: 'POST',
    data: { template_id: templateId, data, scheduled_at: scheduledAt },
  });
}

export function listReminders() {
  return request<ReminderItem[]>({ url: '/api/subscribe/reminders' });
}
