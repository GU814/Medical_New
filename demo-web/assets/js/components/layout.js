/* ==================== 骨架组件：侧边导航 + 顶栏 ====================
   依赖 App.nav（在 app.js 中定义）：[{ path, title, icon, group, badge }] */
(function (App) {
  'use strict';

  var esc = App.esc;

  App.layout = {

    /* ---------- 整体骨架 ---------- */
    shellHTML: function () {
      return '' +
        '<aside class="sidebar" id="sidebar"></aside>' +
        '<div class="nav-mask" data-act="close-nav"></div>' +
        '<div class="app-body">' +
          '<header class="topbar" id="topbar"></header>' +
          '<main class="content scroll-y" id="outlet"></main>' +
        '</div>';
    },

    /* ---------- 侧边导航 ---------- */
    renderSidebar: function (el, activePath) {
      var nav = App.nav || [];
      var groups = [];
      var index = {};
      nav.forEach(function (item) {
        var g = item.group || '主菜单';
        if (!index[g]) { index[g] = []; groups.push(g); }
        index[g].push(item);
      });

      var html = '' +
        '<div class="brand">' +
          '<div class="brand-mark">医</div>' +
          '<div class="brand-text">' +
            '<span class="brand-name">医学问诊智能体</span>' +
            '<span class="brand-sub">界面原型 · 模拟数据</span>' +
          '</div>' +
        '</div>' +
        '<nav class="nav scroll-y">' + groups.map(function (g) {
          return '<div class="nav-group">' +
            '<div class="nav-group-title">' + esc(g) + '</div>' +
            index[g].map(function (it) {
              var active = isActive(it.path, activePath);
              return '<a class="nav-item ' + (active ? 'is-active' : '') + '" href="#' + esc(it.path) + '"' +
                (active ? ' aria-current="page"' : '') + '>' +
                App.icon(it.icon) +
                '<span class="label">' + esc(it.title) + '</span>' +
                (it.badge ? '<span class="dot">' + esc(it.badge) + '</span>' : '') +
                '</a>';
            }).join('') +
          '</div>';
        }).join('') + '</nav>' +
        '<div class="sidebar-foot">v0.1 · 纯前端原型</div>';

      el.innerHTML = html;
    },

    /* ---------- 顶栏 ---------- */
    renderTopbar: function (el, info) {
      info = info || {};
      var crumbs = (info.crumbs || []).map(function (c, i, arr) {
        return (i ? '<span class="sep">/</span>' : '') +
               '<span>' + esc(c) + '</span>';
      }).join('');

      el.innerHTML = '' +
        '<div class="topbar-left">' +
          '<button class="btn btn-ghost btn-icon nav-toggle" data-act="toggle-nav" aria-label="打开导航">' + App.icon('menu') + '</button>' +
          '<div>' +
            '<div class="topbar-title">' + esc(info.title || '') + '</div>' +
            (crumbs ? '<div class="crumbs">' + crumbs + '</div>' : '') +
          '</div>' +
        '</div>' +
        '<div class="topbar-spacer"></div>' +
        '<div class="topbar-actions">' +
          '<div class="search"><span class="ico">' + App.icon('search') + '</span>' +
            '<input class="input" type="search" placeholder="搜索记录…" data-act="global-search" /></div>' +
          '<button class="btn btn-ghost btn-icon" data-act="notify" aria-label="通知">' + App.icon('bell') + '</button>' +
          '<div class="avatar" title="' + esc((App.mock.user && App.mock.user.name) || '') + '">' +
            esc(((App.mock.user && App.mock.user.avatarText) || 'U')) + '</div>' +
        '</div>';
    },

    /* ---------- 骨架事件绑定（移动端抽屉、搜索、通知） ---------- */
    bindShell: function (shell) {
      App.on(shell, 'click', '[data-act="toggle-nav"]', function () {
        shell.classList.toggle('nav-open');
      });
      App.on(shell, 'click', '[data-act="close-nav"]', function () {
        shell.classList.remove('nav-open');
      });
      App.on(shell, 'click', '[data-act="notify"]', function () {
        App.overlay.toast('演示：这里可接入通知中心（订阅消息）');
      });
      App.on(shell, 'keydown', '[data-act="global-search"]', function (e) {
        if (e.key === 'Enter') {
          var kw = e.target.value.trim();
          App.router.navigate('/records?kw=' + encodeURIComponent(kw));
        }
      });
    }
  };

  /* 判断导航选中：精确匹配，或父路径匹配（如 /records 匹配 /records/12） */
  function isActive(itemPath, activePath) {
    if (!activePath) return false;
    if (itemPath === activePath) return true;
    return activePath.indexOf(itemPath + '/') === 0;
  }
})(window.App = window.App || {});
