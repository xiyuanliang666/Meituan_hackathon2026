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
// 每个款式的历史试戴结果图：Map<styleId, string[]>
let tryonHistory = {};
// 收藏集合（持久化到 localStorage）
let favoritesSet = new Set(JSON.parse(localStorage.getItem('prism_favorites') || '[]'));

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
      nailStyles = data.styles.map((s, idx) => {
        // tags 可能是对象（{style_tags:[], scene_tags:[], ...}）或数组
        let tagsArr = [];
        if (Array.isArray(s.tags)) {
          tagsArr = s.tags;
        } else if (s.tags && typeof s.tags === 'object') {
          // 展平所有子标签，优先取 style_tags + scene_tags + color_system
          tagsArr = [
            ...(s.tags.style_tags || []),
            ...(s.tags.scene_tags || []),
            ...(s.tags.color_system || []),
          ].slice(0, 4);
        }
        // 图片：优先 enhanced，其次 original，其次 image_url
        const imageUrl = s.enhanced_style_image_url
          || s.original_style_image_url
          || s.image_url
          || '';
        return {
          id: s.id || idx + 1,
          name: s.style_name || s.name || '美甲款式',
          tags: tagsArr,
          bg: getStyleBg(idx),
          emoji: getStyleEmoji(tagsArr),
          price: s.price || (120 + Math.floor(Math.random() * 100)),
          reason: s.reason || '',
          shop: s.shop || '蔻丹美甲·朝阳店',
          image_url: imageUrl,
          style_id: s.style_id || String(s.id || idx + 1),
        };
      });
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
  if (page === 'tryon-history') loadTryonHistory();
  if (page === 'hands') loadUserHands();
  if (page === 'favorites') renderFavoritesPage();
  // 上传完成后跳回待试款式
  if (page === 'home' && window._pendingTryStyleId) {
    const pid = window._pendingTryStyleId;
    window._pendingTryStyleId = null;
    if (handUploaded) setTimeout(() => openDetail(pid, 'home'), 100);
  }
}
function goBackFromDetail() { navigateTo(detailFrom); }

// ===== 首页Feed =====
function renderFeed() {
  const tagColors = {'法式':'feed-tag-style','简约':'feed-tag-style','可爱':'feed-tag-scene','ins风':'feed-tag-scene','炫彩':'feed-tag-default','高级感':'feed-tag-style','温柔':'feed-tag-scene','日系':'feed-tag-season','节日':'feed-tag-season','闪粉':'feed-tag-default','圣诞':'feed-tag-season','清新':'feed-tag-scene','秋冬':'feed-tag-season','冷淡':'feed-tag-style','夏日':'feed-tag-season','高级':'feed-tag-style','猫眼':'feed-tag-style','渐变':'feed-tag-default','镜面':'feed-tag-style','手绘':'feed-tag-scene'};
  // 图片容器内联样式：固定宽高比3:4，cover居中，完全不依赖外部CSS
  const imgBoxStyle = 'width:100%;aspect-ratio:3/4;position:relative;overflow:hidden;display:block;background:#f0ece8;border-radius:12px 12px 0 0';
  const imgStyle    = 'position:absolute;top:0;left:0;width:100%;height:100%;object-fit:cover;object-position:center top;display:block';
  const overlayStyle= 'position:absolute;bottom:0;left:0;right:0;height:56px;background:linear-gradient(transparent,rgba(0,0,0,.38));pointer-events:none;z-index:1';
  const labelStyle  = 'position:absolute;bottom:8px;left:50%;transform:translateX(-50%);background:rgba(255,255,255,.93);color:#8d79b8;font-size:10px;font-weight:600;padding:3px 12px;border-radius:20px;white-space:nowrap;z-index:2;box-shadow:0 1px 5px rgba(141,121,184,.25)';
  const nameStyle   = 'font-size:12px;font-weight:600;color:rgba(42,32,24,.88);margin-bottom:5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis';

  document.getElementById('feed-container').innerHTML = nailStyles.map(s => `
    <div class="feed-card" onclick="openDetail(${s.id},'home')">
      <div style="${imgBoxStyle}">
        ${s.image_url
          ? `<img src="${staticUrl(s.image_url)}" style="${imgStyle}" onerror="this.style.display='none'">`
          : `<div style="position:absolute;top:0;left:0;width:100%;height:100%;display:flex;align-items:center;justify-content:center;font-size:40px">${s.emoji}</div>`
        }
        <div style="${overlayStyle}"></div>
        <div style="${labelStyle}">立即试戴</div>
      </div>
      <div style="padding:9px 11px 11px">
        <div style="${nameStyle}">${s.name}</div>
        <div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:8px">${s.tags.slice(0,3).map(t=>`<span class="feed-tag ${tagColors[t]||'feed-tag-default'}">${t}</span>`).join('')}</div>
        <div style="display:flex;align-items:center;justify-content:space-between">
          <div class="feed-price"><span class="feed-price-unit">¥</span>${s.price}</div>
          <button class="tryon-btn" onclick="event.stopPropagation();tryFromFeed(${s.id})">AI 试款</button>
        </div>
      </div>
    </div>
  `).join('');
}



function tryFromFeed(id) {
  if (!handUploaded) {
    showUploadGuideModal(id);
  } else {
    openDetail(id, 'home');
  }
}

// 自定义弹窗：引导上传手图
function showUploadGuideModal(pendingStyleId) {
  const existing = document.getElementById('upload-guide-modal');
  if (existing) existing.remove();
  const modal = document.createElement('div');
  modal.id = 'upload-guide-modal';
  modal.innerHTML = `
    <div class="modal-backdrop" onclick="closeUploadGuideModal()"></div>
    <div class="modal-sheet">
      <div class="modal-icon">🤚</div>
      <div class="modal-title">先上传手图</div>
      <div class="modal-desc">上传一张手图后，AI 才能为你生成专属试戴效果</div>
      <button class="modal-btn-primary" onclick="closeUploadGuideModal();navigateTo('upload');window._pendingTryStyleId=${pendingStyleId||'null'}">去上传手图</button>
      <button class="modal-btn-secondary" onclick="closeUploadGuideModal()">再看看其他款</button>
    </div>`;
  document.getElementById('app').appendChild(modal);
}
function closeUploadGuideModal() {
  const m = document.getElementById('upload-guide-modal');
  if (m) m.remove();
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

  // 缩略图 = 当前款式的历史试戴结果图，首次进入为空
  const historyImgs = tryonHistory[currentDetailId] || [];
  const thumbRow = document.getElementById('thumb-row');
  if (historyImgs.length === 0 && !multiSelectMode) {
    thumbRow.innerHTML = '<div style="font-size:11px;color:#bbb;padding:0 4px;white-space:nowrap">试戴后将在此显示历史效果</div>';
  } else {
    thumbRow.innerHTML = historyImgs.map((imgUrl, idx) => `
      <div class="thumb ${idx === (historyImgs.length-1) ? 'active' : ''}" style="overflow:hidden;background:#f7f4ef" onclick="onHistoryThumbClick('${imgUrl}')">
        <img src="${imgUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:9px">
      </div>`).join('') + (multiSelectMode ? nailStyles.slice(0,6).map(s => {
        const isSelected = selectedThumbs.has(s.id);
        const thumbContent = s.image_url
          ? `<img src="${s.image_url}" style="width:100%;height:100%;object-fit:cover;border-radius:9px" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><span style="display:none;font-size:22px">${s.emoji}</span>`
          : s.emoji;
        return `<div class="thumb ${isSelected?'selected':''}" style="background:${s.bg};overflow:hidden" onclick="onThumbClick(${s.id})">
          ${thumbContent}
          ${isSelected ? '<div class="thumb-check"><i class="ti ti-check"></i></div>' : '<div class="thumb-uncheck"></div>'}
        </div>`;
      }).join('') : '');
  }

  if (!multiSelectMode || selectedThumbs.size <= 1) {
    const isFav = favoritesSet.has(item.id);
    const lastResult = historyImgs.length > 0 ? historyImgs[historyImgs.length-1] : null;

    document.getElementById('tryon-main').innerHTML = `
      <div class="tryon-bigimg" id="tryon-bigimg-inner">
        ${lastResult
          ? `<img src="${lastResult}" style="max-width:100%;max-height:100%;object-fit:contain;border-radius:12px">`
          : (item.image_url
              ? `<img src="${staticUrl(item.image_url)}" style="max-width:80%;max-height:80%;object-fit:contain;border-radius:12px" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><span class="emoji-lg" style="display:none">${item.emoji}</span>`
              : `<span class="emoji-lg">${item.emoji}</span>`)
        }
        <div class="tryon-actions">
          <div class="tryon-action-btn" title="保存" onclick="downloadTryonResult(${item.id})"><i class="ti ti-download"></i></div>
          <div class="tryon-action-btn" title="分享" onclick="alert('分享链接已复制')"><i class="ti ti-share"></i></div>
          <div class="tryon-action-btn${isFav?' faved':''}" title="收藏" id="fav-btn-${item.id}" onclick="toggleFavorite(${item.id})"><i class="ti ${isFav?'ti-heart-filled':'ti-heart'}"></i></div>
        </div>
      </div>
      <div class="nail-meta"><span class="nail-name">${item.name}</span><div class="nail-tags-row">${item.tags.map(t=>`<span class="nail-tag">${t}</span>`).join('')}</div></div>
      <div class="tryon-rating"><span>效果满意吗？</span><div class="rating-btns"><button class="rate-btn" onclick="this.classList.add('rated');submitEvaluation('try_on',${item.id},5,true)"><i class="ti ti-thumb-up"></i></button><button class="rate-btn" onclick="this.classList.add('rated');submitEvaluation('try_on',${item.id},2,false)"><i class="ti ti-thumb-down"></i></button></div></div>
      <button class="nail-book-btn" onclick="alert('正在跳转预约页面…\\n\\n¥${item.price} · ${item.name}\\n${item.shop}')"><i class="ti ti-calendar"></i> 立即预约 ¥${item.price}</button>
    `;

    // 有手图时调用试戴 API，并展示进度条
    if (uploadedHandImageUrl && item.image_url && !lastResult) {
      startTryOnWithProgress(item);
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

// 点击历史缩略图，主区域切换到对应结果图
function onHistoryThumbClick(imgUrl) {
  const bigimg = document.getElementById('tryon-bigimg-inner');
  if (!bigimg) return;
  const existingImg = bigimg.querySelector('img:first-child');
  if (existingImg) { existingImg.src = imgUrl; }
}

// 收藏切换（持久化到 localStorage）
function toggleFavorite(styleId) {
  if (favoritesSet.has(styleId)) {
    favoritesSet.delete(styleId);
  } else {
    favoritesSet.add(styleId);
    reportEvent('favorite', styleId);
  }
  localStorage.setItem('prism_favorites', JSON.stringify([...favoritesSet]));
  const isFav = favoritesSet.has(styleId);
  // 更新详情页收藏按钮图标（实心/空心）
  const btn = document.getElementById(`fav-btn-${styleId}`);
  if (btn) {
    btn.className = `tryon-action-btn${isFav?' faved':''}`;
    const icon = btn.querySelector('i');
    if (icon) icon.className = `ti ${isFav?'ti-heart-filled':'ti-heart'}`;
  }
  renderFavoritesPage();
}

// 真实下载试戴结果图
function downloadTryonResult(styleId) {
  const historyImgs = tryonHistory[styleId] || [];
  const imgUrl = historyImgs.length > 0 ? historyImgs[historyImgs.length-1] : null;
  if (!imgUrl) { alert('暂无试戴效果图，请先生成试戴效果'); return; }
  const a = document.createElement('a');
  a.href = imgUrl;
  a.download = `prism_tryon_${styleId}_${Date.now()}.jpg`;
  a.target = '_blank';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
}

// 带进度条的试戴调用
function startTryOnWithProgress(item) {
  const bigimg = document.getElementById('tryon-bigimg-inner');
  if (!bigimg) return;

  // 注入进度条 UI（覆盖在图片上方）
  const overlay = document.createElement('div');
  overlay.id = 'tryon-progress-overlay';
  overlay.innerHTML = `
    <div class="tryon-progress-bg"></div>
    <div class="tryon-progress-box">
      <div class="tryon-progress-label">试戴效果生成中…<span id="tryon-pct">0%</span></div>
      <div class="tryon-progress-bar"><div class="tryon-progress-fill" id="tryon-fill"></div></div>
    </div>`;
  bigimg.appendChild(overlay);

  let pct = 0;
  let timer = setInterval(() => {
    if (pct < 60) pct += 2;
    else if (pct < 95) pct += 0.3;
    pct = Math.min(pct, 95);
    updateProgress(pct);
  }, 120);

  function updateProgress(v) {
    const fill = document.getElementById('tryon-fill');
    const label = document.getElementById('tryon-pct');
    if (fill) fill.style.width = v.toFixed(0) + '%';
    if (label) label.textContent = v.toFixed(0) + '%';
  }

  function finishProgress(resultUrl) {
    clearInterval(timer);
    updateProgress(100);
    setTimeout(() => {
      const ol = document.getElementById('tryon-progress-overlay');
      if (ol) ol.remove();
      if (resultUrl) {
        const existingImg = bigimg.querySelector('img');
        if (existingImg) existingImg.src = resultUrl;
        else {
          const img = document.createElement('img');
          img.src = resultUrl;
          img.style.cssText = 'max-width:100%;max-height:100%;object-fit:contain;border-radius:12px';
          bigimg.insertBefore(img, bigimg.querySelector('.tryon-actions'));
        }
        // 追加到历史
        if (!tryonHistory[item.id]) tryonHistory[item.id] = [];
        tryonHistory[item.id].push(resultUrl);
        // 更新缩略图
        const historyImgs = tryonHistory[item.id];
        const thumbRow = document.getElementById('thumb-row');
        if (thumbRow) {
          thumbRow.innerHTML = historyImgs.map((url, idx) => `
            <div class="thumb ${idx===historyImgs.length-1?'active':''}" style="overflow:hidden;background:#f7f4ef" onclick="onHistoryThumbClick('${url}')">
              <img src="${url}" style="width:100%;height:100%;object-fit:cover;border-radius:9px">
            </div>`).join('');
        }
      }
    }, 300);
  }

  if (backendAvailable) {
    callTryOnAPI(item).then(resultUrl => finishProgress(resultUrl)).catch(() => finishProgress(null));
  } else {
    // Mock 模式：模拟延迟后使用款式原图作为结果
    setTimeout(() => finishProgress(staticUrl(item.image_url)), 2500);
  }
}

// 收藏页渲染
function renderFavoritesPage() {
  const favItems = nailStyles.filter(s => favoritesSet.has(s.id));
  const container = document.querySelector('#page-favorites');
  if (!container) return;
  if (favItems.length === 0) {
    container.innerHTML = `<header class="nav-bar"><span class="nav-title">我的收藏</span><i class="ti ti-x nav-icon" onclick="navigateTo('home')"></i></header>
      <div class="empty-state"><div class="empty-icon">💅</div><div class="empty-title">还没有收藏</div><div class="empty-sub">浏览美甲款式，点击❤️收藏喜欢的</div><button class="cta-btn" style="width:auto;padding:10px 32px" onclick="navigateTo('home')">去逛逛</button></div>`;
  } else {
    container.innerHTML = `<header class="nav-bar"><span class="nav-title">我的收藏</span><i class="ti ti-x nav-icon" onclick="navigateTo('home')"></i></header>
      <div class="feed" style="padding-bottom:20px">${favItems.map(s => `
        <div class="feed-card" onclick="openDetail(${s.id},'favorites')">
          <div class="feed-img" style="background:${s.bg}">
            ${s.image_url ? `<img src="${staticUrl(s.image_url)}" style="width:100%;height:auto;display:block;border-radius:20px 20px 0 0" onerror="this.style.display='none'">` : `<span style="font-size:38px;min-height:140px;display:flex;align-items:center;justify-content:center;width:100%">${s.emoji}</span>`}
            <div class="feed-tryon-label">立即试戴</div>
          </div>
          <div class="feed-card-bottom">
            <div class="feed-name">${s.name}</div>
            <div class="feed-tags">${s.tags.slice(0,3).map(t=>`<span class="feed-tag feed-tag-default">${t}</span>`).join('')}</div>
          </div>
        </div>`).join('')}
      </div>`;
  }
}

// 调用试戴 API，返回结果图 URL
async function callTryOnAPI(item) {
  try {
    const result = await apiPost('/try-on', {
      hand_image_url: uploadedHandImageUrl,
      style_image_url: item.image_url,
      style_id: item.style_id || String(item.id),
    });
    if (result && result.result_image_url) {
      return staticUrl(result.result_image_url);
    }
  } catch (e) {
    console.warn('[试戴] API 调用失败:', e.message);
  }
  return null;
}

// AI 微调面板
function openAiTunePanel() {
  const item = nailStyles.find(s => s.id === currentDetailId);
  if (!item) return;
  const existing = document.getElementById('ai-tune-modal');
  if (existing) { existing.remove(); return; }
  const modal = document.createElement('div');
  modal.id = 'ai-tune-modal';
  modal.innerHTML = `
    <div class="modal-backdrop" onclick="document.getElementById('ai-tune-modal').remove()"></div>
    <div class="modal-sheet">
      <div class="modal-icon">✨</div>
      <div class="modal-title">AI 微调</div>
      <div class="modal-desc" style="margin-bottom:12px">告诉 AI 你想如何调整效果</div>
      <textarea id="ai-tune-input" style="width:100%;height:80px;border:.5px solid #d9cdea;border-radius:10px;padding:10px;font-size:13px;font-family:inherit;resize:none;outline:none;background:#faf8ff" placeholder="例如：颜色再深一点、指甲更长一点…"></textarea>
      <button class="modal-btn-primary" style="margin-top:10px" onclick="submitAiTune(${item.id})">生成微调效果</button>
      <button class="modal-btn-secondary" onclick="document.getElementById('ai-tune-modal').remove()">取消</button>
    </div>`;
  document.getElementById('app').appendChild(modal);
}

async function submitAiTune(styleId) {
  const input = document.getElementById('ai-tune-input');
  const desc = input ? input.value.trim() : '';
  document.getElementById('ai-tune-modal')?.remove();
  const item = nailStyles.find(s => s.id === styleId);
  if (!item) return;
  if (!uploadedHandImageUrl) { showUploadGuideModal(styleId); return; }
  startTryOnWithProgress({ ...item, _tuneDesc: desc });
}

function toggleMultiSelect() {
  multiSelectMode = !multiSelectMode;
  if (!multiSelectMode) { selectedThumbs = new Set([currentDetailId]); }
  renderDetailPage();
}

function onThumbClick(id) {
  if (multiSelectMode) {
    if (selectedThumbs.has(id)) {
      selectedThumbs.delete(id);
    } else if (selectedThumbs.size < 4) {
      // 上限改为四图
      selectedThumbs.add(id);
    } else {
      alert('最多同时对比 4 款哦');
      return;
    }
  } else {
    currentDetailId = id;
    selectedThumbs = new Set([id]);
  }
  renderDetailPage();
}

function renderCompareGrid() {
  const items = [...selectedThumbs].map(id => nailStyles.find(s=>s.id===id)).filter(Boolean);
  const n = items.length;
  // 上限四图：2图上下布局，3/4图四宫格
  let gridClass, maxCells;
  if (n <= 2) { gridClass = 'g2v'; maxCells = 2; }   // 上下排列
  else { gridClass = 'g4'; maxCells = 4; }

  let cells = items.map(s => {
    const resultImgs = tryonHistory[s.id] || [];
    const displayUrl = resultImgs.length > 0 ? resultImgs[resultImgs.length-1] : null;
    const imgContent = displayUrl
      ? `<img src="${displayUrl}" style="width:100%;height:100%;object-fit:cover">`
      : (s.image_url
          ? `<img src="${staticUrl(s.image_url)}" style="width:100%;height:100%;object-fit:cover" onerror="this.style.display='none';this.nextElementSibling.style.display='flex'"><span style="display:none;width:100%;height:100%;align-items:center;justify-content:center;font-size:28px">${s.emoji}</span>`
          : `<span style="font-size:28px">${s.emoji}</span>`);
    return `<div class="grid-cell" style="background:${s.bg}">${imgContent}<span class="cell-name">${s.name}</span><span class="cell-price">¥${s.price}</span></div>`;
  });
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
  // 无论后端是否可用，都触发真实文件选择器
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/*';
  fileInput.onchange = async (e) => {
    const file = e.target.files[0];
    if (!file) return;

    const area = document.getElementById('upload-area');
    // 先用本地 ObjectURL 预览图片
    const localUrl = URL.createObjectURL(file);
    area.className = 'upload-placeholder uploaded';
    area.innerHTML = `<img src="${localUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:16px"><div class="reupload-badge"><i class="ti ti-refresh"></i> 重新上传</div>`;

    if (backendAvailable) {
      // 后端可用：执行真实上传 + 质检
      try {
        const result = await apiUpload('/upload-image', file);
        uploadedHandImageUrl = result.url || result.image_url;

        const stdResult = await standardizeHand(uploadedHandImageUrl);
        if (!stdResult.quality_pass) {
          area.className = 'upload-placeholder';
          const issues = stdResult.issues ? stdResult.issues.join('、') : '图片质量不达标';
          area.innerHTML = `<div class="upload-plus"><i class="ti ti-alert-triangle"></i></div><span class="upload-hint">质检未通过：${issues}<br>请重新上传</span>`;
          URL.revokeObjectURL(localUrl);
          return;
        }
      } catch (err) {
        console.warn('[上传] 后端上传失败，继续使用本地预览:', err.message);
        uploadedHandImageUrl = localUrl;
      }
    } else {
      // Mock 模式：使用本地 ObjectURL 作为手图地址
      uploadedHandImageUrl = localUrl;
    }

    handUploaded = true;
    document.getElementById('analyze-btn').disabled = false;
    // 更新预览区，保留图片并追加重新上传徽标
    area.innerHTML = `<img src="${uploadedHandImageUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:16px"><div class="reupload-badge"><i class="ti ti-refresh"></i> 重新上传</div>`;
  };
  fileInput.click();
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

// ===== 试戴历史（联调 GET /api/tryon-history） =====
async function loadTryonHistory() {
  const body = document.getElementById('tryon-history-body');
  if (!body) return;

  if (!backendAvailable) {
    body.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999"><div style="font-size:48px;margin-bottom:12px">⏱</div><div style="font-size:15px;font-weight:500;margin-bottom:6px">暂无试戴记录</div><div style="font-size:12px">试戴美甲后记录会显示在这里</div></div>';
    return;
  }

  body.innerHTML = '<div style="text-align:center;padding:40px;color:#8b5cf6"><div class="typing-indicator" style="justify-content:center"><span></span><span></span><span></span></div>加载中...</div>';

  try {
    const data = await apiGet('/tryon-history', { user_id: 'demo_user', limit: 20 });
    if (!data.records || data.records.length === 0) {
      body.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999"><div style="font-size:48px;margin-bottom:12px">⏱</div><div style="font-size:15px;font-weight:500;margin-bottom:6px">暂无试戴记录</div><div style="font-size:12px">试戴美甲后记录会显示在这里</div></div>';
      return;
    }
    body.innerHTML = data.records.map(r => `
      <div style="display:flex;gap:10px;padding:12px;background:#fff;border-radius:12px;border:.5px solid #f0f0f0;margin-bottom:10px;align-items:center">
        <img src="${staticUrl(r.result_image_url)}" style="width:64px;height:64px;border-radius:10px;object-fit:cover" onerror="this.src='';this.style.background='#f5f0ff';this.style.display='flex'">
        <div style="flex:1;min-width:0">
          <div style="font-size:13px;font-weight:500;margin-bottom:4px">${r.style_id || '试戴效果'}</div>
          <div style="font-size:11px;color:#999">${r.created_at || ''}</div>
        </div>
        <div style="display:flex;gap:6px">
          <div style="width:28px;height:28px;border-radius:50%;background:#f5f0ff;display:flex;align-items:center;justify-content:center;cursor:pointer" onclick="deleteTryonRecord('${r.record_id}')"><i class="ti ti-trash" style="font-size:13px;color:#8b5cf6"></i></div>
        </div>
      </div>
    `).join('') + `<div style="text-align:center;padding:8px;font-size:11px;color:#ccc">共 ${data.total} 条记录</div>`;
  } catch (e) {
    body.innerHTML = '<div style="text-align:center;padding:40px;color:#999">加载失败，请重试</div>';
    console.warn('[试戴历史] 加载失败:', e.message);
  }
}

async function deleteTryonRecord(recordId) {
  if (!confirm('确定删除这条试戴记录？')) return;
  try {
    await apiRequest(`/tryon-history/${recordId}`, { method: 'DELETE' });
    loadTryonHistory();
  } catch (e) {
    console.warn('[试戴历史] 删除失败:', e.message);
  }
}

// ===== 手图管理（联调 GET /api/user-hands） =====
async function loadUserHands() {
  const body = document.getElementById('hands-body');
  if (!body) return;

  if (!backendAvailable) {
    body.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999"><div style="font-size:48px;margin-bottom:12px">🤚</div><div style="font-size:15px;font-weight:500;margin-bottom:6px">暂无手图</div><div style="font-size:12px">上传手图后可在这里管理</div></div>';
    return;
  }

  try {
    const data = await apiGet('/user-hands', { user_id: 'demo_user' });
    if (!data.hands || data.hands.length === 0) {
      body.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999"><div style="font-size:48px;margin-bottom:12px">🤚</div><div style="font-size:15px;font-weight:500;margin-bottom:6px">暂无手图</div><div style="font-size:12px">上传手图后可在这里管理</div></div>';
      return;
    }
    body.innerHTML = data.hands.map(h => `
      <div style="display:flex;gap:12px;padding:14px;background:${h.selected ? '#faf7ff' : '#fff'};border-radius:12px;border:${h.selected ? '2px solid #8b5cf6' : '.5px solid #f0f0f0'};margin-bottom:10px;align-items:center;cursor:pointer" onclick="selectHand('${h.hand_id}')">
        <img src="${staticUrl(h.image_url)}" style="width:56px;height:56px;border-radius:10px;object-fit:cover" onerror="this.style.background='#f5ede0';this.alt='🤚'">
        <div style="flex:1">
          <div style="font-size:13px;font-weight:500">${h.selected ? '✅ 当前使用' : '点击切换'}</div>
          <div style="font-size:11px;color:#999">${h.hand_id}</div>
        </div>
      </div>
    `).join('');
  } catch (e) {
    body.innerHTML = '<div style="text-align:center;padding:40px;color:#999">加载失败</div>';
    console.warn('[手图管理] 加载失败:', e.message);
  }
}

async function selectHand(handId) {
  if (!backendAvailable) return;
  try {
    const data = await apiGet('/user-hands', { user_id: 'demo_user' });
    if (data.hands) {
      const updatedHands = data.hands.map(h => ({ hand_id: h.hand_id, image_url: h.image_url, selected: h.hand_id === handId }));
      await apiRequest('/user-hands/sync', { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ user_id: 'demo_user', hands: updatedHands }) });
      const selected = data.hands.find(h => h.hand_id === handId);
      if (selected) uploadedHandImageUrl = selected.image_url;
      loadUserHands();
    }
  } catch (e) {
    console.warn('[手图管理] 切换失败:', e.message);
  }
}

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
