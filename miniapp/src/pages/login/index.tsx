import React, { useState } from 'react';
import { View, Text, Button, Input } from '@tarojs/components';
import Taro from '@tarojs/taro';
import { wxLogin, getProfile, updateProfile } from '@/services/auth';
import styles from './index.module.scss';

const GENDER_OPTIONS = ['男', '女'];

/**
 * 登录页 - 微信一键登录 + 个人资料录入
 *
 * 流程:wx.login -> /auth/wx-login 换 token -> 资料未录入则先填性别/年龄 -> 跳首页
 * 说明:性别/年龄存入用户资料(profile_gender/profile_age),新会话创建时由后端预填,
 *      问诊中模型不再重复询问这些信息。
 */
function LoginPage() {
  const [loading, setLoading] = useState(false)
  const [needProfile, setNeedProfile] = useState(false)
  const [gender, setGender] = useState('')
  const [age, setAge] = useState('')
  const [saving, setSaving] = useState(false)

  const goHome = () => {
    Taro.switchTab({ url: '/pages/index/index' })
  }

  const handleLogin = async () => {
    if (loading) return
    setLoading(true)
    try {
      await wxLogin()
      console.info('[Login] 登录成功')
      // 拉取用户资料:已录过性别/年龄则直接进首页,否则先引导补全
      const profile = await getProfile()
      if (profile?.gender || profile?.age) {
        goHome()
      } else {
        setNeedProfile(true)
      }
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

  const handleSaveProfile = async () => {
    if (saving) return
    // 年龄基本校验:1-150
    const ageNum = Number(age)
    if (age && (!Number.isFinite(ageNum) || ageNum <= 0 || ageNum > 150)) {
      Taro.showToast({ title: '请输入 1-150 之间的年龄', icon: 'none' })
      return
    }
    setSaving(true)
    try {
      await updateProfile({
        ...(gender ? { gender } : {}),
        ...(age ? { age: ageNum } : {}),
      })
      await getProfile()
      Taro.showToast({ title: '资料已保存', icon: 'success' })
      goHome()
    } catch (err) {
      console.error('[Login] 保存资料失败', err)
      Taro.showToast({
        title: err instanceof Error ? err.message : '保存失败,请重试',
        icon: 'none',
      })
    } finally {
      setSaving(false)
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

      {needProfile ? (
        <View className={styles.profileForm}>
          <Text className={styles.formTitle}>完善个人资料</Text>
          <Text className={styles.formHint}>问诊时将自动带入,无需反复填写</Text>

          <View className={styles.fieldRow}>
            <Text className={styles.fieldLabel}>性别</Text>
            <View className={styles.genderRow}>
              {GENDER_OPTIONS.map((item) => (
                <Text
                  key={item}
                  className={`${styles.genderTag} ${gender === item ? styles.genderTagActive : ''}`}
                  onClick={() => setGender(gender === item ? '' : item)}
                >
                  {item}
                </Text>
              ))}
            </View>
          </View>

          <View className={styles.fieldRow}>
            <Text className={styles.fieldLabel}>年龄</Text>
            <Input
              className={styles.ageInput}
              type='number'
              value={age}
              placeholder='请输入年龄'
              placeholderClass={styles.inputPlaceholder}
              maxlength={3}
              onInput={(e) => setAge(e.detail.value)}
            />
          </View>

          <Button
            className={styles.saveBtn}
            loading={saving}
            disabled={saving || (!gender && !age)}
            onClick={handleSaveProfile}
          >
            {saving ? '保存中…' : '保存并进入'}
          </Button>
          <Text className={styles.skipText} onClick={goHome}>稍后再填</Text>
        </View>
      ) : (
        <Button
          className={styles.loginBtn}
          loading={loading}
          disabled={loading}
          onClick={handleLogin}
        >
          {loading ? '登录中…' : '微信一键登录'}
        </Button>
      )}

      <View className={styles.features}>
        <Text className={styles.featureItem}>🔒 数据加密</Text>
        <Text className={styles.featureItem}>📋 问诊档案</Text>
        <Text className={styles.featureItem}>📄 报告导出</Text>
      </View>
    </View>
  )
}

export default LoginPage
