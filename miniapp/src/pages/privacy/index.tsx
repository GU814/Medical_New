import React, { useState } from 'react';
import { View, Text, Switch, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { logout } from '@/services/auth';
import styles from './index.module.scss';

const PRIVACY_PREFS_KEY = 'mb_privacy_prefs';

interface PrivacyPrefs {
  report_share: boolean; // 允许生成分享链接
  local_cache: boolean; // 允许本地缓存问诊历史
  analytics: boolean; // 匿名使用统计
}

const DEFAULT_PREFS: PrivacyPrefs = {
  report_share: true,
  local_cache: true,
  analytics: false,
};

/**
 * 隐私与数据安全页
 * - 展示端到端加密机制说明
 * - 提供数据使用偏好开关(本地持久化)
 * - 提供数据清除入口
 */
function PrivacyPage() {
  const [prefs, setPrefs] = useState<PrivacyPrefs>(() => {
    const cached = Taro.getStorageSync(PRIVACY_PREFS_KEY) as PrivacyPrefs;
    return { ...DEFAULT_PREFS, ...cached };
  });

  const updatePref = (key: keyof PrivacyPrefs, value: boolean) => {
    const next = { ...prefs, [key]: value };
    setPrefs(next);
    Taro.setStorageSync(PRIVACY_PREFS_KEY, next);
    Taro.showToast({ title: '已更新', icon: 'none', duration: 800 });
  };

  const handleClearData = async () => {
    const res = await Taro.showModal({
      title: '清除本地数据',
      content:
        '将清除本设备上的问诊缓存与登录信息,并退出登录。云端加密记录不受影响,是否继续?',
      confirmColor: '#f53f3f',
      confirmText: '清除并退出',
    });
    if (!res.confirm) return;
    Taro.removeStorageSync(PRIVACY_PREFS_KEY);
    Taro.removeStorageSync('mb_session_id');
    logout();
  };

  const techPoints = [
    '所有患者敏感字段(病史、诊断、报告)采用 AES-256-GCM 端到端加密存储',
    '三层密钥体系:主密钥 → KEK → DEK,数据密钥按用户隔离',
    '问诊会话与历史记录按用户唯一标识隔离,杜绝同名混淆',
    '分享链接采用一次性 Token,默认 72 小时过期,可随时撤销',
    '所有数据访问行为写入审计日志,可供合规追溯',
  ];

  return (
    <View className={styles.container}>
      {/* 加密概览 */}
      <View className={styles.hero}>
        <View className={styles.heroIcon}>
          <Text>🔐</Text>
        </View>
        <View className={styles.heroText}>
          <Text className={styles.heroTitle}>数据已加密保护</Text>
          <Text className={styles.heroDesc}>AES-256-GCM 端到端加密 · 用户级密钥隔离</Text>
        </View>
      </View>

      {/* 加密技术说明 */}
      <View className={styles.section}>
        <Text className={styles.sectionTitle}>加密与隔离机制</Text>
        <Text className={styles.sectionDesc}>
          本系统遵循医疗数据隐私保护要求,对患者数据进行全链路加密与权限控制。
        </Text>
        <View className={styles.techList}>
          {techPoints.map((p, i) => (
            <View key={i} className={styles.techItem}>
              <Text className={styles.techDot}>✓</Text>
              <Text className={styles.techText}>{p}</Text>
            </View>
          ))}
        </View>
      </View>

      {/* 数据使用偏好 */}
      <View className={styles.section}>
        <Text className={styles.sectionTitle}>数据使用偏好</Text>
        <View className={styles.switchRow}>
          <View className={styles.switchLabel}>
            <Text className={styles.switchTitle}>允许生成报告分享链接</Text>
            <Text className={styles.switchHint}>关闭后将无法向医生分享问诊报告</Text>
          </View>
          <Switch
            checked={prefs.report_share}
            color="#165dff"
            onChange={(e) => updatePref('report_share', e.detail.value)}
          />
        </View>
        <View className={styles.switchRow}>
          <View className={styles.switchLabel}>
            <Text className={styles.switchTitle}>本地缓存问诊历史</Text>
            <Text className={styles.switchHint}>关闭后每次进入需重新加载,流量略增</Text>
          </View>
          <Switch
            checked={prefs.local_cache}
            color="#165dff"
            onChange={(e) => updatePref('local_cache', e.detail.value)}
          />
        </View>
        <View className={styles.switchRow}>
          <View className={styles.switchLabel}>
            <Text className={styles.switchTitle}>匿名使用统计</Text>
            <Text className={styles.switchHint}>用于改进问诊体验,不含任何医疗信息</Text>
          </View>
          <Switch
            checked={prefs.analytics}
            color="#165dff"
            onChange={(e) => updatePref('analytics', e.detail.value)}
          />
        </View>
      </View>

      {/* 数据权利 */}
      <View className={styles.section}>
        <Text className={styles.sectionTitle}>您的数据权利</Text>
        <View className={styles.linkRow}>
          <Text className={styles.linkText}>查看隐私政策全文</Text>
          <Text className={styles.linkArrow}>›</Text>
        </View>
        <View className={styles.linkRow}>
          <Text className={styles.linkText}>查看数据访问审计记录</Text>
          <Text className={styles.linkArrow}>›</Text>
        </View>
        <Button className={styles.dangerBtn} onClick={handleClearData}>
          清除本机数据并退出
        </Button>
      </View>

      <Text className={styles.footer}>
        本应用提供的建议仅供参考,不构成医疗诊断{'\n'}
        如有紧急情况请立即就医
      </Text>
    </View>
  );
}

export default PrivacyPage;
