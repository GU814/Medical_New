import React from 'react';
import { View, Text } from '@tarojs/components';
import classnames from 'classnames';
import Markdown from '@/utils/markdown';
import styles from './index.module.scss';

interface ChatBubbleProps {
  role: 'user' | 'assistant';
  content: string;
  isReport?: boolean;
  streaming?: boolean;
}

export default function ChatBubble({ role, content, isReport, streaming }: ChatBubbleProps) {
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
