// 全局类型定义

export interface UserProfile {
  user_id: number;
  openid_masked?: string;
  nickname?: string;
  avatar_url?: string;
  phone_masked?: string;
  created_at?: string;
  /** 登录资料:性别(profile_gender),新会话创建时由后端预填 */
  gender?: string;
  /** 登录资料:年龄(profile_age),新会话创建时由后端预填 */
  age?: number;
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
  // ReAct 推理过程(步骤时间线)。实时流式累积 + 历史回放回填共用同一字段。
  steps?: ReactStep[];
  // 该轮推理过程为何缺失(历史会话早于上线 / 未开启 / 指定轮无记录)。
  // 有值时必须展示原因,不允许退化成「暂无推理过程」这类空文案。
  stepsMissingReason?: string;
}

// ==================== ReAct 推理过程(可解释性) ====================
/** 一条知识/记忆引用,绑定到正文里的 [n] */
export interface ReactStepRef {
  n: number;
  /** 稳定片段标识:知识库为 {文件名}_chunk_{i},记忆为 {session_id}_t{n} */
  doc_id?: string;
  source?: string;
  chunk_index?: number | null;
  score?: number;
  quote?: string;
  kind?: string;
  session_id?: string;
}

/** 句子级溯源结果:终答正文按句切开后逐句绑定引用 */
export interface ReactSentence {
  text: string;
  refs: ReactStepRef[];
  /** 该句是否引用了知识片段;false 表示通用表述,不丢内容 */
  cited: boolean;
  /**
   * 该句的来源是否由系统按字面重合度「推断绑定」。
   * 模型漏写 [n] 时后端会兜底挂源,但那不是模型显式引用 ——
   * 标 inferred 是为了在界面上和真实引用区分开,避免伪溯源误导用户。
   */
  inferred?: boolean;
}

/** 推理过程的一步(thought / action / observation / final / fallback / note) */
export interface ReactStep {
  seq: number;
  type: 'thought' | 'action' | 'observation' | 'final' | 'fallback' | 'note';
  text?: string;
  ts?: string;
  elapsed_ms?: number;
  status?: string;
  tool?: string | null;
  args?: Record<string, unknown> | null;
  refs?: ReactStepRef[];
  sentences?: ReactSentence[] | null;
  error?: string | null;
}

/** 一轮问答的推理轨迹 */
export interface ReactTraceTurn {
  turn_index: number;
  branch?: string;
  fallback_reason?: string | null;
  steps: ReactStep[];
}

/** GET /api/sessions/{id}/steps 的响应 */
export interface SessionStepsResult {
  session_id: string;
  turns: ReactTraceTurn[];
  /** 整个会话一条步骤记录都没有时的原因说明(不可能是空字符串以外的缺省态) */
  missing_reason?: string;
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
  // step 为 ReAct 推理过程增量事件(后端 react.loop 下发,老版本前端不认识会自然忽略)
  event: 'reply' | 'report' | 'thinking' | 'step' | 'end' | 'report_done' | 'error';
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
