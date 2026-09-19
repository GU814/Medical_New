import React, { useState } from 'react';
import { View, Text } from '@tarojs/components';
import Taro, { useDidShow, usePullDownRefresh, useReachBottom } from '@tarojs/taro';
import { listRecords } from '@/services/medical';
import { isLoggedIn } from '@/services/auth';
import type { RecordListItem } from '@/types';
import styles from './index.module.scss';

const PAGE_SIZE = 10;

/**
 * 就诊记录列表页
 * - 下拉刷新 + 上拉加载更多
 * - 点击进入详情
 */
function RecordsPage() {
  const [list, setList] = useState<RecordListItem[]>([]);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [initialized, setInitialized] = useState(false);

  const loadList = async (pageNum: number, reset = false) => {
    if (loading) return;
    setLoading(true);
    try {
      const res = await listRecords(pageNum, PAGE_SIZE);
      setList((prev) => (reset ? res.items : [...prev, ...res.items]));
      setTotal(res.total);
      setPage(pageNum);
    } catch (err) {
      console.error('[Records] 加载失败', err);
      if (reset) setList([]);
    } finally {
      setLoading(false);
      setInitialized(true);
    }
  };

  useDidShow(() => {
    if (!isLoggedIn()) {
      Taro.reLaunch({ url: '/pages/login/index' });
      return;
    }
    loadList(1, true);
  });

  usePullDownRefresh(() => {
    loadList(1, true).finally(() => Taro.stopPullDownRefresh());
  });

  useReachBottom(() => {
    if (list.length < total && !loading) {
      loadList(page + 1);
    }
  });

  const goDetail = (id: number) => {
    Taro.navigateTo({ url: `/pages/recordDetail/index?id=${id}` });
  };

  const formatDate = (iso: string) => {
    if (!iso) return '';
    return iso.replace('T', ' ').slice(0, 16);
  };

  const hasMore = list.length < total;

  return (
    <View className={styles.container}>
      {initialized && list.length === 0 ? (
        <View className={styles.empty}>
          <Text className={styles.emptyIcon}>📋</Text>
          <Text className={styles.emptyTitle}>暂无就诊记录</Text>
          <Text className={styles.emptyDesc}>
            完成首次问诊后,记录将显示在此处
          </Text>
        </View>
      ) : (
        <View className={styles.list}>
          {list.map((item) => (
            <View
              key={item.id}
              className={styles.card}
              onClick={() => goDetail(item.id)}
            >
              <View className={styles.cardHeader}>
                <Text className={styles.date}>{formatDate(item.visit_date)}</Text>
                <Text className={styles.badge}>第 {item.visit_count} 次</Text>
              </View>
              <Text className={styles.preview}>
                {item.chief_complaint_preview || '主诉信息待补充'}
              </Text>
              <View className={styles.cardFooter}>
                <Text className={styles.visitCount}>查看详情</Text>
                <Text className={styles.arrow}>›</Text>
              </View>
            </View>
          ))}
        </View>
      )}

      {list.length > 0 && (
        <View className={styles.footer}>
          {loading ? '加载中…' : hasMore ? '上拉加载更多' : '— 已全部加载 —'}
        </View>
      )}
    </View>
  );
}

export default RecordsPage;
