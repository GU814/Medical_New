import React, { useState } from 'react';
import { View, Text, Image } from '@tarojs/components';
import classnames from 'classnames';
import Markdown from '@/utils/markdown';
import { ReasoningStepsSafe } from '@/components/ReasoningSteps';
import type { ReactStep } from '@/types';
import styles from './index.module.scss';

interface ChatBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  isReport?: boolean;
  streaming?: boolean;
  imageUrl?: string;
  fromMultimodal?: 'voice' | 'image';
  // 推理模型的「思考过程」(思维链)原文
  thinking?: string;
  // ReAct 推理过程步骤时间线(实时流式累积 / 历史回放回填)
  steps?: ReactStep[];
  // 该轮推理过程缺失的原因(展示具体原因,不显示「暂无推理过程」)
  stepsMissingReason?: string;
}

export default function ChatBubble({
  role,
  content,
  isReport,
  streaming,
  imageUrl,
  fromMultimodal,
  thinking,
  steps,
  stepsMissingReason,
}: ChatBubbleProps) {
  const isUser = role === 'user'
  // 思考过程(思维链)默认展开、定稿后保持展开,仅由用户手动收起;
  // 初版传的是 !!streaming,导致回答一结束思考过程就被收起。
  const [showThink, setShowThink] = useState(true)
  const hasThink = !!thinking && thinking.trim().length > 0
  const hasSteps = !!steps && steps.length > 0
  return (
    <View className={classnames(styles.wrapper, isUser ? styles.userWrapper : styles.botWrapper)}>
      <View
        className={classnames(
          styles.bubble,
          isUser ? styles.userBubble : styles.botBubble,
          isReport && styles.reportBubble
        )}
      >
        {/* 用户上传图片:气泡顶部缩略图 + 识别文本 */}
        {isUser && imageUrl ? (
          <Image className={styles.bubbleImage} src={imageUrl} mode="widthFix" />
        ) : null}
        {fromMultimodal === 'image' && !imageUrl ? (
          <Text className={styles.multimodalTag}>🖼️ 图片识别</Text>
        ) : null}
        {fromMultimodal === 'voice' ? (
          <Text className={styles.multimodalTag}>🎤 语音输入</Text>
        ) : null}
        {/* 思考过程(思维链):可折叠,默认展开,仅 assistant 气泡展示 */}
        {!isUser && hasThink ? (
          <View className={styles.thinkingBlock}>
            <View className={styles.thinkingHeader} onClick={() => setShowThink((v) => !v)}>
              <Text className={styles.thinkingIcon}>💭</Text>
              <Text className={styles.thinkingTitle}>思考过程</Text>
              <Text className={styles.thinkingToggle}>{showThink ? '收起 ▲' : '展开 ▼'}</Text>
            </View>
            {showThink ? (
              <Text className={styles.thinkingContent}>{thinking}</Text>
            ) : null}
          </View>
        ) : null}
        {/* ReAct 推理过程(可折叠时间线):只要拿到步骤就默认展开,流式与回放一致。
            之前传 defaultOpen={!!streaming},回答一结束就自动收起只剩「展开 ▼」,
            用户主诉「看不到思考过程」—— 实际是折叠,不是没产生。用户可手动收起。 */}
        {!isUser && hasSteps ? (
          <ReasoningStepsSafe steps={steps} defaultOpen />
        ) : null}
        {/* 推理过程缺失时必须说明原因,不允许退化成「暂无推理过程」 */}
        {!isUser && stepsMissingReason && !hasSteps ? (
          <View className={styles.missingReason}>
            <Text className={styles.missingReasonIcon}>ℹ️</Text>
            <Text className={styles.missingReasonText}>{stepsMissingReason}</Text>
          </View>
        ) : null}
        {isReport ? (
          <View>
            <View className={styles.reportHeader}>
              <Text className={styles.reportTitle}>问诊报告</Text>
              {streaming && <Text className={styles.streamingTag}>生成中…</Text>}
            </View>
            <Markdown source={content} />
          </View>
        ) : (
          <Markdown source={content} />
        )}
      </View>
    </View>
  )
}
