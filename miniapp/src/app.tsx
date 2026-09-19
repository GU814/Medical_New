import React, { useEffect } from 'react';
import { useDidShow, useDidHide } from '@tarojs/taro';
import Taro from '@tarojs/taro';
import { STORAGE_KEYS } from '@/config';
// 全局样式
import './app.scss';

function App(props) {
  useEffect(() => {
    // 启动时若无 token,且当前不在登录页,则重定向到登录页
    const token = Taro.getStorageSync(STORAGE_KEYS.TOKEN);
    const pages = Taro.getCurrentPages();
    const current = pages[pages.length - 1];
    const route = current?.route || '';
    if (!token && route && !route.includes('pages/login')) {
      Taro.reLaunch({ url: '/pages/login/index' });
    }
  }, []);

  // 对应 onShow
  useDidShow(() => {});

  // 对应 onHide
  useDidHide(() => {});

  return props.children;
}

export default App;
