import React from 'react';
import { View, Text } from '@tarojs/components';
import classnames from 'classnames';
import { STAGES } from '@/config';
import styles from './index.module.scss';

interface StageIndicatorProps {
  current: number;
}

export default function StageIndicator({ current }: StageIndicatorProps) {
  return (
    <View className={styles.container}>
      {STAGES.map((s, idx) => {
        const done = s.value < current
        const active = s.value === current
        return (
          <View key={s.value} className={styles.stepWrap}>
            <View
              className={classnames(
                styles.dot,
                done && styles.dotDone,
                active && styles.dotActive
              )}
            >
              <Text className={styles.dotText}>{done ? '✓' : idx + 1}</Text>
            </View>
            <Text
              className={classnames(
                styles.label,
                (done || active) && styles.labelActive
              )}
            >
              {s.label}
            </Text>
            {idx < STAGES.length - 1 && (
              <View className={classnames(styles.line, done && styles.lineDone)} />
            )}
          </View>
        )
      })}
    </View>
  )
}
