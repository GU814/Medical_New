/* ==================== 接口占位层 ====================
   ★★★ 接真实后端时，只需要改这一个文件 ★★★

   每个函数都标注了：
     - 真实接口：应该请求的真实后端地址与方法
     - 替换方式：把 App.mock.xxx 换成 fetch / axios 调用即可

   约定：所有函数返回 Promise，失败时 throw Error（页面层统一捕获并展示空态/错误态）。
   页面层不允许直接引用 App.mock，必须走这一层 —— 这样替换后端时改动面最小。 */
(function (App) {
  'use strict';

  /* 真实后端的基址。现在为空，表示走本地 mock。
     接入时改成：App.api.base = 'https://api.your-domain.com' */
  App.api = { base: '', usingMock: true };

  /* 统一的请求封装（接入后端后启用）
     用法示例：
       return App.api.request('/api/records', { method:'GET', params:{page:1} })
     现在未启用，保留在此作为接入模板。 */
  App.api.request = function (path, options) {
    options = options || {};
    var qs = options.params
      ? '?' + Object.keys(options.params).map(function (k) {
          return encodeURIComponent(k) + '=' + encodeURIComponent(options.params[k]);
        }).join('&')
      : '';
    var url = (App.api.base || '') + path + qs;

    // TODO: 接入真实后端时打开下面这段，并删掉各函数里的 mock 分支
    // return fetch(url, {
    //   method: options.method || 'GET',
    //   headers: Object.assign(
    //     { 'Content-Type': 'application/json' },
    //     { Authorization: 'Bearer ' + (App.state.token || '') },   // ← 鉴权位
    //     options.headers || {}
    //   ),
    //   body: options.data ? JSON.stringify(options.data) : undefined
    // }).then(function (res) {
    //   if (!res.ok) throw new Error('HTTP ' + res.status);
    //   return res.json();
    // });

    throw new Error('[api] 尚未接入真实后端：' + url);
  };

  /* ---------- 概览 ---------- */
  // 真实接口：GET /api/overview
  App.api.getOverview = function () {
    return App.mock.delay(650, {
      stats: App.mock.stats,
      trend: App.mock.trend,
      user: App.mock.user,
      recent: App.mock.records.slice(0, 5)
    });
  };

  /* ---------- 问诊会话 ---------- */
  // 真实接口：POST /api/sessions
  App.api.createSession = function () {
    return App.mock.delay(400, { id: 'sess-' + App.uid(), stage: 2 });
  };

  // 真实接口：POST /api/chat（后端为 SSE 流式；此处用一次性返回模拟）
  // 替换要点：把这里换成 SSE 订阅，逐 chunk 追加到气泡，结束时用 end 事件的 reply_clean 定稿。
  App.api.sendMessage = function (sessionId, text) {
    var reply = '收到您的描述：「' + text + '」。\n' +
      '这是原型演示的固定回复。接入后端后，这里会替换为模型流式输出的可见正文（已剥离思维链与结构化 JSON）。';
    return App.mock.delay(1100, { role: 'ai', text: reply, stage: 3 });
  };

  /* ---------- 问诊记录 ---------- */
  // 真实接口：GET /api/records?page=1&size=10&keyword=&status=
  App.api.listRecords = function (params) {
    params = params || {};
    var keyword = (params.keyword || '').trim();
    var status = params.status || 'all';
    var page = params.page || 1;
    var size = params.size || 8;

    var list = App.mock.records.filter(function (r) {
      var okStatus = status === 'all' || r.status === status;
      var okKw = !keyword || r.title.indexOf(keyword) >= 0 || r.dept.indexOf(keyword) >= 0;
      return okStatus && okKw;
    });

    return App.mock.delay(700, {
      total: list.length,
      page: page,
      size: size,
      items: list.slice((page - 1) * size, page * size)
    });
  };

  // 真实接口：GET /api/records/{id}
  App.api.getRecord = function (id) {
    return App.mock.delay(600, App.mock.recordDetail(id));
  };

  // 真实接口：DELETE /api/records/{id}
  App.api.deleteRecord = function (id) {
    return App.mock.delay(500, { ok: true, id: id });
  };

  // 真实接口：GET /api/records/{id}/export?format=pdf
  // 小程序侧最终用 Taro.downloadFile + Taro.openDocument；Web 侧可直接 window.open。
  App.api.exportRecordPdf = function (id) {
    return App.mock.delay(800, { ok: true, url: '#/records/' + id });
  };

  /* ---------- 个人资料 ---------- */
  // 真实接口：GET /auth/me
  App.api.getProfile = function () {
    return App.mock.delay(450, App.mock.user);
  };

  // 真实接口：PUT /auth/profile
  App.api.saveProfile = function (payload) {
    Object.keys(payload).forEach(function (k) { App.mock.user[k] = payload[k]; });
    return App.mock.delay(700, { ok: true, user: App.mock.user });
  };

  /* ---------- 分享 ---------- */
  // 真实接口：GET /api/share/list
  App.api.listShareLinks = function () {
    return App.mock.delay(500, App.mock.shareLinks.slice());
  };

  // 真实接口：POST /api/share  body:{ record_id, ttl_hours }
  App.api.createShare = function (recordId, ttlHours) {
    var rec = null;
    App.mock.records.forEach(function (r) { if (String(r.id) === String(recordId)) rec = r; });
    var link = {
      id: App.mock.shareLinks.length + 1,
      token: App.uid('tk') + App.uid('x'),
      recordId: Number(recordId),
      recordTitle: rec ? rec.title : '未命名记录',
      createdAt: Date.now(),
      expiresAt: Date.now() + (ttlHours || 72) * 3600000,
      views: 0
    };
    App.mock.shareLinks.unshift(link);
    return App.mock.delay(700, link);
  };

  // 真实接口：DELETE /api/share/{token}
  App.api.revokeShare = function (token) {
    App.mock.shareLinks = App.mock.shareLinks.filter(function (l) { return l.token !== token; });
    return App.mock.delay(400, { ok: true, token: token });
  };

  /* ---------- 设置 ---------- */
  // 真实接口：GET /api/settings
  App.api.getSettings = function () {
    return App.mock.delay(300, Object.assign({}, App.mock.settings));
  };

  // 真实接口：PUT /api/settings
  App.api.saveSettings = function (payload) {
    Object.assign(App.mock.settings, payload);
    return App.mock.delay(500, { ok: true, settings: Object.assign({}, App.mock.settings) });
  };

  /* ---------- 会员 ---------- */
  // 真实接口：GET /api/plans
  App.api.listPlans = function () {
    return App.mock.delay(400, App.mock.plans.slice());
  };

  // 真实接口：POST /api/orders（创建支付订单）
  App.api.subscribePlan = function (planId) {
    return App.mock.delay(900, { ok: true, planId: planId, orderNo: 'ORD' + Date.now() });
  };
})(window.App = window.App || {});
