/* ==================== 页面：记录详情 ====================
   展示：面包屑返回、患者信息卡、主诉要点、结构化报告、操作栏
   覆盖交互：加载占位、返回、导出提示、分享弹窗、二维码弹窗、删除确认 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  App.pages.recordDetail = {
    path: '/records/:id',
    title: '记录详情',
    icon: 'file',
    group: '工作台',
    hidden: true,

    render: function () {
      return '' +
        '<div style="margin-bottom:12px">' +
          '<button class="btn btn-ghost btn-sm" data-act="back">' + App.icon('arrowLeft') + '返回问诊记录</button>' +
        '</div>' +
        '<div id="detail-head">' +
          ui.PageHead({ title: '正在加载…', desc: '正在读取记录内容…' }) +
        '</div>' +
        '<div class="detail-grid" id="detail-body">' +
          '<div>' + ui.Skeleton.block(220) + '</div>' +
          '<div>' + ui.Skeleton.block(360) + '</div>' +
        '</div>';
    },

    mount: function (root, params) {
      var id = params.id;
      bind(root, id);

      return App.api.getRecord(id).then(function (r) {
        App.qs('#detail-head', root).outerHTML = ui.PageHead({
          title: r.title,
          desc: r.dept + ' · ' + App.fmt.date(r.date) + ' · 用时 ' + r.duration,
          actions: '<button class="btn" data-act="export">' + App.icon('download') + '导出 PDF</button> ' +
                   '<button class="btn" data-act="qr">' + App.icon('qr') + '小程序码</button> ' +
                   '<button class="btn btn-primary" data-act="share">' + App.icon('share') + '分享</button>'
        });

        App.qs('#detail-body', root).innerHTML = '' +
          // 左列：患者信息 + 要点
          '<div style="display:flex;flex-direction:column;gap:16px">' +
            ui.Card({
              icon: 'user', title: '患者信息',
              body: ui.KV([
                { k: '姓名', v: r.patient.name },
                { k: '性别', v: r.patient.gender },
                { k: '年龄', v: r.patient.age + ' 岁' },
                { k: '身高体重', v: r.patient.height + ' / ' + r.patient.weight },
                { k: '过敏史', v: r.patient.allergy }
              ])
            }) +
            ui.Card({
              icon: 'spark', title: '本次要点',
              body: '<div style="display:flex;flex-wrap:wrap;gap:6px">' +
                r.summary.map(function (s) { return '<span class="chip">' + esc(s) + '</span>'; }).join('') +
                '</div>'
            }) +
          '</div>' +

          // 右列：主诉 + 既往史 + 报告
          '<div style="display:flex;flex-direction:column;gap:16px">' +
            ui.Card({ icon: 'chat', title: '主诉与现病史', body: '<div class="t-body">' + esc(r.chief) + '</div>' }) +
            ui.Card({ icon: 'file', title: '既往史', body: '<div class="t-body t-muted">' + esc(r.history) + '</div>' }) +
            ui.Card({
              icon: 'checkCircle', title: 'AI 病历报告',
              headExtra: ui.Badge('AI 生成', 'brand'),
              body: '<div class="report">' + esc(r.report) + '</div>',
              foot: '<span class="t-xs t-dim">报告仅供参考，不能替代医生面诊</span>'
            }) +
          '</div>';
      });
    }
  };

  function bind(root, id) {
    App.on(root, 'click', '[data-act="back"]', function () { App.router.navigate('/records'); });

    App.on(root, 'click', '[data-act="export"]', function (e, el) {
      el.classList.add('is-disabled');
      App.api.exportRecordPdf(id).then(function () {
        el.classList.remove('is-disabled');
        App.overlay.toast('已生成 PDF（原型演示，未真正下载）', 'ok');
      });
    });

    App.on(root, 'click', '[data-act="share"]', function () { openShareModal(id); });

    App.on(root, 'click', '[data-act="qr"]', function () {
      App.overlay.modal({
        title: '小程序码',
        body: '<div style="text-align:center">' +
                '<div class="qr-box"></div>' +
                '<div class="t-small t-muted" style="margin-top:12px">扫码后直达本条记录（脱敏内容）</div>' +
                '<div class="t-xs t-dim" style="margin-top:4px">接入后由后端调用 getwxacode 生成</div>' +
              '</div>',
        foot: '<button class="btn btn-primary" data-act="close-modal">知道了</button>',
        onMount: function (m) {
          App.on(m.el, 'click', '[data-act="close-modal"]', function () { m.close(); });
        }
      });
    });
  }

  function openShareModal(id) {
    var m = App.overlay.modal({
      title: '生成分享链接',
      size: 'lg',
      body: '<div id="share-body">' + ui.Skeleton.lines(2) + '</div>',
      foot: '<button class="btn" data-act="close-modal">取消</button>' +
            '<button class="btn btn-primary" id="btn-do-share">生成并复制链接</button>'
    });

    App.api.getRecord(id).then(function (r) {
      App.qs('#share-body', m.el).innerHTML = '' +
        ui.KV([
          { k: '记录', v: r.title },
          { k: '时间', v: App.fmt.date(r.date) }
        ]) +
        '<div style="height:14px"></div>' +
        ui.Notice('分享链接为脱敏内容：不含姓名等敏感字段，默认 72 小时后失效。', 'brand');
    });

    App.on(m.el, 'click', '[data-act="close-modal"]', function () { m.close(); });
    App.on(m.el, 'click', '#btn-do-share', function () {
      App.api.createShare(id, 72).then(function () {
        App.overlay.toast('已生成分享链接，已复制到剪贴板', 'ok');
        m.close();
        App.router.navigate('/share');
      });
    });
  }
})(window.App = window.App || {});
