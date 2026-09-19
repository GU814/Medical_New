/* ==================== 页面：智能问诊 ====================
   展示：阶段指示器、对话气泡、快捷提问、免责声明、输入区
   覆盖交互：发送与「正在输入」占位、阶段切换、快捷提问填充、空态引导 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  /* 会话内状态（原型级，刷新即重置） */
  var state = { stage: 2, sending: false, messages: [] };

  App.pages.consult = {
    path: '/consult',
    title: '智能问诊',
    icon: 'chat',
    group: '工作台',
    badge: '',

    render: function () {
      state.messages = App.mock.messages.slice();
      state.stage = 2;

      return '' +
        ui.PageHead({
          title: '智能问诊',
          desc: '5 阶段引导式问诊 · 当前为原型演示，回复内容为固定文本',
          actions: '<button class="btn" data-act="reset">' + App.icon('refresh') + '重新开始</button>'
        }) +

        '<section class="card">' +
          '<div class="card-head">' +
            App.icon('spark') +
            '<span class="t-sub">问诊进度</span>' +
            '<div class="extra"><span class="t-xs t-dim">点击阶段可查看高亮效果（原型演示）</span></div>' +
          '</div>' +
          '<div class="card-body tight">' + stageBar() + '</div>' +

          '<div class="chat">' +
            '<div class="chat-body scroll-y" id="chat-body">' + renderMessages() + '</div>' +
          '</div>' +

          '<div class="card-body composer">' +
            '<div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px" id="quick-area">' +
              App.mock.quickQuestions.map(function (q) {
                return '<button class="chip" data-quick="' + esc(q) + '">' + esc(q) + '</button>';
              }).join('') +
            '</div>' +
            '<div class="composer-row">' +
              '<textarea class="textarea" id="chat-input" rows="2" placeholder="描述您的症状，例如：咳嗽三天，晚上比较厉害…"></textarea>' +
              '<button class="btn btn-primary btn-lg" id="btn-send" style="flex:none">' + App.icon('send') + '发送</button>' +
            '</div>' +
            '<div class="composer-hint">' +
              '<span>Enter 发送，Shift + Enter 换行</span>' +
              '<span id="char-count">0 / 500</span>' +
            '</div>' +
          '</div>' +
        '</section>' +

        '<div style="margin-top:14px">' +
          ui.Notice('本助手提供的信息仅供参考，不能替代医生面诊。如出现持续高热、呼吸困难、胸痛等警示症状，请立即就医。') +
        '</div>';
    },

    mount: function (root) {
      var body = App.qs('#chat-body', root);
      var input = App.qs('#chat-input', root);
      var btn = App.qs('#btn-send', root);
      var counter = App.qs('#char-count', root);
      scrollBottom(body);

      /* 输入区 */
      input.addEventListener('input', function () {
        counter.textContent = input.value.length + ' / 500';
        btn.classList.toggle('is-disabled', !input.value.trim() || state.sending);
      });
      input.addEventListener('keydown', function (e) {
        if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); send(); }
      });
      btn.addEventListener('click', send);

      /* 快捷提问 */
      App.on(root, 'click', '[data-quick]', function (e, el) {
        input.value = el.getAttribute('data-quick');
        counter.textContent = input.value.length + ' / 500';
        btn.classList.remove('is-disabled');
        input.focus();
      });

      /* 阶段切换 */
      App.on(root, 'click', '[data-stage]', function (e, el) {
        state.stage = Number(el.getAttribute('data-stage'));
        App.qs('#stage-bar', root).outerHTML = stageBar();
        App.overlay.toast('已切换到阶段 ' + state.stage + '：' + App.mock.stages[state.stage - 1].name);
      });

      /* 重新开始 */
      App.on(root, 'click', '[data-act="reset"]', function () {
        App.overlay.confirm({ title: '重新开始问诊', text: '当前对话将被清空，确定继续吗？', okText: '清空并重新开始' })
          .then(function (ok) { if (ok) App.router.reload(); });
      });

      function send() {
        var text = input.value.trim();
        if (!text || state.sending) return;

        state.sending = true;
        btn.classList.add('is-disabled');
        input.value = '';
        counter.textContent = '0 / 500';

        appendMessage(body, { role: 'me', text: text, time: Date.now() });
        var typing = appendTyping(body);

        App.api.sendMessage('demo-session', text)
          .then(function (reply) {
            typing.remove();
            appendMessage(body, { role: reply.role, text: reply.text, time: Date.now() });
            if (reply.stage && reply.stage !== state.stage) {
              state.stage = reply.stage;
              var bar = App.qs('#stage-bar', root);
              if (bar) bar.outerHTML = stageBar();
            }
          })
          .catch(function (err) {
            typing.remove();
            App.overlay.toast('发送失败：' + err.message, 'err');
          })
          .then(function () {
            state.sending = false;
            btn.classList.remove('is-disabled');
            scrollBottom(body);
          });
      }
    }
  };

  /* ---------- 片段 ---------- */
  function stageBar() {
    return '<div class="stage-bar" id="stage-bar">' + App.mock.stages.map(function (s, i) {
      var cls = s.key < state.stage ? 'is-done' : (s.key === state.stage ? 'is-current' : '');
      return (i ? '<i class="stage-sep"></i>' : '') +
        '<button class="stage ' + cls + '" data-stage="' + s.key + '">' +
          '<span class="num">' + s.key + '</span>' + esc(s.name) +
        '</button>';
    }).join('') + '</div>';
  }

  function renderMessages() {
    if (!state.messages.length) {
      return ui.Empty({
        icon: 'chat',
        title: '还没有对话',
        desc: '在下方输入框描述您的不适，助手会逐步询问并整理成结构化病历。'
      });
    }
    return state.messages.map(messageHTML).join('');
  }

  function messageHTML(m) {
    var isMe = m.role === 'me';
    return '' +
      '<div class="msg ' + (isMe ? 'me' : 'ai') + '">' +
        '<div class="ava">' + (isMe ? esc(App.mock.user.avatarText) : App.icon('spark')) + '</div>' +
        '<div class="msg-wrap">' +
          '<div class="bubble">' + esc(m.text) + '</div>' +
          '<div class="msg-time">' + App.fmt.time(m.time) + '</div>' +
        '</div>' +
      '</div>';
  }

  function appendMessage(body, m) {
    var wrap = document.createElement('div');
    wrap.innerHTML = messageHTML(m);
    var node = wrap.firstElementChild;
    body.appendChild(node);
    state.messages.push(m);
    scrollBottom(body);
    return node;
  }

  function appendTyping(body) {
    var wrap = document.createElement('div');
    wrap.innerHTML = '' +
      '<div class="msg ai">' +
        '<div class="ava">' + App.icon('spark') + '</div>' +
        '<div class="msg-wrap"><div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div>' +
      '</div>';
    var node = wrap.firstElementChild;
    body.appendChild(node);
    scrollBottom(body);
    return node;
  }

  function scrollBottom(el) {
    if (el) el.scrollTop = el.scrollHeight;
  }
})(window.App = window.App || {});
