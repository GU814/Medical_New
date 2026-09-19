import React, { useState } from 'react';
import { View, Text, Button } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { wxLogin, getProfile } from '@/services/auth';
import styles from './index.module.scss';

/**
 * 登录页 - 微信一键登录
 * 流程:wx.login -> /auth/wx-login 换 token -> 新用户引导补全 -> 跳首页
 */
function LoginPage() {
  const [loading, setLoading] = useState(false)

  const handleLogin = async () => {
    if (loading) return
    setLoading(true)
    try {
      const result = await wxLogin()
      console.info('[Login] 登录成功, is_new=', result.is_new)
      // 拉取用户资料
      await getProfile()
      // 新用户可引导补全(此处简化:直接进首页,补全在我的页)
      Taro.switchTab({ url: '/pages/index/index' })
    } catch (err) {
      console.error('[Login] 登录失败', err)
      Taro.showToast({
        title: err instanceof Error ? err.message : '登录失败,请重试',
        icon: 'none',
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <View className={styles.container}>
      <View className={styles.logo}>
        <Text className={styles.logoText}>医</Text>
      </View>
      <Text className={styles.title}>医学问诊智能体</Text>
      <Text className={styles.subtitle}>
        AI 智能问诊 · 隐私加密 · 历史档案{'\n'}为您提供专业医学咨询参考
      </Text>
      <Button
        className={styles.loginBtn}
        loading={loading}
        disabled={loading}
        onClick={handleLogin}
      >
        {loading ? '登录中…' : '微信一键登录'}
      </Button>
      <View className={styles.features}>
        <Text className={styles.featureItem}>🔒 数据加密</Text>
        <Text className={styles.featureItem}>📋 问诊档案</Text>
        <Text className={styles.featureItem}>📄 报告导出</Text>
      </View>
    </View>
  )
}

export default LoginPage
