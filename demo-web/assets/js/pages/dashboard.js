/* ==================== 页面：概览 ====================
   展示：统计卡片、趋势图（条形占位）、快捷入口、最近记录列表
   覆盖交互：加载占位（骨架屏）、列表 hover、空数据提示、刷新 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  App.pages.dashboard = {
    path: '/dashboard',
    title: '概览',
    icon: 'grid',
    group: '工作台',

    /* 同步阶段：先渲染骨架，让结构立刻可见 */
    render: function () {
      return '' +
        ui.PageHead({
          title: '概览',
          desc: '最近使用情况与快捷入口（数据为模拟值）',
          actions: '<button class="btn" data-act="refresh">' + App.icon('refresh') + '刷新</button>' +
                   '<button class="btn btn-primary" data-act="new-consult">' + App.icon('plus') + '开始问诊</button>'
        }) +

        // 统计区（取数后替换）
        '<div class="grid grid-4" id="stat-area">' + ui.Skeleton.stats(4) + '</div>' +

        // 快捷入口（静态，用来看卡片排布）
        '<div class="grid grid-3" id="quick-area" style="margin-top:16px"></div>' +

        // 下半区：趋势 + 最近记录（取数后替换）
        '<div class="grid grid-2" id="lower-grid" style="margin-top:16px">' +
          '<section class="card">' +
            '<div class="card-head">' + App.icon('spark') + '<span class="t-sub">近 7 日问诊量</span></div>' +
            '<div class="card-body">' + ui.Skeleton.block(168) + '</div>' +
          '</section>' +
          '<section class="card">' +
            '<div class="card-head">' + App.icon('list') + '<span class="t-sub">最近问诊</span></div>' +
            '<div class="card-body">' + ui.Skeleton.lines(4) + '</div>' +
          '</section>' +
        '</div>';
    },

    /* 异步阶段：取数 → 局部替换 → 绑定事件 */
    mount: function (root) {
      bindActions(root);
      renderQuick(root);

      return App.api.getOverview().then(function (data) {
        // 1) 统计卡
        App.qs('#stat-area', root).innerHTML = '' +
          ui.Stat({ label: '累计问诊', value: data.stats.total, unit: '次', delta: data.stats.totalDelta, foot: '较上月', icon: 'chat' }) +
          ui.Stat({ label: '本月新增', value: data.stats.month, unit: '次', delta: data.stats.monthDelta, foot: '较上月', icon: 'plus', tone: 'accent' }) +
          ui.Stat({ label: '生成报告', value: data.stats.reports, unit: '份', delta: data.stats.reportsDelta, foot: '较上月', icon: 'file', tone: 'warn' }) +
          ui.Stat({ label: '平均时长', value: data.stats.avgMinutes, unit: '分钟', delta: data.stats.avgDelta, foot: '较上月', icon: 'clock', tone: 'danger' });

        // 2) 下半区
        App.qs('#lower-grid', root).innerHTML = '' +
          '<section class="card">' +
            '<div class="card-head">' + App.icon('spark') + '<span class="t-sub">近 7 日问诊量</span>' +
              '<div class="extra"><span class="t-xs t-dim">单位：次</span></div></div>' +
            '<div class="card-body">' + ui.Bars(data.trend) + '</div>' +
          '</section>' +
          '<section class="card">' +
            '<div class="card-head">' + App.icon('list') + '<span class="t-sub">最近问诊</span>' +
              '<div class="extra"><a href="#/records" class="t-xs">查看全部</a></div></div>' +
            '<div class="card-body" style="padding:0">' + recentList(data.recent) + '</div>' +
          '</section>';

        bindGo(root);
      });
    }
  };

  /* 快捷入口卡片：演示卡片 hover 抬升 */
  function renderQuick(root) {
    var items = [
      { icon: 'chat',  title: '智能问诊', desc: '5 阶段引导式采集，结束后生成结构化病历', href: '/consult', primary: true },
      { icon: 'list',  title: '问诊记录', desc: '按时间浏览历史问诊与报告，支持筛选和分页', href: '/records' },
      { icon: 'share', title: '分享中心', desc: '生成带过期时间的脱敏分享链接', href: '/share' }
    ];
    App.qs('#quick-area', root).innerHTML = items.map(function (it) {
      return '' +
        '<section class="card card-hover" data-go="' + it.href + '" style="cursor:pointer">' +
          '<div class="card-body" style="display:flex;gap:12px;align-items:flex-start">' +
            '<span class="stat-icon' + (it.primary ? '' : ' tone-accent') + '">' + App.icon(it.icon) + '</span>' +
            '<div style="min-width:0">' +
              '<div class="t-sub" style="margin-bottom:3px">' + esc(it.title) + '</div>' +
              '<div class="t-xs t-muted">' + esc(it.desc) + '</div>' +
            '</div>' +
          '</div>' +
        '</section>';
    }).join('');
    bindGo(root);
  }

  function recentList(items) {
    if (!items || !items.length) {
      return ui.Empty({
        icon: 'inbox',
        title: '还没有问诊记录',
        desc: '完成一次问诊后，这里会显示最近 5 条记录。',
        action: '<a class="btn btn-primary" href="#/consult">开始问诊</a>'
      });
    }
    return '<div class="row-list">' + items.map(function (r) {
      return '' +
        '<div class="row-item" data-go="/records/' + r.id + '" style="cursor:pointer">' +
          '<div class="main">' +
            '<div class="title">' + esc(r.title) + '</div>' +
            '<div class="sub">' + esc(r.dept) + ' · ' + App.fmt.ago(r.date) + ' · ' + esc(r.duration) + '</div>' +
          '</div>' +
          '<div class="side">' + ui.Badge(r.status === 'done' ? '已完成' : '进行中', r.status === 'done' ? 'ok' : 'warn', true) + '</div>' +
        '</div>';
    }).join('') + '</div>';
  }

  function bindGo(root) {
    App.on(root, 'click', '[data-go]', function (e, el) {
      App.router.navigate(el.getAttribute('data-go'));
    });
  }

  function bindActions(root) {
    App.on(root, 'click', '[data-act="refresh"]', function (e, el) {
      el.classList.add('is-disabled');
      App.router.reload();
    });
    App.on(root, 'click', '[data-act="new-consult"]', function () {
      App.router.navigate('/consult');
    });
  }
})(window.App = window.App || {});
