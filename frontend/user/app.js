// ===== 数据 =====
// 初始 mock 数据（当后端不可用时的兜底）
let nailStyles = [
  { id:1, name:'法式奶白渐变', tags:['法式','简约'], bg:'#fce4ec', emoji:'💅', price:168, reason:'冷粉色系提亮肤色', shop:'蔻丹美甲·朝阳店', image_url:'http://p0.meituan.net/pilotimages/87797733466cfd525625a5947767e2ff1794125.png' },
  { id:2, name:'春日樱粉', tags:['可爱','ins风'], bg:'#fce4ec', emoji:'🌸', price:148, reason:'裸粉修饰细长甲型', shop:'粉色泡泡美甲', image_url:'http://p0.meituan.net/pilotimages/162afb52255bd908ba3ec418fd61824a2254875.png' },
  { id:3, name:'星空极光', tags:['炫彩','高级感'], bg:'#e8eaf6', emoji:'✨', price:198, reason:'冷紫拉长视觉比例', shop:'指尖艺术美甲', image_url:'http://p1.meituan.net/pilotimages/7bb5bc0c2c741f9f0aa63787a601d7ad2604877.png' },
  { id:4, name:'奶茶裸感', tags:['温柔','日系'], bg:'#fff8e1', emoji:'🌙', price:138, reason:'暖色调衬手白嫩', shop:'蔻丹美甲·朝阳店', image_url:'http://p0.meituan.net/pilotimages/fc8fe60e78341d77a5070fc2f8e520072098070.png' },
  { id:5, name:'圣诞红金', tags:['节日','闪粉'], bg:'#fce4ec', emoji:'🎄', price:178, reason:'红金配色喜庆精致', shop:'指间花园', image_url:'http://p1.meituan.net/pilotimages/3c0d090e20f0cb56f70fcb56c54dd6582416974.png' },
  { id:6, name:'雪夜白绿', tags:['圣诞','清新'], bg:'#e8f5e9', emoji:'❄️', price:158, reason:'冷白绿显手白', shop:'指尖艺术美甲', image_url:'http://p0.meituan.net/pilotimages/6c857edd85a5fa4bcec59698fe9416cb1913981.png' },
  { id:7, name:'暗调酒红', tags:['高级','秋冬'], bg:'#4a1a3e', emoji:'🍷', price:218, reason:'暗调显气质', shop:'蔻丹美甲·朝阳店', image_url:'http://p0.meituan.net/pilotimages/2ac2d01a9bc78320edbe2b545b485b4a2132292.png' },
  { id:8, name:'海盐冰蓝', tags:['冷淡','夏日'], bg:'#e3f2fd', emoji:'🌊', price:158, reason:'冷蓝系显手白嫩', shop:'粉色泡泡美甲', image_url:'http://p1.meituan.net/pilotimages/d15c06e8c2137d4f39f3b60476a90cf92026957.png' },
];

// ===== 状态 =====
let currentPage = 'home';
let detailFrom = 'home';
let chatMessages = [];
let handUploaded = false;
let multiSelectMode = false;
let selectedThumbs = new Set();
let currentDetailId = null;
let backendAvailable = false;
let handProfileId = null;
let handProfileData = null;
let conversationId = null;
let uploadedHandImageUrl = null;

// ===== 初始化后端连接 =====
async function initBackend() {
  backendAvailable = await checkBackendHealth();
  if (backendAvailable) {
    console.log('[前端] 后端连接成功，已启用 API 模式');
    await loadStylesFromBackend();
  } else {
    console.log('[前端] 后端不可用，使用本地 mock 数据');
  }
}

// 从后端加载款式数据
async function loadStylesFromBackend() {
  try {
    const data = await apiGet('/db/styles');
    if (data && data.styles && data.styles.length > 0) {
      nailStyles = data.styles.map((s, idx) => ({
        id: s.id || idx + 1,
        name: s.name || s.style_name,
        tags: s.tags || [],
        bg: getStyleBg(idx),
        emoji: getStyleEmoji(s.tags || []),
        price: s.price || (120 + Math.floor(Math.random() * 100)),
        reason: s.reason || '',
        shop: s.shop || '蔻丹美甲·朝阳店',
        image_url: s.image_url || '',
        style_id: s.style_id || String(s.id || idx + 1),
      }));
      renderFeed();
    }
  } catch (e) {
    console.warn('[前端] 加载款式数据失败，使用本地数据:', e.message);
  }
}

function getStyleBg(idx) {
  const bgs = ['#fce4ec','#e8eaf6','#fff8e1','#e8f5e9','#e3f2fd','#fce4ec','#4a1a3e','#e8f5e9'];
  return bgs[idx % bgs.length];
}
function getStyleEmoji(tags) {
  const tagStr = tags.join(',');
  if (tagStr.includes('法式') || tagStr.includes('简约')) return '💅';
  if (tagStr.includes('猫眼') || tagStr.includes('渐变')) return '✨';
  if (tagStr.includes('圣诞') || tagStr.includes('红')) return '🎄';
  if (tagStr.includes('手绘') || tagStr.includes('晕染')) return '🎨';
  return '💅';
}

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
  const tagColors = {'法式':'feed-tag-style','简约':'feed-tag-style','可爱':'feed-tag-scene','ins风':'feed-tag-scene','炫彩':'feed-tag-default','高级感':'feed-tag-style','温柔':'feed-tag-scene','日系':'feed-tag-season','节日':'feed-tag-season','闪粉':'feed-tag-default','圣诞':'feed-tag-season','清新':'feed-tag-scene','秋冬':'feed-tag-season','冷淡':'feed-tag-style','夏日':'feed-tag-season','高级':'feed-tag-style','猫眼':'feed-tag-style','渐变':'feed-tag-default','镜面':'feed-tag-style','手绘':'feed-tag-scene'};
  document.getElementById('feed-container').innerHTML = nailStyles.map(s => `
    <div class="feed-card" onclick="openDetail(${s.id},'home')">
      <div class="feed-img" style="background:${s.bg}">
        ${s.image_url ? `<img src="${staticUrl(s.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:14px 14px 0 0" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><span style="display:none">${s.emoji}</span>` : s.emoji}
      </div>
      <div class="feed-card-bottom">
        <div class="feed-name">${s.name}</div>
        <div class="feed-tags">${s.tags.slice(0,3).map(t=>`<span class="feed-tag ${tagColors[t]||'feed-tag-default'}">${t}</span>`).join('')}</div>
        <div class="feed-bottom-row">
          <div class="feed-price"><span class="feed-price-unit">¥</span>${s.price}</div>
          <button class="tryon-btn" onclick="event.stopPropagation();tryFromFeed(${s.id})">AI 试款</button>
        </div>
      </div>
    </div>
  `).join('');
}

function tryFromFeed(id) {
  if (!handUploaded) {
    if (confirm('需要先上传手图才能AI试款哦~\n\n点击"确定"去上传手图')) {
      navigateTo('upload');
    }
  } else {
    openDetail(id, 'home');
  }
}

// AI栏文字轮播
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
  reportEvent('try_on', id);
}

function renderDetailPage() {
  const item = nailStyles.find(s => s.id === currentDetailId);
  if (!item) return;

  document.getElementById('thumb-row').innerHTML = nailStyles.slice(0,6).map(s => {
    const isSelected = selectedThumbs.has(s.id);
    const isActive = s.id === currentDetailId && !multiSelectMode;
    return `<div class="thumb ${isSelected?'selected':''} ${isActive?'active':''}" style="background:${s.bg}" onclick="onThumbClick(${s.id})">
      ${s.emoji}
      ${multiSelectMode ? (isSelected ? '<div class="thumb-check"><i class="ti ti-check"></i></div>' : '<div class="thumb-uncheck"></div>') : ''}
    </div>`;
  }).join('');

  if (!multiSelectMode || selectedThumbs.size <= 1) {
    const imgContent = item.image_url 
      ? `<img src="${staticUrl(item.image_url)}" style="max-width:80%;max-height:80%;object-fit:contain;border-radius:12px" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><span class="emoji-lg" style="display:none">${item.emoji}</span>`
      : `<span class="emoji-lg">${item.emoji}</span>`;
    
    document.getElementById('tryon-main').innerHTML = `
      <div class="tryon-bigimg">
        ${imgContent}
        <div class="tryon-generating"><div class="pulse-dot" style="background:#8b5cf6"></div><span>试戴效果生成中…</span></div>
        <div class="tryon-actions">
          <div class="tryon-action-btn" title="保存" onclick="alert('已保存到相册')"><i class="ti ti-download"></i></div>
          <div class="tryon-action-btn" title="分享" onclick="alert('分享链接已复制')"><i class="ti ti-share"></i></div>
          <div class="tryon-action-btn" title="收藏" onclick="this.querySelector('i').style.color='#8b5cf6';reportEvent('favorite',${item.id})"><i class="ti ti-heart"></i></div>
        </div>
      </div>
      <div class="nail-meta"><span class="nail-name">${item.name}</span><div class="nail-tags-row">${item.tags.map(t=>`<span class="nail-tag">${t}</span>`).join('')}</div></div>
      <div class="tryon-rating"><span>效果满意吗？</span><div class="rating-btns"><button class="rate-btn" onclick="this.classList.add('rated');submitEvaluation('try_on',${item.id},5,true)"><i class="ti ti-thumb-up"></i></button><button class="rate-btn" onclick="this.classList.add('rated');submitEvaluation('try_on',${item.id},2,false)"><i class="ti ti-thumb-down"></i></button></div></div>
      <button class="nail-book-btn" onclick="alert('正在跳转预约页面…\\n\\n¥${item.price} · ${item.name}\\n${item.shop}')"><i class="ti ti-calendar"></i> 立即预约 ¥${item.price}</button>
    `;

    // 如果有手图，尝试调用试戴 API
    if (backendAvailable && uploadedHandImageUrl && item.image_url) {
      callTryOnAPI(item);
    }
  } else {
    renderCompareGrid();
  }

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

// 调用试戴 API
async function callTryOnAPI(item) {
  if (!backendAvailable) return;
  try {
    const result = await apiPost('/try-on', {
      hand_image_url: uploadedHandImageUrl,
      style_image_url: item.image_url,
      style_id: item.style_id || String(item.id),
    });
    if (result && result.result_image_url) {
      const bigimg = document.querySelector('.tryon-bigimg');
      if (bigimg) {
        bigimg.innerHTML = `
          <img src="${staticUrl(result.result_image_url)}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:12px">
          <div class="tryon-actions">
            <div class="tryon-action-btn" title="保存" onclick="alert('已保存到相册')"><i class="ti ti-download"></i></div>
            <div class="tryon-action-btn" title="分享" onclick="alert('分享链接已复制')"><i class="ti ti-share"></i></div>
            <div class="tryon-action-btn" title="收藏" onclick="this.querySelector('i').style.color='#8b5cf6'"><i class="ti ti-heart"></i></div>
          </div>
        `;
      }
    }
  } catch (e) {
    console.warn('[试戴] API 调用失败:', e.message);
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

// ===== AI对话（联调后端 /api/chat） =====
function initChat() {
  chatMessages = [];
  conversationId = null;
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
        <div class="style-card" onclick="openDetail(${c.id},'chat')"><div class="style-card-img" style="background:${c.bg}">${c.image_url ? `<img src="${staticUrl(c.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:10px 10px 0 0" onerror="this.style.display='none'">` : c.emoji}</div><div class="style-card-name">${c.name}</div><button class="style-card-tryon" onclick="event.stopPropagation();openDetail(${c.id},'chat')">试款</button></div>
      `).join('')}</div>`;
    }
    if (m.tips) {
      const tipsArr = Array.isArray(m.tips) ? m.tips : [m.tips];
      html += `<div class="tips-box"><div class="tips-title">💡 小贴士</div>${tipsArr.map(t=>`<div class="tips-item">· ${t}</div>`).join('')}</div>`;
    }
    if (m.guideQs) {
      html += `<div class="guide-qs">${m.guideQs.map(q=>`<div class="guide-q" onclick="sendQuickMsg('${q.replace(/'/g, "\\'")}')">${q}</div>`).join('')}</div>`;
    }
    html += '</div></div></div>';
    return html;
  }).join('');
  body.scrollTop = body.scrollHeight;
  if (chatMessages.length > 1) document.getElementById('chat-quick-tags').style.display = 'none';
}

async function sendMsg() {
  const input = document.getElementById('chat-input');
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  addUserMsg(text);

  // 显示打字中动画
  chatMessages.push({role:'ai',text:'<div class="typing-indicator"><span></span><span></span><span></span></div>',cards:null,tips:null,guideQs:null,isTyping:true});
  renderChat();

  if (backendAvailable) {
    try {
      const response = await apiPost('/chat', {
        query: text,
        user_id: 'demo_user',
        hand_profile_id: handProfileId || null,
        conversation_id: conversationId || null,
      });
      
      chatMessages = chatMessages.filter(m => !m.isTyping);
      conversationId = response.conversation_id;
      
      const answer = response.answer;
      const cards = answer.recommendations && answer.recommendations.length > 0
        ? answer.recommendations.map(r => {
            const existing = nailStyles.find(s => s.style_id === r.style_id || s.name === r.style_name);
            return existing || { id: 0, name: r.style_name, bg: '#fce4ec', emoji: '💅', image_url: r.image_url || '' };
          })
        : null;
      
      const tips = answer.tips ? answer.tips.split('\n').filter(t => t.trim()) : null;
      const guideQs = response.suggested_questions && response.suggested_questions.length > 0 ? response.suggested_questions : null;
      
      let msgText = '';
      if (answer.scene_analysis) msgText += `<div class="ai-section-title">场景分析</div>${answer.scene_analysis}`;
      if (answer.follow_up) msgText += (msgText ? '<br><br>' : '') + answer.follow_up;
      if (!msgText) msgText = '根据你的描述，我来帮你推荐~';

      addAiMsg(msgText, cards, tips, guideQs);
    } catch (e) {
      chatMessages = chatMessages.filter(m => !m.isTyping);
      // 回退到本地 mock
      const r = genReplyLocal(text);
      addAiMsg(r.text, r.cards, r.tips, r.guideQs);
    }
  } else {
    setTimeout(() => {
      chatMessages = chatMessages.filter(m => !m.isTyping);
      const r = genReplyLocal(text);
      addAiMsg(r.text, r.cards, r.tips, r.guideQs);
    }, 1200);
  }
}

function sendQuickMsg(text) { document.getElementById('chat-input').value = text; sendMsg(); }

// 本地 mock 回复（兜底）
function genReplyLocal(q) {
  const ql = q.toLowerCase();
  let cards = [], text = '', tips = null, guideQs = null;

  if (ql.includes('圣诞') || ql.includes('节日') || ql.includes('520') || ql.includes('新年')) {
    cards = nailStyles.filter(s=>s.tags.some(t=>t.includes('节日')||t.includes('圣诞'))).slice(0,3);
    text = '<div class="ai-section-title">场景分析</div>圣诞节适合喜庆又精致的款式，今年流行"暗调高级感"，酒红搭配金属光泽非常出圈。';
    tips = ['圣诞前3-5天预约，避开节日高峰','闪粉款建议选凝胶，持久不掉色','金色系点缀让节日感更强'];
    guideQs = ['我是暖黄皮，适合哪款？','附近哪家店可以做圣诞款？'];
  } else if (ql.includes('黄皮') || ql.includes('显白') || ql.includes('肤色')) {
    cards = nailStyles.filter(s=>s.tags.some(t=>t.includes('简约')||t.includes('温柔'))).slice(0,3);
    text = '<div class="ai-section-title">场景分析</div>暖黄皮推荐冷调色系提亮肤色，裸粉、奶白、冷紫都是显白好选择。';
    tips = ['避免饱和度过高的亮黄/亮橙','裸色系+微闪是万能显白搭配','短甲做竖向线条设计更显长'];
    guideQs = ['帮我看看哪款最显手白','有没有适合通勤的款？'];
  } else if (ql.includes('法式') || ql.includes('简约') || ql.includes('通勤')) {
    cards = nailStyles.filter(s=>s.tags.includes('法式')||s.tags.includes('简约')).slice(0,3);
    text = '<div class="ai-section-title">场景分析</div>通勤款追求耐看不夸张，法式简约永不过时。';
    tips = ['法式建议选甲油胶，持久2-3周','微笑线越薄越显精致','裸色打底百搭任何衣服'];
    guideQs = ['有没有再高级一点的款？','这些款大概多少钱？'];
  } else {
    cards = nailStyles.slice(0,3);
    text = '<div class="ai-section-title">为你推荐</div>根据你的描述，我觉得这几款可能适合你~点击可以直接试款哦';
    tips = ['可以多试几款对比效果再做决定','上传手图能获得更精准的推荐'];
    guideQs = ['有没有更显白的？','帮我看看适合约会的款'];
  }

  return { text, cards, tips, guideQs };
}

// ===== 手图上传（联调后端 /api/upload-image + /api/analyze-hand） =====
function simulateUpload() {
  if (backendAvailable) {
    // 真实上传：触发文件选择器
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      
      const area = document.getElementById('upload-area');
      area.className = 'upload-placeholder uploaded';
      area.innerHTML = '<span class="uploaded-emoji">⏳</span><div class="reupload-badge"><i class="ti ti-refresh"></i> 上传中...</div>';
      
      try {
        const result = await apiUpload('/upload-image', file);
        uploadedHandImageUrl = result.url || result.image_url;
        
        // 调用标准化质检
        const stdResult = await standardizeHand(uploadedHandImageUrl);
        if (!stdResult.quality_pass) {
          area.className = 'upload-placeholder';
          const issues = stdResult.issues ? stdResult.issues.join('、') : '图片质量不达标';
          area.innerHTML = `<div class="upload-plus"><i class="ti ti-alert-triangle"></i></div><span class="upload-hint">质检未通过：${issues}<br>请重新上传</span>`;
          return;
        }
        
        handUploaded = true;
        area.innerHTML = `<span class="uploaded-emoji">🤚</span><div class="reupload-badge"><i class="ti ti-refresh"></i> 重新上传</div>`;
        document.getElementById('analyze-btn').disabled = false;
      } catch (err) {
        area.className = 'upload-placeholder';
        area.innerHTML = '<div class="upload-plus"><i class="ti ti-plus"></i></div><span class="upload-hint">上传失败，请重试</span>';
        console.error('[上传] 失败:', err.message);
      }
    };
    fileInput.click();
  } else {
    // Mock 模式
    handUploaded = true;
    const area = document.getElementById('upload-area');
    area.className = 'upload-placeholder uploaded';
    area.innerHTML = '<span class="uploaded-emoji">🤚</span><div class="reupload-badge"><i class="ti ti-refresh"></i> 重新上传</div>';
    document.getElementById('analyze-btn').disabled = false;
  }
}

async function startAnalysis() {
  if (!handUploaded) return;
  navigateTo('analyzing');
  
  const steps = [
    () => { document.getElementById('a-step-1').className='step-icon active'; document.getElementById('a-step-1').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-1').className='step-text'; },
    () => { document.getElementById('a-step-1').className='step-icon done'; document.getElementById('a-step-1').innerHTML='<i class="ti ti-check"></i>'; document.getElementById('a-step-2').className='step-icon active'; document.getElementById('a-step-2').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-2').className='step-text'; },
    () => { document.getElementById('a-step-2').className='step-icon done'; document.getElementById('a-step-2').innerHTML='<i class="ti ti-check"></i>'; document.getElementById('a-step-3').className='step-icon active'; document.getElementById('a-step-3').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-3').className='step-text'; },
  ];
  
  // 显示动画步骤
  steps.forEach((fn, i) => setTimeout(fn, i * 800));

  if (backendAvailable && uploadedHandImageUrl) {
    try {
      const result = await apiPost('/analyze-hand', {
        user_id: 'demo_user',
        hand_image_url: uploadedHandImageUrl,
      });
      handProfileId = result.hand_profile_id;
      handProfileData = result;
      
      // 动画完成后跳转
      setTimeout(() => {
        document.getElementById('a-step-3').className='step-icon done';
        document.getElementById('a-step-3').innerHTML='<i class="ti ti-check"></i>';
        setTimeout(() => navigateTo('recommend'), 400);
      }, 2800);
    } catch (e) {
      console.warn('[分析] API 调用失败，使用 mock:', e.message);
      handProfileData = { skin_tone: '暖黄皮', hand_shape: '标准手型', recommended_nail_shapes: ['方圆甲'], recommended_colors: ['裸粉','冷紫','奶白'] };
      setTimeout(() => {
        document.getElementById('a-step-3').className='step-icon done';
        document.getElementById('a-step-3').innerHTML='<i class="ti ti-check"></i>';
        setTimeout(() => navigateTo('recommend'), 400);
      }, 2800);
    }
  } else {
    // Mock 模式
    handProfileData = { skin_tone: '暖黄皮', hand_shape: '标准手型', recommended_nail_shapes: ['方圆甲'], recommended_colors: ['裸粉','冷紫','奶白'] };
    setTimeout(() => {
      document.getElementById('a-step-3').className='step-icon done';
      document.getElementById('a-step-3').innerHTML='<i class="ti ti-check"></i>';
      setTimeout(() => navigateTo('recommend'), 400);
    }, 2800);
  }
}

// ===== 推荐结果（联调后端 /api/recommendations） =====
async function renderRecommend() {
  let picks = nailStyles.slice(0,4);
  let profileDesc = '暖黄皮 · 标准型 · 方圆甲';

  if (backendAvailable && handProfileId) {
    try {
      const result = await apiPost('/recommendations', {
        user_id: 'demo_user',
        hand_profile_id: handProfileId,
        limit: 4,
      });
      if (result.recommendations && result.recommendations.length > 0) {
        picks = result.recommendations.map((r, idx) => {
          const existing = nailStyles.find(s => s.style_id === r.style_id || s.name === r.style_name);
          return existing || {
            id: 100 + idx,
            name: r.style_name,
            tags: r.matched_tags || [],
            bg: getStyleBg(idx),
            emoji: '💅',
            price: 158,
            reason: r.reason,
            image_url: r.image_url || '',
          };
        });
      }
    } catch (e) {
      console.warn('[推荐] API 调用失败，使用本地数据:', e.message);
    }
  }

  if (handProfileData) {
    const hp = handProfileData;
    profileDesc = `${hp.skin_tone || '暖黄皮'} · ${hp.hand_shape || '标准型'} · ${(hp.recommended_nail_shapes || ['方圆甲'])[0]}`;
  }

  const reportHtml = `<div class="hand-report">
    <div class="hand-report-emoji">🤚</div>
    <div class="hand-report-info">
      <div class="hand-report-title">你的手型报告</div>
      <div class="hand-report-desc">肤色${handProfileData?.skin_tone || '偏暖黄'}，手型${handProfileData?.hand_shape || '标准'}，适合大多数甲形</div>
      <div class="hand-report-tags">
        <span class="hand-report-tag">${handProfileData?.skin_tone || '暖黄皮'}</span>
        <span class="hand-report-tag">${handProfileData?.hand_shape || '标准手型'}</span>
        <span class="hand-report-tag">${(handProfileData?.recommended_nail_shapes || ['方圆甲'])[0]}最佳</span>
        <span class="hand-report-tag">适合${(handProfileData?.recommended_colors || ['暖色调'])[0]}</span>
      </div>
    </div>
  </div>`;

  document.querySelector('#page-recommend .result-body').innerHTML = `
    <div class="result-header">
      <div class="result-ai-badge"><i class="ti ti-sparkles"></i></div>
      <div><div class="result-title">根据你的手型推荐了 ${picks.length} 款</div><div class="result-sub">${profileDesc}</div></div>
    </div>
    ${reportHtml}
    <div class="rec-grid">${picks.map(s => `
      <div class="rec-cell" onclick="openDetail(${s.id},'recommend')">
        <div class="rec-img" style="background:${s.bg}">
          ${s.image_url ? `<img src="${staticUrl(s.image_url)}" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><span style="display:none">${s.emoji}</span>` : s.emoji}
        </div>
        <div class="rec-reason">${s.reason || '适合你的手型'}</div>
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
initBackend();

// ===== 事件上报（联调 POST /api/events） =====
async function reportEvent(eventType, styleId, source = 'organic') {
  if (!backendAvailable) return;
  try {
    await apiPost('/events', {
      user_id: 'demo_user',
      style_id: String(styleId),
      event_type: eventType,
      source: source,
    });
  } catch (e) {
    console.warn('[事件] 上报失败:', e.message);
  }
}

// ===== 评测提交（联调 POST /api/evaluations） =====
async function submitEvaluation(targetType, targetId, score, isPositive) {
  if (!backendAvailable) return;
  const dimensionMap = {
    try_on: isPositive ? { style_fidelity: 5, hand_fidelity: 5 } : { style_fidelity: 2, hand_fidelity: 2 },
    chat: isPositive ? { retrieval_accuracy: 5 } : { retrieval_accuracy: 2 },
    hand_analysis: isPositive ? { skin_tone_accuracy: 5 } : { skin_tone_accuracy: 2 },
  };
  try {
    await apiPost('/evaluations', {
      target_type: targetType,
      target_id: String(targetId),
      scores: dimensionMap[targetType] || {},
      comment: isPositive ? '满意' : '不满意',
    });
    console.log('[评测] 提交成功:', targetType, targetId);
  } catch (e) {
    console.warn('[评测] 提交失败:', e.message);
  }
}

// ===== 手部标准化（联调 POST /api/standardize-hand） =====
async function standardizeHand(imageUrl) {
  if (!backendAvailable) return { quality_pass: true };
  try {
    const result = await apiPost('/standardize-hand', {
      hand_image_url: imageUrl,
      user_id: 'demo_user',
    });
    console.log('[标准化] 质检结果:', result.quality_pass ? '通过' : '不通过');
    return result;
  } catch (e) {
    console.warn('[标准化] 调用失败，跳过质检:', e.message);
    return { quality_pass: true };
  }
}
