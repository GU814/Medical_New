/* ==================== 模拟数据 ====================
   全部写死，仅用于确认页面结构与交互。接真实后端时这一层可直接删除。 */
(function (App) {
  'use strict';

  var now = Date.now();
  var DAY = 86400000;

  App.mock = {
    /* ---------- 当前用户 ---------- */
    user: {
      id: 1,
      name: '林静',
      gender: '女',
      age: 34,
      phone: '138****6721',
      avatarText: '林',
      openid_masked: 'oXy9****3fA',
      created_at: '2026-03-12',
      allergies: '青霉素（皮试阳性）',
      chronic: '过敏性鼻炎',
      tier: '免费版',
      total_consults: 128
    },

    /* ---------- 概览统计 ---------- */
    stats: {
      total: 128,
      totalDelta: 12,
      month: 23,
      monthDelta: 8,
      reports: 96,
      reportsDelta: -3,
      avgMinutes: 8.4,
      avgDelta: -0.6
    },

    /* ---------- 近 7 日问诊量 ---------- */
    trend: [
      { label: '周一', value: 12 }, { label: '周二', value: 18 },
      { label: '周三', value: 9 },  { label: '周四', value: 24 },
      { label: '周五', value: 21 }, { label: '周六', value: 15 },
      { label: '周日', value: 11 }
    ],

    /* ---------- 问诊记录 ---------- */
    records: [
      { id: 10241, title: '持续性咳嗽伴低烧 3 天', stage: '已完成', status: 'done', date: now - 1 * DAY, doctor: 'AI 助手', dept: '呼吸内科', duration: '9 分钟' },
      { id: 10238, title: '餐后上腹胀痛、反酸', stage: '已完成', status: 'done', date: now - 3 * DAY, doctor: 'AI 助手', dept: '消化内科', duration: '7 分钟' },
      { id: 10235, title: '右膝关节运动后疼痛', stage: '进行中', status: 'doing', date: now - 5 * DAY, doctor: 'AI 助手', dept: '骨科', duration: '5 分钟' },
      { id: 10231, title: '入睡困难、夜间易醒', stage: '已完成', status: 'done', date: now - 8 * DAY, doctor: 'AI 助手', dept: '神经内科', duration: '12 分钟' },
      { id: 10227, title: '皮肤散在红疹伴瘙痒', stage: '已完成', status: 'done', date: now - 12 * DAY, doctor: 'AI 助手', dept: '皮肤科', duration: '6 分钟' },
      { id: 10222, title: '头晕、体位变化时加重', stage: '已完成', status: 'done', date: now - 15 * DAY, doctor: 'AI 助手', dept: '耳鼻喉科', duration: '8 分钟' },
      { id: 10218, title: '咽痛、声音嘶哑 2 天', stage: '已完成', status: 'done', date: now - 19 * DAY, doctor: 'AI 助手', dept: '耳鼻喉科', duration: '5 分钟' },
      { id: 10214, title: '体检报告解读咨询', stage: '已完成', status: 'done', date: now - 24 * DAY, doctor: 'AI 助手', dept: '全科', duration: '11 分钟' },
      { id: 10209, title: '儿童发热 38.5℃ 处理咨询', stage: '已完成', status: 'done', date: now - 28 * DAY, doctor: 'AI 助手', dept: '儿科', duration: '10 分钟' },
      { id: 10205, title: '长期伏案后颈肩僵硬', stage: '已完成', status: 'done', date: now - 33 * DAY, doctor: 'AI 助手', dept: '康复科', duration: '7 分钟' },
      { id: 10201, title: '饭后血糖偏高随访', stage: '已完成', status: 'done', date: now - 40 * DAY, doctor: 'AI 助手', dept: '内分泌科', duration: '9 分钟' },
      { id: 10197, title: '季节性打喷嚏、鼻塞加重', stage: '已完成', status: 'done', date: now - 46 * DAY, doctor: 'AI 助手', dept: '耳鼻喉科', duration: '6 分钟' }
    ],

    /* ---------- 记录详情（按 id 返回，找不到则用第一条） ---------- */
    recordDetail: function (id) {
      var r = null;
      App.mock.records.forEach(function (x) { if (String(x.id) === String(id)) r = x; });
      r = r || App.mock.records[0];
      return {
        id: r.id,
        title: r.title,
        dept: r.dept,
        date: r.date,
        duration: r.duration,
        status: r.status,
        patient: { name: App.mock.user.name, gender: '女', age: 34, height: '162 cm', weight: '54 kg', allergy: '青霉素（皮试阳性）' },
        chief: '咳嗽 3 天，夜间加重，伴低烧 37.8℃，咽部轻微疼痛，无胸闷气促。自服感冒药后无明显缓解。',
        history: '过敏性鼻炎 5 年；否认高血压、糖尿病；否认手术史；否认吸烟史；家族无特殊遗传病史。',
        report:
          '一、主诉与现病史\n患者女性，34 岁，因「咳嗽 3 天伴低烧」就诊。咳嗽以干咳为主，夜间及清晨明显加重，' +
          '体温最高 37.8℃，伴咽部轻微疼痛。无咳痰、咯血、胸痛、气促。已自行服用复方感冒制剂 2 天，症状无明显改善。\n\n' +
          '二、可能的判断方向\n1. 上呼吸道感染后咳嗽：最常见，多为病毒感染后气道高反应性，病程常持续 1–3 周。\n' +
          '2. 急性支气管炎：若咳嗽持续加重或出现黄脓痰需考虑。\n' +
          '3. 过敏性因素：患者有过敏性鼻炎史，夜间加重需警惕咳嗽变异性哮喘或鼻后滴漏。\n\n' +
          '三、建议进一步确认的信息\n咳嗽性质（干咳 / 有痰、痰色）、体温曲线、是否伴喘息或胸闷、近期接触史与用药史。\n\n' +
          '四、生活与护理建议\n保证休息与饮水量；室内湿度保持在 40%–60%；避免冷空气与油烟刺激；' +
          '可用温盐水漱口缓解咽痛；暂停自行叠加多种复方感冒药。\n\n' +
          '五、需要及时就医的警示信号\n出现持续高热（≥38.5℃ 超过 3 天）、呼吸困难、胸痛、咯血、或症状超过 3 周无好转，' +
          '请尽快到呼吸内科门诊面诊，必要时完善胸片与血常规检查。\n\n' +
          '免责声明：本报告由 AI 医学问诊助手生成，仅供参考，不能替代医生面诊。请务必咨询专业医疗人员。',
        summary: ['咳嗽 3 天，夜间加重', '低烧 37.8℃，咽部轻痛', '过敏性鼻炎史 5 年', '自服感冒药无效']
      };
    },

    /* ---------- 问诊对话 ---------- */
    messages: [
      { role: 'ai',  time: now - 1200000, text: '您好，我是 AI 医学问诊助手。为了更准确地了解您的情况，我会先问几个基础问题，整个过程大约需要 5–8 分钟。\n请问您的性别和年龄是？' },
      { role: 'me',  time: now - 1180000, text: '女，34 岁。' },
      { role: 'ai',  time: now - 1160000, text: '好的。请问这次主要哪里不舒服？大概持续多久了？' },
      { role: 'me',  time: now - 1140000, text: '咳嗽三天了，晚上比较厉害，还有点低烧 37.8 度，嗓子微疼。' },
      { role: 'ai',  time: now - 1120000, text: '了解了。请问咳嗽是干咳还是有痰？如果有痰，痰是什么颜色？' },
      { role: 'me',  time: now - 1100000, text: '基本是干咳，早上有一点白色的痰。' },
      { role: 'ai',  time: now - 1080000, text: '明白。有没有出现胸闷、气短、胸痛，或者呼吸困难的情况？' }
    ],

    stages: [
      { key: 1, name: '基本信息' },
      { key: 2, name: '主诉现病史' },
      { key: 3, name: '既往史' },
      { key: 4, name: '系统回顾' },
      { key: 5, name: '生成报告' }
    ],

    quickQuestions: ['咳嗽是干咳还是有痰？', '体温最高到多少度？', '有胸闷或气短吗？', '最近接触过感冒的人吗？', '目前在吃什么药？'],

    /* ---------- 分享链接 ---------- */
    shareLinks: [
      { id: 1, token: 'sH7dK2pQ9xLm4nR8vT6wY3zA1bC5eF0g', recordId: 10241, recordTitle: '持续性咳嗽伴低烧 3 天', createdAt: now - 2 * 3600000, expiresAt: now + 70 * 3600000, views: 3 },
      { id: 2, token: 'kL3mN8pQrS2tU7vW9xY4zA6bC1dE5f', recordId: 10238, recordTitle: '餐后上腹胀痛、反酸', createdAt: now - 26 * 3600000, expiresAt: now + 46 * 3600000, views: 0 }
    ],

    /* ---------- 设置项 ---------- */
    settings: {
      notifyRemind: true,
      notifyReport: true,
      analytics: false,
      voice: false,
      density: 'comfortable',
      autoSave: true
    },

    /* ---------- 会员方案 ---------- */
    plans: [
      { id: 'free', name: '免费版', price: 0, unit: '/ 月', featured: false,
        features: ['每月 5 次完整问诊', '基础病历报告', '本地加密存储'] },
      { id: 'pro', name: '专业版', price: 39, unit: '/ 月', featured: true,
        features: ['不限次完整问诊', '深度病历与随访建议', '报告 PDF 导出', '家庭成员档案（5 人）', '优先响应'] },
      { id: 'family', name: '家庭版', price: 79, unit: '/ 月', featured: false,
        features: ['专业版全部权益', '家庭成员档案（不限）', '用药提醒与复诊提醒', '专属客服通道'] }
    ],

    /* ---------- 工具：模拟网络延迟 ---------- */
    delay: function (ms, value) {
      return new Promise(function (resolve) {
        setTimeout(function () { resolve(value); }, ms === undefined ? 500 : ms);
      });
    }
  };
})(window.App = window.App || {});
