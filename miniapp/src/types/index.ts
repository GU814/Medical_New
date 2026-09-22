// 全局类型定义

export interface UserProfile {
  user_id: number;
  openid_masked?: string;
  nickname?: string;
  avatar_url?: string;
  phone_masked?: string;
  created_at?: string;
}

export interface WxLoginResult {
  token: string;
  expires_in: number;
  user_id: number;
  is_new: boolean;
}

export interface SessionBrief {
  session_id: string;
  stage: number;
  is_complete: boolean;
  has_report?: boolean;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  isReport?: boolean;
  streaming?: boolean;
  // 多模态输入:用户上传的图片(本地临时路径),用于气泡内缩略图展示
  imageUrl?: string;
  // 该条是否为语音/图片识别生成(用于气泡角标,可选)
  fromMultimodal?: 'voice' | 'image';
}

export interface RecordListItem {
  id: number;
  visit_date: string;
  visit_count: number;
  chief_complaint_preview?: string;
}

export interface RecordDetail {
  id: number;
  patient_name: string;
  patient_gender?: string;
  patient_age?: number;
  chief_complaint?: string;
  present_illness?: string;
  past_history?: string;
  system_review?: string;
  personal_history?: string;
  family_history?: string;
  diagnosis?: string;
  full_report?: string;
  visit_date: string;
  visit_count: number;
}

export interface PagedResult<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

export interface SSEEvent {
  event: 'reply' | 'report' | 'thinking' | 'end' | 'report_done' | 'error';
  data: string;
}

// ==================== 地理位置 ====================
export interface UserLocation {
  id: number;
  name: string;
  address?: string;
  latitude?: number;
  longitude?: number;
  is_default: boolean;
  created_at: string;
}

// ==================== 小程序码 ====================
export interface WxacodeResult {
  image_base64?: string;
  content_type: string;
  mock: boolean;
}

// ==================== 订阅提醒 ====================
export interface ReminderItem {
  id: number;
  template_id: string;
  data: Record<string, unknown>;
  status: string;
  scheduled_at: string;
  sent_at?: string;
  fail_reason?: string;
}
