/* ==================== 浮层组件 ====================
   Modal / Drawer / Toast / Confirm。
   统一行为：点遮罩关闭、ESC 关闭、关闭后移除 DOM、body 滚动锁定。 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var stack = [];   // 记录已打开的浮层，用于 ESC 逐层关闭

  function lockScroll(on) {
    document.body.style.overflow = on ? 'hidden' : '';
  }

  function push(inst) {
    stack.push(inst);
    lockScroll(true);
  }
  function pop(inst) {
    stack = stack.filter(function (x) { return x !== inst; });
    if (!stack.length) lockScroll(false);
  }

  document.addEventListener('keydown', function (e) {
    if (e.key === 'Escape' && stack.length) {
      e.preventDefault();
      stack[stack.length - 1].close();
    }
  });

  App.overlay = {

    /* ---------- 弹窗 ---------- */
    modal: function (opt) {
      var root = document.createElement('div');
      root.className = 'modal-root';
      root.innerHTML = '' +
        '<div class="modal-mask" data-close></div>' +
        '<div class="modal ' + (opt.size === 'lg' ? 'lg' : '') + '" role="dialog" aria-modal="true">' +
          '<div class="modal-head">' +
            '<span class="t-sub">' + esc(opt.title || '') + '</span>' +
            '<button class="btn btn-ghost btn-icon btn-sm modal-close" data-close aria-label="关闭">' + App.icon('close') + '</button>' +
          '</div>' +
          '<div class="modal-body">' + (opt.body || '') + '</div>' +
          (opt.foot ? '<div class="modal-foot">' + opt.foot + '</div>' : '') +
        '</div>';

      var inst = {
        el: root,
        body: root.querySelector('.modal-body'),
        close: function () {
          if (!root.parentNode) return;
          root.parentNode.removeChild(root);
          pop(inst);
          if (opt.onClose) opt.onClose();
        }
      };

      root.addEventListener('click', function (e) {
        if (e.target.hasAttribute('data-close')) inst.close();
      });

      document.body.appendChild(root);
      push(inst);
      if (opt.onMount) opt.onMount(inst);
      return inst;
    },

    /* ---------- 抽屉 ---------- */
    drawer: function (opt) {
      var root = document.createElement('div');
      root.className = 'drawer-root';
      root.innerHTML = '' +
        '<div class="drawer-mask" data-close></div>' +
        '<aside class="drawer ' + (opt.side === 'left' ? 'left' : '') + '" role="dialog" aria-modal="true">' +
          '<div class="drawer-head">' +
            '<span class="t-sub">' + esc(opt.title || '') + '</span>' +
            '<button class="btn btn-ghost btn-icon btn-sm" data-close style="margin-left:auto" aria-label="关闭">' + App.icon('close') + '</button>' +
          '</div>' +
          '<div class="drawer-body">' + (opt.body || '') + '</div>' +
          (opt.foot ? '<div class="drawer-foot">' + opt.foot + '</div>' : '') +
        '</aside>';

      var inst = {
        el: root,
        body: root.querySelector('.drawer-body'),
        close: function () {
          if (!root.parentNode) return;
          root.parentNode.removeChild(root);
          pop(inst);
          if (opt.onClose) opt.onClose();
        }
      };

      root.addEventListener('click', function (e) {
        if (e.target.hasAttribute('data-close')) inst.close();
      });

      document.body.appendChild(root);
      push(inst);
      if (opt.onMount) opt.onMount(inst);
      return inst;
    },

    /* ---------- 确认框 ---------- */
    confirm: function (opt) {
      return new Promise(function (resolve) {
        var done = false;
        var m = App.overlay.modal({
          title: opt.title || '确认操作',
          body: '<div class="t-body t-muted">' + esc(opt.text || '') + '</div>',
          foot: '' +
            '<button class="btn" data-act="cancel">' + esc(opt.cancelText || '取消') + '</button>' +
            '<button class="btn ' + (opt.danger ? 'btn-danger' : 'btn-primary') + '" data-act="ok">' + esc(opt.okText || '确定') + '</button>',
          onMount: function (inst) {
            App.on(inst.el, 'click', '[data-act="cancel"]', function () {
              done = true; inst.close(); resolve(false);
            });
            App.on(inst.el, 'click', '[data-act="ok"]', function () {
              done = true; inst.close(); resolve(true);
            });
          },
          onClose: function () { if (!done) resolve(false); }
        });
        return m;
      });
    },

    /* ---------- Toast ---------- */
    toast: function (msg, tone) {
      var box = App.qs('.toast-stack');
      if (!box) {
        box = document.createElement('div');
        box.className = 'toast-stack';
        document.body.appendChild(box);
      }
      var el = document.createElement('div');
      el.className = 'toast ' + (tone || '');
      el.innerHTML = (tone === 'ok' ? App.icon('checkCircle') : tone === 'err' ? App.icon('alert') : App.icon('info')) +
                     '<span>' + esc(msg) + '</span>';
      box.appendChild(el);
      setTimeout(function () {
        el.style.transition = 'opacity .2s, transform .2s';
        el.style.opacity = '0';
        el.style.transform = 'translateY(-6px)';
        setTimeout(function () { if (el.parentNode) el.parentNode.removeChild(el); }, 220);
      }, opt_ms(tone));
    }
  };

  function opt_ms(tone) { return tone === 'err' ? 3000 : 2000; }
})(window.App = window.App || {});
