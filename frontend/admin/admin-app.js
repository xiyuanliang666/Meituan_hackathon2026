// ===== 页面切换 =====
function switchPage(page) {
  document.querySelectorAll('.page-panel').forEach(p => { p.classList.remove('active'); p.style.display = 'none'; });
  const special = ['confirm', 'upload', 'notify'];
  const panel = document.getElementById('panel-' + page);
  if (panel) { panel.style.display = 'block'; panel.classList.add('active'); }
  if (!special.includes(page)) {
    document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
    const tab = document.querySelector(`.nav-tab[data-page="${page}"]`);
    if (tab) tab.classList.add('active');
  }
}

// ===== AI助手播报 =====
const bubbleToday = ['· 今日试戴总次数 <span class="hl-up">↑ 23%</span>，投流占比达 <span class="hl-up">41%</span>。','· <span class="hl-warn">奶油渐变猫眼</span> 收藏率达 <span class="hl-up">38%</span>，连续3天上升。','· <span class="hl-warn">圣诞红绿镜面</span> 试戴率 <span class="hl-down">↓ 12%</span>，进入衰退。','· 自然流量下单转化率 <span class="hl-up">9.2%</span>，状态良好。'];
const bubbleWeek = ['· 本周试戴较上周 <span class="hl-up">↑ 31%</span>，投流贡献 <span class="hl-up">48%</span>。','· <span class="hl-warn">奶油渐变猫眼</span> 综合评分 <span class="hl-up">89分</span>，最强爆款。','· <span class="hl-warn">圣诞红绿镜面</span> 热度见顶回落，建议替换。','· 整体转化率提升 <span class="hl-up">2.3个百分点</span>。'];
let currentPeriod = 'today';

function switchPeriod(btn, period) {
  document.querySelectorAll('.assistant-header .period-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  currentPeriod = period;
  renderBubble(period === 'today' ? bubbleToday : bubbleWeek);
}
function renderBubble(lines) { document.getElementById('assistant-bubble').innerHTML = lines.map(l => `<div class="bubble-line">${l}</div>`).join(''); }
function regenBubble() {
  const label = document.getElementById('regen-label');
  label.textContent = '生成中...';
  setTimeout(() => { renderBubble(currentPeriod === 'today' ? bubbleToday : bubbleWeek); label.textContent = '重新生成播报'; }, 1200);
}

// ===== 素材管理 =====
const stylesData = [
  { name: '奶油渐变猫眼', tags: ['猫眼','渐变','奶油白','玫瑰金'], lc: 'up', lcText: '上升期', date: '2024-11-28', bg: '#FAEEDA', bc: '#EF9F27', ic: '#BA7517', seasonal: false },
  { name: '圣诞红绿镜面', tags: ['镜面','红色','绿色','圣诞'], lc: 'peak', lcText: '峰值期', date: '2024-11-25', bg: '#E1F5EE', bc: '#5DCAA5', ic: '#0F6E56', seasonal: true },
  { name: '法式简约纯色', tags: ['法式','简约','裸色'], lc: 'down', lcText: '衰退期', date: '2024-11-20', bg: '#EEEDFE', bc: '#AFA9EC', ic: '#534AB7', seasonal: false },
  { name: '暗红晕染手绘', tags: ['晕染','手绘','暗红'], lc: 'none', lcText: '未关联', date: '2024-11-18', bg: '#FCE4D6', bc: '#F0997B', ic: '#993C1D', seasonal: false }
];

function renderStyleList() {
  const list = document.getElementById('style-list');
  if (!list) return;
  list.innerHTML = stylesData.map((s, i) => `
    <div class="style-item" id="style-${i}">
      <div class="style-thumb" style="background:${s.bg};border-color:${s.bc}"><i class="ti ti-photo" style="color:${s.ic}"></i></div>
      <div class="style-info">
        <div class="style-name-text">${s.name} ${s.seasonal ? '<span class="seasonal-badge">节日限定</span>' : '<span class="evergreen-badge">常青款</span>'}</div>
        <div class="style-tags-row">${s.tags.slice(0,3).map(t=>`<span class="stag stag-craft">${t}</span>`).join('')}</div>
        <div class="style-meta-row"><span class="lc-pill lc-${s.lc}"><i class="ti ti-${s.lc==='up'?'trending-up':s.lc==='peak'?'flame':s.lc==='down'?'trending-down':'minus'}"></i>${s.lcText}</span><span class="style-date">${s.date}</span></div>
      </div>
      <div class="style-actions"><div class="btn-icon"><i class="ti ti-edit"></i></div><div class="btn-icon danger" onclick="deleteStyle(${i})"><i class="ti ti-trash"></i></div></div>
    </div>`).join('');
}
function deleteStyle(idx) { const el = document.getElementById('style-'+idx); if(el){el.style.opacity='0.3';el.style.pointerEvents='none';} }

const templates = [{ label:'自然肤色',selected:true },{ label:'白皙肤色',selected:true },{ label:'暖肤色',selected:true },{ label:'冷白肤色',selected:false },{ label:'店铺自有',selected:false }];

function renderTemplates() {
  const grid = document.getElementById('template-grid');
  if (!grid) return;
  grid.innerHTML = templates.map((t,i) => `<div class="tpl-item ${t.selected?'selected':''}" onclick="toggleTemplate(${i})"><div class="tpl-check">✓</div><i class="ti ti-hand-finger"></i><span>${t.label}</span></div>`).join('');
  updateTplCount();
}
function toggleTemplate(idx) { templates[idx].selected = !templates[idx].selected; renderTemplates(); }
function updateTplCount() { const n = templates.filter(t=>t.selected).length; const el = document.getElementById('tpl-count'); if(el) el.textContent = '已选 '+n+' 张'; }
function toggleTplDropdown(e) { e.stopPropagation(); document.getElementById('tpl-add-dropdown').classList.toggle('show'); }
function handleTplUpload() { document.getElementById('tpl-add-dropdown').classList.remove('show'); templates.push({label:'自定义'+(templates.length+1),selected:true}); renderTemplates(); }
function handleTplPublic() { document.getElementById('tpl-add-dropdown').classList.remove('show'); templates.push({label:'公共'+(templates.length+1),selected:false}); renderTemplates(); }
document.addEventListener('click', function() { const dd = document.getElementById('tpl-add-dropdown'); if(dd) dd.classList.remove('show'); });

// ===== 上传弹窗 =====
function showUploadModal() { document.getElementById('upload-modal').classList.add('show'); }
function hideUploadModal() { document.getElementById('upload-modal').classList.remove('show'); }
function goUploadPage() { hideUploadModal(); goUploadStep(2); switchPage('upload'); }
function addTagPrompt(groupId, tagClass) { const name = prompt('输入标签名称：'); if(!name||!name.trim())return; const group=document.getElementById(groupId); const btn=group.querySelector('.tag-add-btn'); const tag=document.createElement('span'); tag.className='tag '+tagClass; tag.innerHTML=`${name.trim()} <i class="tag-del" onclick="this.parentElement.remove()">×</i>`; group.insertBefore(tag,btn); }

// ===== 上传步骤3-4（#13）=====
function goUploadStep(step) {
  document.querySelectorAll('.upload-step-panel').forEach(p => p.style.display = 'none');
  document.getElementById('upload-step-'+step).style.display = 'block';
  // 更新步骤条
  [2,3,4].forEach(s => {
    const el = document.getElementById('step-'+s);
    if (!el) return;
    el.className = 'step ' + (s < step ? 'step-done' : s === step ? 'step-active' : 'step-pending');
    if (s < step) el.querySelector('.step-num').innerHTML = '<i class="ti ti-check"></i>';
    else el.querySelector('.step-num').textContent = s;
  });
  // 步骤3渲染模板选择
  if (step === 3) {
    const grid = document.getElementById('upload-tpl-grid');
    if (grid) grid.innerHTML = templates.map((t,i) => `<div class="tpl-item ${t.selected?'selected':''}" onclick="this.classList.toggle('selected')"><div class="tpl-check">✓</div><i class="ti ti-hand-finger"></i><span>${t.label}</span></div>`).join('');
  }
}

// ===== 爆款推送 =====
const taglines = ['秋冬约会必备！奶油渐变猫眼，光线下超有氛围感，显白又高级，赶紧安排～','这个秋冬就靠它了！奶油白渐变猫眼，温柔又高级～','简约不简单！奶油渐变猫眼，日常百搭还显白～'];
let taglineIdx = 0;
const coupons = {'1':{name:'全贴甲片简约款',price:'¥168',desc:'可做渐变·猫眼·晕染'},'2':{name:'半贴甲片基础款',price:'¥128',desc:'半贴为主'},'3':{name:'猫眼渐变升级款',price:'¥218',desc:'专攻猫眼渐变'}};

function selectPushImg(el, idx) { document.querySelectorAll('.push-thumbs .push-thumb').forEach(t=>t.classList.remove('active')); el.classList.add('active'); document.getElementById('push-main-img').innerHTML=`<i class="ti ti-photo" style="font-size:38px;color:#BA7517"></i><span>合成效果图 ${idx}</span>`; }
function regenPushImg(btn) { btn.innerHTML='<i class="ti ti-refresh"></i> 生成中...'; setTimeout(()=>{btn.innerHTML='<i class="ti ti-refresh"></i> 重新生成';},1200); }
function regenTagline() { const l=document.getElementById('tagline-regen-label'); l.textContent='生成中...'; setTimeout(()=>{taglineIdx=(taglineIdx+1)%taglines.length; document.getElementById('push-tagline').textContent=taglines[taglineIdx]; l.textContent='重新生成推荐语';},900); }
function updateCoupon() { const v=document.getElementById('coupon-select').value; const c=coupons[v]; document.getElementById('coupon-name').textContent=c.name; document.getElementById('coupon-price').textContent=c.price; }

// 定价微调（#3）
function updatePriceSlider(val) { document.getElementById('price-slider-val').textContent = val; }

function goConfirm() { 
  const price = document.getElementById('price-slider-val').textContent;
  document.getElementById('confirm-price').textContent = price;
  switchPage('confirm'); 
}
function confirmPublish() {
  document.querySelector('#panel-confirm .confirm-grid').style.display = 'none';
  document.querySelector('#panel-confirm .page-top').style.display = 'none';
  document.getElementById('success-page').style.display = 'flex';
}

// ===== 复盘报告 =====
const reportData = {
  week: {
    label: '2024年第48周 · 11月25日—12月1日',
    title: '本周运营复盘 · 助手生成报告',
    sub: '基于本周双渠道数据、爆款热度和历史趋势综合分析',
    sectionTitle: '一、本周数据总结',
    metrics: [
      { label: '试戴总次数', val: '1,284', delta: '+31%', dir: 'up' },
      { label: '自然流量下单率', val: '9.2%', delta: '+2.3pp', dir: 'up' },
      { label: '投流流量下单率', val: '26%', delta: '+8pp', dir: 'up' },
      { label: '试戴收藏率', val: '34%', delta: '+6pp', dir: 'up' },
      { label: '投流试戴占比', val: '48%', delta: '+7pp', dir: 'up' },
      { label: '新上架款式', val: '2', delta: '— 持平', dir: 'flat' }
    ]
  },
  month: {
    label: '2024年11月 · 月度报告',
    title: '11月运营复盘 · 月度总结',
    sub: '基于本月完整数据与上月对比分析',
    sectionTitle: '一、本月数据总结',
    metrics: [
      { label: '试戴总次数', val: '5,126', delta: '+48%', dir: 'up' },
      { label: '自然流量下单率', val: '8.7%', delta: '+1.8pp', dir: 'up' },
      { label: '投流流量下单率', val: '23%', delta: '+5pp', dir: 'up' },
      { label: '试戴收藏率', val: '31%', delta: '+4pp', dir: 'up' },
      { label: '投流试戴占比', val: '45%', delta: '+9pp', dir: 'up' },
      { label: '新上架款式', val: '6', delta: '+2', dir: 'up' }
    ]
  },
  day: {
    label: '2024年11月28日 · 今日日报',
    title: '今日运营日报 · 实时数据',
    sub: '截至当前时刻的今日运营数据汇总',
    sectionTitle: '一、今日数据',
    metrics: [
      { label: '今日试戴次数', val: '203', delta: '+23%', dir: 'up' },
      { label: '自然流量下单率', val: '9.8%', delta: '+0.6pp', dir: 'up' },
      { label: '投流流量下单率', val: '28%', delta: '+2pp', dir: 'up' },
      { label: '试戴收藏率', val: '38%', delta: '+4pp', dir: 'up' },
      { label: '投流试戴占比', val: '41%', delta: '-7pp', dir: 'down' },
      { label: '新收藏数', val: '77', delta: '+15', dir: 'up' }
    ]
  }
};

function switchReportPeriod(btn, period) {
  document.querySelectorAll('.report-top-bar .period-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  const data = reportData[period] || reportData.week;
  document.getElementById('report-period-label').textContent = data.label;
  document.getElementById('report-title').textContent = data.title;
  document.getElementById('report-sub').textContent = data.sub;
  document.getElementById('report-section-title').innerHTML = `<i class="ti ti-chart-bar"></i> ${data.sectionTitle}`;
  document.getElementById('report-metrics').innerHTML = data.metrics.map(m => `
    <div class="metric-card">
      <div class="metric-label">${m.label}</div>
      <div class="metric-val">${m.val}</div>
      <div class="metric-delta delta-${m.dir}"><i class="ti ti-trending-${m.dir === 'down' ? 'down' : 'up'}"></i>${m.delta}</div>
    </div>
  `).join('');
}

// Skills执行层定义
const sugSkills = [
  { action:'boost_budget', label:'加大投流预算', requiresConfirm:true, confirmMsg:'确认将「奶油渐变猫眼」投流预算从 ¥500/天 提升至 ¥650/天？\n\n调整幅度：+30%\n预计额外消耗：¥1,050/周' },
  { action:'prepare_replacement', label:'准备替换款', requiresConfirm:false, execMsg:'已标记「圣诞红绿镜面」为待替换，素材管理页已高亮上传入口' },
  { action:'maintain_strategy', label:'维持当前策略', requiresConfirm:false, execMsg:'已记录：当前策略维持不变' },
  { action:'take_down_style', label:'下架款式', requiresConfirm:false, execMsg:'已将「法式简约纯色」标记为待下架，请在素材管理中确认' }
];

function adoptSug(idx) {
  const skill = sugSkills[idx];
  if (!skill) return;
  if (skill.requiresConfirm) {
    // 二次确认框（涉及资金）
    if (confirm(skill.confirmMsg)) {
      executeSkill(idx, skill);
    }
  } else {
    executeSkill(idx, skill);
  }
}

function executeSkill(idx, skill) {
  const item = document.getElementById('sug-'+idx);
  const actions = document.getElementById('sug-actions-'+idx);
  actions.innerHTML = `<div class="adopted-label"><i class="ti ti-circle-check" style="color:#375623"></i> 已采纳 · ${skill.label}</div><button class="btn-undo" onclick="undoSug(${idx})">撤销</button>`;
  item.classList.add('adopted');
  // 显示执行结果通知
  showToast(skill.execMsg || '操作已执行');
  // Skills联动：跳转相关页面
  if (skill.action === 'prepare_replacement') {
    setTimeout(() => { if(confirm('是否跳转到素材管理页上传新款式？')) switchPage('assets'); }, 500);
  } else if (skill.action === 'take_down_style') {
    setTimeout(() => { if(confirm('是否跳转到素材管理页确认下架？')) switchPage('assets'); }, 500);
  }
}

function undoSug(idx) {
  const item = document.getElementById('sug-'+idx);
  const actions = document.getElementById('sug-actions-'+idx);
  item.classList.remove('adopted');
  actions.innerHTML = `<button class="btn-adopt" onclick="adoptSug(${idx})">采纳建议</button><button class="btn-ignore" onclick="ignoreSug(${idx})">忽略</button>`;
  showToast('已撤销操作');
}

function ignoreSug(idx) { const item=document.getElementById('sug-'+idx); const actions=document.getElementById('sug-actions-'+idx); actions.innerHTML='<div class="adopted-label" style="color:#aaa"><i class="ti ti-x"></i> 已忽略</div>'; item.classList.add('adopted'); }

// Toast通知
function showToast(msg) {
  let toast = document.getElementById('global-toast');
  if (!toast) { toast = document.createElement('div'); toast.id = 'global-toast'; toast.className = 'global-toast'; document.body.appendChild(toast); }
  toast.textContent = msg;
  toast.classList.add('show');
  setTimeout(() => toast.classList.remove('show'), 2500);
}

// ===== 偏好配置（#9）=====
function showPrefModal() { document.getElementById('pref-modal').classList.add('show'); }
function hidePrefModal() { document.getElementById('pref-modal').classList.remove('show'); }

// ===== 投流管理（#5）=====
function genBoostPost() { alert('AI正在生成投流帖子...\n\n生成内容预览：\n\n标题：秋冬必做！奶油渐变猫眼超显白\n正文：光线下自带氛围感的猫眼甲，奶油白渐变到玫瑰金...\n话题：#秋冬美甲 #猫眼甲 #显白美甲\n关键词：猫眼渐变、显白、秋冬'); }

function toggleBoostDetail(el) {
  const detail = el.nextElementSibling;
  if (detail) detail.classList.toggle('show');
}

// 上传自有图片
function uploadOwnImage() { alert('打开图片选择器…\n\n（Demo模拟：商户可上传自己拍摄的款式图替换AI合成图）'); }

// ===== 初始化 =====
function init() { renderStyleList(); renderTemplates(); switchPage('home'); }
init();
