import React, { useEffect, useState } from 'react';
import { View, Text, Button } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { isLoggedIn, getProfile } from '@/services/auth';
import { getLatestSession } from '@/services/medical';
import DisclaimerBanner from '@/components/DisclaimerBanner';
import { STORAGE_KEYS } from '@/config';
import type { UserProfile } from '@/types';
import styles from './index.module.scss';

interface GridItem {
  icon: string
  title: string
  desc: string
  bg: string
  action: () => void
}

function HomePage() {
  const [user, setUser] = useState<UserProfile | null>(null)
  const [hasUnfinished, setHasUnfinished] = useState(false)

  const loadUser = async () => {
    if (!isLoggedIn()) {
      Taro.reLaunch({ url: '/pages/login/index' })
      return
    }
    try {
      const cached = Taro.getStorageSync(STORAGE_KEYS.USER)
      if (cached) setUser(cached)
      const profile = await getProfile()
      setUser(profile)
    } catch (err) {
      console.error('[Home] 获取用户信息失败', err)
    }
  }

  const checkUnfinished = async () => {
    try {
      const latest = await getLatestSession()
      setHasUnfinished(!latest.is_complete)
    } catch (err) {
      // 404 表示无未完成会话,正常情况
      setHasUnfinished(false)
    }
  }

  useEffect(() => {
    loadUser()
  }, [])

  useDidShow(() => {
    if (isLoggedIn()) {
      loadUser()
      checkUnfinished()
    }
  })

  const goConsult = () => Taro.switchTab({ url: '/pages/consult/index' })
  const goRecords = () => Taro.switchTab({ url: '/pages/records/index' })
  const goProfile = () => Taro.switchTab({ url: '/pages/profile/index' })
  const goPrivacy = () => Taro.navigateTo({ url: '/pages/privacy/index' })
  const goFamily = () => Taro.navigateTo({ url: '/pages/family/index' })

  const gridItems: GridItem[] = [
    {
      icon: '📋',
      title: '历史记录',
      desc: '查看就诊档案',
      bg: 'rgba(54, 207, 201, 0.12)',
      action: goRecords,
    },
    {
      icon: '👤',
      title: '个人中心',
      desc: '账户与资料',
      bg: 'rgba(22, 93, 255, 0.1)',
      action: goProfile,
    },
    {
      icon: '🔒',
      title: '隐私设置',
      desc: '数据安全',
      bg: 'rgba(255, 125, 0, 0.1)',
      action: goPrivacy,
    },
    {
      icon: '👨‍👩‍👧',
      title: '家庭成员',
      desc: '多人管理与紧急守护',
      bg: 'rgba(0, 180, 42, 0.1)',
      action: goFamily,
    },
  ]

  const initial = user?.nickname?.[0] || '用'

  return (
    <View className={styles.container}>
      <View className={styles.header}>
        <View className={styles.avatar}>
          <Text className={styles.avatarText}>{initial}</Text>
        </View>
        <View className={styles.headerInfo}>
          <Text className={styles.greeting}>您好,</Text>
          <Text className={styles.userName}>{user?.nickname || '欢迎使用'}</Text>
        </View>
        <Text className={styles.brand}>医学问诊</Text>
      </View>

      <View className={styles.heroCard}>
        <Text className={styles.heroTitle}>开始智能问诊</Text>
        <Text className={styles.heroDesc}>
          {hasUnfinished ? '您有未完成的问诊,继续上次对话' : 'AI 医生将引导您完成 5 阶段问诊并生成报告'}
        </Text>
        <Button className={styles.heroBtn} onClick={goConsult}>
          {hasUnfinished ? '继续问诊 →' : '开始咨询 →'}
        </Button>
      </View>

      <Text className={styles.gridTitle}>常用功能</Text>
      <View className={styles.grid}>
        {gridItems.map((item) => (
          <View key={item.title} className={styles.gridItem}>
            <View className={styles.card} onClick={item.action}>
              <View className={styles.cardIcon} style={{ background: item.bg }}>
                <Text>{item.icon}</Text>
              </View>
              <Text className={styles.cardTitle}>{item.title}</Text>
              <Text className={styles.cardDesc}>{item.desc}</Text>
            </View>
          </View>
        ))}
      </View>

      <View className={styles.phaseSection}>
        <Text className={styles.phaseTitle}>问诊阶段说明</Text>
        <View className={styles.phaseItem}>
          <View className={styles.phaseNum}>1</View>
          <View className={styles.phaseInfo}>
            <Text className={styles.phaseName}>基础底座</Text>
            <Text className={styles.phaseText}>用户认证 · 会话持久化 · 数据加密 · 输入安全</Text>
          </View>
        </View>
        <View className={styles.phaseItem}>
          <View className={styles.phaseNum}>2</View>
          <View className={styles.phaseInfo}>
            <Text className={styles.phaseName}>体验闭环</Text>
            <Text className={styles.phaseText}>历史记录 · 报告导出 · 多成员 · 加载优化</Text>
          </View>
        </View>
        <View className={styles.phaseItem}>
          <View className={styles.phaseNum}>3</View>
          <View className={styles.phaseInfo}>
            <Text className={styles.phaseName}>运营增值</Text>
            <Text className={styles.phaseText}>知识库后台 · 监控统计 · 反馈机制 · 无障碍</Text>
          </View>
        </View>
      </View>

      <DisclaimerBanner />
    </View>
  )
}

export default HomePage
