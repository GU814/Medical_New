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
  // 按需注入(用时注入的前提):基础库 2.11.1+ 支持,未达版本自动忽略、无副作用。
  // 仅注入当前访问页面所需的代码与依赖组件,降低启动注入耗时与运行时内存。
  // 注意:本工程为 Taro React,自定义组件均被内联进各页 JS,无独立 usingComponents,
  // 故无需(也无法)配置 componentPlaceholder;本字段即为本工程支持该能力的方式。
  lazyCodeLoading: 'requiredComponents',
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
