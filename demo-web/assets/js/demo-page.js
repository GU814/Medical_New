/* ==================== 简约 Demo 页逻辑 ====================
   依赖：core/dom.js（App.esc / App.icon / App.qs / App.on / App.copy / App.fmt）
   三个示例：智能问诊对话、结构化报告预览、分享中心。
   能力概览数据与《微信能力对标核查与实施计划.md》一致。 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var qs = App.qs;
  var on = App.on;

  /* ==================== 能力概览 ==================== */
  /* 状态: ok=已实现  warn=部分实现  danger=缺失 */
  var STATUS = {
    ok:     { cls: 'ok',     label: '已实现' },
    warn:   { cls: 'warn',   label: '部分实现' },
    danger: { cls: 'danger', label: '缺失' }
  };

  var CAP_GROUPS = [
    { name: '微信生态基础', icon: 'chat', note: '小程序与登录已跑通，本阶段补齐订阅/位置/客服/分享/二维码', items: [
      ['微信小程序', 'ok'], ['登录授权', 'ok'], ['分享', 'ok'],
      ['微信云开发', 'danger'], ['支付', 'danger'], ['订阅消息', 'ok'], ['二维码触达', 'ok']
    ]},
    { name: '业务能力', icon: 'file', note: 'PDF 报告导出可用，本阶段补齐位置/地图/客服消息', items: [
      ['文件处理（PDF 导出）', 'ok'], ['数据分析', 'warn'],
      ['地图', 'ok'], ['位置', 'ok'], ['音视频', 'danger'],
      ['OCR', 'danger'], ['客服消息', 'ok'], ['内容安全', 'danger']
    ]},
    { name: 'AI 能力融合', icon: 'spark', note: '本项目最强项：双 LLM + RAG + 跨会话长记忆', items: [
      ['大模型接口（双 LLM）', 'ok'], ['RAG 知识库（ChromaDB）', 'ok'],
      ['智能问答（流式 SSE）', 'ok'], ['生成式报告', 'ok'],
      ['AI 工作流（5 阶段状态机）', 'warn'], ['Agent（工具调用）', 'danger'], ['语音与图像识别', 'danger']
    ]},
    { name: '增长与运营', icon: 'star', note: '留存底座已有，订阅消息打通私域触达', items: [
      ['社交传播（分享链接）', 'ok'], ['用户留存（续诊 + 长记忆）', 'warn'],
      ['私域触达', 'warn'], ['活动运营', 'danger'], ['会员体系', 'danger'], ['裂变设计', 'danger']
    ]},
    { name: '工程与工具', icon: 'cog', note: '接口联调与审计日志扎实，测试覆盖已扩展', items: [
      ['接口联调（Swagger /docs）', 'ok'], ['日志监控（脱敏 + 审计）', 'ok'],
      ['自动化测试', 'ok'], ['AI 辅助开发', 'warn'],
      ['MCP', 'danger'], ['A/B 测试', 'danger']
    ]}
  ];

  function countAll() {
    var c = { ok: 0, warn: 0, danger: 0, total: 0 };
    CAP_GROUPS.forEach(function (g) {
      g.items.forEach(function (it) { c[it[1]]++; c.total++; });
    });
    return c;
  }

  function renderCapStats() {
    var c = countAll();
    var box = qs('#cap-stats');
    if (!box) return;
    var stats = [
      ['能力核查项', c.total, '', 'grid', ''],
      ['已实现', c.ok, '项', 'checkCircle', 'tone-accent'],
      ['部分实现', c.warn, '项', 'alert', 'tone-warn'],
      ['待建设', c.danger, '项', 'info', 'tone-danger']
    ];
    box.innerHTML = stats.map(function (s) {
      return '<div class="card stat card-hover">' +
        '<div class="stat-label"><span class="stat-icon ' + s[4] + '">' + App.icon(s[3]) + '</span>' + esc(s[0]) + '</div>' +
        '<div class="stat-value">' + s[1] + '<span class="unit">' + s[2] + '</span></div>' +
      '</div>';
    }).join('');
  }

  function renderCapGrid() {
    var grid = qs('#cap-grid');
    if (!grid) return;
    grid.innerHTML = CAP_GROUPS.map(function (g) {
      var rows = g.items.map(function (it) {
        var st = STATUS[it[1]];
        return '<div class="cap-item">' +
          '<span class="name">' + esc(it[0]) + '</span>' +
          '<span class="badge ' + st.cls + '"><span class="dot"></span>' + st.label + '</span>' +
        '</div>';
      }).join('');
      return '<div class="card card-hover cap-card">' +
        '<div class="card-head">' + App.icon(g.icon) + '<span class="t-sub">' + esc(g.name) + '</span></div>' +
        '<div class="card-body">' +
          '<div class="cap-note">' + esc(g.note) + '</div>' + rows +
        '</div>' +
      '</div>';
    }).join('');
  }

  /* ==================== 示例 1：智能问诊对话 ==================== */
  var STAGES = ['基本信息', '主诉现病史', '既往史', '系统回顾', '完成'];
  var QUICK = ['我最近咳嗽三天了', '夜间咳嗽比较明显', '有高血压，在吃氨氯地平'];
  /* 依次回复并推进阶段；走到尽头后循环兜底回复 */
  var REPLIES = [
    { stage: 2, text: '了解，已记录。请问有发热、咽痛或流涕吗？咳嗽是干咳还是有痰？' },
    { stage: 3, text: '收到。夜间加重伴咽痒，倾向呼吸道刺激。既往有无慢性病？目前是否规律服药？' },
    { stage: 5, text: '好的，高血压用药已记录，信息采集完成。正在为你整理结构化病历草稿——可在下方「结构化报告」示例中查看样式。' }
  ];
  var FALLBACK = '本次为纯前端演示，回复为固定文本；完整原型见 index.html，接入真实模型只需替换 assets/js/api/index.js。';

  var chat = { stage: 1, step: 0, sending: false };

  function stageBarHTML() {
    return '<div class="stage-bar">' + STAGES.map(function (name, i) {
      var key = i + 1;
      var cls = key < chat.stage ? 'is-done' : (key === chat.stage ? 'is-current' : '');
      return (i ? '<i class="stage-sep"></i>' : '') +
        '<span class="stage ' + cls + '"><span class="num">' + key + '</span>' + esc(name) + '</span>';
    }).join('') + '</div>';
  }

  function bubbleHTML(m) {
    var isMe = m.role === 'me';
    return '<div class="msg ' + (isMe ? 'me' : 'ai') + '">' +
      '<div class="ava">' + (isMe ? '我' : App.icon('spark')) + '</div>' +
      '<div class="msg-wrap">' +
        '<div class="bubble">' + esc(m.text) + '</div>' +
        '<div class="msg-time">' + App.fmt.time(m.time) + '</div>' +
      '</div></div>';
  }

  function appendMsg(body, m) {
    var wrap = document.createElement('div');
    wrap.innerHTML = bubbleHTML(m);
    var node = wrap.firstElementChild;
    body.appendChild(node);
    body.scrollTop = body.scrollHeight;
    return node;
  }

  function typingNode(body) {
    var wrap = document.createElement('div');
    wrap.innerHTML = '<div class="msg ai"><div class="ava">' + App.icon('spark') + '</div>' +
      '<div class="msg-wrap"><div class="bubble"><span class="typing"><i></i><i></i><i></i></span></div></div></div>';
    var node = wrap.firstElementChild;
    body.appendChild(node);
    body.scrollTop = body.scrollHeight;
    return node;
  }

  function renderStage() {
    var el = qs('#demo-stage');
    if (el) el.innerHTML = stageBarHTML();
  }

  function initChat() {
    chat.stage = 1; chat.step = 0; chat.sending = false;
    renderStage();

    var body = qs('#demo-chat-body');
    body.innerHTML = '';
    appendMsg(body, {
      role: 'ai', time: Date.now(),
      text: '您好，我是医学问诊助手。请简单描述您的不适，我会分 5 个阶段引导您完成问诊，并整理成结构化病历。'
    });

    qs('#demo-quick').innerHTML = QUICK.map(function (q) {
      return '<button class="chip" data-quick="' + esc(q) + '">' + esc(q) + '</button>';
    }).join('');
  }

  function sendChat() {
    var input = qs('#demo-input');
    var btn = qs('#demo-send');
    var text = (input.value || '').trim();
    if (!text || chat.sending) return;

    chat.sending = true;
    btn.classList.add('is-disabled');
    input.value = '';
    qs('#demo-count').textContent = '0 / 500';

    var body = qs('#demo-chat-body');
    appendMsg(body, { role: 'me', text: text, time: Date.now() });
    var typing = typingNode(body);

    var step = chat.step < REPLIES.length ? REPLIES[chat.step] : null;
    var delay = 700 + Math.random() * 500;

    setTimeout(function () {
      typing.remove();
      var replyText = step ? step.text : FALLBACK;
      appendMsg(body, { role: 'ai', text: replyText, time: Date.now() });
      if (step) {
        chat.step++;
        chat.stage = step.stage;
        renderStage();
      }
      chat.sending = false;
      btn.classList.remove('is-disabled');
      body.scrollTop = body.scrollHeight;
    }, delay);
  }

  function initChatEvents(root) {
    var input = qs('#demo-input');
    var btn = qs('#demo-send');

    input.addEventListener('input', function () {
      qs('#demo-count').textContent = input.value.length + ' / 500';
      btn.classList.toggle('is-disabled', !input.value.trim() || chat.sending);
    });
    input.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendChat(); }
    });
    btn.addEventListener('click', sendChat);

    on(root, 'click', '[data-quick]', function (e, el) {
      input.value = el.getAttribute('data-quick');
      qs('#demo-count').textContent = input.value.length + ' / 500';
      btn.classList.remove('is-disabled');
      input.focus();
    });

    on(root, 'click', '[data-act="chat-reset"]', function () { initChat(); });
  }

  /* ==================== 示例 2：结构化报告预览 ==================== */
  var REPORT_HTML =
    '<h4>基本信息</h4>' +
    '<p>张三（示例数据） · 男 · 34 岁 · 问诊时间：' + App.fmt.date(new Date()) + '</p>' +
    '<h4>主诉</h4><p>咳嗽 3 天，夜间加重。</p>' +
    '<h4>现病史</h4><p>3 天前受凉后出现咳嗽，干咳为主，夜间明显，偶有咽痒；无发热、无胸痛、无呼吸困难。</p>' +
    '<h4>既往史</h4><p>高血压病史 2 年，规律服用氨氯地平，血压控制可。</p>' +
    '<h4>初步评估</h4><p>急性上呼吸道感染可能性大；高血压为共病管理项。</p>' +
    '<h4>处理建议</h4><p>1. 多饮水、注意休息，避免刺激性饮食；<br>2. 咳嗽超过 1 周或出现发热、咳血、呼吸困难请及时就诊；<br>3. 高血压继续规律服药并监测血压。</p>' +
    '<h4>声明</h4><p>本报告由 AI 生成，仅供参考，不能替代医生面诊。</p>';

  function reportEmptyHTML() {
    return '<div class="empty">' +
      '<div class="empty-icon">' + App.icon('file') + '</div>' +
      '<div class="empty-title">尚未生成报告</div>' +
      '<div class="empty-desc">点击右上角「生成报告」，查看结构化病历的排版样式。</div>' +
    '</div>';
  }

  function generateReport() {
    var body = qs('#demo-report-body');
    var btn = qs('#demo-report-btn');
    btn.disabled = true;
    btn.textContent = '生成中…';
    body.innerHTML =
      '<div class="sk sk-line mid"></div><div class="sk sk-line"></div>' +
      '<div class="sk sk-line"></div><div class="sk sk-line short"></div>' +
      '<div class="sk sk-block" style="margin-top:10px"></div>';

    setTimeout(function () {
      body.innerHTML = '<div class="report">' + REPORT_HTML + '</div>';
      btn.disabled = false;
      btn.textContent = '重新生成';
    }, 900);
  }

  /* ==================== 示例 3：分享中心 ==================== */
  var SHARE = {
    url: 'https://demo.medbot.cn/s/x7Kp2a',
    created: '2026-09-19',
    views: 12,
    alive: true
  };

  function shareRowHTML() {
    if (!SHARE.alive) {
      return '<div class="empty">' +
        '<div class="empty-icon">' + App.icon('share') + '</div>' +
        '<div class="empty-title">暂无分享链接</div>' +
        '<div class="empty-desc">撤销后链接立即失效；真实环境由后端 /api/share 签发带 token 的脱敏链接。</div>' +
        '<div class="empty-actions"><button class="btn btn-primary btn-sm" data-act="share-create">新建分享</button></div>' +
      '</div>';
    }
    return '<div class="row-list">' +
      '<div class="row-item">' +
        '<div class="main">' +
          '<div class="title">感冒问诊 · 结构化报告</div>' +
          '<div class="sub t-mono">' + esc(SHARE.url) + '</div>' +
        '</div>' +
        '<div class="side">' +
          '<span class="badge ok"><span class="dot"></span>有效 · 7 天</span>' +
          '<span class="badge"><span class="dot"></span>浏览 ' + SHARE.views + '</span>' +
          '<button class="btn btn-sm" data-act="share-copy">复制</button>' +
          '<button class="btn btn-sm" data-act="share-qr">小程序码</button>' +
          '<button class="btn btn-sm btn-danger" data-act="share-revoke">撤销</button>' +
        '</div>' +
      '</div>' +
    '</div>';
  }

  function renderShare() { qs('#demo-share-body').innerHTML = shareRowHTML(); }

  /* ---------- 轻量 Toast ---------- */
  function toast(msg) {
    var stack = qs('.toast-stack');
    if (!stack) {
      stack = document.createElement('div');
      stack.className = 'toast-stack';
      document.body.appendChild(stack);
    }
    var t = document.createElement('div');
    t.className = 'toast ok';
    t.textContent = msg;
    stack.appendChild(t);
    setTimeout(function () { t.remove(); }, 1800);
  }

  /* ==================== 启动 ==================== */
  function boot() {
    renderCapStats();
    renderCapGrid();
    initChat();
    initChatEvents(document);

    qs('#demo-report-body').innerHTML = reportEmptyHTML();
    qs('#demo-report-btn').addEventListener('click', generateReport);

    renderShare();
    on(document, 'click', '[data-act="share-copy"]', function () {
      App.copy(SHARE.url);
      toast('链接已复制到剪贴板');
    });
    on(document, 'click', '[data-act="share-qr"]', function () {
      var wrap = qs('#demo-qr-wrap');
      var show = wrap.style.display === 'none';
      wrap.style.display = show ? '' : 'none';
    });
    on(document, 'click', '[data-act="share-revoke"]', function () {
      SHARE.alive = false;
      qs('#demo-qr-wrap').style.display = 'none';
      renderShare();
      toast('分享已撤销');
    });
    on(document, 'click', '[data-act="share-create"]', function () {
      SHARE.alive = true;
      renderShare();
      toast('已创建新分享链接');
    });

    var notice = qs('#demo-notice');
    if (notice) notice.innerHTML = App.icon('alert', 'ico') +
      '<span>本页所有数据为本地模拟，仅用于演示页面结构与交互；真实问诊请就医。如出现持续高热、呼吸困难、胸痛等警示症状，请立即就医。</span>';
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot);
  } else {
    boot();
  }
})(window.App = window.App || {});
