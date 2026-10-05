export default defineAppConfig({
  pages: [
    'pages/index/index',
    'pages/consult/index',
    'pages/records/index',
    'pages/profile/index',
    'pages/login/index',
    'pages/recordDetail/index',
    'pages/privacy/index',
    'pages/location/index',
    'pages/share/index',
    'pages/family/index',
  ],
  // 使用位置相关接口需声明(隐私合规)
  requiredPrivateInfos: ['getLocation', 'chooseLocation', 'onLocationChange'],
  window: {
    backgroundTextStyle: 'dark',
    navigationBarBackgroundColor: '#ffffff',
    navigationBarTitleText: '医学问诊智能体',
    navigationBarTextStyle: 'black',
    backgroundColor: '#f7fafd',
  },
  tabBar: {
    color: '#86909c',
    selectedColor: '#165dff',
    backgroundColor: '#ffffff',
    borderStyle: 'white',
    list: [
      {
        pagePath: 'pages/index/index',
        text: '首页',
        iconPath: 'assets/tabbar/home.png',
        selectedIconPath: 'assets/tabbar/home-selected.png',
      },
      {
        pagePath: 'pages/consult/index',
        text: '咨询',
        iconPath: 'assets/tabbar/consult.png',
        selectedIconPath: 'assets/tabbar/consult-selected.png',
      },
      {
        pagePath: 'pages/records/index',
        text: '记录',
        iconPath: 'assets/tabbar/records.png',
        selectedIconPath: 'assets/tabbar/records-selected.png',
      },
      {
        pagePath: 'pages/profile/index',
        text: '我的',
        iconPath: 'assets/tabbar/profile.png',
        selectedIconPath: 'assets/tabbar/profile-selected.png',
      },
    ],
  },
})
