import React, { useState } from 'react';
import { View, Text, Input, Button } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { getProfile, updateProfile, logout, isLoggedIn } from '@/services/auth';
import { STORAGE_KEYS } from '@/config';
import type { UserProfile } from '@/types';
import styles from './index.module.scss';

/**
 * 个人中心页
 * - 展示账户资料与认证状态
 * - 支持昵称编辑
 * - 提供隐私入口与登出
 */
function ProfilePage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [nickEdit, setNickEdit] = useState('');
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const loadUser = async () => {
    if (!isLoggedIn()) {
      Taro.reLaunch({ url: '/pages/login/index' });
      return;
    }
    setLoading(true);
    setLoadError('');
    try {
      const cached = Taro.getStorageSync(STORAGE_KEYS.USER) as UserProfile;
      if (cached) setUser(cached);
      const profile = await getProfile();
      // 后端异常时可能返回空对象,按无数据处理并提示,避免页面空白
      if (!profile || typeof profile !== 'object' || !profile.user_id) {
        setLoadError('未获取到用户资料');
        return;
      }
      setUser(profile);
      setNickEdit(profile.nickname || '');
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取资料失败';
      console.error('[Profile] 获取资料失败', err);
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  };

  useDidShow(() => {
    loadUser();
  });

  const handleSave = async () => {
    const name = nickEdit.trim();
    if (!name) {
      Taro.showToast({ title: '昵称不能为空', icon: 'none' });
      return;
    }
    if (name === user?.nickname) {
      setEditing(false);
      return;
    }
    setSaving(true);
    try {
      await updateProfile({ nickname: name });
      const updated = { ...(user as UserProfile), nickname: name };
      setUser(updated);
      Taro.setStorageSync(STORAGE_KEYS.USER, updated);
      setEditing(false);
      Taro.showToast({ title: '已保存', icon: 'success' });
    } catch (err) {
      console.error('[Profile] 保存失败', err);
      Taro.showToast({
        title: err instanceof Error ? err.message : '保存失败',
        icon: 'none',
      });
    } finally {
      setSaving(false);
    }
  };

  const handleLogout = async () => {
    const res = await Taro.showModal({
      title: '退出登录',
      content: '退出后将清除本地登录信息,需重新登录',
      confirmColor: '#f53f3f',
    });
    if (res.confirm) {
      logout();
    }
  };

  const goPrivacy = () => Taro.navigateTo({ url: '/pages/privacy/index' });
  const goRecords = () => Taro.switchTab({ url: '/pages/records/index' });

  const formatDate = (iso?: string) =>
    iso ? iso.replace('T', ' ').slice(0, 10) : '';
  const initial = user?.nickname?.[0] || '用';

  return (
    <View className={styles.container}>
      {/* 加载中 / 加载失败提示,避免页面空白无反馈 */}
      {!user && (loading || !!loadError) && (
        <View className={styles.card}>
          <Text className={styles.cardTitle}>
            {loading ? '资料加载中…' : '资料加载失败'}
          </Text>
          {!loading && (
            <>
              <Text className={styles.userMeta}>
                {loadError || '请检查网络或后端服务是否已启动'}
              </Text>
              <Button className={styles.saveBtn} onClick={loadUser}>
                重试
              </Button>
            </>
          )}
        </View>
      )}

      {/* 用户卡片 */}
      <View className={styles.userCard}>
        <View className={styles.avatar}>
          <Text>{initial}</Text>
        </View>
        <View className={styles.userInfo}>
          <Text className={styles.userName}>{user?.nickname || '未设置昵称'}</Text>
          <Text className={styles.userMeta}>
            ID:{user?.openid_masked || '-'} · 注册于 {formatDate(user?.created_at)}
          </Text>
          <View className={styles.authRow}>
            <Text className={styles.authTag}>✓ 已认证</Text>
            {user?.phone_masked && (
              <Text className={styles.userMeta}>{user.phone_masked}</Text>
            )}
          </View>
        </View>
      </View>

      {/* 资料编辑 */}
      <View className={styles.card}>
        <Text className={styles.cardTitle}>账户资料</Text>
        <View className={styles.row}>
          <Text className={styles.rowLabel}>昵称</Text>
          {editing ? (
            <Input
              className={styles.nickInput}
              value={nickEdit}
              onInput={(e) => setNickEdit(e.detail.value)}
              maxlength={20}
              placeholder="请输入昵称"
              focus
            />
          ) : (
            <Text
              className={styles.rowValue}
              onClick={() => {
                setNickEdit(user?.nickname || '');
                setEditing(true);
              }}
            >
              {user?.nickname || '点击设置'} ›
            </Text>
          )}
        </View>
        <View className={styles.row}>
          <Text className={styles.rowLabel}>用户 ID</Text>
          <Text className={styles.rowValue}>{user?.user_id ?? '-'}</Text>
        </View>
        <View className={styles.row}>
          <Text className={styles.rowLabel}>微信标识</Text>
          <Text className={styles.rowValue}>{user?.openid_masked || '未授权'}</Text>
        </View>
        {editing && (
          <Button
            className={styles.saveBtn}
            loading={saving}
            disabled={saving}
            onClick={handleSave}
          >
            {saving ? '保存中…' : '保存昵称'}
          </Button>
        )}
      </View>

      {/* 功能入口 */}
      <View className={styles.menuItem} onClick={goRecords}>
        <View className={styles.menuText}>
          <Text className={styles.menuIcon}>📋</Text>
          <Text className={styles.menuLabel}>就诊记录</Text>
        </View>
        <Text className={styles.menuArrow}>›</Text>
      </View>

      <View className={styles.menuItem} onClick={goPrivacy}>
        <View className={styles.menuText}>
          <Text className={styles.menuIcon}>🔒</Text>
          <Text className={styles.menuLabel}>隐私与数据安全</Text>
        </View>
        <Text className={styles.menuArrow}>›</Text>
      </View>

      {/* 登出 */}
      <Button className={styles.logoutBtn} onClick={handleLogout}>
        退出登录
      </Button>
    </View>
  );
}

export default ProfilePage;
