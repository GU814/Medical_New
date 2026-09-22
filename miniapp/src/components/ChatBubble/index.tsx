import React, { useState } from 'react';
import { View, Text, Image } from '@tarojs/components';
import classnames from 'classnames';
import Markdown from '@/utils/markdown';
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
}

export default function ChatBubble({ role, content, isReport, streaming, imageUrl, fromMultimodal, thinking }: ChatBubbleProps) {
  const isUser = role === 'user'
  // 思考过程默认在流式进行中展开,结束定稿后保持(用户可手动收起)
  const [showThink, setShowThink] = useState(!!streaming)
  const hasThink = !!thinking && thinking.trim().length > 0
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
