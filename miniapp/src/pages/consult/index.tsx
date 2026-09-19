import React, { useRef, useState } from 'react';
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
  resetSession,
} from '@/services/medical';
import { STORAGE_KEYS } from '@/config';
import type { ChatMessage } from '@/types';
import styles from './index.module.scss';

const WELCOME_MESSAGE: ChatMessage = {
  id: 'welcome',
  role: 'assistant',
  content:
    '您好,我是 AI 问诊助手。请描述您的主要症状或不适,我将引导您完成问诊并生成报告。\n\n例如:头痛三天,伴有恶心。',
};

/**
 * 问诊页 - 核心交互页
 * 流程:加载/创建会话 -> 加载历史 -> SSE 流式发送 -> 处理 reply/report/end 事件
 */
function ConsultPage() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [sending, setSending] = useState(false);
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [currentStage, setCurrentStage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [scrollAnchor, setScrollAnchor] = useState('');
  const abortRef = useRef<{ abort: () => void } | null>(null);

  const loadSession = async () => {
    setLoading(true);
    try {
      // 优先使用本地缓存的 session_id
      const cached = Taro.getStorageSync(STORAGE_KEYS.SESSION_ID) as string;
      if (cached) {
        setSessionId(cached);
        await loadHistory(cached);
        return;
      }
      // 拉取最近会话
      try {
        const latest = await getLatestSession();
        setSessionId(latest.session_id);
        setCurrentStage(latest.stage);
        Taro.setStorageSync(STORAGE_KEYS.SESSION_ID, latest.session_id);
        if (!latest.is_complete) {
          await loadHistory(latest.session_id);
        } else {
          setMessages([WELCOME_MESSAGE]);
        }
      } catch {
        // 无最近会话 -> 新建
        await createNewSession();
      }
    } catch (err) {
      console.error('[Consult] 加载会话失败', err);
      setMessages([WELCOME_MESSAGE]);
    } finally {
      setLoading(false);
    }
  };

  const loadHistory = async (sid: string) => {
    try {
      const { items } = await getSessionHistory(sid, 0, 50);
      if (!items || items.length === 0) {
        setMessages([WELCOME_MESSAGE]);
        return;
      }
      const history: ChatMessage[] = items.map((item, idx) => ({
        id: `history-${idx}`,
        role: item.role === 'user' ? 'user' : 'assistant',
        content: item.content,
        isReport: item.role === 'assistant' && item.content.includes('## '),
      }));
      setMessages(history);
      setTimeout(scrollToBottom, 100);
    } catch (err) {
      console.error('[Consult] 加载历史失败', err);
      setMessages([WELCOME_MESSAGE]);
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

  const handleReset = async () => {
    if (sending) {
      Taro.showToast({ title: '请等待当前回复结束', icon: 'none' });
      return;
    }
    const res = await Taro.showModal({
      title: '重置问诊',
      content: '将清空当前对话并开始新的问诊,确定继续?',
      confirmColor: '#165dff',
    });
    if (!res.confirm) return;
    try {
      // 已有会话则重置,否则新建
      if (sessionId) {
        const session = await resetSession(sessionId);
        setSessionId(session.session_id);
        setCurrentStage(session.stage);
        Taro.setStorageSync(STORAGE_KEYS.SESSION_ID, session.session_id);
      } else {
        await createNewSession();
      }
      setMessages([WELCOME_MESSAGE]);
      setInput('');
      Taro.showToast({ title: '已重置', icon: 'success' });
    } catch (err) {
      console.error('[Consult] 重置失败', err);
      Taro.showToast({ title: '重置失败', icon: 'none' });
    }
  };

  const sendMessage = async () => {
    const text = input.trim();
    if (!text || !sessionId || sending) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: text,
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput('');
    setSending(true);
    scrollToBottom();

    // 插入占位的助手消息(流式追加)
    const typingId = `bot-${Date.now()}`;
    setMessages((prev) => [
      ...prev,
      { id: typingId, role: 'assistant', content: '', streaming: true },
    ]);
    scrollToBottom();

    abortRef.current?.abort();
    const controller = streamChat({
      url: '/api/chat',
      body: { message: text, session_id: sessionId },
      onEvent: (ev) => {
        switch (ev.event) {
          case 'reply':
            // 增量追加回复内容
            setMessages((prev) =>
              prev.map((m) =>
                m.id === typingId
                  ? { ...m, content: m.content + ev.data, streaming: true }
                  : m
              )
            );
            break;
          case 'report':
            // 报告同样是分块流式:必须累加,不能直接覆盖
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
            // 单轮结束:用后端清洗后的 reply_clean 定稿(兜底剥离思维链/JSON块)
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
                      }
                    : m
                )
              );
            } catch {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === typingId ? { ...m, streaming: false } : m
                )
              );
            }
            setSending(false);
            break;
          case 'report_done':
            // report_done 的 data 是 {"stage":..,"is_complete":..} 元信息,
            // 不能拿来当正文,否则会把 JSON 覆盖到报告气泡上
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
            break;
          case 'error':
            setMessages((prev) =>
              prev.filter((m) => m.id !== typingId).concat({
                id: `err-${Date.now()}`,
                role: 'assistant',
                content: `⚠️ ${ev.data || '服务异常'}`,
              })
            );
            setSending(false);
            break;
        }
        scrollToBottom();
      },
      onError: (err) => {
        setMessages((prev) =>
          prev.filter((m) => m.id !== typingId).concat({
            id: `err-${Date.now()}`,
            role: 'assistant',
            content: `⚠️ 发送失败:${err instanceof Error ? err.message : '网络错误'}`,
          })
        );
        setSending(false);
        scrollToBottom();
      },
    });
    abortRef.current = controller;
  };

  // 滚动到底部:先清空再设值,强制触发 scroll-into-view
  const scrollToBottom = () => {
    setScrollAnchor('');
    setTimeout(() => setScrollAnchor('msg-bottom'), 50);
  };

  // 页面显示时加载会话(放在函数定义之后,避免 use-before-define)
  useDidShow(() => {
    loadSession();
  });

  const isEmpty = messages.length === 0;

  return (
    <View className={styles.container}>
      <View className={styles.stageBar}>
        <StageIndicator current={currentStage} />
      </View>
      <Button className={styles.resetBtn} onClick={handleReset}>
        重置会话
      </Button>
      <ScrollView
        className={styles.scrollArea}
        scrollY
        scrollIntoView={scrollAnchor}
        enhanced
        showScrollbar={false}
      >
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
            />
          ))
        )}
        <View id="msg-bottom" />
      </ScrollView>
      <View className={styles.inputBar}>
        <Textarea
          className={styles.input}
          value={input}
          onInput={(e) => setInput(e.detail.value)}
          placeholder="请输入您的症状或问题…"
          maxlength={500}
          autoHeight
          showConfirmBar={false}
          adjustPosition
        />
        <Button
          className={classnames(
            styles.sendBtn,
            (!input.trim() || sending) && styles.sendBtnDisabled
          )}
          disabled={!input.trim() || sending}
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
