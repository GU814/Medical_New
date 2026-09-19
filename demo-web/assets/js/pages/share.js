/* ==================== 页面：分享中心 ====================
   展示：分享链接列表卡、新建分享弹窗、二维码弹窗、空态
   覆盖交互：复制 Toast、撤销确认、列表 hover、加载占位 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  App.pages.share = {
    path: '/share',
    title: '分享中心',
    icon: 'share',
    group: '我的',

    render: function () {
      return '' +
        ui.PageHead({
          title: '分享中心',
          desc: '把问诊报告以脱敏链接的形式分享给医生或家人',
          actions: '<button class="btn btn-primary" data-act="create">' + App.icon('plus') + '新建分享</button>'
        }) +
        '<div id="share-area">' + ui.Skeleton.block(180) + '</div>';
    },

    mount: function (root) {
      bind(root);
      return App.api.listShareLinks().then(function (links) { fill(root, links); });
    }
  };

  function fill(root, links) {
    if (!links.length) {
      App.qs('#share-area', root).innerHTML = ui.Card({
        body: ui.Empty({
          icon: 'share',
          title: '还没有分享链接',
          desc: '新建的分享会脱敏处理（不含姓名），并可设置 72 小时后自动失效。',
          action: '<button class="btn btn-primary" data-act="create">新建分享</button>'
        })
      });
      return;
    }

    App.qs('#share-area', root).innerHTML = ui.Card({
      icon: 'share',
      title: '分享中的链接',
      headExtra: '<span class="t-xs t-dim">共 ' + links.length + ' 条</span>',
      body: '<div class="row-list">' + links.map(function (l) {
        var expired = l.expiresAt < Date.now();
        return '' +
          '<div class="row-item">' +
            '<div class="main">' +
              '<div class="title">' + esc(l.recordTitle) + '</div>' +
              '<div class="sub">' + esc(shareUrl(l.token)) + '</div>' +
              '<div class="sub" style="margin-top:3px">' +
                '创建于 ' + App.fmt.ago(l.createdAt) + ' · 访问 ' + l.views + ' 次 · ' +
                (expired ? '<span style="color:var(--c-danger)">已过期</span>' : App.fmt.ago(l.expiresAt).replace('前', '后失效')) +
              '</div>' +
            '</div>' +
            '<div class="side">' +
              '<button class="btn btn-sm" data-act="copy" data-token="' + esc(l.token) + '">' + App.icon('copy') + '复制</button> ' +
              '<button class="btn btn-sm" data-act="qr" data-token="' + esc(l.token) + '">' + App.icon('qr') + '</button> ' +
              '<button class="btn btn-sm btn-danger" data-act="revoke" data-token="' + esc(l.token) + '">撤销</button>' +
            '</div>' +
          '</div>';
      }).join('') + '</div>'
    });
  }

  function shareUrl(token) {
    // 原型里没有真实域名，这里给出示意地址
    return 'https://demo.example.com/s/' + token.slice(0, 12) + '…';
  }

  function bind(root) {
    /* 新建分享 */
    App.on(root, 'click', '[data-act="create"]', function () {
      var options = App.mock.records.slice(0, 6).map(function (r) {
        return '<option value="' + r.id + '">' + esc(r.title) + '</option>';
      }).join('');

      var m = App.overlay.modal({
        title: '新建分享',
        size: 'lg',
        body: '' +
          '<div class="field" style="margin-bottom:14px">' +
            '<label>选择记录</label>' +
            '<select class="select" id="s-record">' + options + '</select>' +
          '</div>' +
          '<div class="field">' +
            '<label>有效期</label>' +
            '<select class="select" id="s-ttl">' +
              '<option value="24">24 小时</option>' +
              '<option value="72" selected>72 小时（推荐）</option>' +
              '<option value="168">7 天</option>' +
            '</select>' +
          '</div>' +
          '<div style="height:14px"></div>' +
          ui.Notice('分享内容将自动脱敏：不包含姓名、联系方式等敏感字段。', 'brand'),
        foot: '<button class="btn" data-act="close-modal">取消</button>' +
              '<button class="btn btn-primary" id="s-ok">生成链接</button>'
      });

      App.on(m.el, 'click', '[data-act="close-modal"]', function () { m.close(); });
      App.on(m.el, 'click', '#s-ok', function () {
        var rid = App.qs('#s-record', m.el).value;
        var ttl = Number(App.qs('#s-ttl', m.el).value);
        App.api.createShare(rid, ttl).then(function () {
          m.close();
          App.overlay.toast('分享链接已生成', 'ok');
          App.router.reload();
        });
      });
    });

    /* 复制 */
    App.on(root, 'click', '[data-act="copy"]', function (e, el) {
      App.copy(shareUrl(el.getAttribute('data-token'))).then(function () {
        App.overlay.toast('链接已复制到剪贴板', 'ok');
      });
    });

    /* 二维码 */
    App.on(root, 'click', '[data-act="qr"]', function () {
      var m = App.overlay.modal({
        title: '分享二维码',
        body: '<div style="text-align:center">' +
                '<div class="qr-box"></div>' +
                '<div class="t-small t-muted" style="margin-top:12px">扫码打开脱敏报告</div>' +
              '</div>',
        foot: '<button class="btn btn-primary" data-act="close-modal">关闭</button>'
      });
      App.on(m.el, 'click', '[data-act="close-modal"]', function () { m.close(); });
    });

    /* 撤销 */
    App.on(root, 'click', '[data-act="revoke"]', function (e, el) {
      var token = el.getAttribute('data-token');
      App.overlay.confirm({
        title: '撤销这条分享？',
        text: '撤销后链接立即失效，已收到链接的人将无法访问。',
        okText: '确认撤销',
        danger: true
      }).then(function (ok) {
        if (!ok) return;
        App.api.revokeShare(token).then(function () {
          App.overlay.toast('已撤销分享', 'ok');
          App.router.reload();
        });
      });
    });
  }
})(window.App = window.App || {});
