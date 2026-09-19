/* ==================== 哈希路由 ====================
   路由契约：
     {
       path:   '/records/:id',      // 支持 :param
       title:  '记录详情',
       icon:   'list',
       group:  '工作台',
       hidden: true,                // 不出现在侧边导航
       render: function(params){ return '<html>' },   // 同步：骨架 / 静态结构
       mount:  function(root, params){  // 异步：取数 + 绑定事件
     }
   用法：App.router.register(route).init(outletEl).start('/dashboard') */
(function (App) {
  'use strict';

  var routes = [];
  var listeners = [];
  var outlet = null;
  var current = null;
  var defaultPath = '/dashboard';

  function currentPath() {
    var h = location.hash || '';
    if (h.charAt(0) === '#') h = h.slice(1);
    return h || defaultPath;
  }

  /* pattern '/records/:id' vs path '/records/12' -> { id:'12' } 或 null */
  function match(pattern, path) {
    var pp = pattern.split('/');
    var sp = path.split('/');
    if (pp.length !== sp.length) return null;
    var params = {};
    for (var i = 0; i < pp.length; i++) {
      if (pp[i].charAt(0) === ':') {
        params[pp[i].slice(1)] = decodeURIComponent(sp[i]);
      } else if (pp[i] !== sp[i]) {
        return null;
      }
    }
    return params;
  }

  function find(path) {
    for (var i = 0; i < routes.length; i++) {
      var params = match(routes[i].path, path);
      if (params) return { route: routes[i], params: params };
    }
    return null;
  }

  /* 把 '/records?kw=abc' 拆成 path + query */
  function parse(raw) {
    var i = raw.indexOf('?');
    var path = i >= 0 ? raw.slice(0, i) : raw;
    var query = {};
    if (i >= 0) {
      raw.slice(i + 1).split('&').forEach(function (kv) {
        if (!kv) return;
        var p = kv.split('=');
        query[decodeURIComponent(p[0])] = decodeURIComponent(p[1] || '');
      });
    }
    return { path: path, query: query };
  }

  function resolve() {
    var parsed = parse(currentPath());
    var hit = find(parsed.path);
    if (!hit) { location.replace('#' + defaultPath); return; }

    current = { path: parsed.path, query: parsed.query, route: hit.route, params: hit.params };

    // 1) 同步渲染骨架
    outlet.innerHTML = typeof hit.route.render === 'function'
      ? (hit.route.render(hit.params) || '')
      : '';
    outlet.scrollTop = 0;

    // 2) 异步装载数据并绑定事件
    if (typeof hit.route.mount === 'function') {
      Promise.resolve()
        .then(function () { return hit.route.mount(outlet, hit.params); })
        .catch(function (err) {
          console.error('[router] 页面装载失败', err);
          outlet.innerHTML = App.ui.Empty({
            title: '页面加载失败',
            desc: String((err && err.message) || err),
            action: '<button class="btn btn-primary" data-act="retry">重试</button>'
          });
          App.on(outlet, 'click', '[data-act="retry"]', function () { resolve(); });
        });
    }

    listeners.forEach(function (fn) { fn(current); });
  }

  App.router = {
    register: function (route) { routes.push(route); return this; },
    all: function () { return routes.slice(); },
    init: function (el) {
      outlet = el;
      window.addEventListener('hashchange', resolve);
      return this;
    },
    start: function (def) {
      if (def) defaultPath = def;
      if (!location.hash) location.replace('#' + defaultPath);
      resolve();
      return this;
    },
    navigate: function (path) {
      if (currentPath() === path) { resolve(); return; }
      location.hash = path;
    },
    reload: resolve,
    current: function () { return current; },
    onChange: function (fn) { listeners.push(fn); return this; }
  };
})(window.App = window.App || {});
