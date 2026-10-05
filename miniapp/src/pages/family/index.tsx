import React, { useState } from 'react';
import { View, Text, Input, Button, Switch, Image } from '@tarojs/components';
import Taro, { useDidShow, getCurrentInstance } from '@tarojs/taro';
import { isLoggedIn } from '@/services/auth';
import {
  listFamily,
  addFamily,
  updateFamily,
  deleteFamily,
  acceptFamily,
} from '@/services/family';
import { generateWxacode } from '@/services/wxacode';
import type { FamilyMember } from '@/types';
import styles from './index.module.scss';

/**
 * 家庭成员页
 * - 主用户:添加成员(生成待绑定邀请) / 列表管理 / 开关配置 / 删除 / 生成邀请二维码
 * - 家庭成员:扫描邀请二维码或打开带 token 的链接 -> 本页自动识别 token -> 一键接受绑定
 * - 紧急推送:问诊中识别到紧急症状时,后端会向开启「重大情况推送」的成员发送订阅消息
 *   (含用户常用地址,按成员 address_shared 开关决定是否附带),详见 backend family_service.notify_emergency
 */
function FamilyPage() {
  const [members, setMembers] = useState<FamilyMember[]>([]);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState('');

  const [showAdd, setShowAdd] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    member_name: '',
    relationship: '',
    emergency_contact: true,
    notify_on_emergency: true,
    address_shared: true,
    can_view_status: true,
  });

  // 邀请二维码:memberId -> base64
  const [qr, setQr] = useState<{ id: number; src: string } | null>(null);
  const [qrLoading, setQrLoading] = useState(false);

  // 家庭成员接受邀请:从链接/二维码携带的 token
  const [acceptToken, setAcceptToken] = useState('');
  const [accepting, setAccepting] = useState(false);

  const loadMembers = async () => {
    setLoading(true);
    setLoadError('');
    try {
      const list = await listFamily();
      setMembers(list || []);
    } catch (err) {
      const msg = err instanceof Error ? err.message : '加载失败';
      console.error('[Family] 加载失败', err);
      setLoadError(msg);
    } finally {
      setLoading(false);
    }
  };

  useDidShow(() => {
    if (!isLoggedIn()) {
      Taro.reLaunch({ url: '/pages/login/index' });
      return;
    }
    loadMembers();
    // 读取邀请 token(普通分享链接带 ?token=,小程序码扫码带 scene=)
    const params = getCurrentInstance().router?.params || {};
    const token = (params.token || params.scene || '') as string;
    if (token) setAcceptToken(token);
  });

  const openAdd = () => {
    setForm({
      member_name: '',
      relationship: '',
      emergency_contact: true,
      notify_on_emergency: true,
      address_shared: true,
      can_view_status: true,
    });
    setShowAdd(true);
  };

  const handleAdd = async () => {
    if (!form.member_name.trim()) {
      Taro.showToast({ title: '请填写成员称呼', icon: 'none' });
      return;
    }
    setSaving(true);
    try {
      await addFamily({ ...form, member_name: form.member_name.trim() });
      setShowAdd(false);
      Taro.showToast({ title: '已添加,请分享邀请', icon: 'success' });
      await loadMembers();
    } catch (err) {
      Taro.showToast({
        title: err instanceof Error ? err.message : '添加失败',
        icon: 'none',
      });
    } finally {
      setSaving(false);
    }
  };

  const toggle = async (
    m: FamilyMember,
    key: 'notify_on_emergency' | 'address_shared' | 'can_view_status',
  ) => {
    const next = !m[key];
    try {
      await updateFamily(m.id, { [key]: next });
      setMembers((prev) =>
        prev.map((x) => (x.id === m.id ? { ...x, [key]: next } : x)),
      );
    } catch (err) {
      Taro.showToast({
        title: err instanceof Error ? err.message : '更新失败',
        icon: 'none',
      });
    }
  };

  const removeMember = async (m: FamilyMember) => {
    const res = await Taro.showModal({
      title: '移除成员',
      content: `确定移除「${m.member_name}」?`,
      confirmColor: '#f53f3f',
    });
    if (!res.confirm) return;
    try {
      await deleteFamily(m.id);
      Taro.showToast({ title: '已移除', icon: 'success' });
      await loadMembers();
    } catch (err) {
      Taro.showToast({
        title: err instanceof Error ? err.message : '移除失败',
        icon: 'none',
      });
    }
  };

  const genQr = async (m: FamilyMember) => {
    if (m.invite_status !== 'pending' || !m.invite_token) {
      Taro.showToast({ title: '该成员已绑定', icon: 'none' });
      return;
    }
    setQrLoading(true);
    try {
      // scene 限 32 位 ASCII;token 为 16 位 hex,符合要求
      const res = await generateWxacode(m.invite_token, 'pages/family/index');
      if (res.mock || !res.image_base64) {
        // 开发环境无小程序码能力,降级为复制邀请口令
        Taro.setClipboardData({ data: m.invite_token || '' });
        Taro.showToast({ title: '已复制邀请口令(开发环境)', icon: 'none' });
        return;
      }
      setQr({ id: m.id, src: `data:${res.content_type};base64,${res.image_base64}` });
    } catch (err) {
      Taro.showToast({
        title: err instanceof Error ? err.message : '生成二维码失败',
        icon: 'none',
      });
    } finally {
      setQrLoading(false);
    }
  };

  const handleAccept = async () => {
    if (!acceptToken) return;
    setAccepting(true);
    try {
      await acceptFamily(acceptToken);
      setAcceptToken('');
      Taro.showToast({ title: '已绑定为家庭成员', icon: 'success' });
    } catch (err) {
      Taro.showToast({
        title: err instanceof Error ? err.message : '绑定失败',
        icon: 'none',
      });
    } finally {
      setAccepting(false);
    }
  };

  return (
    <View className={styles.container}>
      {/* 家庭成员接受邀请横幅 */}
      {acceptToken && (
        <View className={styles.banner}>
          <Text className={styles.bannerText}>收到家庭成员邀请,点击绑定以查看其健康状态</Text>
          <Button
            className={styles.bannerBtn}
            loading={accepting}
            disabled={accepting}
            onClick={handleAccept}
          >
            接受邀请
          </Button>
        </View>
      )}

      <View className={styles.headRow}>
        <Text className={styles.title}>家庭成员</Text>
        <Button className={styles.addBtn} onClick={openAdd}>
          + 添加成员
        </Button>
      </View>

      {loading && <Text className={styles.hint}>加载中…</Text>}
      {!loading && loadError && (
        <View className={styles.card}>
          <Text className={styles.hint}>{loadError}</Text>
          <Button className={styles.saveBtn} onClick={loadMembers}>
            重试
          </Button>
        </View>
      )}

      {!loading && !loadError && members.length === 0 && (
        <View className={styles.empty}>
          <Text className={styles.emptyText}>还没有家庭成员</Text>
          <Text className={styles.hint}>添加成员后,您遇到紧急情况时会向其推送提醒与地址</Text>
        </View>
      )}

      {members.map((m) => (
        <View className={styles.card} key={m.id}>
          <View className={styles.cardHead}>
            <View>
              <Text className={styles.memberName}>{m.member_name}</Text>
              {m.relationship && (
                <Text className={styles.memberRel}>（{m.relationship}）</Text>
              )}
            </View>
            <Text
              className={
                m.invite_status === 'bound' ? styles.badgeOn : styles.badgeOff
              }
            >
              {m.invite_status === 'bound' ? '已绑定' : '待绑定'}
            </Text>
          </View>

          <View className={styles.toggleRow}>
            <Text className={styles.toggleLabel}>重大情况推送</Text>
            <Switch
              checked={m.notify_on_emergency}
              onChange={() => toggle(m, 'notify_on_emergency')}
            />
          </View>
          <View className={styles.toggleRow}>
            <Text className={styles.toggleLabel}>推送时附带我的地址</Text>
            <Switch
              checked={m.address_shared}
              onChange={() => toggle(m, 'address_shared')}
            />
          </View>
          <View className={styles.toggleRow}>
            <Text className={styles.toggleLabel}>允许其查看我的状态</Text>
            <Switch
              checked={m.can_view_status}
              onChange={() => toggle(m, 'can_view_status')}
            />
          </View>

          <View className={styles.cardActions}>
            {m.invite_status === 'pending' && (
              <Button
                className={styles.qrBtn}
                loading={qrLoading}
                disabled={qrLoading}
                onClick={() => genQr(m)}
              >
                生成邀请二维码
              </Button>
            )}
            <Button className={styles.delBtn} onClick={() => removeMember(m)}>
              移除
            </Button>
          </View>

          {qr && qr.id === m.id && (
            <View className={styles.qrWrap}>
              <Image className={styles.qrImg} src={qr.src} mode="aspectFit" />
              <Text className={styles.hint}>请家庭成员扫码,在小程序中点击「接受邀请」</Text>
            </View>
          )}
        </View>
      ))}

      {/* 添加成员弹层 */}
      {showAdd && (
        <View className={styles.mask} onClick={() => setShowAdd(false)}>
          <View className={styles.sheet} onClick={(e) => e.stopPropagation()}>
            <Text className={styles.sheetTitle}>添加家庭成员</Text>
            <View className={styles.row}>
              <Text className={styles.rowLabel}>称呼</Text>
              <Input
                className={styles.input}
                value={form.member_name}
                onInput={(e) => setForm({ ...form, member_name: e.detail.value })}
                placeholder="如:父亲 / 李医生"
                maxlength={20}
              />
            </View>
            <View className={styles.row}>
              <Text className={styles.rowLabel}>关系</Text>
              <Input
                className={styles.input}
                value={form.relationship}
                onInput={(e) => setForm({ ...form, relationship: e.detail.value })}
                placeholder="父母 / 配偶 / 子女 等(选填)"
                maxlength={20}
              />
            </View>
            <View className={styles.toggleRow}>
              <Text className={styles.toggleLabel}>设为紧急联系人</Text>
              <Switch
                checked={form.emergency_contact}
                onChange={(e) =>
                  setForm({ ...form, emergency_contact: e.detail.value })
                }
              />
            </View>
            <View className={styles.toggleRow}>
              <Text className={styles.toggleLabel}>重大情况推送(默认开)</Text>
              <Switch
                checked={form.notify_on_emergency}
                onChange={(e) =>
                  setForm({ ...form, notify_on_emergency: e.detail.value })
                }
              />
            </View>
            <View className={styles.toggleRow}>
              <Text className={styles.toggleLabel}>推送附带我的地址(默认开)</Text>
              <Switch
                checked={form.address_shared}
                onChange={(e) =>
                  setForm({ ...form, address_shared: e.detail.value })
                }
              />
            </View>
            <View className={styles.toggleRow}>
              <Text className={styles.toggleLabel}>允许查看我的状态(默认开)</Text>
              <Switch
                checked={form.can_view_status}
                onChange={(e) =>
                  setForm({ ...form, can_view_status: e.detail.value })
                }
              />
            </View>
            <View className={styles.sheetActions}>
              <Button className={styles.cancelBtn} onClick={() => setShowAdd(false)}>
                取消
              </Button>
              <Button
                className={styles.saveBtn}
                loading={saving}
                disabled={saving}
                onClick={handleAdd}
              >
                添加
              </Button>
            </View>
          </View>
        </View>
      )}
    </View>
  );
}

export default FamilyPage;
