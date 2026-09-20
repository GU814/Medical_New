import React, { useState } from 'react';
import { View, Text, Button } from '@tarojs/components';
import Taro, { useDidShow, useShareAppMessage, useShareTimeline } from '@tarojs/taro';
import Markdown from '@/utils/markdown';
import { getRecordDetail, exportRecordPdf, createShare } from '@/services/medical';
import { API_BASE } from '@/config';
import type { RecordDetail as RecordDetailType } from '@/types';
import styles from './index.module.scss';

/**
 * 就诊记录详情页
 * - 展示患者信息、问诊字段、诊断、完整报告
 * - 支持 PDF 导出与分享链接
 */
function RecordDetailPage() {
  const [record, setRecord] = useState<RecordDetailType | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [acting, setActing] = useState(false);

  const id = Number(Taro.getCurrentInstance().router?.params?.id);

  const loadDetail = async () => {
    if (!id) {
      setError('记录 ID 缺失');
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await getRecordDetail(id);
      setRecord(data);
    } catch (err) {
      console.error('[RecordDetail] 加载失败', err);
      setError(err instanceof Error ? err.message : '加载失败');
    } finally {
      setLoading(false);
    }
  };

  useDidShow(() => {
    loadDetail();
  });

  // 原生转发 / 分享朋友圈
  useShareAppMessage(() => ({
    title: record
      ? `${record.patient_name || '患者'} 的就诊记录 · 第 ${record.visit_count} 次就诊`
      : '就诊记录详情',
    path: `/pages/recordDetail/index?id=${id}`,
  }));

  useShareTimeline(() => ({
    title: '就诊记录详情 · 智康医疗 AI 助手',
    query: `id=${id}`,
  }));

  const handleExport = async () => {
    if (acting || !record) return;
    setActing(true);
    Taro.showLoading({ title: '生成 PDF…', mask: true });
    try {
      await exportRecordPdf(record.id);
      Taro.hideLoading();
      Taro.showToast({ title: '已打开文档', icon: 'success' });
    } catch (err) {
      Taro.hideLoading();
      console.error('[RecordDetail] 导出失败', err);
      Taro.showToast({
        title: err instanceof Error ? err.message : '导出失败',
        icon: 'none',
      });
    } finally {
      setActing(false);
    }
  };

  const handleShare = async () => {
    if (acting || !record) return;
    setActing(true);
    Taro.showLoading({ title: '生成分享链接…', mask: true });
    try {
      const { token, expires_at } = await createShare(record.id, 72);
      const link = `${API_BASE}/api/share/${token}`;
      await Taro.setClipboardText(link);
      Taro.hideLoading();
      const exp = expires_at.replace('T', ' ').slice(0, 16);
      await Taro.showModal({
        title: '分享链接已复制',
        content: `链接有效期至:${exp}\n\n可粘贴发送给医生查看。`,
        showCancel: false,
        confirmColor: '#165dff',
      });
    } catch (err) {
      Taro.hideLoading();
      console.error('[RecordDetail] 分享失败', err);
      Taro.showToast({
        title: err instanceof Error ? err.message : '分享失败',
        icon: 'none',
      });
    } finally {
      setActing(false);
    }
  };

  const formatDate = (iso: string) => (iso ? iso.replace('T', ' ').slice(0, 16) : '');

  if (loading) {
    return (
      <View className={styles.stateWrap}>
        <Text className={styles.stateIcon}>⏳</Text>
        <Text className={styles.stateText}>正在加载记录…</Text>
      </View>
    );
  }

  if (error || !record) {
    return (
      <View className={styles.stateWrap}>
        <Text className={styles.stateIcon}>📄</Text>
        <Text className={styles.stateText}>{error || '记录不存在'}</Text>
      </View>
    );
  }

  // 病史字段配置
  const fields: { label: string; value?: string }[] = [
    { label: '主诉', value: record.chief_complaint },
    { label: '现病史', value: record.present_illness },
    { label: '既往史', value: record.past_history },
    { label: '系统回顾', value: record.system_review },
    { label: '个人史', value: record.personal_history },
    { label: '家族史', value: record.family_history },
  ];

  return (
    <View className={styles.container}>
      {/* 头部 */}
      <View className={styles.header}>
        <Text className={styles.date}>{formatDate(record.visit_date)}</Text>
        <Text className={styles.subInfo}>第 {record.visit_count} 次就诊</Text>
      </View>

      {/* 患者信息 */}
      <View className={styles.patient}>
        <View className={styles.patientHeader}>
          <View className={styles.patientAvatar}>
            <Text>{record.patient_name?.[0] || '患'}</Text>
          </View>
          <View>
            <Text className={styles.patientName}>{record.patient_name}</Text>
            <Text className={styles.patientMeta}>
              {record.patient_gender || '未知性别'}
              {record.patient_age ? ` · ${record.patient_age} 岁` : ''}
            </Text>
          </View>
        </View>
      </View>

      {/* 病史字段 */}
      {fields.map(
        (f) =>
          f.value && (
            <View key={f.label} className={styles.section}>
              <Text className={styles.sectionTitle}>{f.label}</Text>
              <Text className={styles.sectionText}>{f.value}</Text>
            </View>
          )
      )}

      {/* 诊断 */}
      {record.diagnosis && (
        <View className={styles.section}>
          <Text className={styles.sectionTitle}>诊断意见</Text>
          <View className={styles.diagnosis}>{record.diagnosis}</View>
        </View>
      )}

      {/* 完整报告 */}
      {record.full_report && (
        <View className={styles.report}>
          <Text className={styles.sectionTitle}>完整问诊报告</Text>
          <View className={styles.reportBody}>
            <Markdown source={record.full_report} />
          </View>
        </View>
      )}

      {/* 底部操作栏 */}
      <View className={styles.actionBar}>
        <Button
          className={`${styles.actionBtn} ${styles.btnSecondary}`}
          onClick={handleShare}
          disabled={acting}
        >
          生成分享链接
        </Button>
        <Button
          className={`${styles.actionBtn} ${styles.btnPrimary}`}
          onClick={handleExport}
          disabled={acting}
        >
          导出 PDF
        </Button>
      </View>
    </View>
  );
}

export default RecordDetailPage;
