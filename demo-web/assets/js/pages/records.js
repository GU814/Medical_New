/* ==================== 页面：问诊记录 ====================
   展示：工具栏（搜索 / 状态筛选 / 时间排序）、表格、分页、行操作
   覆盖交互：加载占位、空数据提示、删除确认弹窗、移动端筛选抽屉、行 hover */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  var state = { keyword: '', status: 'all', page: 1, size: 8, loading: false };

  App.pages.records = {
    path: '/records',
    title: '问诊记录',
    icon: 'list',
    group: '工作台',

    render: function () {
      // 支持从顶栏全局搜索跳入：#/records?kw=关键词
      state.keyword = queryKw();
      state.page = 1;

      return '' +
        ui.PageHead({
          title: '问诊记录',
          desc: '历史问诊与生成报告，支持搜索与状态筛选',
          actions: '<button class="btn" data-act="refresh">' + App.icon('refresh') + '刷新</button>' +
                   '<button class="btn btn-primary" data-act="new">' + App.icon('plus') + '新建问诊</button>'
        }) +

        '<section class="card">' +
          '<div class="card-head">' +
            '<div class="search" style="width:220px;max-width:100%">' +
              '<span class="ico">' + App.icon('search') + '</span>' +
              '<input class="input" id="kw" type="search" placeholder="搜索标题或科室…" value="' + esc(state.keyword) + '" />' +
            '</div>' +
            '<div class="extra">' +
              '<div class="segmented" id="status-tabs">' +
                tabBtn('all', '全部') + tabBtn('doing', '进行中') + tabBtn('done', '已完成') +
              '</div>' +
              '<button class="btn btn-sm" data-act="filter" id="btn-filter">' + App.icon('filter') + '筛选</button>' +
            '</div>' +
          '</div>' +
          '<div id="list-area">' + ui.Skeleton.table(6) + '</div>' +
        '</section>';
    },

    mount: function (root) {
      bind(root);
      return load(root);
    }
  };

  /* 从 hash 中读取 ?kw= */
  function queryKw() {
    if (typeof location === 'undefined') return '';   // 非浏览器环境（如 Node 冒烟测试）保护
    var h = location.hash || '';
    var i = h.indexOf('?');
    if (i < 0) return '';
    var m = /[?&]kw=([^&]*)/.exec(h.slice(i));
    return m ? decodeURIComponent(m[1]) : '';
  }

  function tabBtn(key, label) {
    return '<button data-status="' + key + '"' + (state.status === key ? ' class="is-active"' : '') + '>' + label + '</button>';
  }

  /* ---------- 取数与渲染 ---------- */
  function load(root) {
    var area = App.qs('#list-area', root);
    if (!area) return Promise.resolve();

    state.loading = true;
    area.innerHTML = ui.Skeleton.table(6);

    return App.api.listRecords({ keyword: state.keyword, status: state.status, page: state.page, size: state.size })
      .then(function (res) {
        state.loading = false;
        area.innerHTML = listHTML(res);
      })
      .catch(function (err) {
        state.loading = false;
        area.innerHTML = ui.Empty({ icon: 'alert', title: '加载失败', desc: err.message, action: '<button class="btn" data-act="refresh">重试</button>' });
      });
  }

  function listHTML(res) {
    if (!res.total) {
      return ui.Empty({
        icon: 'inbox',
        title: '没有匹配的记录',
        desc: state.keyword || state.status !== 'all'
          ? '试试更换关键词，或把状态筛选切回「全部」。'
          : '还没有问诊记录，完成一次问诊后会出现在这里。',
        action: '<button class="btn" data-act="clear-filter">清除筛选</button>' +
                '<a class="btn btn-primary" href="#/consult">开始问诊</a>'
      });
    }

    var table = ui.Table({
      columns: [
        { title: '问诊主题', key: 'title', render: function (r) {
            return '<div class="cell-main">' + esc(r.title) + '</div>' +
                   '<div class="cell-sub">编号 ' + esc(r.id) + ' · ' + esc(r.duration) + '</div>';
          } },
        { title: '科室', key: 'dept', width: '110px' },
        { title: '时间', key: 'date', width: '130px', render: function (r) {
            return '<span class="t-small">' + App.fmt.date(r.date) + '</span>' +
                   '<div class="cell-sub">' + App.fmt.ago(r.date) + '</div>';
          } },
        { title: '状态', key: 'status', width: '96px', render: function (r) {
            return r.status === 'done'
              ? ui.Badge('已完成', 'ok', true)
              : ui.Badge('进行中', 'warn', true);
          } },
        { title: '操作', key: 'id', align: 'right', width: '180px', render: function (r) {
            return '<button class="btn btn-sm" data-act="view" data-id="' + r.id + '">查看</button> ' +
                   '<button class="btn btn-sm" data-act="share" data-id="' + r.id + '">分享</button> ' +
                   '<button class="btn btn-sm btn-danger" data-act="del" data-id="' + r.id + '">删除</button>';
          } }
      ],
      rows: res.items
    });

    var pager = '<div style="padding:12px 16px;border-top:1px solid var(--c-border)">' +
      ui.Pager({ page: res.page, size: res.size, total: res.total }) + '</div>';

    return table + pager;
  }

  /* ---------- 事件 ---------- */
  function bind(root) {
    /* 顶部按钮 */
    App.on(root, 'click', '[data-act="refresh"]', function () { App.router.reload(); });
    App.on(root, 'click', '[data-act="new"]', function () { App.router.navigate('/consult'); });

    /* 搜索（防抖） */
    var kwEl = App.qs('#kw', root);
    if (kwEl) {
      var timer = null;
      kwEl.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(function () {
          state.keyword = kwEl.value.trim();
          state.page = 1;
          load(root);
        }, 320);
      });
    }

    /* 状态筛选 */
    App.on(root, 'click', '[data-status]', function (e, el) {
      state.status = el.getAttribute('data-status');
      state.page = 1;
      App.qsa('#status-tabs button', root).forEach(function (b) {
        b.classList.toggle('is-active', b === el);
      });
      load(root);
    });

    /* 行操作 */
    App.on(root, 'click', '[data-act="view"]', function (e, el) {
      App.router.navigate('/records/' + el.getAttribute('data-id'));
    });
    App.on(root, 'click', '[data-act="share"]', function (e, el) {
      openShareModal(el.getAttribute('data-id'));
    });
    App.on(root, 'click', '[data-act="del"]', function (e, el) {
      var id = el.getAttribute('data-id');
      App.overlay.confirm({
        title: '删除这条问诊记录？',
        text: '删除后不可恢复，关联的历史报告与分享链接也会失效。',
        okText: '确认删除',
        danger: true
      }).then(function (ok) {
        if (!ok) return;
        App.api.deleteRecord(id).then(function () {
          App.overlay.toast('已删除记录 ' + id, 'ok');
          App.router.reload();
        });
      });
    });

    /* 分页 */
    App.on(root, 'click', '[data-page]', function (e, el) {
      if (el.disabled) return;
      state.page = Number(el.getAttribute('data-page'));
      load(root);
    });

    /* 空态里的清除筛选 */
    App.on(root, 'click', '[data-act="clear-filter"]', function () {
      state.keyword = ''; state.status = 'all'; state.page = 1;
      App.router.reload();
    });

    /* 移动端筛选抽屉 */
    App.on(root, 'click', '[data-act="filter"]', function () { openFilterDrawer(root); });
  }

  /* ---------- 弹窗：分享 ---------- */
  function openShareModal(recordId) {
    var m = App.overlay.modal({
      title: '生成分享链接',
      size: 'lg',
      body: '<div id="share-body" style="padding:20px 0;text-align:center">' + ui.Skeleton.lines(2) + '</div>',
      foot: '<button class="btn" data-act="close-modal">取消</button>' +
            '<button class="btn btn-primary" id="btn-do-share">生成并复制链接</button>'
    });

    App.api.getRecord(recordId).then(function (r) {
      App.qs('#share-body', m.el).innerHTML = '' +
        '<div style="text-align:left;margin-bottom:14px">' +
          ui.KV([
            { k: '记录', v: r.title },
            { k: '科室', v: r.dept },
            { k: '时间', v: App.fmt.date(r.date) }
          ]) +
        '</div>' +
        ui.Notice('分享链接为脱敏内容：不包含姓名等敏感字段，可设置有效期。', 'brand');
    });

    App.on(m.el, 'click', '[data-act="close-modal"]', function () { m.close(); });
    App.on(m.el, 'click', '#btn-do-share', function () {
      App.api.createShare(recordId, 72).then(function (link) {
        var url = location.origin + location.pathname + '#/share';
        App.copy(url).then(function () {});
        App.overlay.toast('已生成分享链接（72 小时有效）', 'ok');
        m.close();
        App.router.navigate('/share');
      });
    });
  }

  /* ---------- 抽屉：筛选（移动端） ---------- */
  function openFilterDrawer(root) {
    var d = App.overlay.drawer({
      title: '筛选条件',
      body: '' +
        '<div class="field" style="margin-bottom:14px">' +
          '<label>关键词</label>' +
          '<input class="input" id="d-kw" value="' + esc(state.keyword) + '" placeholder="标题 / 科室" />' +
        '</div>' +
        '<div class="field" style="margin-bottom:14px">' +
          '<label>状态</label>' +
          '<select class="select" id="d-status">' +
            '<option value="all"' + (state.status === 'all' ? ' selected' : '') + '>全部</option>' +
            '<option value="doing"' + (state.status === 'doing' ? ' selected' : '') + '>进行中</option>' +
            '<option value="done"' + (state.status === 'done' ? ' selected' : '') + '>已完成</option>' +
          '</select>' +
        '</div>' +
        '<div class="field">' +
          '<label>每页条数</label>' +
          '<select class="select" id="d-size">' +
            [5, 8, 12, 20].map(function (n) {
              return '<option value="' + n + '"' + (state.size === n ? ' selected' : '') + '>' + n + ' 条 / 页</option>';
            }).join('') +
          '</select>' +
        '</div>',
      foot: '<button class="btn" data-act="reset-drawer">重置</button>' +
            '<button class="btn btn-primary" data-act="apply-drawer">应用</button>'
    });

    App.on(d.el, 'click', '[data-act="reset-drawer"]', function () {
      state.keyword = ''; state.status = 'all'; state.size = 8; state.page = 1;
      d.close(); App.router.reload();
    });
    App.on(d.el, 'click', '[data-act="apply-drawer"]', function () {
      state.keyword = App.qs('#d-kw', d.el).value.trim();
      state.status = App.qs('#d-status', d.el).value;
      state.size = Number(App.qs('#d-size', d.el).value);
      state.page = 1;
      d.close();
      App.router.reload();
    });
  }
})(window.App = window.App || {});
