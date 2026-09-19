/* ==================== 展示型组件 ====================
   全部为「输入配置对象 → 返回 HTML 字符串」的纯函数，无状态、无副作用。 */
(function (App) {
  'use strict';

  var esc = App.esc;

  App.ui = {

    /* ---------- 页头 ---------- */
    PageHead: function (opt) {
      var actions = opt.actions ? '<div class="actions">' + opt.actions + '</div>' : '';
      return '' +
        '<div class="page-head">' +
          '<div class="page-head-row">' +
            '<div>' +
              '<h1 class="t-title">' + esc(opt.title) + '</h1>' +
              (opt.desc ? '<div class="desc">' + esc(opt.desc) + '</div>' : '') +
            '</div>' +
            actions +
          '</div>' +
        '</div>';
    },

    /* ---------- 卡片 ---------- */
    Card: function (opt) {
      var head = opt.title ? '' +
        '<div class="card-head">' +
          (opt.icon ? App.icon(opt.icon) : '') +
          '<span class="t-sub">' + esc(opt.title) + '</span>' +
          (opt.headExtra || '') +
          (opt.extra ? '<div class="extra">' + opt.extra + '</div>' : '') +
        '</div>' : '';
      var body = opt.body !== undefined ? '<div class="card-body' + (opt.tight ? ' tight' : '') + '">' + opt.body + '</div>' : '';
      var foot = opt.foot ? '<div class="card-foot">' + opt.foot + '</div>' : '';
      return '<section class="card ' + App.cx(opt.hover && 'card-hover', opt.cls) + '">' + head + body + foot + '</section>';
    },

    /* ---------- 统计卡 ---------- */
    Stat: function (opt) {
      var trend = opt.delta === undefined ? '' :
        '<span class="trend ' + (opt.delta >= 0 ? 'up' : 'down') + '">' +
          (opt.delta >= 0 ? '↑ ' : '↓ ') + Math.abs(opt.delta) + (opt.deltaUnit || '%') +
        '</span>';
      return '' +
        '<section class="card card-hover stat">' +
          '<div class="stat-label">' +
            '<span class="stat-icon ' + (opt.tone ? 'tone-' + opt.tone : '') + '">' + App.icon(opt.icon || 'spark') + '</span>' +
            esc(opt.label) +
          '</div>' +
          '<div class="stat-value">' + esc(opt.value) + (opt.unit ? '<span class="unit">' + esc(opt.unit) + '</span>' : '') + '</div>' +
          '<div class="stat-foot">' + trend + (opt.foot ? '<span>' + esc(opt.foot) + '</span>' : '') + '</div>' +
        '</section>';
    },

    /* ---------- 徽标 ---------- */
    Badge: function (text, tone, dot) {
      return '<span class="badge ' + (tone || '') + '">' + (dot ? '<i class="dot"></i>' : '') + esc(text) + '</span>';
    },

    /* ---------- 表格 ---------- */
    Table: function (opt) {
      var th = opt.columns.map(function (c) {
        return '<th' + (c.width ? ' style="width:' + c.width + '"' : '') +
               (c.align === 'right' ? ' class="col-actions"' : '') + '>' + esc(c.title) + '</th>';
      }).join('');

      var tb = opt.rows.map(function (row, i) {
        var tds = opt.columns.map(function (c) {
          var v = c.render ? c.render(row, i) : row[c.key];
          var cls = c.align === 'right' ? ' class="col-actions"' : '';
          return '<td' + cls + '>' + (v === undefined || v === null ? '' : v) + '</td>';
        }).join('');
        return '<tr data-row="' + esc(row.id !== undefined ? row.id : i) + '">' + tds + '</tr>';
      }).join('');

      return '<div class="table-wrap"><table class="table"><thead><tr>' + th + '</tr></thead><tbody>' + tb + '</tbody></table></div>';
    },

    /* ---------- 空状态 ---------- */
    Empty: function (opt) {
      return '' +
        '<div class="empty">' +
          '<div class="empty-icon">' + App.icon(opt.icon || 'inbox') + '</div>' +
          '<div class="empty-title">' + esc(opt.title || '暂无数据') + '</div>' +
          (opt.desc ? '<div class="empty-desc">' + esc(opt.desc) + '</div>' : '') +
          (opt.action ? '<div class="empty-actions">' + opt.action + '</div>' : '') +
        '</div>';
    },

    /* ---------- 骨架屏 ---------- */
    Skeleton: {
      lines: function (n) {
        var s = '';
        for (var i = 0; i < (n || 3); i++) {
          s += '<div class="sk sk-line' + (i === n - 1 ? ' short' : (i % 2 ? ' mid' : '')) + '"></div>';
        }
        return s;
      },
      stats: function (n) {
        var s = '';
        for (var i = 0; i < (n || 4); i++) {
          s += '<section class="card stat">' +
                 '<div class="sk sk-line short"></div>' +
                 '<div class="sk" style="height:26px;width:60%;margin:6px 0"></div>' +
                 '<div class="sk sk-line" style="width:40%;margin:0"></div>' +
               '</section>';
        }
        return s;
      },
      table: function (n) {
        var s = '';
        for (var i = 0; i < (n || 6); i++) s += '<div class="sk sk-row"></div>';
        return '<div style="padding:16px">' + s + '</div>';
      },
      block: function (h) {
        return '<div class="sk sk-block" style="' + (h ? 'height:' + h + 'px' : '') + '"></div>';
      }
    },

    /* ---------- 分页 ---------- */
    Pager: function (opt) {
      var page = opt.page || 1;
      var size = opt.size || 10;
      var total = opt.total || 0;
      var pages = Math.max(1, Math.ceil(total / size));
      var from = total === 0 ? 0 : (page - 1) * size + 1;
      var to = Math.min(page * size, total);

      var btn = function (label, p, opts) {
        opts = opts || {};
        return '<button data-page="' + p + '"' +
          (opts.active ? ' class="is-active"' : '') +
          (opts.disabled ? ' disabled' : '') +
          (opts.arrow ? ' data-arrow="' + opts.arrow + '"' : '') +
          '>' + label + '</button>';
      };

      var nums = '';
      var win = [];
      for (var i = 1; i <= pages; i++) {
        if (i === 1 || i === pages || Math.abs(i - page) <= 1) win.push(i);
      }
      var last = 0;
      win.forEach(function (i) {
        if (last && i - last > 1) nums += '<button disabled>…</button>';
        nums += btn(i, i, { active: i === page });
        last = i;
      });

      return '' +
        '<div class="pager">' +
          '<span class="info">显示 ' + from + '–' + to + ' 条，共 ' + total + ' 条</span>' +
          '<div class="pages">' +
            btn('上一页', Math.max(1, page - 1), { disabled: page <= 1, arrow: 'prev' }) +
            nums +
            btn('下一页', Math.min(pages, page + 1), { disabled: page >= pages, arrow: 'next' }) +
          '</div>' +
        '</div>';
    },

    /* ---------- 条形图（纯 CSS 占位，用于看清趋势类元素的排布） ---------- */
    Bars: function (data) {
      var max = 1;
      data.forEach(function (d) { if (d.value > max) max = d.value; });
      return '<div class="bars">' + data.map(function (d) {
        var h = Math.max(6, Math.round(d.value / max * 130));
        return '<div class="bar-col" title="' + esc(d.label) + '：' + d.value + ' 次">' +
                 '<div class="bar-value">' + d.value + '</div>' +
                 '<div class="bar" style="height:' + h + 'px"></div>' +
                 '<div class="bar-label">' + esc(d.label) + '</div>' +
               '</div>';
      }).join('') + '</div>';
    },

    /* ---------- 键值对列表 ---------- */
    KV: function (items) {
      return '<dl class="kv">' + items.map(function (it) {
        return '<dt>' + esc(it.k) + '</dt><dd>' + (it.raw ? it.v : esc(it.v)) + '</dd>';
      }).join('') + '</dl>';
    },

    /* ---------- 提示条 ---------- */
    Notice: function (text, tone) {
      return '<div class="notice" ' + (tone ? 'style="background:var(--c-brand-soft);color:var(--c-brand-strong);border-color:#c3dbf7"' : '') + '>' +
        App.icon('info') + '<div>' + esc(text) + '</div></div>';
    }
  };
})(window.App = window.App || {});
