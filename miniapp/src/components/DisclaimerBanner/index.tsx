import React from 'react';
import { View, Text } from '@tarojs/components';
import styles from './index.module.scss';

interface DisclaimerBannerProps {
  text?: string;
}

export default function DisclaimerBanner({
  text = '本系统提供的问诊建议仅供参考,不能替代医生面诊。如有不适请及时就医。',
}: DisclaimerBannerProps) {
  return (
    <View className={styles.container}>
      <Text className={styles.icon}>⚠️</Text>
      <Text className={styles.text}>{text}</Text>
    </View>
  )
}
