// ===== 数据 =====
const nailStyles = [
  { id:1, name:'法式奶白渐变', tags:['法式','简约'], bg:'#fce4ec', emoji:'💅', price:168, reason:'冷粉色系提亮肤色', shop:'蔻丹美甲·朝阳店' },
  { id:2, name:'春日樱粉', tags:['可爱','ins风'], bg:'#fce4ec', emoji:'🌸', price:148, reason:'裸粉修饰细长甲型', shop:'粉色泡泡美甲' },
  { id:3, name:'星空极光', tags:['炫彩','高级感'], bg:'#e8eaf6', emoji:'✨', price:198, reason:'冷紫拉长视觉比例', shop:'指尖艺术美甲' },
  { id:4, name:'奶茶裸感', tags:['温柔','日系'], bg:'#fff8e1', emoji:'🌙', price:138, reason:'暖色调衬手白嫩', shop:'蔻丹美甲·朝阳店' },
  { id:5, name:'圣诞红金', tags:['节日','闪粉'], bg:'#fce4ec', emoji:'🎄', price:178, reason:'红金配色喜庆精致', shop:'指间花园' },
  { id:6, name:'雪夜白绿', tags:['圣诞','清新'], bg:'#e8f5e9', emoji:'❄️', price:158, reason:'冷白绿显手白', shop:'指尖艺术美甲' },
  { id:7, name:'暗调酒红', tags:['高级','秋冬'], bg:'#4a1a3e', emoji:'🍷', price:218, reason:'暗调显气质', shop:'蔻丹美甲·朝阳店' },
  { id:8, name:'海盐冰蓝', tags:['冷淡','夏日'], bg:'#e3f2fd', emoji:'🌊', price:158, reason:'冷蓝系显手白嫩', shop:'粉色泡泡美甲' },
];

// ===== 状态 =====
let currentPage = 'home';
let detailFrom = 'home';
let chatMessages = [];
let handUploaded = false;
let multiSelectMode = false;
let selectedThumbs = new Set();
let currentDetailId = null;

// ===== 导航 =====
function navigateTo(page) {
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  currentPage = page;
  if (page === 'chat' && chatMessages.length === 0) initChat();
  if (page === 'recommend') renderRecommend();
}
function goBackFromDetail() { navigateTo(detailFrom); }

// ===== 首页Feed =====
function renderFeed() {
  const tagColors = {'法式':'feed-tag-style','简约':'feed-tag-style','可爱':'feed-tag-scene','ins风':'feed-tag-scene','炫彩':'feed-tag-default','高级感':'feed-tag-style','温柔':'feed-tag-scene','日系':'feed-tag-season','节日':'feed-tag-season','闪粉':'feed-tag-default','圣诞':'feed-tag-season','清新':'feed-tag-scene','秋冬':'feed-tag-season','冷淡':'feed-tag-style','夏日':'feed-tag-season','高级':'feed-tag-style'};
  document.getElementById('feed-container').innerHTML = nailStyles.map(s => `
    <div class="feed-card" onclick="openDetail(${s.id},'home')">
      <div class="feed-img" style="background:${s.bg}">${s.emoji}</div>
      <div class="feed-card-bottom">
        <div class="feed-name">${s.name}</div>
        <div class="feed-tags">${s.tags.map(t=>`<span class="feed-tag ${tagColors[t]||'feed-tag-default'}">${t}</span>`).join('')}</div>
        <div class="feed-bottom-row">
          <div class="feed-price"><span class="feed-price-unit">¥</span>${s.price}</div>
          <button class="tryon-btn" onclick="event.stopPropagation();tryFromFeed(${s.id})">AI 试款</button>
        </div>
      </div>
    </div>
  `).join('');
}

// 点击试款时检查手图状态
function tryFromFeed(id) {
  if (!handUploaded) {
    // 弹出引导上传
    if (confirm('需要先上传手图才能AI试款哦~\n\n点击"确定"去上传手图')) {
      navigateTo('upload');
    }
  } else {
    openDetail(id, 'home');
  }
}

// AI栏文字轮播（淡入淡出）
const barTexts = ['暖黄皮适合什么美甲颜色？','圣诞节有什么美甲推荐？','法式简约款有哪些？','附近哪家店可以做这个款？'];
let barIdx = 0;
setInterval(() => {
  const el = document.getElementById('ai-bar-text');
  if (!el) return;
  el.classList.add('fade');
  setTimeout(() => { barIdx = (barIdx+1) % barTexts.length; el.textContent = barTexts[barIdx]; el.classList.remove('fade'); }, 400);
}, 3500);

// ===== 试款详情页 =====
function openDetail(id, from) {
  detailFrom = from || 'home';
  currentDetailId = id;
  multiSelectMode = false;
  selectedThumbs = new Set([id]);
  renderDetailPage();
  navigateTo('detail');
}

function renderDetailPage() {
  const item = nailStyles.find(s => s.id === currentDetailId);
  // 渲染缩略图行（多选模式显示空圆圈/选中圆）
  document.getElementById('thumb-row').innerHTML = nailStyles.slice(0,6).map(s => {
    const isSelected = selectedThumbs.has(s.id);
    const isActive = s.id === currentDetailId && !multiSelectMode;
    return `<div class="thumb ${isSelected?'selected':''} ${isActive?'active':''}" style="background:${s.bg}" onclick="onThumbClick(${s.id})">
      ${s.emoji}
      ${multiSelectMode ? (isSelected ? '<div class="thumb-check"><i class="ti ti-check"></i></div>' : '<div class="thumb-uncheck"></div>') : ''}
    </div>`;
  }).join('');

  // 渲染主区域
  if (!multiSelectMode || selectedThumbs.size <= 1) {
    document.getElementById('tryon-main').innerHTML = `
      <div class="tryon-bigimg">
        <span class="emoji-lg">${item.emoji}</span>
        <div class="tryon-generating"><div class="pulse-dot" style="background:#8b5cf6"></div><span>试戴效果生成中…</span></div>
        <div class="tryon-actions">
          <div class="tryon-action-btn" title="保存" onclick="alert('已保存到相册')"><i class="ti ti-download"></i></div>
          <div class="tryon-action-btn" title="分享" onclick="alert('分享链接已复制')"><i class="ti ti-share"></i></div>
          <div class="tryon-action-btn" title="收藏" onclick="this.querySelector('i').style.color='#8b5cf6'"><i class="ti ti-heart"></i></div>
        </div>
      </div>
      <div class="nail-meta"><span class="nail-name">${item.name}</span><div class="nail-tags-row">${item.tags.map(t=>`<span class="nail-tag">${t}</span>`).join('')}</div></div>
      <div class="tryon-rating"><span>效果满意吗？</span><div class="rating-btns"><button class="rate-btn" onclick="this.classList.add('rated')"><i class="ti ti-thumb-up"></i></button><button class="rate-btn" onclick="this.classList.add('rated')"><i class="ti ti-thumb-down"></i></button></div></div>
      <button class="nail-book-btn" onclick="alert('正在跳转预约页面…\\n\\n¥${item.price} · ${item.name}\\n${item.shop}')"><i class="ti ti-calendar"></i> 立即预约 ¥${item.price}</button>
    `;
  } else {
    renderCompareGrid();
  }
  // 更新按钮状态
  const btn = document.getElementById('multisel-btn');
  const circle = document.getElementById('multisel-circle');
  const label = document.getElementById('multisel-label');
  if (multiSelectMode) {
    btn.className = 'action-btn active-mode';
    circle.className = 'multisel-circle filled';
    circle.innerHTML = '<i class="ti ti-check" style="font-size:8px;color:#fff"></i>';
    label.textContent = '多选对比 ' + selectedThumbs.size;
  } else {
    btn.className = 'action-btn';
    circle.className = 'multisel-circle';
    circle.innerHTML = '';
    label.textContent = '多选对比';
  }
}

function toggleMultiSelect() {
  multiSelectMode = !multiSelectMode;
  if (!multiSelectMode) { selectedThumbs = new Set([currentDetailId]); }
  renderDetailPage();
}

function onThumbClick(id) {
  if (multiSelectMode) {
    if (selectedThumbs.has(id)) selectedThumbs.delete(id);
    else if (selectedThumbs.size < 9) selectedThumbs.add(id);
  } else {
    currentDetailId = id;
    selectedThumbs = new Set([id]);
  }
  renderDetailPage();
}

// 多选对比布局：2=左右/3=四宫格缺一/4=四宫格/5-6=六宫格/7-9=九宫格
function renderCompareGrid() {
  const items = [...selectedThumbs].map(id => nailStyles.find(s=>s.id===id)).filter(Boolean);
  const n = items.length;
  let gridClass, maxCells;
  if (n <= 2) { gridClass = 'g2'; maxCells = 2; }
  else if (n <= 4) { gridClass = 'g4'; maxCells = 4; }
  else if (n <= 6) { gridClass = 'g6'; maxCells = 6; }
  else { gridClass = 'g9'; maxCells = 9; }

  let cells = items.map(s => `<div class="grid-cell" style="background:${s.bg}">${s.emoji}<span class="cell-name">${s.name}</span><span class="cell-price">¥${s.price}</span></div>`);
  while (cells.length < maxCells) cells.push('<div class="grid-cell empty"><i class="ti ti-plus"></i></div>');
  document.getElementById('tryon-main').innerHTML = `
    <div class="grid-compare ${gridClass}">${cells.join('')}</div>
    <div class="nail-meta"><span class="nail-name">已选 ${n} 款 · 对比预览</span><div class="nail-tags-row"><span class="nail-tag">对比中</span></div></div>
    <button class="nail-book-btn" onclick="alert('请选择一款进行预约')"><i class="ti ti-calendar"></i> 选定后预约</button>
  `;
}

// ===== AI对话 =====
function initChat() {
  chatMessages = [];
  addAiMsg('你好！我是小团 ✦\n\n告诉我你的场合、肤色或喜好，我来帮你找到最适合的美甲款式~', null, null, null);
}
function addAiMsg(text, cards, tips, guideQs) { chatMessages.push({role:'ai',text,cards,tips,guideQs}); renderChat(); }
function addUserMsg(text) { chatMessages.push({role:'user',text}); renderChat(); }

function renderChat() {
  const body = document.getElementById('chat-body');
  body.innerHTML = chatMessages.map(m => {
    if (m.role === 'user') return `<div class="chat-msg user"><div class="chat-avatar-sm" style="background:#e8e8e8"><i class="ti ti-user" style="color:#888"></i></div><div class="chat-bubble">${m.text}</div></div>`;
    let html = `<div class="chat-msg ai"><div class="chat-avatar-sm"><i class="ti ti-sparkles"></i></div><div><div class="chat-bubble">${m.text.replace(/\n/g,'<br>')}`;
    if (m.cards && m.cards.length) {
      html += `<div class="ai-section-title">为你推荐</div><div class="style-cards">${m.cards.map(c=>`
        <div class="style-card" onclick="openDetail(${c.id},'chat')"><div class="style-card-img" style="background:${c.bg}">${c.emoji}</div><div class="style-card-name">${c.name}</div><button class="style-card-tryon" onclick="event.stopPropagation();openDetail(${c.id},'chat')">试款</button></div>
      `).join('')}</div>`;
    }
    if (m.tips) {
      html += `<div class="tips-box"><div class="tips-title">💡 小贴士</div>${m.tips.map(t=>`<div class="tips-item">· ${t}</div>`).join('')}</div>`;
    }
    if (m.guideQs) {
      html += `<div class="guide-qs">${m.guideQs.map(q=>`<div class="guide-q" onclick="sendQuickMsg('${q}')">${q}</div>`).join('')}</div>`;
    }
    html += '</div></div></div>';
    return html;
  }).join('');
  body.scrollTop = body.scrollHeight;
  if (chatMessages.length > 1) document.getElementById('chat-quick-tags').style.display = 'none';
}

function sendMsg() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addUserMsg(text);
  chatMessages.push({role:'ai',text:'<div class="typing-indicator"><span></span><span></span><span></span></div>',cards:null,tips:null,guideQs:null,isTyping:true});
  renderChat();
  setTimeout(() => {
    chatMessages = chatMessages.filter(m => !m.isTyping);
    const r = genReply(text);
    addAiMsg(r.text, r.cards, r.tips, r.guideQs);
  }, 1200);
}
function sendQuickMsg(text) { document.getElementById('chat-input').value = text; sendMsg(); }

function genReply(q) {
  const ql = q.toLowerCase();
  let cards = [], text = '', tips = null, guideQs = null;

  if (ql.includes('圣诞') || ql.includes('节日') || ql.includes('520') || ql.includes('新年')) {
    cards = nailStyles.filter(s=>s.tags.some(t=>t.includes('节日')||t.includes('圣诞'))).slice(0,3);
    text = '<div class="ai-section-title">场景分析</div>圣诞节适合喜庆又精致的款式，今年流行"暗调高级感"，酒红搭配金属光泽非常出圈。';
    tips = ['圣诞前3-5天预约，避开节日高峰','闪粉款建议选凝胶，持久不掉色','金色系点缀让节日感更强'];
    guideQs = ['我是暖黄皮，适合哪款？','附近哪家店可以做圣诞款？'];
  }
  else if (ql.includes('黄皮') || ql.includes('显白') || ql.includes('肤色') || ql.includes('肉手') || ql.includes('短甲')) {
    cards = nailStyles.filter(s=>s.tags.some(t=>t.includes('简约')||t.includes('温柔'))).slice(0,3);
    text = '<div class="ai-section-title">场景分析</div>暖黄皮推荐冷调色系提亮肤色，裸粉、奶白、冷紫都是显白好选择。短甲可选圆甲/方圆甲，视觉上拉长手指。';
    tips = ['避免饱和度过高的亮黄/亮橙','裸色系+微闪是万能显白搭配','短甲做竖向线条设计更显长'];
    guideQs = ['帮我看看哪款最显手白','有没有适合通勤的款？'];
  }
  else if (ql.includes('法式') || ql.includes('简约') || ql.includes('通勤') || ql.includes('上班')) {
    cards = nailStyles.filter(s=>s.tags.includes('法式')||s.tags.includes('简约')).slice(0,3);
    text = '<div class="ai-section-title">场景分析</div>通勤款追求耐看不夸张，法式简约永不过时，干净优雅，百搭不腻。';
    tips = ['法式建议选甲油胶，持久2-3周','微笑线越薄越显精致','裸色打底百搭任何衣服'];
    guideQs = ['有没有再高级一点的款？','这些款大概多少钱？'];
  }
  else if (ql.includes('附近') || ql.includes('哪家店') || ql.includes('店') || ql.includes('预约')) {
    cards = null;
    text = '<div class="ai-section-title">商户推荐</div>根据你的位置，附近有以下店铺可以做：\n\n🏠 <strong>蔻丹美甲·朝阳店</strong>\n距您 0.8km · 评分 4.9 · 可做法式/猫眼/渐变\n\n🏠 <strong>指尖艺术美甲</strong>\n距您 1.2km · 评分 4.7 · 擅长手绘/复杂款\n\n🏠 <strong>粉色泡泡美甲</strong>\n距您 1.5km · 评分 4.8 · 日系风格为主';
    tips = ['建议提前1-2天预约','到店后可给技师看AI试款效果图'];
    guideQs = ['蔻丹美甲有什么团购？','帮我推荐一款适合约会的'];
  }
  else if (ql.includes('手') || ql.includes('推荐适合') || ql.includes('根据我')) {
    text = '好的！请先上传你的手图，我来帮你分析手型并推荐最适合的款式~\n\n👉 点击右上角 🤚 上传手图即可开始';
    tips = ['拍照时光线充足效果更准','手背朝上、五指自然展开最佳'];
    guideQs = null; cards = null;
  }
  else if (ql.includes('多少钱') || ql.includes('价格')) {
    cards = nailStyles.slice(0,3);
    text = '这几款的价格参考：\n\n💅 法式奶白渐变 ¥168\n🌸 春日樱粉 ¥148\n✨ 星空极光 ¥198\n\n具体价格以门店团购为准~';
    tips = ['团购价通常比到店价优惠15-30%','新客首单一般有额外折扣'];
    guideQs = ['帮我找200以内的款','附近哪家店性价比高？'];
  }
  else {
    cards = nailStyles.slice(0,3);
    text = '<div class="ai-section-title">为你推荐</div>根据你的描述，我觉得这几款可能适合你~点击可以直接试款哦';
    tips = ['可以多试几款对比效果再做决定','上传手图能获得更精准的推荐'];
    guideQs = ['有没有更显白的？','帮我看看适合约会的款'];
  }

  return { text, cards, tips, guideQs };
}

// ===== 手图上传 =====
function simulateUpload() {
  handUploaded = true;
  const area = document.getElementById('upload-area');
  area.className = 'upload-placeholder uploaded';
  area.innerHTML = '<span class="uploaded-emoji">🤚</span><div class="reupload-badge"><i class="ti ti-refresh"></i> 重新上传</div>';
  document.getElementById('analyze-btn').disabled = false;
}

function startAnalysis() {
  if (!handUploaded) return;
  navigateTo('analyzing');
  const steps = [
    () => { document.getElementById('a-step-1').className='step-icon active'; document.getElementById('a-step-1').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-1').className='step-text'; },
    () => { document.getElementById('a-step-1').className='step-icon done'; document.getElementById('a-step-1').innerHTML='<i class="ti ti-check"></i>'; document.getElementById('a-step-2').className='step-icon active'; document.getElementById('a-step-2').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-2').className='step-text'; },
    () => { document.getElementById('a-step-2').className='step-icon done'; document.getElementById('a-step-2').innerHTML='<i class="ti ti-check"></i>'; document.getElementById('a-step-3').className='step-icon active'; document.getElementById('a-step-3').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-3').className='step-text'; },
    () => { document.getElementById('a-step-3').className='step-icon done'; document.getElementById('a-step-3').innerHTML='<i class="ti ti-check"></i>'; setTimeout(()=>navigateTo('recommend'), 400); }
  ];
  steps.forEach((fn, i) => setTimeout(fn, i * 1000));
}

// ===== 推荐结果 =====
function renderRecommend() {
  const picks = nailStyles.slice(0,4);
  const reportHtml = `<div class="hand-report">
    <div class="hand-report-emoji">🤚</div>
    <div class="hand-report-info">
      <div class="hand-report-title">你的手型报告</div>
      <div class="hand-report-desc">肤色偏暖黄，手型标准，指节比例匀称，适合大多数甲形</div>
      <div class="hand-report-tags">
        <span class="hand-report-tag">暖黄皮</span>
        <span class="hand-report-tag">标准手型</span>
        <span class="hand-report-tag">方圆甲最佳</span>
        <span class="hand-report-tag">适合暖色调</span>
      </div>
    </div>
  </div>`;
  document.querySelector('#page-recommend .result-body').innerHTML = `
    <div class="result-header">
      <div class="result-ai-badge"><i class="ti ti-sparkles"></i></div>
      <div><div class="result-title">根据你的手型推荐了 4 款</div><div class="result-sub">暖黄皮 · 标准型 · 方圆甲</div></div>
    </div>
    ${reportHtml}
    <div class="rec-grid">${picks.map(s => `
      <div class="rec-cell" onclick="openDetail(${s.id},'recommend')">
        <div class="rec-img" style="background:${s.bg}">${s.emoji}</div>
        <div class="rec-reason">${s.reason}</div>
        <div class="rec-bottom">
          <span class="rec-name">${s.name}</span>
          <div class="rec-actions">
            <div class="rec-btn" onclick="event.stopPropagation();this.querySelector('i').className='ti ti-thumb-up';this.style.background='#f0ebff'"><i class="ti ti-thumb-up"></i></div>
            <div class="rec-btn" onclick="event.stopPropagation();this.querySelector('i').className='ti ti-thumb-down';this.style.background='#fff0f0'"><i class="ti ti-thumb-down"></i></div>
            <div class="rec-btn" onclick="event.stopPropagation();this.querySelector('i').style.color='#8b5cf6';this.style.background='#f0ebff'"><i class="ti ti-heart"></i></div>
          </div>
        </div>
      </div>
    `).join('')}</div>
  `;
}

function tryAllRecommend() {
  const picks = nailStyles.slice(0,4);
  selectedThumbs = new Set(picks.map(s=>s.id));
  currentDetailId = picks[0].id;
  multiSelectMode = true;
  renderDetailPage();
  navigateTo('detail');
}

// ===== 初始化 =====
renderFeed();
navigateTo('home');
