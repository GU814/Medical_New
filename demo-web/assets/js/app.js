/* ==================== 启动入口 ====================
   职责：定义导航 → 渲染骨架 → 注册路由 → 启动。
   新增页面时：写完 pages/xxx.js 后，在下面的 ORDER 里加一项即可。 */
(function (App) {
  'use strict';

  /* ---------- 侧边导航配置（顺序即展示顺序） ---------- */
  App.nav = [
    { path: '/dashboard', title: '概览',     icon: 'grid',  group: '工作台' },
    { path: '/consult',   title: '智能问诊', icon: 'chat',  group: '工作台' },
    { path: '/records',   title: '问诊记录', icon: 'list',  group: '工作台' },
    { path: '/profile',   title: '个人中心', icon: 'user',  group: '我的' },
    { path: '/share',     title: '分享中心', icon: 'share', group: '我的' },
    { path: '/settings',  title: '设置',     icon: 'cog',   group: '我的' }
  ];

  /* ---------- 页面注册顺序（隐藏页面也要注册） ---------- */
  var ORDER = ['dashboard', 'consult', 'records', 'recordDetail', 'profile', 'share', 'settings'];

  function boot() {
    var shell = document.getElementById('shell');
    if (!shell) return;

    /* 1) 骨架 */
    shell.innerHTML = App.layout.shellHTML();
    var sidebar = document.getElementById('sidebar');
    var topbar = document.getElementById('topbar');
    var outlet = document.getElementById('outlet');
    App.layout.bindShell(shell);

    /* 2) 注册路由 */
    ORDER.forEach(function (key) {
      var page = App.pages && App.pages[key];
      if (page) App.router.register(page);
      else console.warn('[app] 页面未找到：' + key);
    });

    /* 3) 路由变化时更新导航选中态与顶栏 */
    App.router.init(outlet).onChange(function (cur) {
      App.layout.renderSidebar(sidebar, cur.path);
      App.layout.renderTopbar(topbar, {
        title: cur.route.title,
        crumbs: crumbsFor(cur)
      });
      document.title = cur.route.title + ' · 医学问诊智能体';
      // 移动端跳转后自动收起抽屉
      shell.classList.remove('nav-open');
    });

    /* 4) 启动 */
    App.router.start('/dashboard');
    console.log('%c[原型] 已启动','color:#1a6fd4','— 所有数据来自 assets/js/data/mock.js，接口层在 assets/js/api/index.js');
  }

  function crumbsFor(cur) {
    var route = cur.route;
    if (route.path === '/records/:id') return ['工作台', '问诊记录', '记录详情'];
    return [route.group || '主菜单', route.title];
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window.App = window.App || {});
