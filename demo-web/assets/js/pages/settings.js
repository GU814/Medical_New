/* ==================== 页面：设置 ====================
   展示：开关分组、密度选择（分段控件）、会员方案卡片、关于
   覆盖交互：开关即时保存 Toast、密度切换、升级弹窗、加载占位 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  App.pages.settings = {
    path: '/settings',
    title: '设置',
    icon: 'cog',
    group: '我的',

    render: function () {
      return '' +
        ui.PageHead({ title: '设置', desc: '通知、隐私与显示偏好（原型演示，改动仅保存在内存）' }) +
        '<div id="set-area">' + ui.Skeleton.block(240) + '</div>';
    },

    mount: function (root) {
      return Promise.all([App.api.getSettings(), App.api.listPlans()]).then(function (res) {
        var s = res[0], plans = res[1];
        App.qs('#set-area', root).innerHTML = '' +

          '<div style="display:flex;flex-direction:column;gap:16px">' +

            ui.Card({
              icon: 'bell', title: '消息通知',
              body: '<div style="display:flex;flex-direction:column;gap:14px">' +
                switchRow('notifyRemind', '复诊与用药提醒', '在关键节点提醒您回访与复诊', s.notifyRemind) +
                switchRow('notifyReport', '报告生成通知', '问诊报告生成后推送通知', s.notifyReport) +
                '</div>'
            }) +

            ui.Card({
              icon: 'cog', title: '偏好设置',
              body: '<div style="display:flex;flex-direction:column;gap:14px">' +
                switchRow('voice', '语音播报回复', '需要浏览器支持语音合成', s.voice) +
                switchRow('analytics', '匿名使用统计', '帮助我们了解功能使用情况，不含任何问诊内容', s.analytics) +
                '<div class="field">' +
                  '<label>列表密度</label>' +
                  '<div class="segmented" id="density">' +
                    '<button data-density="comfortable"' + (s.density === 'comfortable' ? ' class="is-active"' : '') + '>宽松</button>' +
                    '<button data-density="compact"' + (s.density === 'compact' ? ' class="is-active"' : '') + '>紧凑</button>' +
                  '</div>' +
                '</div>' +
                '</div>'
            }) +

            ui.Card({
              icon: 'star', title: '会员方案',
              headExtra: ui.Badge('当前：' + App.mock.user.tier, 'brand'),
              body: '<div class="grid grid-3">' + plans.map(planCard).join('') + '</div>'
            }) +

            ui.Card({
              icon: 'info', title: '关于',
              body: ui.KV([
                { k: '版本', v: 'v0.1.0（界面原型）' },
                { k: '数据来源', v: '本地模拟数据，未接入后端' },
                { k: '说明', v: '本原型仅用于确认页面结构、布局与交互' }
              ])
            }) +

          '</div>';

        bind(root, s);
      });
    }
  };

  function switchRow(key, title, desc, checked) {
    return '' +
      '<div style="display:flex;align-items:center;gap:14px">' +
        '<div style="min-width:0;flex:1">' +
          '<div class="t-body" style="font-weight:500">' + esc(title) + '</div>' +
          '<div class="t-xs t-dim">' + esc(desc) + '</div>' +
        '</div>' +
        '<label class="switch"><input type="checkbox" data-setting="' + esc(key) + '"' + (checked ? ' checked' : '') + ' /> <span class="track"></span></label>' +
      '</div>';
  }

  function planCard(p) {
    return '' +
      '<section class="card card-hover plan' + (p.featured ? ' is-featured' : '') + '">' +
        '<div class="plan-name">' + esc(p.name) +
          (p.featured ? ui.Badge('推荐', 'brand') : '') +
        '</div>' +
        '<div class="plan-price">¥' + p.price + '<span class="unit">' + esc(p.unit) + '</span></div>' +
        '<ul class="plan-features">' + p.features.map(function (f) {
          return '<li>' + App.icon('check') + '<span>' + esc(f) + '</span></li>';
        }).join('') + '</ul>' +
        '<button class="btn ' + (p.featured ? 'btn-primary' : '') + ' btn-block" data-plan="' + esc(p.id) + '">' +
          (p.price === 0 ? '当前方案' : '升级到' + p.name) +
        '</button>' +
      '</section>';
  }

  function bind(root, s) {
    /* 开关：改动即保存 */
    App.on(root, 'change', '[data-setting]', function (e, el) {
      var key = el.getAttribute('data-setting');
      var payload = {};
      payload[key] = el.checked;
      App.api.saveSettings(payload).then(function () {
        App.overlay.toast('已保存：' + (el.checked ? '开启' : '关闭'), 'ok');
      });
    });

    /* 密度切换 */
    App.on(root, 'click', '[data-density]', function (e, el) {
      App.qsa('#density button', root).forEach(function (b) { b.classList.remove('is-active'); });
      el.classList.add('is-active');
      App.api.saveSettings({ density: el.getAttribute('data-density') }).then(function () {
        App.overlay.toast('列表密度已更新');
      });
    });

    /* 升级弹窗 */
    App.on(root, 'click', '[data-plan]', function (e, el) {
      var id = el.getAttribute('data-plan');
      if (id === 'free') { App.overlay.toast('当前已是免费版'); return; }

      var m = App.overlay.modal({
        title: '确认升级',
        body: '<div class="t-body t-muted">原型演示：这里将创建支付订单并拉起支付。接入后端后对应 <code class="t-mono">POST /api/orders</code>。</div>' +
              '<div style="height:12px"></div>' + ui.Notice('支付、退款与权益校验均为后端能力，本原型不涉及。', 'brand'),
        foot: '<button class="btn" data-act="close-modal">再想想</button>' +
              '<button class="btn btn-primary" id="plan-ok">确认升级</button>'
      });
      App.on(m.el, 'click', '[data-act="close-modal"]', function () { m.close(); });
      App.on(m.el, 'click', '#plan-ok', function () {
        App.api.subscribePlan(id).then(function () {
          m.close();
          App.overlay.toast('已创建订单（演示）', 'ok');
        });
      });
    });
  }
})(window.App = window.App || {});
