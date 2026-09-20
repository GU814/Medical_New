import React from 'react';
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
}

export default function ChatBubble({ role, content, isReport, streaming, imageUrl, fromMultimodal }: ChatBubbleProps) {
  const isUser = role === 'user'
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
