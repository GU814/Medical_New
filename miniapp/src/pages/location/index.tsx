import React, { useState } from 'react';
import { View, Text, Button } from '@tarojs/components';
import Taro, { useDidShow } from '@tarojs/taro';
import {
  listLocations,
  addLocation,
  deleteLocation,
  setDefaultLocation,
} from '@/services/location';
import type { UserLocation } from '@/types';
import styles from './index.module.scss';

/**
 * 我的地点页 - 选点保存常用地点(如常就诊医院)
 * 经纬度为公开坐标,不进加密/RAG
 */
function LocationPage() {
  const [list, setList] = useState<UserLocation[]>([]);
  const [loading, setLoading] = useState(true);

  const load = async () => {
    setLoading(true);
    try {
      const data = await listLocations();
      setList(data || []);
    } catch (err) {
      console.error('[Location] 加载失败', err);
      Taro.showToast({ title: '加载失败', icon: 'none' });
    } finally {
      setLoading(false);
    }
  };

  useDidShow(load);

  const handlePick = async () => {
    try {
      const res = await Taro.chooseLocation();
      await addLocation({
        name: res.name || '未命名地点',
        address: res.address,
        latitude: res.latitude,
        longitude: res.longitude,
        is_default: list.length === 0,
      });
      Taro.showToast({ title: '已保存', icon: 'success' });
      load();
    } catch {
      /* 用户取消选点,不提示 */
    }
  };

  const handleLocate = async () => {
    try {
      const res = await Taro.getLocation({ type: 'gcj02' });
      await addLocation({
        name: '当前位置',
        latitude: res.latitude,
        longitude: res.longitude,
        is_default: list.length === 0,
      });
      Taro.showToast({ title: '已保存当前位置', icon: 'success' });
      load();
    } catch (err) {
      console.warn('[Location] getLocation 失败', err);
    }
  };

  const handleDelete = async (id: number) => {
    const m = await Taro.showModal({
      title: '删除地点',
      content: '确定删除该地点?',
      confirmColor: '#f53f3f',
    });
    if (!m.confirm) return;
    try {
      await deleteLocation(id);
      load();
    } catch {
      Taro.showToast({ title: '删除失败', icon: 'none' });
    }
  };

  const handleDefault = async (id: number) => {
    try {
      await setDefaultLocation(id);
      load();
    } catch {
      Taro.showToast({ title: '设置失败', icon: 'none' });
    }
  };

  return (
    <View className={styles.container}>
      <View className={styles.actions}>
        <Button className={styles.primaryBtn} onClick={handlePick}>
          📍 选择地点
        </Button>
        <Button className={styles.ghostBtn} onClick={handleLocate}>
          定位当前位置
        </Button>
      </View>

      {loading ? (
        <Text className={styles.tip}>加载中…</Text>
      ) : list.length === 0 ? (
        <View className={styles.empty}>
          <Text className={styles.emptyIcon}>🗺️</Text>
          <Text className={styles.emptyText}>还没有保存的地点</Text>
        </View>
      ) : (
        list.map((loc) => (
          <View key={loc.id} className={styles.card}>
            <View className={styles.cardMain}>
              <Text className={styles.name}>{loc.name}</Text>
              {loc.address && <Text className={styles.addr}>{loc.address}</Text>}
            </View>
            <View className={styles.cardOps}>
              {loc.is_default ? (
                <Text className={styles.defaultTag}>默认</Text>
              ) : (
                <Text className={styles.op} onClick={() => handleDefault(loc.id)}>
                  设为默认
                </Text>
              )}
              <Text className={styles.op} onClick={() => handleDelete(loc.id)}>
                删除
              </Text>
            </View>
          </View>
        ))
      )}
    </View>
  );
}

export default LocationPage;
