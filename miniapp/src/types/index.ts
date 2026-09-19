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
  event: 'reply' | 'report' | 'end' | 'report_done' | 'error';
  data: string;
}
