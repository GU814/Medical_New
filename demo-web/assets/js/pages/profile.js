/* ==================== 页面：个人中心 ====================
   展示：头像卡、基本信息表单、健康档案表单、保存/重置操作
   覆盖交互：表单校验、保存中禁用态、Toast、开关项、加载占位 */
(function (App) {
  'use strict';

  var esc = App.esc;
  var ui = App.ui;

  App.pages = App.pages || {};

  App.pages.profile = {
    path: '/profile',
    title: '个人中心',
    icon: 'user',
    group: '我的',

    render: function () {
      return '' +
        ui.PageHead({ title: '个人中心', desc: '基本信息与健康档案（保存为原型演示，不会真正提交）' }) +
        '<div class="detail-grid">' +
          '<div id="side-area">' + ui.Skeleton.block(200) + '</div>' +
          '<div id="form-area">' + ui.Skeleton.block(320) + '</div>' +
        '</div>';
    },

    mount: function (root) {
      bind(root);
      return App.api.getProfile().then(function (u) { fill(root, u); });
    }
  };

  function fill(root, u) {
    App.qs('#side-area', root).innerHTML = '' +
      ui.Card({
        body: '<div style="display:flex;gap:14px;align-items:center">' +
                '<div class="avatar lg">' + esc(u.avatarText) + '</div>' +
                '<div style="min-width:0">' +
                  '<div class="t-sub">' + esc(u.name) + '</div>' +
                  '<div class="t-xs t-dim">' + esc(u.gender) + ' · ' + u.age + ' 岁</div>' +
                '</div>' +
              '</div>' +
              '<div style="height:14px"></div>' +
              ui.KV([
                { k: '账号标识', v: u.openid_masked },
                { k: '注册时间', v: u.created_at },
                { k: '当前版本', v: u.tier },
                { k: '累计问诊', v: u.total_consults + ' 次' }
              ])
      });

    App.qs('#form-area', root).innerHTML = '' +
      '<form id="profile-form" novalidate>' +
        ui.Card({
          icon: 'user', title: '基本信息',
          body: '<div class="grid grid-2">' +
            field('姓名', 'name', '<input class="input" name="name" value="' + esc(u.name) + '" placeholder="请输入姓名" />', '必填，2–20 个字符') +
            field('手机号', 'phone', '<input class="input" name="phone" value="' + esc(u.phone) + '" placeholder="11 位手机号" />', '用于接收复诊提醒') +
            field('性别', 'gender', '<select class="select" name="gender">' +
              ['女', '男', '其他'].map(function (g) {
                return '<option' + (u.gender === g ? ' selected' : '') + '>' + g + '</option>';
              }).join('') + '</select>') +
            field('年龄', 'age', '<input class="input" name="age" type="number" min="0" max="120" value="' + u.age + '" />', '0–120') +
          '</div>'
        }) +
        '<div style="height:16px"></div>' +
        ui.Card({
          icon: 'file', title: '健康档案',
          body: '<div style="display:flex;flex-direction:column;gap:14px">' +
            field('过敏史', 'allergies', '<input class="input" name="allergies" value="' + esc(u.allergies) + '" placeholder="如：青霉素" />') +
            field('既往病史', 'chronic', '<input class="input" name="chronic" value="' + esc(u.chronic) + '" placeholder="如：过敏性鼻炎" />') +
            '<label class="switch"><input type="checkbox" name="shareForResearch" /> <span class="track"></span>' +
              '<span class="t-small">允许匿名数据用于模型优化</span></label>' +
          '</div>'
        }) +
        '<div style="height:16px"></div>' +
        '<div style="display:flex;gap:8px;justify-content:flex-end">' +
          '<button type="button" class="btn" data-act="reset">重置</button>' +
          '<button type="submit" class="btn btn-primary" id="btn-save">保存修改</button>' +
        '</div>' +
      '</form>';
  }

  function field(label, key, control, hint) {
    return '<div class="field" data-field="' + key + '">' +
      '<label>' + esc(label) + '</label>' + control +
      (hint ? '<span class="hint">' + esc(hint) + '</span>' : '') +
      '<span class="err" data-err></span>' +
    '</div>';
  }

  /* ---------- 校验与提交 ---------- */
  function validate(form) {
    var ok = true;
    var rules = [
      { key: 'name',  test: function (v) { return v.length >= 2 && v.length <= 20; }, msg: '姓名需为 2–20 个字符' },
      { key: 'phone', test: function (v) { return /^1\d{10}$/.test(v) || /^\d{3}\*{4}\d{4}$/.test(v); }, msg: '请填写 11 位手机号' },
      { key: 'age',   test: function (v) { var n = Number(v); return n >= 0 && n <= 120; }, msg: '年龄需在 0–120 之间' }
    ];

    rules.forEach(function (r) {
      var wrap = form.querySelector('[data-field="' + r.key + '"]');
      var input = form.elements[r.key];
      var err = wrap.querySelector('[data-err]');
      var pass = r.test((input.value || '').trim());
      wrap.classList.toggle('is-invalid', !pass);
      err.textContent = pass ? '' : r.msg;
      if (!pass && ok) { input.focus(); ok = false; }
    });

    return ok;
  }

  function bind(root) {
    App.on(root, 'submit', '#profile-form', function (e, form) {
      e.preventDefault();
      if (!validate(form)) { App.overlay.toast('请先修正标红的字段', 'err'); return; }

      var btn = App.qs('#btn-save', form);
      btn.classList.add('is-disabled');
      btn.textContent = '保存中…';

      var payload = {
        name: form.elements.name.value.trim(),
        phone: form.elements.phone.value.trim(),
        gender: form.elements.gender.value,
        age: Number(form.elements.age.value),
        allergies: form.elements.allergies.value.trim(),
        chronic: form.elements.chronic.value.trim()
      };

      App.api.saveProfile(payload)
        .then(function () {
          App.overlay.toast('资料已保存', 'ok');
          App.mock.user.avatarText = payload.name.charAt(0);
        })
        .catch(function (err) { App.overlay.toast('保存失败：' + err.message, 'err'); })
        .then(function () {
          btn.classList.remove('is-disabled');
          btn.textContent = '保存修改';
        });
    });

    App.on(root, 'click', '[data-act="reset"]', function () { App.router.reload(); });
  }
})(window.App = window.App || {});
