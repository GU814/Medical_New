import React, { useEffect, useRef, useState } from 'react';
import { View, Text, ScrollView, Textarea, Button } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import classnames from 'classnames';
import StageIndicator from '@/components/StageIndicator';
import ChatBubble from '@/components/ChatBubble';
import { streamChat } from '@/services/sse';
import {
  createSession,
  getLatestSession,
  getSessionHistory,
  getSessionReport,
  getSessionSteps,
  listSessions,
  retryReport,
} from '@/services/medical';
import { recognizeSpeech, recognizeImage } from '@/services/multimodal';
import { STORAGE_KEYS } from '@/config';
import type { ChatMessage, ReactStep } from '@/types';
import styles from './index.module.scss';

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    '您好,我是 AI 问诊助手。请描述您的主要症状或不适,我将引导您完成问诊并生成报告。\n\n例如:头痛三天,伴有恶心。\n\n您也可以点按 🎤 语音描述,或点按 🖼️ 上传检查单/病历照片。',
};

/**
 * 问诊页 - 核心交互页
 * 流程:加载/创建会话 -> 加载历史 -> SSE 流式发送 -> 处理 reply/report/end 事件
 * 多模态入口:🎤 语音识别、🖼️ 图片识别,识别结果作为文本输入复用同一套问诊流程。
 */
function ConsultPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentStage, setCurrentStage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [scrollAnchor, setScrollAnchor] = useState('');
  // 多模态交互态:录音中 / 上传识别中
  const [recording, setRecording] = useState(false);
  const [uploading, setUploading] = useState(false);
  // 整个会话一条推理步骤都没有时的原因(历史会话早于上线 / 当时未启用),由后端给出
  const [stepsNotice, setStepsNotice] = useState<string | null>(null);

  const abortRef = useRef<{ abort: () => void } | null>(null);
  // 用 ref 保存最新会话/发送态,供录音回调(挂载时注册一次)安全读取
  const sessionIdRef = useRef<string | null>(null);
  const sendingRef = useRef(false);
  const recorderRef = useRef<Taro.RecorderManager | null>(null);
  // 后台报告轮询定时器(报告由后端任务生成,前端轮询拿取结果)
  const pollTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const clearPoll = () => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  };

  // 组件卸载时清理轮询与进行中的流
  useEffect(() => {
    return () => {
      clearPoll();
      abortRef.current?.abort();
    };
  }, []);

  const REPORT_PENDING_ID = 'report-pending';

  // 展示"报告生成中"占位气泡(复用 streaming 指示,不新增样式)
  const showPendingBubble = () => {
    setMessages((prev) =>
      prev.some((m) => m.id === REPORT_PENDING_ID)
        ? prev
        : [
            ...prev,
            {
              id: REPORT_PENDING_ID,
              role: 'assistant' as const,
              content: '📋 正在为您生成问诊报告,请稍候…',
              streaming: true,
            },
          ]
    );
    scrollToBottom();
  };

  // 用后台返回的报告正文替换占位气泡
  const appendReportBubble = (report: string) => {
    setMessages((prev) =>
      prev
        .filter((m) => m.id !== REPORT_PENDING_ID)
        .some((m) => m.isReport)
        ? prev.filter((m) => m.id !== REPORT_PENDING_ID)
        : [
            ...prev.filter((m) => m.id !== REPORT_PENDING_ID),
            {
              id: `report-${Date.now()}`,
              role: 'assistant' as const,
              content: report,
              isReport: true,
            },
          ]
    );
    scrollToBottom();
  };

  /**
   * 轮询后台报告状态(断点续传核心):
   * running/pending -> 3s 后继续;done -> 渲染报告;failed -> 自动重试一次,再失败提示。
   */
  const pollReport = (sid: string) => {
    clearPoll();
    let ticks = 0;
    let retriedOnce = false;
    pollTimerRef.current = setInterval(async () => {
      ticks += 1;
      if (ticks > 100) {
        // 约 5 分钟仍未完成:停止轮询,保留占位气泡,下次进页会重新续接
        clearPoll();
        return;
      }
      try {
        const st = await getSessionReport(sid);
        if (st.report_status === 'done' && st.report) {
          appendReportBubble(st.report);
          clearPoll();
          return;
        }
        if (st.report_status === 'failed') {
          if (!retriedOnce) {
            retriedOnce = true;
            await retryReport(sid);
            return;
          }
          clearPoll();
          Taro.showToast({ title: '报告生成失败,请稍后重进本页重试', icon: 'none' });
        }
        // none/pending/running: 继续轮询
      } catch {
        /* 网络抖动忽略,下一轮继续 */
      }
    }, 3000);
  };

  /**
   * 进入页面时的断点续传检查:
   * - 报告生成中 -> 续接轮询;
   * - 已生成但历史里没有(旧会话/历史接口截断) -> 直接展示;
   * - 失败 -> 提示可重试。
   */
  const resumeReportCheck = async (sid: string, hasReportInHistory: boolean) => {
    try {
      const st = await getSessionReport(sid);
      if (st.report_status === 'pending' || st.report_status === 'running') {
        showPendingBubble();
        pollReport(sid);
      } else if (st.report_status === 'done' && st.report && !hasReportInHistory) {
        appendReportBubble(st.report);
      }
      // none/failed: 保持安静,不打扰用户
    } catch {
      /* 会话不存在或网络异常:忽略 */
    }
  };

  useEffect(() => {
    sessionIdRef.current = sessionId;
  }, [sessionId]);

  // 注册录音管理器(仅一次):停止/出错回调通过 ref 读取最新状态
  useEffect(() => {
    const rm = Taro.getRecorderManager();
    rm.onStop((res) => {
      setRecording(false);
      void handleSpeechResult(res.tempFilePath);
    });
    rm.onError((err) => {
      setRecording(false);
      const msg = (err as { errMsg?: string })?.errMsg || '';
      Taro.showToast({
        title: msg.includes('auth') ? '请允许麦克风权限后重试' : '录音失败,请重试',
        icon: 'none',
      });
    });
    recorderRef.current = rm;
  }, []);

  const loadSession = async () => {
    setLoading(true);
    try {
      const cached = Taro.getStorageSync(STORAGE_KEYS.SESSION_ID) as string;
      if (cached) {
        setSessionId(cached);
        const hasReport = await loadHistory(cached);
        await resumeReportCheck(cached, hasReport);
        return;
      }
      try {
        // 复用最近一条会话(不论是否已完成),保证历史可回溯;
        // 只有当该用户从未有过会话时后端才返回 404,此时才新建。
        const latest = await getLatestSession();
        setSessionId(latest.session_id);
        setCurrentStage(latest.stage);
        Taro.setStorageSync(STORAGE_KEYS.SESSION_ID, latest.session_id);
        const hasReport = await loadHistory(latest.session_id);
        await resumeReportCheck(latest.session_id, hasReport);
      } catch {
        // 该用户暂无任何会话:静默降级为新建,无需提示用户。
        await createNewSession();
      }
    } catch (err) {
      console.error('[Consult] 加载会话失败', err);
      setMessages([WELCOME_MESSAGE]);
    } finally {
      setLoading(false);
    }
  };

  /**
   * 把后端推理步骤回填到历史气泡上(历史回放的核心)。
   *
   * 后端 session_steps 以 (session_id, turn_index) 定位,turn_index = 该轮开始前
   * conversation_history 长度 // 2;而历史 items 是扁平按序返回的第 idx 条,
   * 因此第 idx 条助手回复对应 turn_index = idx // 2。
   *
   * 兜底策略(不允许出现「暂无推理过程」空态):
   * - 有步骤 -> 按 seq 排序后挂到对应气泡,完整回放;
   * - 部分轮次缺失 -> 在该轮气泡上写明「第 N 轮未记录」的原因;
   * - 整条会话都没有 -> 用后端 missing_reason(上线前旧会话 / 当时未启用)统一提示。
   */
  const attachStepsToHistory = async (
    sid: string,
    messages: ChatMessage[]
  ): Promise<ChatMessage[]> => {
    if (!sid) return messages;
    try {
      const data = await getSessionSteps(sid);
      const byTurn = new Map<number, ReactStep[]>();
      for (const t of data.turns || []) {
        const steps = [...(t.steps || [])].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0));
        if (steps.length > 0) byTurn.set(t.turn_index, steps);
      }

      let matched = 0;
      const next = messages.map((m, idx) => {
        if (m.role !== 'assistant') return m;
        const steps = byTurn.get(Math.floor(idx / 2));
        if (steps && steps.length > 0) {
          matched += 1;
          return { ...m, steps, stepsMissingReason: undefined };
        }
        // 该轮没有步骤:给出明确原因,而不是什么都不显示
        if (byTurn.size > 0) {
          return {
            ...m,
            stepsMissingReason: `第 ${Math.floor(idx / 2) + 1} 轮问答未记录推理过程,可能当时未命中直接问答分支,或该轮产生于「推理过程」功能上线前。`,
          };
        }
        return m;
      });

      if (matched === 0 && data.missing_reason) {
        setStepsNotice(data.missing_reason);
      } else {
        setStepsNotice(null);
      }
      return next;
    } catch {
      // 步骤接口异常绝不能影响历史消息的正常展示
      return messages;
    }
  };

  const loadHistory = async (sid: string): Promise<boolean> => {
    try {
      const { items } = await getSessionHistory(sid, 0, 50);
      if (!items || items.length === 0) {
        setMessages([WELCOME_MESSAGE]);
        setStepsNotice(null);
        return false;
      }
      const history: ChatMessage[] = items.map((item, idx) => ({
        id: `history-${idx}`,
        role: item.role === 'user' ? 'user' : 'assistant',
        content: item.content,
        isReport: item.role === 'assistant' && item.content.includes('## '),
        imageUrl: (item as { image_url?: string }).image_url,
      }));
      const withSteps = await attachStepsToHistory(sid, history);
      setMessages(withSteps);
      setTimeout(scrollToBottom, 100);
      return withSteps.some((m) => m.isReport);
    } catch (err) {
      console.error('[Consult] 加载历史失败', err);
      setMessages([WELCOME_MESSAGE]);
      setStepsNotice(null);
      return false;
    }
  };

  const createNewSession = async () => {
    try {
      const session = await createSession();
      setSessionId(session.session_id);
      setCurrentStage(session.stage);
      Taro.setStorageSync(STORAGE_KEYS.SESSION_ID, session.session_id);
      setMessages([WELCOME_MESSAGE]);
    } catch (err) {
      console.error('[Consult] 创建会话失败', err);
      Taro.showToast({ title: '初始化失败,请重试', icon: 'none' });
      setMessages([WELCOME_MESSAGE]);
    }
  };

  // 主动「新建对话」:只新建,不删除旧会话(旧会话仍可从「历史会话」回溯)
  const handleNewSession = async () => {
    if (sending || recording || uploading) {
      Taro.showToast({ title: '请等待当前操作结束', icon: 'none' });
      return;
    }
    const res = await Taro.showModal({
      title: '新建对话',
      content: '开始一个新的问诊对话?当前对话会保留,可在「历史会话」中查看。',
      confirmColor: '#165dff',
    });
    if (!res.confirm) return;
    try {
      clearPoll();
      await createNewSession();
      setInput('');
      Taro.showToast({ title: '已新建对话', icon: 'success' });
    } catch (err) {
      console.error('[Consult] 新建会话失败', err);
      Taro.showToast({ title: '新建失败', icon: 'none' });
    }
  };

  // 历史会话回溯:列出该用户全部会话,选择后加载其完整消息
  const handleHistory = async () => {
    if (sending || recording || uploading) {
      Taro.showToast({ title: '请等待当前操作结束', icon: 'none' });
      return;
    }
    try {
      const { items } = await listSessions(20);
      if (!items || items.length === 0) {
        Taro.showToast({ title: '暂无历史会话', icon: 'none' });
        return;
      }
      // 微信 showActionSheet 最多 6 项
      const shown = items.slice(0, 6);
      const labels = shown.map((s) => {
        const time = (s.updated_at || '').slice(5, 16);
        const title = s.title || (s.message_count ? '对话记录' : '空会话');
        const cur = s.session_id === sessionId ? ' · 当前' : '';
        return `${time} ${title}${cur}`;
      });
      const picked = await Taro.showActionSheet({ itemList: labels });
      const target = shown[picked.tapIndex];
      if (!target || target.session_id === sessionId) return;
      clearPoll();
      setSessionId(target.session_id);
      setCurrentStage(target.stage || 1);
      Taro.setStorageSync(STORAGE_KEYS.SESSION_ID, target.session_id);
      const hasReport = await loadHistory(target.session_id);
      await resumeReportCheck(target.session_id, hasReport);
    } catch (err) {
      // 用户点击取消会走进 catch,静默忽略
      const msg = err instanceof Error ? err.message : String(err);
      if (msg.includes('cancel')) return;
      console.error('[Consult] 加载会话列表失败', err);
    }
  };

  // ============ 核心:把一段文本作为用户输入,跑现有 SSE 问诊流程 ============
  const runChatTurn = (messageText: string, userMsg: ChatMessage) => {
    const sid = sessionIdRef.current;
    if (!messageText.trim() || !sid || sendingRef.current) return;

    const typingId = `bot-${Date.now()}`;
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);
    sendingRef.current = true;
    scrollToBottom();

    setMessages((prev) => [
      ...prev,
      { id: typingId, role: 'assistant', content: '', streaming: true, steps: [] },
    ]);
    // 新开一轮:先清掉上一会话残留的缺失提示
    setStepsNotice(null);
    scrollToBottom();

    abortRef.current?.abort();
    const controller = streamChat({
      url: '/api/chat',
      body: { message: messageText, session_id: sid },
      onEvent: (ev) => {
        switch (ev.event) {
          case 'thinking':
            // 推理模型的「思考过程」:累加到当前机器人气泡,不影响正文
            setMessages((prev) =>
              prev.map((m) =>
                m.id === typingId
                  ? { ...m, thinking: (m.thinking || '') + ev.data }
                  : m
              )
            );
            scrollToBottom();
            break;
          case 'reply':
            setMessages((prev) =>
              prev.map((m) =>
                m.id === typingId ? { ...m, content: m.content + ev.data, streaming: true } : m
              )
            );
            break;
          case 'step':
            // ReAct 推理过程增量:按 seq 去重排序后累积到当前气泡
            try {
              const step = JSON.parse(ev.data) as ReactStep;
              if (step && typeof step.seq === 'number') {
                setMessages((prev) =>
                  prev.map((m) =>
                    m.id === typingId
                      ? {
                          ...m,
                          steps: [
                            ...(m.steps || []).filter((s) => s.seq !== step.seq),
                            step,
                          ].sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0)),
                        }
                      : m
                  )
                );
                scrollToBottom();
              }
            } catch {
              /* 非 JSON 负载忽略,不影响正文 */
            }
            break;
          case 'report':
            setMessages((prev) =>
              prev.map((m) =>
                m.id === typingId
                  ? {
                      ...m,
                      content: m.isReport ? m.content + ev.data : ev.data,
                      isReport: true,
                      streaming: true,
                    }
                  : m
              )
            );
            break;
          case 'end':
            try {
              const endData = JSON.parse(ev.data);
              if (endData.stage) setCurrentStage(endData.stage);
              const finalText =
                typeof endData.reply_clean === 'string' && endData.reply_clean
                  ? endData.reply_clean
                  : null;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === typingId
                    ? {
                        ...m,
                        content: finalText ?? m.content,
                        streaming: false,
                        // 本轮没有推理步骤时说明原因,而不是留下「暂无推理过程」空态
                        stepsMissingReason:
                          endData.react_enabled === false
                            ? '当前服务未启用推理过程记录(ENABLE_REACT=false),本轮不展示推理步骤。'
                            : m.stepsMissingReason,
                      }
                    : m
                )
              );
              // 后台报告架构:问诊完成但报告未就绪 -> 展示占位气泡并轮询续传
              const sid = sessionIdRef.current;
              if (
                sid &&
                endData.is_complete &&
                endData.report_status &&
                endData.report_status !== 'done'
              ) {
                setTimeout(() => {
                  showPendingBubble();
                  pollReport(sid);
                }, 300);
              }
            } catch {
              setMessages((prev) =>
                prev.map((m) => (m.id === typingId ? { ...m, streaming: false } : m))
              );
            }
            setSending(false);
            sendingRef.current = false;
            break;
          case 'report_done':
            try {
              const doneData = JSON.parse(ev.data);
              if (doneData.stage) setCurrentStage(doneData.stage);
            } catch {
              /* 忽略非 JSON 负载 */
            }
            setMessages((prev) =>
              prev.map((m) =>
                m.id === typingId ? { ...m, isReport: true, streaming: false } : m
              )
            );
            setSending(false);
            sendingRef.current = false;
            break;
          case 'error':
            setMessages((prev) =>
              prev
                .filter((m) => m.id !== typingId)
                .concat({
                  id: `err-${Date.now()}`,
                  role: 'assistant',
                  content: `⚠️ ${ev.data || '服务异常'}`,
                })
            );
            setSending(false);
            sendingRef.current = false;
            break;
        }
        scrollToBottom();
      },
      onError: (err) => {
        setMessages((prev) =>
          prev
            .filter((m) => m.id !== typingId)
            .concat({
              id: `err-${Date.now()}`,
              role: 'assistant',
              content: `⚠️ 发送失败:${err instanceof Error ? err.message : '网络错误'}`,
            })
        );
        setSending(false);
        sendingRef.current = false;
        scrollToBottom();
      },
    });
    abortRef.current = controller;
  };

  // 文字发送
  const sendMessage = () => {
    const text = input.trim();
    if (!text || !sessionId || sending || recording || uploading) return;
    runChatTurn(text, { id: `user-${Date.now()}`, role: 'user', content: text });
  };

  // ============ 语音识别入口 ============
  const toggleRecord = () => {
    if (sending || uploading) return;
    const rm = recorderRef.current;
    if (!rm) return;
    if (recording) {
      rm.stop();
    } else {
      setRecording(true);
      Taro.showToast({ title: '正在录音,再次点击结束', icon: 'none' });
      try {
        rm.start({
          duration: 60000,
          format: 'mp3',
          sampleRate: 16000,
          numberOfChannels: 1,
          encodeBitRate: 24000,
        });
      } catch (e) {
        setRecording(false);
        Taro.showToast({ title: '无法开始录音', icon: 'none' });
        console.error('[Consult] 录音启动失败', e);
      }
    }
  };

  const handleSpeechResult = async (tempFilePath?: string) => {
    if (!tempFilePath) return;
    setUploading(true);
    try {
      const { text } = await recognizeSpeech(tempFilePath);
      if (!text) {
        Taro.showToast({ title: '未识别到内容,请重试或用文字', icon: 'none' });
        return;
      }
      runChatTurn(text, {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        fromMultimodal: 'voice',
      });
    } catch (e) {
      Taro.showToast({ title: errMsg(e), icon: 'none' });
    } finally {
      setUploading(false);
    }
  };

  // ============ 图片识别入口 ============
  const pickImage = async () => {
    if (sending || recording || uploading) return;
    let res: Taro.chooseMedia.SuccessCallbackResult;
    try {
      res = await Taro.chooseMedia({
        mediaType: ['image'],
        count: 1,
        sourceType: ['album', 'camera'],
        sizeType: ['compressed'],
      });
    } catch {
      // 用户取消或拒绝相册/相机权限:静默返回,不打扰
      return;
    }
    const file = res.tempFiles?.[0];
    if (!file) return;
    setUploading(true);
    try {
      const { text } = await recognizeImage(file.tempFilePath);
      if (!text) {
        Taro.showToast({ title: '未识别到信息,请换一张', icon: 'none' });
        return;
      }
      runChatTurn(text, {
        id: `user-${Date.now()}`,
        role: 'user',
        content: text,
        imageUrl: file.tempFilePath,
        fromMultimodal: 'image',
      });
    } catch (e) {
      Taro.showToast({ title: errMsg(e), icon: 'none' });
    } finally {
      setUploading(false);
    }
  };

  const errMsg = (e: unknown): string =>
    e instanceof Error ? e.message : '识别失败,请重试';

  // 滚动到底部
  const scrollToBottom = () => {
    setScrollAnchor('');
    setTimeout(() => setScrollAnchor('msg-bottom'), 50);
  };

  useDidShow(() => {
    loadSession();
  });

  const isEmpty = messages.length === 0;
  const inputDisabled = sending || recording || uploading;

  return (
    <View className={styles.container}>
      <View className={styles.stageBar}>
        <StageIndicator current={currentStage} />
      </View>
      <Button className={styles.historyBtn} onClick={handleHistory}>
        历史会话
      </Button>
      <Button className={styles.resetBtn} onClick={handleNewSession}>
        新建对话
      </Button>
      <ScrollView
        className={styles.scrollArea}
        scrollY
        scrollIntoView={scrollAnchor}
        enhanced
        showScrollbar={false}
      >
        <View className={styles.scrollInner}>
          {/* 整条会话都没有推理步骤时,在会话顶部用后端给的原因统一说明 */}
          {stepsNotice ? (
            <View className={styles.stepsNotice}>
              <Text className={styles.stepsNoticeIcon}>🧠</Text>
              <Text className={styles.stepsNoticeText}>{stepsNotice}</Text>
            </View>
          ) : null}
          {loading ? (
            <View className={styles.emptyState}>
              <Text className={styles.emptyIcon}>⏳</Text>
              <Text className={styles.emptyText}>正在加载问诊…</Text>
            </View>
          ) : isEmpty ? (
            <View className={styles.emptyState}>
              <Text className={styles.emptyIcon}>💬</Text>
              <Text className={styles.emptyText}>
                开始描述您的症状,与 AI 医生对话
              </Text>
            </View>
          ) : (
            messages.map((msg) => (
              <ChatBubble
                key={msg.id}
                role={msg.role}
                content={msg.content}
                isReport={msg.isReport}
                streaming={msg.streaming}
                imageUrl={msg.imageUrl}
                fromMultimodal={msg.fromMultimodal}
                thinking={msg.thinking}
                steps={msg.steps}
                stepsMissingReason={msg.stepsMissingReason}
              />
            ))
          )}
          <View id="msg-bottom" />
        </View>
      </ScrollView>
      <View className={styles.inputBar}>
        <Button
          className={classnames(styles.iconBtn, recording && styles.iconBtnRecording)}
          disabled={sending || uploading}
          onClick={toggleRecord}
        >
          {recording ? '■' : '🎤'}
        </Button>
        <Button
          className={styles.iconBtn}
          disabled={inputDisabled}
          onClick={pickImage}
        >
          {uploading ? '⏳' : '🖼️'}
        </Button>
        <Textarea
          className={styles.input}
          value={input}
          onInput={(e) => setInput(e.detail.value)}
          placeholder={recording ? '正在录音…' : '请输入您的症状或问题…'}
          maxlength={500}
          autoHeight
          showConfirmBar={false}
          adjustPosition
        />
        <Button
          className={classnames(
            styles.sendBtn,
            (!input.trim() || inputDisabled) && styles.sendBtnDisabled
          )}
          disabled={!input.trim() || inputDisabled}
          onClick={sendMessage}
        >
          {sending ? (
            <View>
              <Text className={styles.loadingDot}>.</Text>
              <Text className={styles.loadingDot}>.</Text>
              <Text className={styles.loadingDot}>.</Text>
            </View>
          ) : (
            '发送'
          )}
        </Button>
      </View>
    </View>
  );
}

export default ConsultPage;
