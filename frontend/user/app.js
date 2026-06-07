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
const DEMO_USER_ID = 'demo_user';
let currentPage = 'home';
let detailFrom = 'home';
let chatMessages = [];
let handUploaded = false;
let multiSelectMode = false;
let selectedThumbs = new Set();
let selectedTryonRecordIds = new Set();
let tryonRecords = [];
let activeTryonRecordId = null;
let currentDetailId = null;
let backendAvailable = false;
let handProfileId = null;
let handProfileData = null;
let conversationId = null;
let uploadedHandImageUrl = null;
let handReviewInProgress = false;
let preparedRecommendationData = null;
let latestRecommendationSnapshot = null;
let latestTuneByStyleId = {};
let demoStateHydrated = false;
// 每个款式的历史试戴结果图：Map<styleId, string[]>
let tryonHistory = {};
// 已尝试过试戴但 AI 模型未返回结果的款式 ID 集合（避免重复调用）
let tryonAttempted = new Set();
// 收藏集合（持久化到 localStorage）
let favoritesSet = new Set(JSON.parse(localStorage.getItem('prism_favorites') || '[]'));

// ===== 初始化后端连接 =====
async function initBackend() {
  backendAvailable = await checkBackendHealth();
  if (backendAvailable) {
    console.log('[前端] 后端连接成功，已启用 API 模式');
    await loadStylesFromBackend();
    try {
      await loadDemoState();
    } catch (e) {
      console.warn('[前端] demo-state 恢复失败，回退常规加载:', e.message);
      await loadCurrentHand();
      await loadTryonRecords();
    }
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
  if (handReviewInProgress && page !== 'upload') return;
  document.querySelectorAll('.page').forEach(p => p.classList.remove('active'));
  document.getElementById('page-' + page).classList.add('active');
  currentPage = page;
  if (page === 'chat' && chatMessages.length === 0) initChat();
  if (page === 'upload') loadCurrentHand();
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

function _hydrateRecommendationItems(items) {
  return (items || []).map((r, idx) => {
    const existing = nailStyles.find(s => String(s.style_id || s.id) === String(r.style_id || '') || s.name === r.style_name);
    return existing || {
      id: 100 + idx,
      name: r.style_name || '美甲款式',
      tags: r.matched_tags || [],
      bg: getStyleBg(idx),
      emoji: '💅',
      price: 158,
      reason: r.reason || '',
      image_url: r.image_url || '',
      style_id: r.style_id || String(100 + idx),
    };
  });
}

function _rememberLatestTune(tune) {
  if (!tune || !tune.tuned_image_url) return;
  const style = nailStyles.find(item => (
    (tune.source_style_id && String(item.style_id || item.id) === String(tune.source_style_id))
    || (tune.source_style_image_url && (
      String(item.image_url || '') === String(tune.source_style_image_url)
      || String(staticUrl(item.image_url || '')) === String(tune.source_style_image_url)
    ))
  ));
  if (style) latestTuneByStyleId[String(style.id)] = tune;
}

async function loadDemoState() {
  const data = await apiGet('/demo-state', { user_id: DEMO_USER_ID });
  demoStateHydrated = true;
  tryonRecords = data.tryon_records || [];
  if (data.current_hand?.image_url) applyCurrentHand(data.current_hand.image_url, { resetAnalysis: false });
  else resetUploadHand();
  if (data.hand_profile) {
    handProfileId = data.hand_profile.hand_profile_id;
    handProfileData = data.hand_profile;
  } else {
    handProfileId = null;
    handProfileData = null;
  }
  latestRecommendationSnapshot = data.recommendation_snapshot || null;
  if (latestRecommendationSnapshot?.recommendations?.length) {
    preparedRecommendationData = _hydrateRecommendationItems(latestRecommendationSnapshot.recommendations);
  } else {
    preparedRecommendationData = null;
  }
  latestTuneByStyleId = {};
  if (data.current_tune) _rememberLatestTune(data.current_tune);
  if (!activeTryonRecordId) activeTryonRecordId = tryonRecords[0]?.record_id || null;
  return data;
}

// ===== 首页Feed =====
function renderFeed() {
  const tagColors = {'法式':'feed-tag-style','简约':'feed-tag-style','可爱':'feed-tag-scene','ins风':'feed-tag-scene','炫彩':'feed-tag-default','高级感':'feed-tag-style','温柔':'feed-tag-scene','日系':'feed-tag-season','节日':'feed-tag-season','闪粉':'feed-tag-default','圣诞':'feed-tag-season','清新':'feed-tag-scene','秋冬':'feed-tag-season','冷淡':'feed-tag-style','夏日':'feed-tag-season','高级':'feed-tag-style','猫眼':'feed-tag-style','渐变':'feed-tag-default','镜面':'feed-tag-style','手绘':'feed-tag-scene'};

  const makeCard = s => `
    <div class="feed-card" onclick="openDetail(${s.id},'home')">
      <div class="feed-img">
        ${s.image_url
          ? `<img src="${staticUrl(s.image_url)}" loading="lazy" onerror="this.style.display='none'">`
          : `<div class="feed-emoji-placeholder">${s.emoji}</div>`
        }
        <span class="feed-tryon-label">立即试戴</span>
      </div>
      <div class="feed-card-bottom">
        <div class="feed-name">${s.name}</div>
        <div class="feed-tags">${s.tags.slice(0,3).map(t=>`<span class="feed-tag ${tagColors[t]||'feed-tag-default'}">${t}</span>`).join('')}</div>
        <div class="feed-price"><span class="feed-price-unit">¥</span>${s.price}</div>
      </div>
    </div>`;

  const left  = nailStyles.filter((_,i) => i % 2 === 0).map(makeCard).join('');
  const right = nailStyles.filter((_,i) => i % 2 === 1).map(makeCard).join('');
  document.getElementById('feed-container').innerHTML =
    `<div class="feed-inner"><div class="feed-col">${left}</div><div class="feed-col">${right}</div></div>`;
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

function setHandReviewInProgress(inProgress) {
  handReviewInProgress = inProgress;
}

function showHandReviewModal(status, message = '') {
  const existing = document.getElementById('hand-review-modal');
  if (existing) existing.remove();

  const content = {
    reviewing: {
      icon: '<i class="ti ti-loader-2 hand-review-spinner"></i>',
      title: '正在审核手图',
      desc: 'AI 正在审核手图是否符合规范，请稍候等待。<br><strong>审核期间请勿退出页面。</strong>',
      action: '',
    },
    passed: {
      icon: '<i class="ti ti-circle-check"></i>',
      title: '手图审核完成',
      desc: '手图符合规范，现在可以点击“一键分析手型”。',
      action: '<button class="modal-btn-primary" onclick="closeHandReviewModal()">我知道了</button>',
    },
    failed: {
      icon: '<i class="ti ti-alert-circle"></i>',
      title: '手图审核未通过',
      desc: `${message || '图片不符合上传规范，请重新上传。'}`,
      action: '<button class="modal-btn-primary" onclick="closeHandReviewModal();simulateUpload()">重新上传</button>',
    },
    error: {
      icon: '<i class="ti ti-wifi-off"></i>',
      title: '手图审核暂未完成',
      desc: '网络或审核服务出现异常，请重新上传后再试。',
      action: '<button class="modal-btn-primary" onclick="closeHandReviewModal();simulateUpload()">重新上传</button>',
    },
  }[status];

  const modal = document.createElement('div');
  modal.id = 'hand-review-modal';
  modal.innerHTML = `
    <div class="modal-backdrop"></div>
    <div class="modal-sheet">
      <div class="hand-review-icon ${status}">${content.icon}</div>
      <div class="modal-title">${content.title}</div>
      <div class="modal-desc">${content.desc}</div>
      ${content.action}
    </div>`;
  document.getElementById('app').appendChild(modal);
}

function closeHandReviewModal() {
  if (handReviewInProgress) return;
  const modal = document.getElementById('hand-review-modal');
  if (modal) modal.remove();
}

function applyCurrentHand(imageUrl, { resetAnalysis = true } = {}) {
  uploadedHandImageUrl = imageUrl;
  handUploaded = Boolean(imageUrl);
  if (resetAnalysis) {
    handProfileId = null;
    handProfileData = null;
    preparedRecommendationData = null;
    latestRecommendationSnapshot = null;
  }

  const analyzeButton = document.getElementById('analyze-btn');
  if (analyzeButton) analyzeButton.disabled = !handUploaded;

  const area = document.getElementById('upload-area');
  if (!area || !handUploaded) return;
  area.className = 'upload-placeholder uploaded';
  area.innerHTML = `
    <img src="${staticUrl(imageUrl)}" style="width:100%;height:100%;object-fit:cover;border-radius:16px">
    <div class="upload-new-hand-badge"><i class="ti ti-upload"></i> 上传新手图</div>`;
}

function resetUploadHand() {
  uploadedHandImageUrl = null;
  handUploaded = false;
  handProfileId = null;
  handProfileData = null;
  preparedRecommendationData = null;
  latestRecommendationSnapshot = null;
  const analyzeButton = document.getElementById('analyze-btn');
  if (analyzeButton) analyzeButton.disabled = true;

  const area = document.getElementById('upload-area');
  if (!area) return;
  area.className = 'upload-placeholder';
  area.innerHTML = '<div class="upload-plus"><i class="ti ti-plus"></i></div><span class="upload-hint">上传手图<br>用于试戴美甲</span>';
}

async function loadCurrentHand() {
  if (!backendAvailable || handReviewInProgress) return;
  try {
    const status = await apiGet('/user-hand-status', { user_id: DEMO_USER_ID });
    if (handReviewInProgress) return;
    if (status.has_hand && status.standardized_image_url) {
      applyCurrentHand(status.standardized_image_url, { resetAnalysis: false });
    } else {
      resetUploadHand();
    }
  } catch (e) {
    console.warn('[手图] 加载当前手图失败:', e.message);
  }
}

async function setCurrentHand(handId) {
  const data = await apiGet('/user-hands', { user_id: DEMO_USER_ID });
  const selected = (data.hands || []).find(h => h.hand_id === handId);
  if (!selected) return null;

  const updatedHands = data.hands.map(h => ({
    hand_id: h.hand_id,
    image_url: h.image_url,
    selected: h.hand_id === handId,
  }));
  await apiRequest('/user-hands/sync', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ user_id: DEMO_USER_ID, hands: updatedHands }),
  });
  applyCurrentHand(selected.image_url);
  return selected;
}

window.addEventListener('beforeunload', (event) => {
  if (!handReviewInProgress) return;
  event.preventDefault();
  event.returnValue = '';
});

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
  selectedTryonRecordIds = new Set();
  const latestRecord = getTryonRecordsForStyle(id)[0];
  activeTryonRecordId = latestRecord?.record_id || null;
  renderDetailPage();
  navigateTo('detail');
  reportEvent('try_on', id);
}

function renderDetailPage() {
  const item = nailStyles.find(s => s.id === currentDetailId);
  if (!item) return;

  const styleRecords = getTryonRecordsForStyle(currentDetailId);
  const activeRecord = tryonRecords.find(record => record.record_id === activeTryonRecordId)
    || styleRecords[0]
    || null;
  const thumbRow = document.getElementById('thumb-row');
  if (tryonRecords.length === 0) {
    thumbRow.innerHTML = '<div style="font-size:11px;color:#bbb;padding:0 4px;white-space:nowrap">试戴后将在此显示历史效果</div>';
  } else {
    thumbRow.innerHTML = tryonRecords.map(record => {
      const isSelected = selectedTryonRecordIds.has(record.record_id);
      const isActive = record.record_id === activeRecord?.record_id;
      return `
        <div class="thumb ${isActive ? 'active' : ''} ${isSelected ? 'selected' : ''}" style="overflow:hidden;background:#f7f4ef" onclick="onTryonRecordClick('${record.record_id}')">
          <img src="${staticUrl(record.style_image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:9px">
          ${multiSelectMode ? (isSelected
            ? '<div class="thumb-check"><i class="ti ti-check"></i></div>'
            : '<div class="thumb-uncheck"></div>') : ''}
        </div>`;
    }).join('');
  }

  if (!multiSelectMode || selectedTryonRecordIds.size <= 1) {
    const isFav = favoritesSet.has(item.id);
    const lastResult = activeRecord?.result_image_url
      ? staticUrl(activeRecord.result_image_url)
      : null;

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

    // 有手图时调用试戴 API，并展示进度条（不重复调用已失败的）
    if (uploadedHandImageUrl && item.image_url && styleRecords.length === 0 && !tryonAttempted.has(item.id)) {
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
    label.textContent = '多选对比 ' + selectedTryonRecordIds.size;
  } else {
    btn.className = 'action-btn';
    circle.className = 'multisel-circle';
    circle.innerHTML = '';
    label.textContent = '多选对比';
  }
}

function getTryonRecordsForStyle(styleId) {
  const item = nailStyles.find(style => style.id === styleId);
  if (!item) return [];
  const ids = new Set([String(item.id), String(item.style_id || '')].filter(Boolean));
  return tryonRecords.filter(record => ids.has(String(record.style_id || '')));
}

function findStyleForTryonRecord(record) {
  return nailStyles.find(item => (
    String(item.style_id || item.id) === String(record.style_id || '')
    || String(item.id) === String(record.style_id || '')
  ));
}

function onTryonRecordClick(recordId) {
  const record = tryonRecords.find(item => item.record_id === recordId);
  if (!record) return;
  if (multiSelectMode) {
    if (selectedTryonRecordIds.has(recordId)) {
      selectedTryonRecordIds.delete(recordId);
    } else if (selectedTryonRecordIds.size < 4) {
      selectedTryonRecordIds.add(recordId);
    } else {
      alert('最多同时对比 4 款哦');
      return;
    }
  } else {
    activeTryonRecordId = recordId;
    const style = findStyleForTryonRecord(record);
    if (style) currentDetailId = style.id;
  }
  renderDetailPage();
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
      <div class="tryon-progress-tip">请勿退出当前页面</div>
    </div>`;
  bigimg.appendChild(overlay);

  const progressStartedAt = Date.now();
  let timer = setInterval(() => {
    const elapsedSeconds = (Date.now() - progressStartedAt) / 1000;
    updateProgress(estimatedTryOnProgress(elapsedSeconds));
  }, 250);

  function estimatedTryOnProgress(elapsedSeconds) {
    if (elapsedSeconds <= 20) return elapsedSeconds * 3;
    if (elapsedSeconds <= 60) return 60 + (elapsedSeconds - 20) * 0.625;
    if (elapsedSeconds <= 120) return 85 + (elapsedSeconds - 60) * 0.15;
    return Math.min(96, 94 + (elapsedSeconds - 120) * 0.02);
  }

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
        // 立即更新当前页，随后从后端同步完整记录
        if (!tryonHistory[item.id]) tryonHistory[item.id] = [];
        tryonHistory[item.id].push(resultUrl);
        if (backendAvailable) {
          loadTryonRecords({ rerenderDetail: true });
        } else {
          const localRecord = {
            record_id: `local-${Date.now()}`,
            style_id: item.style_id || String(item.id),
            style_image_url: item.image_url,
            result_image_url: resultUrl,
            created_at: new Date().toISOString(),
          };
          tryonRecords.unshift(localRecord);
          activeTryonRecordId = localRecord.record_id;
          renderDetailPage();
        }
      } else {
        // AI 模型未启用或调用失败，标记已尝试，显示友好提示
        tryonAttempted.add(item.id);
        const existingNotice = bigimg.querySelector('.tryon-fallback-notice');
        if (!existingNotice) {
          const notice = document.createElement('div');
          notice.className = 'tryon-fallback-notice';
          notice.innerHTML = `
            <div style="display:flex;flex-direction:column;align-items:center;gap:8px;padding:20px;text-align:center">
              <i class="ti ti-photo-ai" style="font-size:32px;color:var(--accent,#8b5cf6);opacity:.7"></i>
              <div style="font-size:13px;font-weight:500;color:var(--text,#1a1a1a)">AI 试戴效果生成中</div>
              <div style="font-size:11px;color:var(--muted,#999);line-height:1.5">真实 AI 生图模型正在部署中<br>请稍后再试，或先浏览其他款式</div>
            </div>`;
          const actions = bigimg.querySelector('.tryon-actions');
          bigimg.insertBefore(notice, actions);
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
      user_id: DEMO_USER_ID,
      hand_image_url: uploadedHandImageUrl,
      style_image_url: item.image_url,
      style_id: item.style_id || String(item.id),
    });
    if (result && result.result_image_url) {
      // 如果后端返回的是 SVG 占位图（AI 模型未启用），不当作真实结果
      if (result.generation_mode === 'local_svg_fallback' || result.result_image_url.endsWith('.svg')) {
        console.warn('[试戴] AI 生图模型未启用，返回了占位图');
        return null;
      }
      return staticUrl(result.result_image_url);
    }
  } catch (e) {
    console.warn('[试戴] API 调用失败:', e.message);
  }
  return null;
}

// ===== AI 款式微调页 =====
const TUNE_MOR = ['#b5a89a','#c4b5a5','#9aaa99','#b0b8a0','#a8a0b0','#b8a0a8','#c0b098','#a8b8c0','#b0a890','#c8b8a8'];
const TUNE_MAC = ['#f7c5c5','#f7d9b0','#f5f0a0','#b8e8b8','#a8d8f0','#c8b8f0','#f0b8d8','#b8f0e0','#d0c8f0','#d0e8f8'];

// 微调状态
let tuneIsGenerating = false;
let tuneMode = 0;
let tuneStyleItem = null;
let tunePendingShape = null;
let tunePendingColor = null;
let tuneShapeOptions = [];
let tuneColorSystem = 'morandi';
let tuneCustomColors = [];

async function openAiTunePanel() {
  const item = nailStyles.find(s => s.id === currentDetailId);
  if (!item) return;
  const latestTune = latestTuneByStyleId[String(item.id)];
  tuneStyleItem = latestTune ? { ...item, _tuned_image_url: latestTune.tuned_image_url } : { ...item };
  tuneIsGenerating = false;
  tuneMode = 0;
  tunePendingShape = null;
  tunePendingColor = null;
  tuneColorSystem = 'morandi';
  tuneCustomColors = [];

  _tuneResetUI();
  navigateTo('tune');
  _tuneUpdatePreview(tuneStyleItem._tuned_image_url || item.image_url, item.name);
  await _tuneLoadOptions();
}

function closeTunePage() {
  navigateTo('detail');
}

function _tuneResetUI() {
  document.getElementById('tuneTab0').classList.add('on');
  document.getElementById('tunePaneWhole').classList.add('on');
  const textField = document.getElementById('tuneTextField');
  if (textField) textField.value = '';
  _tuneUpdateConfirmBtn();
  _tuneRenderPickedColors();
  _tuneBuildSwatches('tuneSwWhole', TUNE_MOR);
  document.querySelectorAll('#tuneCtWhole .tune-ctab').forEach((t,i) => t.classList.toggle('on', i===0));
  const tipBar = document.getElementById('tuneTipBar');
  if (tipBar) tipBar.style.display = '';
  const shapeGrid = document.getElementById('tuneSgWhole');
  if (shapeGrid) shapeGrid.innerHTML = '<div class="tune-shape-empty">正在加载甲型参考素材…</div>';
}

async function _tuneLoadOptions() {
  const shapeGrid = document.getElementById('tuneSgWhole');
  try {
    const options = backendAvailable ? await apiGet('/tune/options') : { shapes: [] };
    tuneShapeOptions = options.shapes || [];
    _tuneBuildShapeGrid('tuneSgWhole', tuneShapeOptions);
  } catch (e) {
    tuneShapeOptions = [];
    if (shapeGrid) shapeGrid.innerHTML = '<div class="tune-shape-empty">甲型素材加载失败，请检查素材清单。</div>';
    console.warn('[微调] 甲型选项加载失败:', e.message);
  }
}

function _tuneUpdatePreview(imageUrl, name) {
  const image = document.getElementById('tuneStyleImg');
  if (image && imageUrl) image.src = staticUrl(imageUrl);
  const label = document.getElementById('tunePreviewName');
  if (label) label.textContent = name || '当前款式';
}

function _tuneUpdateConfirmBtn() {
  const btn = document.getElementById('tuneConfirmBtn');
  if (!btn) return;
  btn.disabled = tuneIsGenerating || !(tunePendingShape || tunePendingColor);
}

function _tuneToggleColor(col, swatchEl = null) {
  const normalized = String(col || '').toLowerCase();
  const isActive = String(tunePendingColor || '').toLowerCase() === normalized;
  if (isActive) {
    tunePendingColor = null;
  } else {
    tunePendingColor = col;
  }
  if (swatchEl) {
    const container = swatchEl.parentElement;
    if (container) {
      container.querySelectorAll('.tune-sw').forEach(x => x.classList.remove('on'));
    }
    if (!isActive) swatchEl.classList.add('on');
  }
  _tuneRenderPickedColors();
  _tuneUpdateConfirmBtn();
}

function _tuneRenderPickedColors() {
  const container = document.getElementById('tunePickedColors');
  if (!container) return;
  if (!tuneCustomColors.length) {
    container.innerHTML = '<div class="tune-picked-empty">自定义取色后会在这里按顺序保留，方便你回看和复用。</div>';
    return;
  }
  container.innerHTML = tuneCustomColors.map((col, idx) => {
    const active = String(tunePendingColor || '').toLowerCase() === String(col).toLowerCase();
    return `
      <button type="button" class="tune-picked-chip${active ? ' active' : ''}" onclick="_tuneTogglePickedColor('${col}', ${idx})">
        <span class="tune-picked-chip-swatch" style="background:${col}"></span>
        <span>${col.toUpperCase()}</span>
      </button>
    `;
  }).join('');
}

function _tuneTogglePickedColor(col) {
  _tuneToggleColor(col);
}

function _tunePickCustomColor() {
  const input = document.createElement('input');
  input.type = 'color';
  input.style.cssText = 'position:absolute;opacity:0;width:0;height:0';
  document.body.appendChild(input);
  input.click();
  input.oninput = () => {
    const color = String(input.value || '').toLowerCase();
    if (!color) return;
    if (!tuneCustomColors.includes(color)) {
      tuneCustomColors.push(color);
    }
    tunePendingColor = color;
    const trigger = document.querySelector('#tuneSwWhole .tune-sw-c');
    if (trigger) {
      trigger.style.background = color;
      trigger.classList.add('has-color');
      trigger.textContent = '';
    }
    _tuneRenderPickedColors();
    _tuneBuildSwatches('tuneSwWhole', tuneCustomColors);
    _tuneUpdateConfirmBtn();
  };
  input.onchange = () => input.remove();
}

function _tuneBuildSwatches(containerId, colors) {
  const c = document.getElementById(containerId);
  if (!c) return;
  c.innerHTML = '';
  colors.forEach(col => {
    const s = document.createElement('div');
    s.className = 'tune-sw';
    s.style.background = col;
    const active = String(tunePendingColor || '').toLowerCase() === String(col).toLowerCase();
    if (active) s.classList.add('on');
    s.onclick = () => _tuneToggleColor(col, s);
    c.appendChild(s);
  });
  if (tuneColorSystem === 'custom') {
    const cu = document.createElement('button');
    cu.type = 'button';
    cu.className = 'tune-sw-c';
    if (tunePendingColor) {
      cu.style.background = tunePendingColor;
      cu.classList.add('has-color');
      cu.textContent = '';
    } else {
      cu.textContent = '选色';
      cu.style.cssText += 'width:auto;border-radius:12px;padding:0 10px;font-size:11px;';
    }
    cu.onclick = () => _tunePickCustomColor();
    c.appendChild(cu);
  }
}

function _tuneBuildShapeGrid(containerId, shapes) {
  const g = document.getElementById(containerId);
  if (!g) return;
  g.innerHTML = '';
  if (!shapes.length) {
    g.innerHTML = '<div class="tune-shape-empty">暂无可用甲型。请将参考图放入后端素材目录。</div>';
    return;
  }
  shapes.forEach(sh => {
    const d = document.createElement('div');
    d.className = 'tune-si';
    d.innerHTML = `<img src="${staticUrl(sh.image_url)}" alt="${sh.label}"><span>${sh.label}</span>`;
    d.onclick = () => {
      g.querySelectorAll('.tune-si').forEach(x => x.classList.remove('on'));
      d.classList.add('on');
      tunePendingShape = sh.id;
      _tuneUpdateConfirmBtn();
    };
    g.appendChild(d);
  });
}

function tuneSetMode(m) {
  if (m !== 0 || tuneIsGenerating) return;
  tuneMode = 0;
  _tuneUpdateConfirmBtn();
}

function tuneSetCTab(el, ctabId, swId, sys) {
  if (tuneIsGenerating) return;
  document.getElementById(ctabId).querySelectorAll('.tune-ctab').forEach(t => t.classList.remove('on'));
  el.classList.add('on');
  tuneColorSystem = sys;
  tunePendingColor = null;
  if (sys === 'custom') {
    _tuneBuildSwatches(swId, tuneCustomColors);
  } else {
    _tuneBuildSwatches(swId, sys === 'morandi' ? TUNE_MOR : TUNE_MAC);
  }
  _tuneRenderPickedColors();
  _tuneUpdateConfirmBtn();
}

function _tuneBuildLoadingDesc() {
  const parts = [];
  const shape = tuneShapeOptions.find(item => item.id === tunePendingShape);
  if (shape) parts.push('甲型调整为' + shape.label);
  if (tunePendingColor) parts.push('匹配所选色卡');
  return '正在' + parts.join('并') + '…';
}

async function tuneConfirmGenerate() {
  if (tuneIsGenerating) return;
  const btn = document.getElementById('tuneConfirmBtn');
  if (btn && btn.disabled) return;

  const desc = _tuneBuildLoadingDesc();
  tuneIsGenerating = true;
  document.getElementById('tuneLdDesc').textContent = desc;
  document.getElementById('tuneLdlay').classList.add('show');
  document.getElementById('tuneSc').classList.add('tune-disabled');
  document.querySelectorAll('.tune-tab').forEach(t => t.style.pointerEvents = 'none');
  if (btn) btn.disabled = true;

  // 获取当前款式图 URL
  const styleImageUrl = tuneStyleItem
    ? (tuneStyleItem._tuned_image_url || tuneStyleItem.image_url || '')
    : '';

  let tunedImageUrl = null;

  if (backendAvailable && styleImageUrl) {
    try {
      const result = await apiPost('/tune/overall', {
        style_image_url: staticUrl(styleImageUrl),
        nail_shape_id: tunePendingShape || null,
        color: tunePendingColor || null,
        user_text: document.getElementById('tuneTextField')?.value.trim() || null,
      });
      if (result?.generation_mode === 'local_svg_fallback' || result?.tuned_image_url?.endsWith('.svg')) {
        throw new Error(result.warnings?.[0] || 'AI 生图失败，请稍后重试');
      }
      if (result && result.tuned_image_url) {
        tunedImageUrl = result.tuned_image_url;
        // 更新款式图为微调后结果
        _tuneUpdateStyleImage(tunedImageUrl);
        // 同步更新 tuneStyleItem 的 image_url，确保"试戴预览"使用微调后图片
        if (tuneStyleItem) {
          tuneStyleItem = { ...tuneStyleItem, _tuned_image_url: tunedImageUrl };
          latestTuneByStyleId[String(tuneStyleItem.id)] = {
            tune_id: 'latest',
            source_style_id: String(tuneStyleItem.style_id || tuneStyleItem.id),
            source_style_image_url: styleImageUrl,
            tuned_image_url: tunedImageUrl,
          };
        }
        if (result.warnings && result.warnings.length > 0) {
          console.warn('[微调] 警告:', result.warnings.join('; '));
        }
      }
    } catch (e) {
      alert('微调生成失败：' + e.message);
      console.warn('[微调] API 调用失败:', e.message);
    }
  }

  tuneIsGenerating = false;
  document.getElementById('tuneLdlay').classList.remove('show');
  document.getElementById('tuneSc').classList.remove('tune-disabled');
  document.querySelectorAll('.tune-tab').forEach(t => t.style.pointerEvents = '');
  // 重置 pending，等待下一次选择
  tunePendingShape = null;
  tunePendingColor = null;
  tuneColorSystem = 'morandi';
  // 清除选中高亮，回到初始态
  document.querySelectorAll('.tune-si').forEach(x => x.classList.remove('on'));
  document.querySelectorAll('.tune-sw').forEach(x => x.classList.remove('on'));
  document.querySelectorAll('.tune-pill').forEach(x => x.classList.remove('on'));
  _tuneBuildSwatches('tuneSwWhole', TUNE_MOR);
  document.querySelectorAll('#tuneCtWhole .tune-ctab').forEach((t,i) => t.classList.toggle('on', i===0));
  _tuneRenderPickedColors();
  _tuneUpdateConfirmBtn();
}

function _tuneUpdateStyleImage(imageUrl) {
  if (tuneStyleItem && imageUrl) {
    tuneStyleItem = { ...tuneStyleItem, _tuned_image_url: imageUrl };
    _tuneUpdatePreview(imageUrl, tuneStyleItem.name);
  }
}

function tuneSubmitText() { _tuneUpdateConfirmBtn(); }

function submitTuneToTryon() {
  // 将微调后款式图送入试戴流程
  if (!uploadedHandImageUrl) { showUploadGuideModal(tuneStyleItem?.id); return; }
  if (tuneStyleItem) {
    // 如果有微调后图片，构造临时 item 用于试戴
    const tunedUrl = tuneStyleItem._tuned_image_url;
    const itemForTryon = tunedUrl
      ? { ...tuneStyleItem, image_url: tunedUrl }
      : tuneStyleItem;
    // 清除该款式的已有试戴记录，强制重新生成（使用微调后图片）
    if (tunedUrl) {
      tryonAttempted.delete(tuneStyleItem.id);
      tryonHistory[tuneStyleItem.id] = [];
      latestTuneByStyleId[String(tuneStyleItem.id)] = {
        tune_id: 'latest',
        source_style_id: String(tuneStyleItem.style_id || tuneStyleItem.id),
        source_style_image_url: tuneStyleItem.image_url,
        tuned_image_url: tunedUrl,
      };
      // 更新 nailStyles 中对应款式的图片
      const idx = nailStyles.findIndex(s => s.id === tuneStyleItem.id);
      if (idx >= 0) nailStyles[idx] = { ...nailStyles[idx], image_url: tunedUrl };
    }
    closeTunePage();
    startTryOnWithProgress(itemForTryon);
  } else {
    closeTunePage();
  }
}

function toggleMultiSelect() {
  multiSelectMode = !multiSelectMode;
  if (multiSelectMode) {
    selectedTryonRecordIds = activeTryonRecordId
      ? new Set([activeTryonRecordId])
      : new Set();
  } else {
    selectedTryonRecordIds = new Set();
  }
  renderDetailPage();
}

function onThumbClick(id) {
  const record = getTryonRecordsForStyle(id)[0];
  if (record) onTryonRecordClick(record.record_id);
}

function renderCompareGrid() {
  const records = [...selectedTryonRecordIds]
    .map(recordId => tryonRecords.find(record => record.record_id === recordId))
    .filter(Boolean);
  const n = records.length;
  // 上限四图：2图上下布局，3/4图四宫格
  let gridClass, maxCells;
  if (n <= 2) { gridClass = 'g2v'; maxCells = 2; }   // 上下排列
  else { gridClass = 'g4'; maxCells = 4; }

  let cells = records.map(record => {
    const style = findStyleForTryonRecord(record);
    const name = style?.name || '历史试戴';
    return `<div class="grid-cell" style="background:${style?.bg || '#f7f4ef'}">
      <img src="${staticUrl(record.result_image_url)}" style="width:100%;height:100%;object-fit:cover">
      <span class="cell-name">${name}</span>
    </div>`;
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
        user_id: DEMO_USER_ID,
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
    const analyzeButton = document.getElementById('analyze-btn');
    handUploaded = false;
    uploadedHandImageUrl = null;
    analyzeButton.disabled = true;

    // 先用本地 ObjectURL 预览图片
    const localUrl = URL.createObjectURL(file);
    area.className = 'upload-placeholder uploaded';
    area.innerHTML = `<img src="${localUrl}" style="width:100%;height:100%;object-fit:cover;border-radius:16px">`;
    setHandReviewInProgress(true);
    showHandReviewModal('reviewing');

    if (backendAvailable) {
      // 后端可用：执行真实上传 + 质检
      try {
        const result = await apiUpload('/upload-image', file);
        uploadedHandImageUrl = result.url || result.image_url;

        const stdResult = await standardizeHand(uploadedHandImageUrl);
        if (!stdResult.quality_pass) {
          setHandReviewInProgress(false);
          area.className = 'upload-placeholder';
          const qualityIssues = stdResult.quality_issues || stdResult.issues || [];
          const issues = qualityIssues.length ? qualityIssues.join('、') : '图片质量不达标';
          area.innerHTML = `<div class="upload-plus"><i class="ti ti-alert-triangle"></i></div><span class="upload-hint">质检未通过：${issues}<br>请重新上传</span>`;
          showHandReviewModal('failed', `未通过原因：${issues}`);
          URL.revokeObjectURL(localUrl);
          return;
        }
        uploadedHandImageUrl = stdResult.standardized_image_url || uploadedHandImageUrl;
        if (stdResult.standardized_hand_id) {
          await setCurrentHand(stdResult.standardized_hand_id);
        }
      } catch (err) {
        console.warn('[上传] 手图上传或审核失败:', err.message);
        setHandReviewInProgress(false);
        area.className = 'upload-placeholder';
        area.innerHTML = '<div class="upload-plus"><i class="ti ti-alert-triangle"></i></div><span class="upload-hint">审核暂未完成<br>请重新上传</span>';
        showHandReviewModal('error');
        URL.revokeObjectURL(localUrl);
        return;
      }
    } else {
      // Mock 模式：使用本地 ObjectURL 作为手图地址
      uploadedHandImageUrl = localUrl;
    }

    applyCurrentHand(uploadedHandImageUrl);
    setHandReviewInProgress(false);
    showHandReviewModal('passed');
  };
  fileInput.click();
}

async function startAnalysis() {
  if (!handUploaded) return;
  navigateTo('analyzing');
  const minimumAnimation = new Promise(resolve => setTimeout(resolve, 2800));
  
  const steps = [
    () => { document.getElementById('a-step-1').className='step-icon active'; document.getElementById('a-step-1').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-1').className='step-text'; },
    () => { document.getElementById('a-step-1').className='step-icon done'; document.getElementById('a-step-1').innerHTML='<i class="ti ti-check"></i>'; document.getElementById('a-step-2').className='step-icon active'; document.getElementById('a-step-2').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-2').className='step-text'; },
    () => { document.getElementById('a-step-2').className='step-icon done'; document.getElementById('a-step-2').innerHTML='<i class="ti ti-check"></i>'; document.getElementById('a-step-3').className='step-icon active'; document.getElementById('a-step-3').innerHTML='<div class="pulse-dot"></div>'; document.getElementById('a-text-3').className='step-text'; },
  ];
  
  // 显示动画步骤
  steps.forEach((fn, i) => setTimeout(fn, i * 800));

  if (handProfileId && handProfileData && preparedRecommendationData) {
    console.log('[分析] 使用已持久化的手型分析与推荐快照');
  } else if (backendAvailable && uploadedHandImageUrl) {
    try {
      const result = await apiPost('/analyze-hand', {
        user_id: DEMO_USER_ID,
        hand_image_url: uploadedHandImageUrl,
      });
      handProfileId = result.hand_profile_id;
      handProfileData = result;
    } catch (e) {
      console.warn('[分析] API 调用失败，使用 mock:', e.message);
      handProfileId = null;
      handProfileData = { skin_tone: '暖黄皮', hand_shape: '标准手型', recommended_nail_shapes: ['方圆甲'], recommended_colors: ['裸粉','冷紫','奶白'] };
    }
  } else {
    handProfileData = { skin_tone: '暖黄皮', hand_shape: '标准手型', recommended_nail_shapes: ['方圆甲'], recommended_colors: ['裸粉','冷紫','奶白'] };
  }

  await Promise.all([
    prepareRecommendations(),
    minimumAnimation,
  ]);

  document.getElementById('a-step-3').className='step-icon done';
  document.getElementById('a-step-3').innerHTML='<i class="ti ti-check"></i>';
  await renderRecommend();
  await new Promise(resolve => setTimeout(resolve, 400));
  navigateTo('recommend');
}

// ===== 推荐结果（联调后端 /api/recommendations） =====
async function prepareRecommendations() {
  if (preparedRecommendationData && preparedRecommendationData.length > 0) return preparedRecommendationData;
  let picks = nailStyles.slice(0,4);

  if (backendAvailable && handProfileId) {
    try {
      const result = await apiPost('/recommendations', {
        user_id: DEMO_USER_ID,
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

  preparedRecommendationData = picks;
  return picks;
}

async function renderRecommend() {
  const picks = preparedRecommendationData || await prepareRecommendations();
  let profileDesc = '暖黄皮 · 标准型 · 方圆甲';

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
  const records = tryonRecords.slice(0,4);
  if (records.length === 0) return;
  selectedTryonRecordIds = new Set(records.map(record => record.record_id));
  const firstStyle = findStyleForTryonRecord(records[0]);
  if (firstStyle) currentDetailId = firstStyle.id;
  activeTryonRecordId = records[0].record_id;
  multiSelectMode = true;
  renderDetailPage();
  navigateTo('detail');
}

// ===== 初始化 =====
renderFeed();
navigateTo('home');
initBackend();

// ===== 试戴历史（联调 GET /api/tryon-history） =====
async function loadTryonRecords({ rerenderDetail = false } = {}) {
  if (!backendAvailable) return tryonRecords;
  try {
    const data = await apiGet('/tryon-history', { user_id: DEMO_USER_ID, limit: 100 });
    tryonRecords = data.records || [];
    if (activeTryonRecordId && !tryonRecords.some(record => record.record_id === activeTryonRecordId)) {
      activeTryonRecordId = null;
    }
    if (!activeTryonRecordId) {
      activeTryonRecordId = getTryonRecordsForStyle(currentDetailId)[0]?.record_id || null;
    }
    if (rerenderDetail && currentPage === 'detail') renderDetailPage();
    return tryonRecords;
  } catch (e) {
    console.warn('[试戴记录] 同步失败:', e.message);
    return tryonRecords;
  }
}

async function loadTryonHistory() {
  const body = document.getElementById('tryon-history-body');
  if (!body) return;

  if (!backendAvailable) {
    body.innerHTML = '<div style="text-align:center;padding:60px 20px;color:#999"><div style="font-size:48px;margin-bottom:12px">⏱</div><div style="font-size:15px;font-weight:500;margin-bottom:6px">暂无试戴记录</div><div style="font-size:12px">试戴美甲后记录会显示在这里</div></div>';
    return;
  }

  body.innerHTML = '<div style="text-align:center;padding:40px;color:#8b5cf6"><div class="typing-indicator" style="justify-content:center"><span></span><span></span><span></span></div>加载中...</div>';

  try {
    const data = await apiGet('/tryon-history', { user_id: DEMO_USER_ID, limit: 20 });
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
    await loadTryonRecords({ rerenderDetail: true });
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
    const data = await apiGet('/user-hands', { user_id: DEMO_USER_ID });
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
    await setCurrentHand(handId);
    loadUserHands();
  } catch (e) {
    console.warn('[手图管理] 切换失败:', e.message);
  }
}

// ===== 事件上报（联调 POST /api/events） =====
async function reportEvent(eventType, styleId, source = 'organic') {
  if (!backendAvailable) return;
  try {
    await apiPost('/events', {
      user_id: DEMO_USER_ID,
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
  const result = await apiPost('/standardize-hand', {
    hand_image_url: imageUrl,
    user_id: DEMO_USER_ID,
  });
  console.log('[标准化] 质检结果:', result.quality_pass ? '通过' : '不通过');
  return result;
}
