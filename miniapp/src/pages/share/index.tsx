import React, { useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import Markdown from '@/utils/markdown';
import { getShareView } from '@/services/medical';
import styles from './index.module.scss';

interface ShareView {
  patient_age?: number;
  patient_gender?: string;
  report?: string;
  visit_date?: string;
  disclaimer?: string;
}

/**
 * 分享落地页 - 被「转发卡片 / 小程序码」打开
 * 通过 query.token 或 query.shareToken 读取公开脱敏报告(后端 /api/share/{token})
 */
function SharePage() {
  const [data, setData] = useState<ShareView | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const params = Taro.getCurrentInstance().router?.params;
  const key = params?.token || params?.shareToken || '';

  useDidShow(async () => {
    if (!key) {
      setError('分享参数缺失');
      setLoading(false);
      return;
    }
    try {
      const d = await getShareView(key);
      setData(d);
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  });

  if (loading) {
    return (
      <View className={styles.state}>
        <Text className={styles.stateText}>加载中…</Text>
      </View>
    );
  }

  if (error || !data) {
    return (
      <View className={styles.state}>
        <Text className={styles.stateText}>{error || '内容不存在或已失效'}</Text>
      </View>
    );
  }

  return (
    <View className={styles.container}>
      <View className={styles.header}>
        <Text className={styles.title}>医学问诊报告(分享)</Text>
        <Text className={styles.meta}>
          {[data.patient_gender, data.patient_age ? `${data.patient_age}岁` : '', data.visit_date]
            .filter(Boolean)
            .join(' · ')}
        </Text>
      </View>

      {data.report && (
        <View className={styles.report}>
          <Markdown source={data.report} />
        </View>
      )}

      <View className={styles.disclaimer}>
        <Text>{data.disclaimer || '本报告由 AI 医学问诊助手生成,仅供参考,不能替代医生面诊。'}</Text>
      </View>
    </View>
  );
}

export default SharePage;
