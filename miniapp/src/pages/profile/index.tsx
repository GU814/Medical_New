import React, { useState } from 'react';
import { View, Text, Input, Button } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import { getProfile, updateProfile, logout, isLoggedIn } from '@/services/auth';
import { requestConsultDoneSubscribe } from '@/services/subscribe';
import { STORAGE_KEYS, CONTACT_SESSION_FROM } from '@/config';
import type { UserProfile } from '@/types';
import styles from './index.module.scss';

/**
 * 个人中心页
 * - 展示账户资料与认证状态
 * - 支持昵称 / 性别 / 年龄 编辑(性别、年龄来自注册时填写,此处可查看并修改)
 * - 提供隐私入口与登出
 *
 * 缺陷修复:此前仅展示与编辑「昵称」,登录时填写的性别/年龄在个人页完全不可见,
 * 导致用户以为「没数据、要重新填」。现补齐性别/年龄的展示与编辑,且直接复用
 * 后端已返回并持久化的 gender/age 字段(见 auth_service.get_profile / update_profile)。
 */
function ProfilePage() {
  const [user, setUser] = useState<UserProfile | null>(null);
  const [nickEdit, setNickEdit] = useState('');
  const [genderEdit, setGenderEdit] = useState('');
  const [ageEdit, setAgeEdit] = useState('');
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
      if (cached) syncEditFields(cached);
      const profile = await getProfile();
      // 后端异常时可能返回空对象,按无数据处理并提示,避免页面空白
      if (!profile || typeof profile !== 'object' || !profile.user_id) {
        setLoadError('未获取到用户资料');
        return;
      }
      setUser(profile);
      syncEditFields(profile);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '获取资料失败';
      console.error('[Profile] 获取资料失败', err);
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  };

  // 把后端资料同步进可编辑表单(进入编辑态或初次加载时都调用,避免读到旧值)
  const syncEditFields = (p: UserProfile) => {
    setNickEdit(p.nickname || '');
    setGenderEdit(p.gender || '');
    setAgeEdit(p.age != null ? String(p.age) : '');
  };

  useDidShow(() => {
    loadUser();
  });

  const startEdit = () => {
    if (user) syncEditFields(user);
    setEditing(true);
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      // 仅携带被允许编辑的字段;任一为空则不改动该项,避免误清空。
      const payload: Partial<UserProfile> = {};
      const name = nickEdit.trim();
      if (name) payload.nickname = name;
      if (genderEdit) payload.gender = genderEdit;
      if (ageEdit.trim()) {
        const a = parseInt(ageEdit, 10);
        if (!Number.isNaN(a) && a > 0 && a < 150) payload.age = a;
      }
      await updateProfile(payload);
      const updated: UserProfile = { ...(user as UserProfile), ...payload };
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
  const goLocation = () => Taro.navigateTo({ url: '/pages/location/index' });
  const handleSubscribe = async () => {
    Taro.showLoading({ title: '请求授权…', mask: true });
    await requestConsultDoneSubscribe();
    Taro.hideLoading();
    Taro.showToast({ title: '可在弹窗中允许复诊提醒', icon: 'none' });
  };

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
            {[user?.gender, user?.age != null ? `${user.age}岁` : '']
              .filter(Boolean)
              .join(' · ') || '未填写性别/年龄'}
            {'  ·  '}ID:{user?.openid_masked || '-'}
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
        <View className={styles.cardHead}>
          <Text className={styles.cardTitle}>账户资料</Text>
          {!editing && user && (
            <Text className={styles.editLink} onClick={startEdit}>
              编辑
            </Text>
          )}
        </View>

        {/* 昵称 */}
        <View className={styles.row}>
          <Text className={styles.rowLabel}>昵称</Text>
          {editing ? (
            <Input
              className={styles.nickInput}
              value={nickEdit}
              onInput={(e) => setNickEdit(e.detail.value)}
              maxlength={20}
              placeholder="请输入昵称"
              focus={false}
            />
          ) : (
            <Text className={styles.rowValue}>{user?.nickname || '点击编辑'} ›</Text>
          )}
        </View>

        {/* 性别 */}
        <View className={styles.row}>
          <Text className={styles.rowLabel}>性别</Text>
          {editing ? (
            <View className={styles.genderOpts}>
              {['男', '女', '其他'].map((g) => (
                <Text
                  key={g}
                  className={
                    genderEdit === g ? styles.genderOn : styles.genderOff
                  }
                  onClick={() => setGenderEdit(g)}
                >
                  {g}
                </Text>
              ))}
            </View>
          ) : (
            <Text className={styles.rowValue}>{user?.gender || '点击编辑'} ›</Text>
          )}
        </View>

        {/* 年龄 */}
        <View className={styles.row}>
          <Text className={styles.rowLabel}>年龄</Text>
          {editing ? (
            <Input
              className={styles.nickInput}
              type="number"
              value={ageEdit}
              onInput={(e) => setAgeEdit(e.detail.value)}
              maxlength={3}
              placeholder="请输入年龄"
            />
          ) : (
            <Text className={styles.rowValue}>
              {user?.age != null ? `${user.age} 岁` : '点击编辑'} ›
            </Text>
          )}
        </View>

        {/* 只读身份字段 */}
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
            {saving ? '保存中…' : '保存'}
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

      <View className={styles.menuItem} onClick={goLocation}>
        <View className={styles.menuText}>
          <Text className={styles.menuIcon}>📍</Text>
          <Text className={styles.menuLabel}>我的地点</Text>
        </View>
        <Text className={styles.menuArrow}>›</Text>
      </View>

      <View className={styles.menuItem} onClick={handleSubscribe}>
        <View className={styles.menuText}>
          <Text className={styles.menuIcon}>🔔</Text>
          <Text className={styles.menuLabel}>订阅复诊提醒</Text>
        </View>
        <Text className={styles.menuArrow}>›</Text>
      </View>

      {/* 联系客服:微信原生入口,点击唤起客服会话(无需后端) */}
      <Button className={styles.contactBtn} open-type="contact" session-from={CONTACT_SESSION_FROM}>
        <View className={styles.menuText}>
          <Text className={styles.menuIcon}>💬</Text>
          <Text className={styles.menuLabel}>联系客服</Text>
        </View>
        <Text className={styles.menuArrow}>›</Text>
      </Button>

      {/* 登出 */}
      <Button className={styles.logoutBtn} onClick={handleLogout}>
        退出登录
      </Button>
    </View>
  );
}

export default ProfilePage;
