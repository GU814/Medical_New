/* ==================== 基础工具 ====================
   极小依赖的工具集：DOM 查询、事件委托、HTML 转义、图标、格式化。
   没有任何第三方库。 */
(function (App) {
  'use strict';

  /* ---------- HTML 转义（所有插入 innerHTML 的动态文本都必须过这里） ---------- */
  App.esc = function (s) {
    if (s === null || s === undefined) return '';
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;')
      .replace(/'/g, '&#39;');
  };

  /* ---------- 查询 ---------- */
  App.qs = function (sel, root) { return (root || document).querySelector(sel); };
  App.qsa = function (sel, root) {
    return Array.prototype.slice.call((root || document).querySelectorAll(sel));
  };

  /* ---------- 事件委托 ---------- */
  App.on = function (root, evt, sel, handler) {
    root.addEventListener(evt, function (e) {
      var t = e.target;
      if (!t || !t.closest) return;
      var hit = t.closest(sel);
      if (hit && root.contains(hit)) handler.call(hit, e, hit);
    });
  };

  /* ---------- class 拼接 ---------- */
  App.cx = function () {
    return Array.prototype.filter.call(arguments, function (x) { return !!x; }).join(' ');
  };

  /* ---------- 图标（内联 SVG，stroke 风格） ---------- */
  var ICONS = {
    grid:  '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/>',
    chat:  '<path d="M21 12a8 8 0 0 1-8 8H8l-5 3 1.2-4.2A8 8 0 1 1 21 12z"/>',
    list:  '<path d="M8 6h13M8 12h13M8 18h13M3.5 6h.01M3.5 12h.01M3.5 18h.01"/>',
    user:  '<circle cx="12" cy="8" r="4"/><path d="M4.5 20.5c.6-4 3.9-6 7.5-6s6.9 2 7.5 6"/>',
    share: '<circle cx="18" cy="5.5" r="2.8"/><circle cx="6" cy="12" r="2.8"/><circle cx="18" cy="18.5" r="2.8"/><path d="M8.4 13.6l7.2 3.6M15.6 7.2l-7.2 3.6"/>',
    cog:   '<circle cx="12" cy="12" r="3.2"/><path d="M12 2.5v3M12 18.5v3M2.5 12h3M18.5 12h3M5.2 5.2l2.1 2.1M16.7 16.7l2.1 2.1M18.8 5.2l-2.1 2.1M7.3 16.7l-2.1 2.1"/>',
    menu:  '<path d="M4 7h16M4 12h16M4 17h16"/>',
    close: '<path d="M6 6l12 12M18 6L6 18"/>',
    search:'<circle cx="11" cy="11" r="6.5"/><path d="M16 16l4.5 4.5"/>',
    bell:  '<path d="M18 15V10a6 6 0 1 0-12 0v5l-1.5 3h15L18 15z"/><path d="M10 21h4"/>',
    plus:  '<path d="M12 5v14M5 12h14"/>',
    more:  '<circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/>',
    eye:   '<path d="M2.5 12S6 5.5 12 5.5 21.5 12 21.5 12 18 18.5 12 18.5 2.5 12 2.5 12z"/><circle cx="12" cy="12" r="3"/>',
    send:  '<path d="M4.5 12l15-7.5-7.5 15-2-6.5-5.5-1z"/>',
    copy:  '<rect x="9" y="9" width="11" height="11" rx="2"/><path d="M5 15V6a2 2 0 0 1 2-2h8"/>',
    trash: '<path d="M4 7h16M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M6 7l1 13h10l1-13"/>',
    download:'<path d="M12 3v12M7 11l5 5 5-5M4 21h16"/>',
    qr:    '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><path d="M14 14h3v3h-3zM19 19h2v2h-2z"/>',
    check: '<path d="M5 13l4 4L19 7"/>',
    checkCircle:'<circle cx="12" cy="12" r="9"/><path d="M8 12.5l2.5 2.5L16 9.5"/>',
    alert: '<path d="M12 3.5L1.8 20.5h20.4L12 3.5z"/><path d="M12 10v4M12 17h.01"/>',
    info:  '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/>',
    inbox: '<path d="M3 13l3-8h12l3 8v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-6z"/><path d="M3 13h5l1 2.5h6l1-2.5h5"/>',
    refresh:'<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 5v6h-6"/>',
    filter:'<path d="M3 5h18l-7 8v6l-4 2v-8L3 5z"/>',
    file:  '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5z"/><path d="M14 3v5h5"/>',
    clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3.5 2"/>',
    spark: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8L12 3z"/>',
    arrowLeft: '<path d="M19 12H5M11 6l-6 6 6 6"/>',
    arrowRight:'<path d="M5 12h14M13 6l6 6-6 6"/>',
    star:  '<path d="M12 3.5l2.6 5.4 5.9.8-4.3 4.1 1.1 5.8L12 16.9l-5.3 2.7 1.1-5.8L3.5 9.7l5.9-.8L12 3.5z"/>'
  };

  App.icon = function (name, cls) {
    var d = ICONS[name] || ICONS.info;
    return '<span class="ico ' + (cls || '') + '" aria-hidden="true">' +
      '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" ' +
      'stroke-linecap="round" stroke-linejoin="round">' + d + '</svg></span>';
  };

  /* ---------- 格式化 ---------- */
  App.fmt = {
    pad: function (n) { return n < 10 ? '0' + n : '' + n; },
    time: function (d) {
      d = d instanceof Date ? d : new Date(d);
      return App.fmt.pad(d.getHours()) + ':' + App.fmt.pad(d.getMinutes());
    },
    date: function (d) {
      d = d instanceof Date ? d : new Date(d);
      return d.getFullYear() + '-' + App.fmt.pad(d.getMonth() + 1) + '-' + App.fmt.pad(d.getDate());
    },
    ago: function (d) {
      var diff = (Date.now() - new Date(d).getTime()) / 1000;
      if (diff < 60) return '刚刚';
      if (diff < 3600) return Math.floor(diff / 60) + ' 分钟前';
      if (diff < 86400) return Math.floor(diff / 3600) + ' 小时前';
      if (diff < 2592000) return Math.floor(diff / 86400) + ' 天前';
      return App.fmt.date(d);
    }
  };

  App.uid = function (prefix) {
    return (prefix || 'id') + '-' + Math.random().toString(36).slice(2, 9);
  };

  /* ---------- 复制到剪贴板（带降级） ---------- */
  App.copy = function (text) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(text).catch(function () { App.copyFallback(text); });
    }
    App.copyFallback(text);
    return Promise.resolve();
  };
  App.copyFallback = function (text) {
    var ta = document.createElement('textarea');
    ta.value = text;
    ta.style.position = 'fixed';
    ta.style.opacity = '0';
    document.body.appendChild(ta);
    ta.select();
    try { document.execCommand('copy'); } catch (e) { /* 忽略 */ }
    document.body.removeChild(ta);
  };
})(window.App = window.App || {});
