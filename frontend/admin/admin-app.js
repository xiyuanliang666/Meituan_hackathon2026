// ===== 页面切换 =====
const ADMIN_PAGES = new Set(['home', 'dashboard', 'assets', 'trend-agent', 'push', 'boost', 'report', 'notify', 'upload', 'confirm']);
const SPECIAL_PAGE_NAV_PARENT = { confirm: 'push', upload: 'assets', notify: 'home' };
const IS_SMART_OPS_PLATFORM = new URLSearchParams(window.location.search).get('platform') === 'ops';

function pageFromHash() {
  if (IS_SMART_OPS_PLATFORM) return 'trend-agent';
  const page = pushHashPage();
  if (page === 'trend-agent') return 'home';
  return ADMIN_PAGES.has(page) ? page : 'home';
}

function pushHashPage() {
  return decodeURIComponent((window.location.hash || '').replace(/^#/, '').split('?')[0] || '');
}

function pushHashParams() {
  const hash = (window.location.hash || '').replace(/^#/, '');
  const query = hash.includes('?') ? hash.slice(hash.indexOf('?') + 1) : '';
  return new URLSearchParams(query);
}

function switchPage(page, options = {}) {
  if (IS_SMART_OPS_PLATFORM) page = 'trend-agent';
  if (!ADMIN_PAGES.has(page)) page = 'home';
  const shouldUpdateHash = options.updateHash !== false;

  document.querySelectorAll('.page-panel').forEach(p => { p.classList.remove('active'); p.style.display = 'none'; });
  const panel = document.getElementById('panel-' + page);
  if (panel) { panel.style.display = 'block'; panel.classList.add('active'); }
  const navPage = SPECIAL_PAGE_NAV_PARENT[page] || page;
  document.querySelectorAll('.nav-tab').forEach(t => t.classList.remove('active'));
  const tab = document.querySelector(`.nav-tab[data-page="${navPage}"]`);
  if (tab) tab.classList.add('active');
  if (shouldUpdateHash && window.location.hash !== '#' + page) {
    window.location.hash = page;
  }
  // 页面加载时从后端拉取数据
  if (page === 'dashboard') loadDashboardData();
  if (page === 'trend-agent') { loadTrendRunsAndList(); loadCandidateTaxonomyTerms(); }
  if (page === 'push') loadPushData();
  if (page === 'boost') renderBoostBudgetState();
  if (page === 'notify') renderNotifyList();
  if (page === 'report') loadReportData('week');
}

function applyPlatformChrome() {
  if (!IS_SMART_OPS_PLATFORM) return;
  document.body.classList.add('smart-ops-platform');
  document.title = 'Prism 智能运营平台';
  const brand = document.querySelector('.brand-cn');
  if (brand) brand.textContent = '智能运营平台';
}

window.addEventListener('hashchange', () => {
  switchPage(pageFromHash(), { updateHash: false });
});

// ===== 后端状态 =====
let adminBackendAvailable = false;
const DEMO_BASE_BOOST_BUDGET = 500;
const runtimeDemoState = {
  boostBudget: null,
  publishedPushIds: new Set(),
  publishedStyles: new Map(),
  removedPushIds: new Set(),
  removedStyleIds: new Set(),
  adoptedSuggestions: new Map(),
  unreadNotifyIds: new Set(['notify-push', 'notify-report']),
};

const demoPushCardOverrides = {
  'push-b38bf71ae1': {
    hot_score: 93,
    life_cycle: '上升期',
    signal_sources: [
      { signal: '搜索热度', value: 92, delta: 0.24, weight: 0.30 },
      { signal: '评价词频', value: 218, delta: 0.17, weight: 0.30 },
      { signal: '试戴收藏率', value: 0.43, delta: 0.28, weight: 0.40 },
    ],
  },
  'push-b567a4e3b0': {
    hot_score: 88,
    life_cycle: '峰值期',
    signal_sources: [
      { signal: '搜索热度', value: 84, delta: 0.19, weight: 0.30 },
      { signal: '评价词频', value: 176, delta: 0.12, weight: 0.30 },
      { signal: '试戴收藏率', value: 0.37, delta: 0.21, weight: 0.40 },
    ],
  },
  'push-ca2ef69375': {
    hot_score: 79,
    life_cycle: '上升期',
    signal_sources: [
      { signal: '搜索热度', value: 77, delta: 0.11, weight: 0.30 },
      { signal: '评价词频', value: 142, delta: 0.09, weight: 0.30 },
      { signal: '试戴收藏率', value: 0.31, delta: 0.16, weight: 0.40 },
    ],
  },
};

const notifyItems = [
  {
    id: 'notify-push',
    iconBg: '#FCE4D6',
    iconColor: '#993C1D',
    icon: 'rocket',
    title: '新爆款推送',
    text: '「淡粉色珍珠法式」综合评分89，建议上架',
    time: '10分钟前',
  },
  {
    id: 'notify-report',
    iconBg: '#EEEDFE',
    iconColor: '#534AB7',
    icon: 'report-analytics',
    title: '周报已生成',
    text: '第48周复盘报告已就绪，含4条运营建议',
    time: '1小时前',
  },
  {
    id: 'notify-alert',
    iconBg: '#E2EFDA',
    iconColor: '#375623',
    icon: 'trending-down',
    title: '热度预警',
    text: '「法式简约纯色」连续下降3天，接近下架阈值',
    time: '3小时前',
  },
  {
    id: 'notify-boost',
    iconBg: '#E3F2FD',
    iconColor: '#1565C0',
    icon: 'speakerphone',
    title: '投流效果',
    text: '「奶油渐变猫眼」投流帖子曝光突破3000',
    time: '5小时前',
  },
  {
    id: 'notify-publish',
    iconBg: '#FAEEDA',
    iconColor: '#BA7517',
    icon: 'circle-check',
    title: '上架成功',
    text: '「奶油渐变猫眼」已成功上架，AI试戴已开通',
    time: '昨天 14:30',
  },
];

async function initAdminBackend() {
  adminBackendAvailable = await checkBackendHealth();
  if (adminBackendAvailable) {
    console.log('[运营端] 后端连接成功，已启用 API 模式');
  } else {
    console.log('[运营端] 后端不可用，使用本地 mock 数据');
  }
}

// ===== 数据看板（联调 /api/events/stats） =====
async function loadDashboardData() {
  if (!adminBackendAvailable) return;
  try {
    const stats = await apiGet('/events/stats');
    if (stats) {
      // 更新 AI 助手播报中的数据
      console.log('[数据看板] 加载数据成功:', stats);
    }
  } catch (e) {
    console.warn('[数据看板] 加载失败:', e.message);
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

async function regenBubble() {
  const label = document.getElementById('regen-label');
  label.textContent = '生成中...';
  
  if (adminBackendAvailable) {
    try {
      const result = await apiPost('/report', {
        period: currentPeriod === 'today' ? 'today' : 'this_week',
        merchant_id: 'demo_shop',
      });
      if (result && result.report_summary) {
        const lines = result.report_summary.split('\n').filter(l => l.trim()).map(l => `· ${l}`);
        renderBubble(lines);
        label.textContent = '重新生成播报';
        return;
      }
    } catch (e) {
      console.warn('[播报] API 调用失败:', e.message);
    }
  }
  
  setTimeout(() => { renderBubble(currentPeriod === 'today' ? bubbleToday : bubbleWeek); label.textContent = '重新生成播报'; }, 1200);
}

// ===== 素材管理 =====
let stylesData = [];
let stylesLoading = false;
let activeStyleStatus = 'active';
let styleSearchQuery = '';
const selectedStyleIds = new Set();
let styleSearchTimer = null;
let styleDeleteMode = false;

// ===== 趋势发现 =====
let trendSourceMode = 'links';
let trendListData = [];
let selectedTrendId = '';
let latestTrendPipelineRunId = localStorage.getItem('trend_latest_pipeline_run_id') || '';
let trendRunPollTimer = null;
let trendSeenIds = new Set();
let trendScoreScaleMax = 0;
const TREND_DISPLAY_SCORE_MAX = 93.8;

async function loadStylesData() {
  if (!adminBackendAvailable) {
    renderStyleList();
    return;
  }
  stylesLoading = true;
  renderStyleList();
  try {
    const data = await apiGet('/db/styles', {
      status: activeStyleStatus,
      q: styleSearchQuery,
      limit: 200,
    });
    if (data && data.styles && data.styles.length > 0) {
      const baseStyles = data.styles.map(s => ({
        style_id: s.style_id || s.id,
        name: s.style_name || s.name || '',
        tags: flattenStyleTagsForPreview(s.tags || {}).slice(0, 4),
        lc: lifeCycleClass(s.life_cycle),
        lcText: s.life_cycle || '',
        date: s.created_at || '',
        bg: '#FAEEDA',
        bc: '#EF9F27',
        ic: '#BA7517',
        seasonal: false,
        image_url: s.enhanced_style_image_url || '',
        tryon_enabled: s.tryon_enabled !== false,
        status: s.status || 'active',
        review_status: s.review_status || '',
        source: s.source || '',
      }));
      stylesData = applyRuntimeStyleOverrides(baseStyles);
    } else {
      stylesData = applyRuntimeStyleOverrides([]);
    }
  } catch (e) {
    console.warn('[素材] 加载款式失败:', e.message);
    stylesData = applyRuntimeStyleOverrides([]);
  }
  stylesLoading = false;
  renderStyleList();
}

function switchStyleTab(status, btn) {
  activeStyleStatus = status;
  selectedStyleIds.clear();
  styleDeleteMode = false;
  document.querySelectorAll('#panel-assets .asset-tabs .asset-tab').forEach(b => {
    if (b.textContent.includes('已上架') || b.textContent.includes('草稿箱')) b.classList.remove('active');
  });
  if (btn) btn.classList.add('active');
  updateStyleDeleteUI();
  loadStylesData();
}

function onStyleSearchInput(value) {
  styleSearchQuery = value.trim();
  clearTimeout(styleSearchTimer);
  styleSearchTimer = setTimeout(loadStylesData, 250);
}

function renderStyleList() {
  const list = document.getElementById('style-list');
  if (!list) return;

  if (stylesLoading) {
    list.innerHTML = `<div class="style-empty-loading"><i class="ti ti-loader" style="font-size:20px;animation:spin 1s linear infinite;display:block;margin-bottom:8px"></i><span>标签提取中...</span></div>`;
    return;
  }

  if (!stylesData.length) {
    updateStyleCount();
    list.innerHTML = `<div class="style-empty-loading"><i class="ti ti-photo" style="font-size:20px;display:block;margin-bottom:8px;color:#ccc"></i><span>暂无款式，请上传新款式</span></div>`;
    return;
  }

  updateStyleCount();
  list.innerHTML = stylesData.map((s, i) => `
    <div class="style-item" id="style-${i}" onclick="${styleDeleteMode ? `toggleStyleSelection('${s.style_id}', !selectedStyleIds.has('${s.style_id}')); renderStyleList(); updateStyleDeleteUI()` : `continueDraft('${s.style_id}')`}">
      ${styleDeleteMode ? `<input type="checkbox" class="style-select" ${selectedStyleIds.has(s.style_id) ? 'checked' : ''} onclick="event.stopPropagation()" onchange="toggleStyleSelection('${s.style_id}', this.checked); updateStyleDeleteUI()">` : ''}
      <div class="style-thumb" style="background:${s.bg};border-color:${s.bc}">
        ${s.image_url ? `<img src="${staticUrl(s.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><i class="ti ti-photo" style="color:${s.ic};display:none"></i>` : `<i class="ti ti-photo" style="color:${s.ic}"></i>`}
      </div>
      <div class="style-info">
        <div class="style-name-text">${s.name || '未命名款式'} ${s.status === 'draft' ? '<span class="seasonal-badge">草稿</span>' : '<span class="evergreen-badge">已上架</span>'}</div>
        <div class="style-tags-row">${s.tags.slice(0,3).map(t=>`<span class="stag stag-craft">${escapeHtml(t)}</span>`).join('')}</div>
        <div class="style-meta-row">${styleStatusPill(s)}<span class="style-date">${s.date}</span></div>
      </div>
      <div class="style-actions">
        <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:${s.tryon_enabled?'#375623':'#aaa'};cursor:pointer" title="AI试戴开关">
          <input type="checkbox" ${s.tryon_enabled?'checked':''} onclick="event.stopPropagation()" onchange="toggleTryon('${s.style_id}',this.checked)" style="accent-color:#FFCD00">试戴
        </label>
      </div>
    </div>`).join('');
}

function updateStyleCount() {
  const el = document.getElementById('style-count');
  if (el) el.textContent = `共 ${stylesData.length} 款`;
}

function styleStatusPill(style) {
  if (style.status === 'draft') {
    const klass = style.review_status === 'tag_extracting' ? 'peak' : style.review_status === 'tag_failed' ? 'down' : 'watch';
    const icon = style.review_status === 'tag_extracting' ? 'loader' : style.review_status === 'tag_failed' ? 'alert-circle' : 'clock';
    return `<span class="lc-pill lc-${klass}"><i class="ti ti-${icon}"></i>${reviewStatusText(style.review_status)}</span>`;
  }
  const text = style.lcText || '观察期';
  return `<span class="lc-pill lc-${lifeCycleClass(text)}"><i class="ti ti-${lifeCycleIcon(text)}"></i>${text}</span>`;
}

function lifeCycleClass(lifeCycle) {
  if (lifeCycle === '上升期') return 'up';
  if (lifeCycle === '峰值期') return 'peak';
  if (lifeCycle === '衰退期') return 'down';
  return 'watch';
}

function lifeCycleIcon(lifeCycle) {
  if (lifeCycle === '上升期') return 'trending-up';
  if (lifeCycle === '峰值期') return 'flame';
  if (lifeCycle === '衰退期') return 'trending-down';
  return 'eye';
}

function reviewStatusText(status) {
  return {
    tag_extracting: '标签提取中',
    tag_ready: '待确认标签',
    merchant_confirmed: '标签已确认',
    composite_ready: '合成待确认',
    published: '已完成',
    tag_failed: '提取失败',
  }[status] || status;
}

function toggleStyleSelection(styleId, checked) {
  if (checked) selectedStyleIds.add(styleId);
  else selectedStyleIds.delete(styleId);
}

function toggleStyleDeleteMode(force) {
  styleDeleteMode = typeof force === 'boolean' ? force : !styleDeleteMode;
  if (!styleDeleteMode) selectedStyleIds.clear();
  updateStyleDeleteUI();
  renderStyleList();
}

function updateStyleDeleteUI() {
  const bar = document.getElementById('style-delete-bar');
  const toggle = document.getElementById('style-delete-toggle');
  const selectAll = document.getElementById('style-select-all');
  if (bar) bar.style.display = styleDeleteMode ? 'flex' : 'none';
  if (toggle) toggle.innerHTML = `<i class="ti ti-trash"></i> ${styleDeleteMode ? '删除中' : '删除'}`;
  if (selectAll) {
    selectAll.checked = !!stylesData.length && selectedStyleIds.size === stylesData.length;
    selectAll.indeterminate = selectedStyleIds.size > 0 && selectedStyleIds.size < stylesData.length;
  }
}

function toggleSelectAllStyles(checked) {
  selectedStyleIds.clear();
  if (checked) stylesData.forEach(item => selectedStyleIds.add(item.style_id));
  renderStyleList();
  updateStyleDeleteUI();
}

async function confirmDeleteSelectedStyles() {
  const ids = [...selectedStyleIds];
  if (!ids.length) { showToast('请先选择款式'); return; }
  if (!confirm(`确定删除选中的 ${ids.length} 款？`)) return;
  if (adminBackendAvailable) {
    await apiPost('/styles/batch-delete', { style_ids: ids });
  }
  selectedStyleIds.clear();
  styleDeleteMode = false;
  updateStyleDeleteUI();
  showToast('已删除所选款式');
  loadStylesData();
}

async function deleteStyleFromBackend(styleId, idx) {
  if (!confirm('确定删除该款式？')) return;
  if (adminBackendAvailable) {
    try {
      await apiRequest(`/styles/${styleId}`, { method: 'DELETE' });
      stylesData.splice(idx, 1);
      renderStyleList();
      showToast('款式已删除');
      return;
    } catch (e) {
      console.warn('[删除] 失败:', e.message);
    }
  }
  const el = document.getElementById('style-'+idx);
  if (el) { el.style.opacity='0.3'; el.style.pointerEvents='none'; }
}

async function toggleTryon(styleId, enabled) {
  if (!adminBackendAvailable) return;
  try {
    await apiRequest(`/styles/${styleId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tryon_enabled: enabled }),
    });
    showToast(enabled ? 'AI试戴已开通' : 'AI试戴已关闭');
  } catch (e) {
    console.warn('[试戴开关] 失败:', e.message);
  }
}

const selectedTemplateIds = new Set();
const selectedMerchantTemplateIds = new Set();
const DEMO_MERCHANT_ID = 'demo_shop';
let publicTemplates = [];
let merchantTemplates = [];
let activeTemplateTab = 'public';
let activeUploadTemplateTab = 'public';
let merchantTemplateDeleteMode = false;
const MAX_COMPOSITE_TEMPLATE_SELECTION = 4;

async function renderTemplates() {
  if (adminBackendAvailable) {
    try {
      publicTemplates = await apiGet('/templates/public');
      merchantTemplates = await apiGet('/templates', { source: 'merchant' });
      const selection = await apiGet('/templates/selection', { merchant_id: DEMO_MERCHANT_ID });
      selectedTemplateIds.clear();
      (selection.template_ids || []).forEach(id => selectedTemplateIds.add(id));
    } catch (e) {
      console.warn('[模板] 加载失败:', e.message);
    }
  }
  renderTemplateLibrary('template-groups', activeTemplateTab);
  renderTemplateLibrary('upload-template-groups', activeUploadTemplateTab);
  updateTplCount();
  updateMerchantTemplateDeleteUI();
}

function switchTemplateTab(tab, btn, isUpload = false) {
  if (isUpload) activeUploadTemplateTab = tab;
  else {
    activeTemplateTab = tab;
    if (tab !== 'merchant') {
      merchantTemplateDeleteMode = false;
      selectedMerchantTemplateIds.clear();
    }
  }
  const scope = isUpload ? '#upload-step-3' : '#panel-assets';
  document.querySelectorAll(`${scope} .asset-tab`).forEach(b => b.classList.remove('active'));
  if (btn) btn.classList.add('active');
  if (!isUpload) {
    const toolbar = document.getElementById('merchant-template-toolbar');
    if (toolbar) toolbar.style.display = tab === 'merchant' ? 'flex' : 'none';
    updateMerchantTemplateDeleteUI();
  }
  renderTemplateLibrary(isUpload ? 'upload-template-groups' : 'template-groups', tab);
}

function renderTemplateLibrary(containerId, tab) {
  const container = document.getElementById(containerId);
  if (!container) return;
  const items = tab === 'public' ? publicTemplates : merchantTemplates;
  if (!items.length) {
    container.innerHTML = `<div class="style-empty-loading"><i class="ti ti-hand-finger" style="font-size:20px;display:block;margin-bottom:8px;color:#ccc"></i><span>${tab === 'public' ? '公共模板加载中' : '暂无自有模板，请上传'}</span></div>`;
    return;
  }
  const grouped = groupTemplatesBySkinTone(items);
  container.innerHTML = Object.entries(grouped).map(([group, groupItems]) => `
    <div class="tpl-group">
      <div class="tag-section-label">${group}</div>
      <div class="template-grid">${groupItems.map(item => renderTemplateItem(item, tab, containerId)).join('')}</div>
    </div>
  `).join('');
}

function groupTemplatesBySkinTone(items) {
  return items.reduce((acc, item) => {
    const key = item.skin_tone || '未分类';
    (acc[key] ||= []).push(item);
    return acc;
  }, {});
}

function renderTemplateItem(t, tab = 'public', containerId = '') {
  const id = t.hand_template_id;
  const isMerchant = tab === 'merchant';
  const showDeleteSelect = isMerchant && containerId === 'template-groups' && merchantTemplateDeleteMode;
  const clickAction = showDeleteSelect
    ? `toggleMerchantTemplateDeleteSelection('${id}', !selectedMerchantTemplateIds.has('${id}')); renderTemplateLibrary('template-groups', 'merchant'); updateMerchantTemplateDeleteUI()`
    : `toggleTemplateSelection('${id}')`;
  return `<div class="tpl-item ${selectedTemplateIds.has(id) ? 'selected' : ''}" onclick="${clickAction}">
    <div class="tpl-check">✓</div>
    ${showDeleteSelect ? `<input type="checkbox" class="tpl-delete-check" ${selectedMerchantTemplateIds.has(id) ? 'checked' : ''} onclick="event.stopPropagation()" onchange="toggleMerchantTemplateDeleteSelection('${id}', this.checked)">` : ''}
    <img src="${staticUrl(t.hand_image_url)}" style="width:100%;height:80%;object-fit:cover;border-radius:8px 8px 0 0" onerror="this.outerHTML='<i class=\\'ti ti-hand-finger\\'></i>'">
    <div class="tpl-item-footer">
      <span>${t.label || t.skin_tone || '模板'}</span>
      <button class="tpl-info-btn" onclick="event.stopPropagation();openTemplateInfo('${id}')">配置信息</button>
    </div>
  </div>`;
}

async function toggleTemplateSelection(templateId) {
  const wasSelected = selectedTemplateIds.has(templateId);
  if (wasSelected) selectedTemplateIds.delete(templateId);
  else {
    if (selectedTemplateIds.size >= MAX_COMPOSITE_TEMPLATE_SELECTION) {
      showToast(`最多只能选择 ${MAX_COMPOSITE_TEMPLATE_SELECTION} 张模板`);
      return;
    }
    selectedTemplateIds.add(templateId);
  }
  renderTemplateLibrary('template-groups', activeTemplateTab);
  renderTemplateLibrary('upload-template-groups', activeUploadTemplateTab);
  updateTplCount();
  if (adminBackendAvailable) {
    try {
      await saveTemplateSelection();
    } catch (e) {
      if (wasSelected) selectedTemplateIds.add(templateId);
      else selectedTemplateIds.delete(templateId);
      renderTemplateLibrary('template-groups', activeTemplateTab);
      renderTemplateLibrary('upload-template-groups', activeUploadTemplateTab);
      updateTplCount();
      console.warn('[模板选择] 保存失败:', e.message);
      showToast('模板选择保存失败');
    }
  }
}

async function saveTemplateSelection() {
  return apiRequest('/templates/selection', {
    method: 'PUT',
    body: JSON.stringify({
      merchant_id: DEMO_MERCHANT_ID,
      template_ids: [...selectedTemplateIds],
    }),
  });
}

function toggleMerchantTemplateDeleteSelection(templateId, checked) {
  if (checked) selectedMerchantTemplateIds.add(templateId);
  else selectedMerchantTemplateIds.delete(templateId);
}

function toggleMerchantTemplateDeleteMode(force) {
  merchantTemplateDeleteMode = typeof force === 'boolean' ? force : !merchantTemplateDeleteMode;
  if (!merchantTemplateDeleteMode) selectedMerchantTemplateIds.clear();
  updateMerchantTemplateDeleteUI();
  renderTemplateLibrary('template-groups', 'merchant');
}

function updateMerchantTemplateDeleteUI() {
  const bar = document.getElementById('merchant-template-delete-bar');
  const toggle = document.getElementById('template-delete-toggle');
  const selectAll = document.getElementById('merchant-template-select-all');
  if (bar) bar.style.display = activeTemplateTab === 'merchant' && merchantTemplateDeleteMode ? 'flex' : 'none';
  if (toggle) toggle.innerHTML = `<i class="ti ti-trash"></i> ${merchantTemplateDeleteMode ? '删除中' : '删除'}`;
  if (selectAll) {
    selectAll.checked = !!merchantTemplates.length && selectedMerchantTemplateIds.size === merchantTemplates.length;
    selectAll.indeterminate = selectedMerchantTemplateIds.size > 0 && selectedMerchantTemplateIds.size < merchantTemplates.length;
  }
}

function toggleSelectAllMerchantTemplates(checked) {
  selectedMerchantTemplateIds.clear();
  if (checked) merchantTemplates.forEach(item => selectedMerchantTemplateIds.add(item.hand_template_id));
  renderTemplateLibrary('template-groups', 'merchant');
  updateMerchantTemplateDeleteUI();
}

async function confirmDeleteSelectedTemplates() {
  const ids = [...selectedMerchantTemplateIds];
  if (!ids.length) { showToast('请先选择自有模板'); return; }
  if (!confirm(`确定删除选中的 ${ids.length} 张自有模板？`)) return;
  try {
    await apiPost('/templates/batch-delete', { template_ids: ids });
    ids.forEach(id => {
      selectedMerchantTemplateIds.delete(id);
      selectedTemplateIds.delete(id);
    });
    merchantTemplateDeleteMode = false;
    if (adminBackendAvailable) await saveTemplateSelection();
    updateMerchantTemplateDeleteUI();
    showToast('自有模板已删除');
    await renderTemplates();
  } catch (e) {
    alert('删除失败：' + e.message);
  }
}

function updateTplCount() {
  const text = `已选 ${selectedTemplateIds.size}/${MAX_COMPOSITE_TEMPLATE_SELECTION} 张`;
  const el = document.getElementById('tpl-count');
  const uploadEl = document.getElementById('upload-tpl-count');
  if (el) el.textContent = text;
  if (uploadEl) uploadEl.textContent = text;
}
function toggleTplDropdown(e) { e.stopPropagation(); }

function findTemplateInMemory(templateId) {
  return [...publicTemplates, ...merchantTemplates].find(item => item.hand_template_id === templateId);
}

async function openTemplateInfo(templateId) {
  let template = findTemplateInMemory(templateId);
  if (adminBackendAvailable) {
    try {
      template = await apiGet(`/templates/${templateId}`);
    } catch (e) {
      console.warn('[模板] 详情加载失败:', e.message);
    }
  }
  if (!template) return;

  const editable = template.source === 'merchant' || template.source === 'merchant_upload';
  const modal = document.createElement('div');
  modal.className = 'modal-overlay show';
  modal.id = 'template-info-modal';
  modal.innerHTML = `<div class="modal-content template-info-modal">
    <div class="detail-head"><h3>${editable ? '编辑自有模板信息' : '公共模板信息'}</h3><button class="btn-icon" onclick="document.getElementById('template-info-modal').remove()"><i class="ti ti-x"></i></button></div>
    <div class="template-info-grid">
      <img src="${staticUrl(template.hand_image_url)}" class="template-info-img" onerror="this.style.display='none'">
      <div class="template-info-form">
        <label>模板名称</label>
        <input id="tpl-edit-label" class="asset-search" value="${escapeAttr(template.label || '')}" ${editable ? '' : 'disabled'}>
        <label>肤色分类</label>
        ${templateSelect('tpl-edit-skin', ['冷白', '自然肤', '暖黄', '深肤', 'unknown'], template.skin_tone, editable)}
        <label>手型分类</label>
        ${templateSelect('tpl-edit-shape', ['修长', '标准', '短宽', 'unknown'], template.hand_shape, editable)}
        <label>分析依据</label>
        <textarea id="tpl-edit-reason" class="template-reason-input" ${editable ? '' : 'disabled'}>${escapeHtml(template.analysis_reason || '')}</textarea>
        <div class="style-tags-row">${(template.recommended_colors || []).map(t => `<span class="stag stag-color">${t}</span>`).join('')}${(template.recommended_styles || []).map(t => `<span class="stag stag-style">${t}</span>`).join('')}</div>
        <div class="style-date">来源：${template.source || ''}${template.analysis_mode ? ' · ' + template.analysis_mode : ''}</div>
        ${editable ? `<button class="btn-primary-sm" onclick="saveTemplateInfo('${templateId}')"><i class="ti ti-device-floppy"></i> 保存信息</button>` : `<div class="style-date">公共模板由平台维护，商家不可修改</div>`}
      </div>
    </div>
  </div>`;
  document.body.appendChild(modal);
}

function templateSelect(id, options, value, editable) {
  return `<select id="${id}" class="coupon-select" ${editable ? '' : 'disabled'}>${options.map(opt => `<option value="${opt}" ${opt === value ? 'selected' : ''}>${opt}</option>`).join('')}</select>`;
}

function escapeAttr(value) {
  return String(value || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

function escapeHtml(value) {
  return String(value || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function flattenStyleTagsForPreview(tags) {
  const orderedKeys = [
    'color_system',
    'style_tags',
    'scene_tags',
    'season_tags',
    'nail_technique',
    'nail_decoration',
    'nail_finish',
    'nail_shape',
    'nail_length',
    'skin_tone_suitability',
    'hand_skin_tone',
    'hand_shape',
    'candidate_tags'
  ];
  const values = [];
  orderedKeys.forEach(key => {
    const raw = tags[key];
    const items = Array.isArray(raw) ? raw : (raw && raw !== 'unknown' ? [raw] : []);
    items.forEach(item => {
      const text = candidateTagValue(item);
      if (text && text !== 'unknown' && !values.includes(text)) values.push(text);
    });
  });
  return values;
}

function candidateTagValue(item) {
  const text = String(item || '').trim();
  if (!text) return '';
  const parts = text.split(':');
  return (parts.length > 1 ? parts.slice(1).join(':') : text).trim();
}

async function saveTemplateInfo(templateId) {
  try {
    const payload = {
      label: document.getElementById('tpl-edit-label').value.trim(),
      skin_tone: document.getElementById('tpl-edit-skin').value,
      hand_shape: document.getElementById('tpl-edit-shape').value,
      analysis_reason: document.getElementById('tpl-edit-reason').value.trim(),
    };
    await apiRequest(`/templates/${templateId}`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    showToast('模板信息已保存');
    document.getElementById('template-info-modal').remove();
    await renderTemplates();
  } catch (e) {
    alert('保存失败：' + e.message);
  }
}

async function handleTplUpload() {
  const dd = document.getElementById('tpl-add-dropdown');
  if (dd) dd.classList.remove('show');
  if (adminBackendAvailable) {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const uploaded = await apiUpload('/upload-image', file);
        const imageUrl = uploaded.url || uploaded.image_url;
        await apiPost('/templates', { image_url: imageUrl, label: '自有模板' });
        showToast('模板上传成功');
        renderTemplates();
      } catch (err) {
        alert('上传失败：' + err.message);
      }
    };
    fileInput.click();
  }
}

// ===== 上传弹窗 =====
function showUploadModal() { document.getElementById('upload-modal').classList.add('show'); }
function hideUploadModal() {
  document.getElementById('upload-modal').classList.remove('show');
  setUploadModalStatus('');
}

function setUploadModalStatus(text) {
  const el = document.getElementById('upload-modal-status');
  if (el) el.textContent = text || '';
}

function getStyleTabButton(status) {
  return [...document.querySelectorAll('#panel-assets .asset-tabs .asset-tab')]
    .find(btn => status === 'draft' ? btn.textContent.includes('草稿箱') : btn.textContent.includes('已上架')) || null;
}

function openDraftStylesTab() {
  switchPage('assets');
  switchStyleTab('draft', getStyleTabButton('draft'));
}

function goUploadPage() {
  hideUploadModal();

  if (adminBackendAvailable) {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const result = await apiUpload('/upload-image', file);
        console.log('[上传] 款式图上传成功:', result);

        if (result.url || result.image_url) {
          const imageUrl = result.url || result.image_url;
          lastUploadedImageUrl = imageUrl;
          const draft = await apiPost('/styles/upload-draft', {
            image_url: imageUrl,
            style_name: file.name.replace(/\.[^.]+$/, '') || '新款式草稿',
          });
          currentUploadStyleId = draft.style_id;
          localStorage.setItem('current_upload_style_id', currentUploadStyleId);

          // 先更新预览图，切到步骤2
          const previewImg = document.querySelector('.upload-img');
          if (previewImg) previewImg.innerHTML = `<img src="${staticUrl(imageUrl)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px;cursor:pointer" onclick="event.stopPropagation();openLightbox('${staticUrl(imageUrl)}')" onerror="this.outerHTML='<i class=\\'ti ti-photo\\' style=\\'font-size:32px;color:#BA7517\\'></i>'">`;

          // 更新文件信息
          const filenameEl = document.querySelector('.upload-filename');
          if (filenameEl) filenameEl.textContent = file.name;
          const nameInput = document.getElementById('upload-style-name');
          if (nameInput) nameInput.value = draft.style_name || file.name.replace(/\.[^.]+$/, '') || '新款式草稿';
          const sizeEl = document.querySelector('.upload-size');
          if (sizeEl) sizeEl.textContent = (file.size / 1024 / 1024).toFixed(1) + ' MB';

          // 显示标签提取中
          const statusEl = document.getElementById('upload-tag-status');
          if (statusEl) { statusEl.style.display = 'inline-flex'; statusEl.innerHTML = '<i class="ti ti-loader"></i> 标签提取中...'; }

          goUploadStep(2);
          switchPage('upload');
          pollDraftTags(currentUploadStyleId);
        }
      } catch (err) {
        alert('上传失败：' + err.message);
      }
    };
    fileInput.click();
  } else {
    goUploadStep(2);
    switchPage('upload');
  }
}

function goBatchUploadPage() {
  if (!adminBackendAvailable) {
    showToast('当前环境暂不支持批量上传');
    return;
  }
  const fileInput = document.createElement('input');
  fileInput.type = 'file';
  fileInput.accept = 'image/*';
  fileInput.multiple = true;
  fileInput.onchange = async (e) => {
    const files = [...(e.target.files || [])].filter(Boolean);
    if (!files.length) return;
    showUploadModal();
    setUploadModalStatus(`准备上传 ${files.length} 张款式图...`);
    const uploadedItems = [];
    let uploadedCount = 0;
    let failedCount = 0;

    for (const file of files) {
      try {
        setUploadModalStatus(`正在上传第 ${uploadedCount + failedCount + 1}/${files.length} 张：${file.name}`);
        const result = await apiUpload('/upload-image', file);
        const imageUrl = result.url || result.image_url;
        if (!imageUrl) throw new Error('未返回图片地址');
        uploadedItems.push({
          image_url: imageUrl,
          style_name: file.name.replace(/\.[^.]+$/, '') || '新款式草稿',
        });
        uploadedCount += 1;
      } catch (err) {
        failedCount += 1;
        console.warn('[批量上传] 单张上传失败:', file.name, err.message);
      }
    }

    if (!uploadedItems.length) {
      setUploadModalStatus('');
      alert('批量上传失败：没有可用的款式图片上传成功');
      return;
    }

    try {
      setUploadModalStatus(`正在创建 ${uploadedItems.length} 个草稿并提交标签提取...`);
      const result = await apiPost('/styles/upload-drafts', { items: uploadedItems });
      hideUploadModal();
      openDraftStylesTab();
      await loadStylesData();
      showToast(`已创建 ${result.created || uploadedItems.length} 个草稿，正在提取标签${failedCount ? `，${failedCount} 张上传失败` : ''}`);
    } catch (err) {
      setUploadModalStatus('');
      alert('批量建草稿失败：' + err.message);
    }
  };
  fileInput.click();
}

// 将后端返回的标签动态渲染到确认标签页
function renderExtractedTags(tags) {
  const craftGroup = document.getElementById('craft-tags');
  const marketGroup = document.getElementById('market-tags');
  if (!craftGroup || !marketGroup) return;
  
  // 工艺维度标签
  const craftTags = [];
  if (tags.nail_technique) craftTags.push(...tagItemsForField(tags.nail_technique, 'nail_technique'));
  if (tags.nail_decoration) craftTags.push(...tagItemsForField(tags.nail_decoration, 'nail_decoration'));
  if (tags.nail_finish) craftTags.push(...tagItemsForField(tags.nail_finish, 'nail_finish'));
  if (tags.nail_shape) craftTags.push(...tagItemsForField(tags.nail_shape, 'nail_shape'));
  if (tags.nail_length) craftTags.push(...tagItemsForField(tags.nail_length, 'nail_length'));
  
  // 营销维度标签
  const marketTags = [];
  if (tags.color_system) marketTags.push(...tagItemsForField(tags.color_system, 'color_system'));
  if (tags.style_tags) marketTags.push(...tagItemsForField(tags.style_tags, 'style_tags'));
  if (tags.scene_tags) marketTags.push(...tagItemsForField(tags.scene_tags, 'scene_tags'));
  if (tags.season_tags) marketTags.push(...tagItemsForField(tags.season_tags, 'season_tags'));
  if (tags.skin_tone_suitability) marketTags.push(...tagItemsForField(tags.skin_tone_suitability, 'skin_tone_suitability'));
  
  const candidateGroups = splitCandidateTags(tags.candidate_tags || []);

  // 渲染工艺维度
  const craftFiltered = craftTags.filter(item => item.value && item.value !== 'unknown');
  craftGroup.innerHTML = craftFiltered.map(item => renderTagChip(item.value, 'tag-craft', false, item.fieldKey)).join('')
    + candidateGroups.craft.map(t => renderTagChip(t, 'tag-craft', true)).join('')
    + '<button class="tag-add-btn" onclick="addTagPrompt(\'craft-tags\',\'tag-craft\')">+</button>';
  
  // 渲染营销维度
  const marketFiltered = marketTags.filter(item => item.value && item.value !== 'unknown');
  marketGroup.innerHTML = marketFiltered.map(item => {
    const cls = tagClassForField(item.fieldKey);
    return renderTagChip(item.value, cls, false, item.fieldKey);
  }).join('')
    + candidateGroups.market.map(t => renderTagChip(t, 'tag-color', true)).join('')
    + '<button class="tag-add-btn" onclick="addTagPrompt(\'market-tags\',\'tag-color\')">+</button>';
  
  // 更新标签计数
  const total = craftFiltered.length + marketFiltered.length;
  const resultEl = document.getElementById('upload-tag-status');
  if (resultEl) {
    resultEl.style.display = 'inline-flex';
    resultEl.innerHTML = `<i class="ti ti-check"></i> 共识别到 <strong>${total}</strong> 个标签`;
  }
}

function tagItemsForField(raw, fieldKey) {
  const values = Array.isArray(raw) ? raw : [raw];
  return values.map(value => ({ value: String(value || '').trim(), fieldKey }));
}

function tagClassForField(fieldKey) {
  if (fieldKey === 'color_system') return 'tag-color';
  if (fieldKey === 'scene_tags') return 'tag-scene';
  if (fieldKey === 'season_tags') return 'tag-season';
  if (fieldKey === 'style_tags') return 'tag-style';
  return 'tag-craft';
}

function renderTagChip(name, tagClass, isCandidate = false, fieldKey = '') {
  return `<span class="tag ${tagClass}" data-candidate="${isCandidate ? '1' : '0'}" data-field="${escapeAttr(fieldKey)}">${escapeHtml(name)} <i class="tag-del" onclick="removeUploadTag(this)">×</i></span>`;
}

function splitCandidateTags(candidateTags) {
  const groups = { craft: [], market: [] };
  candidateTags.forEach(item => {
    const text = String(item || '').trim();
    if (!text) return;
    const parts = text.split(':');
    const field = parts.length > 1 ? parts[0].trim() : '';
    const value = candidateTagValue(text);
    if (!value) return;
    if (field === '工艺维度' || field === 'craft-tags') groups.craft.push(value);
    else groups.market.push(value);
  });
  return groups;
}

function removeUploadTag(el) {
  el.parentElement.remove();
  scheduleSaveCurrentUploadTags();
}

let activeTagDropdown = null;
let tagSearchTimer = null;
let taxonomyCatalogCache = null;

const TAG_FIELD_GROUPS = {
  craft: [
    'nail_technique',
    'nail_decoration',
    'nail_finish',
    'nail_shape',
    'nail_length'
  ],
  market: [
    'color_system',
    'style_tags',
    'scene_tags',
    'season_tags',
    'hand_skin_tone',
    'hand_shape'
  ]
};

function closeTagDropdown(e) {
  if (activeTagDropdown && (!e || !activeTagDropdown.contains(e.target))) {
    activeTagDropdown.remove();
    activeTagDropdown = null;
    document.removeEventListener('click', closeTagDropdown);
    document.removeEventListener('keydown', onTagDropdownKey);
  }
}

function onTagDropdownKey(e) {
  if (e.key === 'Escape') closeTagDropdown();
}

async function ensureTaxonomyCatalog() {
  if (taxonomyCatalogCache) return taxonomyCatalogCache;
  if (!adminBackendAvailable) return null;
  const data = await apiGet('/taxonomy');
  taxonomyCatalogCache = {
    version: data.version || 'v2',
    fields: Array.isArray(data.fields) ? data.fields : []
  };
  return taxonomyCatalogCache;
}

function getTagPromptConfig(groupId) {
  const kind = groupId === 'craft-tags' ? 'craft' : 'market';
  return {
    kind,
    fields: TAG_FIELD_GROUPS[kind]
  };
}

function positionTagDropdown(dd, rect) {
  const dropdownWidth = 320;
  const margin = 12;
  const viewportWidth = window.innerWidth || document.documentElement.clientWidth || 0;
  const viewportHeight = window.innerHeight || document.documentElement.clientHeight || 0;
  const estimatedHeight = 420;

  let left = rect.left;
  if (left + dropdownWidth > viewportWidth - margin) {
    left = Math.max(margin, viewportWidth - dropdownWidth - margin);
  }

  let top = rect.bottom + 4;
  if (top + estimatedHeight > viewportHeight - margin) {
    top = Math.max(margin, rect.top - estimatedHeight - 4);
  }

  dd.style.left = `${left}px`;
  dd.style.top = `${top}px`;
  dd.style.width = `${dropdownWidth}px`;
}

function renderTagDropdownList(dd, groupId, tagClass, query) {
  const listEl = dd.querySelector('.tag-dd-list');
  const config = getTagPromptConfig(groupId);
  const fields = config.fields;
  const normalizedQuery = String(query || '').trim().toLowerCase();
  const existingValues = new Set(
    [...document.querySelectorAll(`#${groupId} .tag`)]
      .map(el => tagText(el).toLowerCase())
  );

  if (!taxonomyCatalogCache || !Array.isArray(taxonomyCatalogCache.fields)) {
    listEl.innerHTML = '<div class="tag-dd-empty">标签库暂时不可用</div>';
    return;
  }

  const fieldGroups = taxonomyCatalogCache.fields
    .filter(field => fields.includes(field.field_key))
    .map(field => {
      const options = Array.isArray(field.options) ? field.options : [];
      const filtered = options.filter(option => {
        const value = String(option.value || '').trim();
        if (!value) return false;
        if (value.toLowerCase() === 'unknown') return false;
        if (!normalizedQuery) return true;
        return value.toLowerCase().includes(normalizedQuery);
      });
      return {
        fieldKey: field.field_key,
        label: field.label_cn || field.field_key,
        options: filtered
      };
    })
    .filter(group => group.options.length > 0);

  if (!fieldGroups.length) {
    listEl.innerHTML = normalizedQuery
      ? '<div class="tag-dd-empty">没有找到匹配标签，可以直接添加为新标签</div>'
      : '<div class="tag-dd-empty">当前分类下暂无可选标签</div>';
    return;
  }

  listEl.innerHTML = '';
  fieldGroups.forEach(group => {
    const section = document.createElement('div');
    section.className = 'tag-dd-group';

    const title = document.createElement('div');
    title.className = 'tag-dd-group-title';
    title.textContent = group.label;
    section.appendChild(title);

    const optionsWrap = document.createElement('div');
    optionsWrap.className = 'tag-dd-group-options';

    group.options.forEach(option => {
      const item = document.createElement('button');
      item.type = 'button';
      item.className = 'tag-dd-item';
      item.innerHTML = `<span>${option.value}</span>${existingValues.has(String(option.value).toLowerCase()) ? '<span class="dd-picked">已添加</span>' : ''}`;
      if (existingValues.has(String(option.value).toLowerCase())) {
        item.classList.add('is-selected');
      }
      item.addEventListener('click', function (ev) {
        ev.stopPropagation();
        if (existingValues.has(String(option.value).toLowerCase())) return;
        _insertTag(groupId, tagClassForField(group.fieldKey), option.value, false, group.fieldKey);
        renderTagDropdownList(dd, groupId, tagClass, dd.querySelector('input').value);
      });
      optionsWrap.appendChild(item);
    });

    section.appendChild(optionsWrap);
    listEl.appendChild(section);
  });
}

async function addTagPrompt(groupId, tagClass) {
  closeTagDropdown();

  const btn = document.querySelector(`#${groupId} .tag-add-btn`);
  if (!btn) return;

  const rect = btn.getBoundingClientRect();

  const dd = document.createElement('div');
  dd.className = 'tag-search-dropdown';
  dd.style.cssText = 'position:fixed;width:320px';
  dd.innerHTML = `<input type="text" placeholder="输入关键词搜索..." autocomplete="off">
    <div class="tag-dd-list"><div class="tag-dd-empty">标签加载中...</div></div>
    <div class="tag-dd-new">+ 添加为新标签</div>`;
  positionTagDropdown(dd, rect);

  const input = dd.querySelector('input');
  const newBtn = dd.querySelector('.tag-dd-new');
  const listEl = dd.querySelector('.tag-dd-list');

  input.addEventListener('input', function () {
    clearTimeout(tagSearchTimer);
    const q = this.value.trim();
    tagSearchTimer = setTimeout(() => renderTagDropdownList(dd, groupId, tagClass, q), 120);
  });

  newBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    const v = input.value.trim();
    if (v) {
      _insertTag(groupId, tagClass, v, true);
      closeTagDropdown();
    }
  });

  dd.addEventListener('click', function (e) { e.stopPropagation(); });
  listEl.addEventListener('wheel', function (e) { e.stopPropagation(); }, { passive: true });

  document.body.appendChild(dd);
  setTimeout(() => input.focus(), 50);
  activeTagDropdown = dd;

  try {
    await ensureTaxonomyCatalog();
    renderTagDropdownList(dd, groupId, tagClass, '');
  } catch (e) {
    dd.querySelector('.tag-dd-list').innerHTML = '<div class="tag-dd-empty">标签加载失败，请稍后重试</div>';
  }

  setTimeout(() => {
    document.addEventListener('click', closeTagDropdown);
    document.addEventListener('keydown', onTagDropdownKey);
  }, 0);
}

function _insertTag(groupId, tagClass, name, isCandidate = false, fieldKey = '') {
  const group = document.getElementById(groupId);
  const btn = group.querySelector('.tag-add-btn');
  const normalized = String(name || '').trim().toLowerCase();
  const exists = [...group.querySelectorAll('.tag')].some(el => tagText(el).toLowerCase() === normalized);
  if (exists) return;
  const tag = document.createElement('span');
  tag.className = 'tag ' + tagClass;
  tag.dataset.candidate = isCandidate ? '1' : '0';
  tag.dataset.field = fieldKey;
  tag.innerHTML = `${escapeHtml(name)} <i class="tag-del" onclick="removeUploadTag(this)">×</i>`;
  group.insertBefore(tag, btn);
  scheduleSaveCurrentUploadTags();
}

// ===== 上传步骤 =====
let lastUploadedImageUrl = ''; // 暂存上传图片URL
let lastExtractedTags = {};    // 暂存提取的标签
let currentUploadStyleId = localStorage.getItem('current_upload_style_id') || '';
let currentCompositeIds = [];
let draftPollTimer = null;
let uploadTagSaveTimer = null;

async function goUploadStep(step) {
  document.querySelectorAll('.upload-step-panel').forEach(p => p.style.display = 'none');
  document.getElementById('upload-step-'+step).style.display = 'block';
  [2,3].forEach(s => {
    const el = document.getElementById('step-'+s);
    if (!el) return;
    el.className = 'step ' + (s < step ? 'step-done' : s === step ? 'step-active' : 'step-pending');
    if (s < step) el.querySelector('.step-num').innerHTML = '<i class="ti ti-check"></i>';
    else el.querySelector('.step-num').textContent = s;
  });
}

async function saveCurrentUploadTags(options = {}) {
  await saveUploadStyleName();
  const payload = emptyStyleTagsPayload();
  const craftEls = [...document.querySelectorAll('#craft-tags .tag')];
  const marketEls = [...document.querySelectorAll('#market-tags .tag')];
  craftEls.forEach(el => applyTagElementToPayload(payload, el, 'craft'));
  marketEls.forEach(el => applyTagElementToPayload(payload, el, 'market'));
  payload.candidate_tags = [
    ...craftEls.filter(el => el.dataset.candidate === '1').map(el => `工艺维度: ${tagText(el)}`),
    ...marketEls.filter(el => el.dataset.candidate === '1').map(el => `营销维度: ${tagText(el)}`),
  ].filter(Boolean);
  try {
    const saved = await apiRequest(`/styles/${currentUploadStyleId}/tags`, {
      method: 'PUT',
      body: JSON.stringify(payload),
    });
    lastExtractedTags = saved;
  } catch (e) {
    console.warn('[标签] 保存失败:', e.message);
    if (!options.silent) throw e;
  }
}

function emptyStyleTagsPayload() {
  return {
    color_system: [],
    style_tags: [],
    scene_tags: [],
    season_tags: [],
    skin_tone_suitability: [],
    nail_technique: [],
    nail_decoration: [],
    nail_finish: 'unknown',
    nail_shape: 'unknown',
    nail_length: 'unknown',
    finger_shape: lastExtractedTags.finger_shape || 'unknown',
    nail_bed_shape: lastExtractedTags.nail_bed_shape || 'unknown',
    candidate_tags: [],
  };
}

function applyTagElementToPayload(payload, el, fallbackGroup) {
  if (el.dataset.candidate === '1') return;
  const value = tagText(el);
  if (!value) return;
  const field = el.dataset.field || (fallbackGroup === 'craft' ? 'nail_technique' : 'style_tags');
  if (['nail_finish', 'nail_shape', 'nail_length', 'finger_shape', 'nail_bed_shape'].includes(field)) {
    if (!payload[field] || payload[field] === 'unknown') payload[field] = value;
    return;
  }
  if (!Array.isArray(payload[field])) payload[field] = [];
  if (!payload[field].includes(value)) payload[field].push(value);
}

function tagText(el) {
  return el.textContent.replace('×', '').trim();
}

function scheduleSaveCurrentUploadTags() {
  if (!currentUploadStyleId) return;
  clearTimeout(uploadTagSaveTimer);
  uploadTagSaveTimer = setTimeout(() => saveCurrentUploadTags({ silent: true }), 350);
}

async function saveUploadStyleName() {
  if (!adminBackendAvailable || !currentUploadStyleId) return;
  const input = document.getElementById('upload-style-name');
  const styleName = (input?.value || '').trim();
  if (!styleName || styleName === '待上传...') return;
  try {
    await apiRequest(`/styles/${currentUploadStyleId}`, {
      method: 'PUT',
      body: JSON.stringify({ style_name: styleName }),
    });
  } catch (e) {
    console.warn('[款式名称] 保存失败:', e.message);
  }
}

async function continueDraft(styleId) {
  currentUploadStyleId = styleId;
  localStorage.setItem('current_upload_style_id', styleId);
  await restoreUploadDraft(styleId);
  goUploadStep(2);
  switchPage('upload');
}

async function restoreUploadDraft(styleId = currentUploadStyleId) {
  if (!styleId || !adminBackendAvailable) return;
  try {
    const style = await apiGet(`/styles/${styleId}`);
    currentUploadStyleId = style.style_id;
    lastUploadedImageUrl = style.image_url;
    lastExtractedTags = style.tags || {};
    const previewImg = document.querySelector('.upload-img');
    if (previewImg && style.image_url) previewImg.innerHTML = `<img src="${staticUrl(style.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px;cursor:pointer" onclick="event.stopPropagation();openLightbox('${staticUrl(style.image_url)}')">`;
    const filenameEl = document.querySelector('.upload-filename');
    if (filenameEl) filenameEl.textContent = style.style_name || '新款式草稿';
    const nameInput = document.getElementById('upload-style-name');
    if (nameInput) nameInput.value = style.style_name || '新款式草稿';
    const sizeEl = document.querySelector('.upload-size');
    if (sizeEl) sizeEl.textContent = reviewStatusText(style.review_status || '');
    if (style.review_status === 'tag_extracting') {
      setTagStatus('标签仍在提取中，请等待', true);
      pollDraftTags(styleId);
    } else if (Object.keys(lastExtractedTags).length) {
      renderExtractedTags(lastExtractedTags);
    }
  } catch (e) {
    console.warn('[草稿] 恢复失败:', e.message);
  }
}

function setTagStatus(text, loading = false) {
  const statusEl = document.getElementById('upload-tag-status');
  if (statusEl) {
    statusEl.style.display = 'inline-flex';
    statusEl.innerHTML = `<i class="ti ti-${loading ? 'loader' : 'info-circle'}"></i> ${text}`;
  }
}

function pollDraftTags(styleId) {
  clearInterval(draftPollTimer);
  draftPollTimer = setInterval(async () => {
    try {
      const style = await apiGet(`/styles/${styleId}`);
      if (style.review_status === 'tag_extracting') {
        setTagStatus('标签仍在提取中，请等待', true);
        return;
      }
      clearInterval(draftPollTimer);
      lastExtractedTags = style.tags || {};
      if (style.review_status === 'tag_failed') {
        setTagStatus('标签提取失败，请手动添加');
      } else {
        renderExtractedTags(lastExtractedTags);
      }
      loadStylesData();
    } catch (e) {
      clearInterval(draftPollTimer);
    }
  }, 1500);
}

async function previewComposite() {
  const area = document.getElementById('composite-preview-area');
  if (!area || !currentUploadStyleId) return;

  const templateIds = [...selectedTemplateIds];
  if (templateIds.length === 0) {
    area.innerHTML = '<div style="font-size:12px;color:#CC2200;margin-top:8px">请先在模板网格中选择至少一个模板</div>';
    return;
  }
  if (templateIds.length > MAX_COMPOSITE_TEMPLATE_SELECTION) {
    area.innerHTML = `<div style="font-size:12px;color:#CC2200;margin-top:8px">最多只能选择 ${MAX_COMPOSITE_TEMPLATE_SELECTION} 张模板进行合成</div>`;
    return;
  }

  area.innerHTML = '<div class="composite-preview-loading"><i class="ti ti-loader"></i> 批量合成中...</div>';

  try {
    const results = await apiPost(`/styles/${currentUploadStyleId}/composites/batch-generate`, {
      template_ids: templateIds,
    });
    if (Array.isArray(results) && results.length) {
      currentCompositeIds = results.map(item => item.composite_id);
      area.innerHTML = `<div class="composite-grid">${results.map(item => `
        <div class="composite-card selected" onclick="toggleCompositeCard(this, '${item.composite_id}')">
          <div class="tpl-check">✓</div>
          <img src="${staticUrl(item.result_image_url)}" class="composite-preview-img" alt="合成预览">
        </div>
      `).join('')}</div>`;
    } else {
      area.innerHTML = '<div style="font-size:12px;color:#CC2200;margin-top:8px">合成失败，请重试</div>';
    }
  } catch (e) {
    area.innerHTML = '<div style="font-size:12px;color:#CC2200;margin-top:8px">合成失败：' + e.message + '</div>';
  }
}

async function loadTemplatesForUpload() {
  await renderTemplates();
}

function toggleCompositeCard(el, compositeId) {
  el.classList.toggle('selected');
  if (el.classList.contains('selected')) {
    if (!currentCompositeIds.includes(compositeId)) currentCompositeIds.push(compositeId);
  } else {
    currentCompositeIds = currentCompositeIds.filter(id => id !== compositeId);
  }
}

async function finishUpload() {
  if (!currentUploadStyleId) return;
  try {
    clearTimeout(uploadTagSaveTimer);
    await saveCurrentUploadTags();
    if (currentCompositeIds.length) {
      await apiRequest(`/styles/${currentUploadStyleId}/composites/selection`, {
        method: 'PUT',
        body: JSON.stringify({ selected_composite_ids: currentCompositeIds }),
      });
    }
    await apiPost(`/styles/${currentUploadStyleId}/publish`, {});
    localStorage.removeItem('current_upload_style_id');
    currentUploadStyleId = '';
    activeStyleStatus = 'active';
    selectedStyleIds.clear();
    styleDeleteMode = false;
    switchPage('assets');
    const activeTab = getStyleTabButton('active');
    if (activeTab) {
      document.querySelectorAll('#panel-assets .asset-tabs .asset-tab').forEach(b => {
        if (b.textContent.includes('已上架') || b.textContent.includes('草稿箱')) b.classList.remove('active');
      });
      activeTab.classList.add('active');
    }
    updateStyleDeleteUI();
    loadStylesData();
    showToast('款式已完成上传');
  } catch (e) {
    alert('完成上传失败：' + e.message);
  }
}

function switchTrendSourceMode(mode, btn) {
  trendSourceMode = mode;
  document.querySelectorAll('[data-source-mode]').forEach(el => el.classList.remove('active'));
  if (btn) btn.classList.add('active');
  document.querySelectorAll('.trend-source-panel').forEach(panel => {
    panel.classList.remove('active');
    panel.style.display = 'none';
  });
  const activePanel = document.getElementById(`trend-source-${mode}`);
  if (activePanel) {
    activePanel.style.display = 'block';
    activePanel.classList.add('active');
  }
}

function setTrendSourceStatus(id, text, isError = false) {
  const el = document.getElementById(id);
  if (!el) return;
  el.textContent = text;
  el.style.color = isError ? '#CC2200' : '#888';
}

function loadSampleXhsLinks() {
  const textarea = document.getElementById('trend-link-seeds');
  if (!textarea) return;
  textarea.value = [
    'http://xhslink.com/o/6eCHpoPK40Y',
    'http://xhslink.com/o/1mP7vLmfX1y',
    'http://xhslink.com/o/5UxZykb2cQK',
  ].join('\n');
  setTrendSourceStatus('trend-link-status', '已载入示例链接，可继续编辑后保存');
}

function saveTrendSeedLinks() {
  const textarea = document.getElementById('trend-link-seeds');
  const value = (textarea?.value || '').trim();
  localStorage.setItem('trend_seed_links', value);
  const count = value ? value.split('\n').map(s => s.trim()).filter(Boolean).length : 0;
  setTrendSourceStatus('trend-link-status', `已保存 ${count} 条链接种子，点击“运行趋势识别”将由后端统一触发抓取和分析。`);
  showToast('链接种子已保存');
}

function restoreTrendSourceConfig() {
  const savedLinks = localStorage.getItem('trend_seed_links');
  if (savedLinks) {
    const textarea = document.getElementById('trend-link-seeds');
    if (textarea && !textarea.value) textarea.value = savedLinks;
  }
}

async function runTrendAgent() {
  if (!adminBackendAvailable) {
    showToast('后端未连接，无法运行趋势识别');
    return;
  }
  renderTrendRunCard({
    pipeline_run_id: latestTrendPipelineRunId || '',
    status: 'pending',
    triggered_by: 'manual',
    stage: 'queued',
    total_posts: 0,
    processed_posts: 0,
    imported_posts: 0,
    updated_posts: 0,
    generated_trends: 0,
    converted_drafts: 0,
    linked_trend_run_id: '',
    updated_at: '',
    created_at: '',
    error_message: '',
    logs: [],
    payload: {},
  });
  try {
    const request = buildTrendPipelineRequest();
    if (request == null) return;
    const run = await apiPost('/trend-agent/pipeline-runs', {
      triggered_by: 'manual',
      ...request,
    });
    latestTrendPipelineRunId = run.pipeline_run_id;
    localStorage.setItem('trend_latest_pipeline_run_id', latestTrendPipelineRunId);
    renderTrendRunCard(run);
    pollTrendRun(run.pipeline_run_id);
    showToast('趋势任务已创建');
  } catch (e) {
    renderTrendRunCard({
      status: 'failed',
      stage: 'failed',
      error_message: e.message,
      pipeline_run_id: '',
      triggered_by: 'manual',
      total_posts: 0,
      processed_posts: 0,
      imported_posts: 0,
      updated_posts: 0,
      generated_trends: 0,
      converted_drafts: 0,
      linked_trend_run_id: '',
      updated_at: '',
      created_at: '',
      logs: [],
      payload: {},
    });
    showToast('趋势任务创建失败');
  }
}

async function loadTrendRunsAndList() {
  restoreTrendSourceConfig();
  await Promise.all([loadLatestTrendRun(), loadTrendList(), loadCandidateTaxonomyTerms()]);
}

async function loadLatestTrendRun() {
  if (!adminBackendAvailable) {
    renderTrendRunCard(null);
    return;
  }
  try {
    const data = await apiGet('/trend-agent/pipeline-runs', { limit: 1 });
    const latestRun = Array.isArray(data?.runs) && data.runs.length ? data.runs[0] : null;
    let run = latestRun;

    if (latestTrendPipelineRunId && (!latestRun || latestRun.pipeline_run_id !== latestTrendPipelineRunId)) {
      try {
        const storedRun = await apiGet(`/trend-agent/pipeline-runs/${latestTrendPipelineRunId}`);
        const storedUpdatedAt = new Date(storedRun?.updated_at || storedRun?.created_at || 0).getTime();
        const latestUpdatedAt = new Date(latestRun?.updated_at || latestRun?.created_at || 0).getTime();
        run = storedUpdatedAt > latestUpdatedAt ? storedRun : latestRun;
      } catch (e) {
        run = latestRun;
      }
    }

    if (run?.pipeline_run_id) {
      latestTrendPipelineRunId = run.pipeline_run_id;
      localStorage.setItem('trend_latest_pipeline_run_id', latestTrendPipelineRunId);
    }
    renderTrendRunCard(run);
    if (run && (run.status === 'pending' || run.status === 'running')) pollTrendRun(run.pipeline_run_id);
  } catch (e) {
    renderTrendRunCard(null);
  }
}

function pollTrendRun(runId) {
  clearInterval(trendRunPollTimer);
  trendRunPollTimer = setInterval(async () => {
    try {
      const run = await apiGet(`/trend-agent/pipeline-runs/${runId}`);
      renderTrendRunCard(run);
      if (run.status === 'succeeded' || run.status === 'failed') {
        clearInterval(trendRunPollTimer);
        if (run.status === 'succeeded') {
          await Promise.all([
            loadTrendList(),
            loadCandidateTaxonomyTerms(),
          ]);
          showToast(`趋势任务完成，产出 ${run.generated_trends || 0} 条趋势`);
        }
      }
    } catch (e) {
      clearInterval(trendRunPollTimer);
    }
  }, 1500);
}

function renderTrendRunCard(run) {
  const el = document.getElementById('trend-run-card');
  if (!el) return;
  if (!run || !run.pipeline_run_id) {
    el.innerHTML = '<div class="trend-run-empty">尚未运行趋势识别任务</div>';
    return;
  }
  const statusText = {
    pending: '等待执行',
    running: '运行中',
    succeeded: '已完成',
    failed: '失败',
  }[run.status] || run.status;
  const statusClass = run.status === 'failed' ? 'down' : run.status === 'succeeded' ? 'up' : 'peak';
  const stageText = {
    queued: '已排队',
    build_posts: '构建帖子',
    classify_posts: '清洗与分类',
    comment_pipeline: '评论抓取与摘要',
    import_posts: '导入帖子',
    trend_discovery: '趋势识别',
    convert_to_draft: '推送队列',
    completed: '已完成',
    failed: '失败',
  }[run.stage] || run.stage || '处理中';
  const sourceMode = run?.payload?.source_mode || '';
  const nestedTrendRun = run?.payload?.trend_run || {};
  const discoveredPostCount = nestedTrendRun.total_posts || 0;
  const commentCompletedPosts = run.processed_posts || 0;
  const dataSyncText = `${Number(run.imported_posts || 0)} 新增 / ${Number(run.updated_posts || 0)} 更新`;
  const commentInsightText = commentCompletedPosts > 0 ? `${commentCompletedPosts} 篇已处理` : '复用已清洗数据';
  const summaryText = run.status === 'succeeded'
    ? `已基于 ${discoveredPostCount || run.total_posts || 0} 篇有效帖子生成 ${run.generated_trends || 0} 条趋势，帖子库完成 ${dataSyncText}。`
    : run.status === 'failed'
      ? '本次趋势识别未完成，请查看失败原因后重试。'
      : `正在处理 ${run.total_posts || 0} 篇帖子，当前阶段为「${stageText}」。`;
  const needsLoginHint = sourceMode === 'seed_links' && run.stage === 'comment_pipeline' && (run.status === 'pending' || run.status === 'running');
  el.innerHTML = `
    <div class="trend-run-head">
      <div>
        <div class="trend-run-title">最近一次趋势识别</div>
        <div class="trend-run-meta">任务编号：${run.pipeline_run_id} · 触发方式：${run.triggered_by || 'manual'} · 更新时间：${formatDateTime(run.updated_at || run.created_at)}</div>
      </div>
      <span class="lc-pill lc-${statusClass}">${statusText}</span>
    </div>
    <div class="trend-run-summary">${escapeHtml(summaryText)}</div>
    <div class="trend-run-stats">
      <div class="trend-run-stat"><span>本次接入帖子</span><strong>${run.total_posts || 0}</strong></div>
      <div class="trend-run-stat"><span>参与趋势识别</span><strong>${discoveredPostCount || run.total_posts || 0}</strong></div>
      <div class="trend-run-stat"><span>产出趋势</span><strong>${run.generated_trends || 0}</strong></div>
      <div class="trend-run-stat"><span>帖子库更新</span><strong>${dataSyncText}</strong></div>
    </div>
    <div class="trend-run-note"><i class="ti ti-info-circle"></i><span>评论洞察：${escapeHtml(commentInsightText)}。爆款推送由趋势详情中的「爆款推送」单独触发，不计入本次识别任务。</span></div>
    ${needsLoginHint ? `<div class="trend-run-login-hint"><i class="ti ti-user-check"></i><span>当前正在抓取链接评论，需要本机 Playwright 浏览器登录小红书并保持页面可继续执行。</span></div>` : ''}
    ${run.error_message ? `<div class="trend-run-error">${run.error_message}</div>` : ''}
  `;
}

function buildTrendPipelineRequest() {
  const base = {
    provider: 'auto',
    comment_limit: 0,
    min_support: 2,
    max_trends: 20,
    resume: true,
    from_start: false,
    force_summary: false,
    headless: false,
    auto_convert_to_draft: false,
    convert_limit: 3,
    merchant_id: 'demo_shop',
    use_trend_tags: true,
  };
  if (trendSourceMode === 'links') {
    const textarea = document.getElementById('trend-link-seeds');
    const seedLinks = (textarea?.value || '')
      .split('\n')
      .map(s => s.trim())
      .filter(Boolean);
    if (!seedLinks.length) {
      setTrendSourceStatus('trend-link-status', '请先粘贴至少 1 条链接', true);
      return null;
    }
    setTrendSourceStatus('trend-link-status', `准备提交 ${seedLinks.length} 条链接种子到后端任务`);
    return {
      ...base,
      seed_links: seedLinks,
      output_json_path: 'backend/mock_data/ugc_posts_from_links_clean.json',
      raw_comments_file: 'backend/mock_data/ugc_posts_from_links_clean_raw_comments.json',
    };
  }
  if (trendSourceMode === 'clean') {
    setTrendSourceStatus('trend-clean-status', '将直接复用现有 clean 文件，跳过评论抓取并重新运行趋势识别');
    return {
      ...base,
      input_json_path: 'backend/mock_data/ugc_posts_from_links_clean.json',
      output_json_path: 'backend/mock_data/ugc_posts_from_links_clean.json',
      raw_comments_file: 'backend/mock_data/ugc_posts_from_links_clean_raw_comments.json',
      skip_comment_pipeline: true,
    };
  }
  return null;
}

async function loadTrendList() {
  const listEl = document.getElementById('trend-list');
  if (!listEl) return;
  if (!adminBackendAvailable) {
    trendListData = [];
    listEl.innerHTML = '<div class="trend-run-empty">后端未连接，趋势池不可用</div>';
    updateTrendCount();
    return;
  }
  const status = document.getElementById('trend-status-filter')?.value || '';
  const lifeCycle = document.getElementById('trend-life-cycle-filter')?.value || '';
  listEl.innerHTML = '<div class="trend-run-empty">趋势池加载中...</div>';
  try {
    const data = await apiGet('/trends', {
      limit: 100,
      status: status || undefined,
      life_cycle: lifeCycle || undefined,
    });
    const incomingTrends = Array.isArray(data?.trends) ? data.trends : [];
    trendListData = dedupeTrendItems(incomingTrends);
    trendScoreScaleMax = Math.max(...trendListData.map(item => Number(item?.trend_score || 0)), 0);
    renderTrendList();
    updateTrendCount();
    if (trendListData.length) {
      const nextId = trendListData.some(item => item.trend_id === selectedTrendId) ? selectedTrendId : trendListData[0].trend_id;
      await openTrendDetail(nextId);
    } else {
      selectedTrendId = '';
      renderTrendDetail(null);
    }
  } catch (e) {
    listEl.innerHTML = `<div class="trend-run-empty">趋势池加载失败：${e.message}</div>`;
    trendListData = [];
    trendScoreScaleMax = 0;
    updateTrendCount();
  }
}

function dedupeTrendItems(items) {
  const bestByCoreStyle = new Map();
  for (const item of items || []) {
    const key = String(item?.core_style || '').trim() || String(item?.trend_id || '').trim();
    const existing = bestByCoreStyle.get(key);
    if (!existing) {
      bestByCoreStyle.set(key, item);
      continue;
    }
    const itemScore = Number(item?.trend_score || 0);
    const existingScore = Number(existing?.trend_score || 0);
    const itemUpdated = new Date(item?.updated_at || item?.identified_at || 0).getTime();
    const existingUpdated = new Date(existing?.updated_at || existing?.identified_at || 0).getTime();
    if (itemScore > existingScore || (itemScore === existingScore && itemUpdated > existingUpdated)) {
      bestByCoreStyle.set(key, item);
    }
  }
  return Array.from(bestByCoreStyle.values()).sort((a, b) => {
    const scoreDelta = Number(b?.trend_score || 0) - Number(a?.trend_score || 0);
    if (scoreDelta !== 0) return scoreDelta;
    return new Date(b?.identified_at || b?.updated_at || 0).getTime() - new Date(a?.identified_at || a?.updated_at || 0).getTime();
  });
}

function updateTrendCount() {
  const el = document.getElementById('trend-count');
  if (el) el.textContent = `${trendListData.length} 条`;
}

function renderTrendList() {
  const listEl = document.getElementById('trend-list');
  if (!listEl) return;
  if (!trendListData.length) {
    listEl.innerHTML = '<div class="trend-run-empty">暂无趋势结果，先运行趋势识别。</div>';
    return;
  }
  listEl.innerHTML = trendListData.map(item => {
    const metrics = item.metrics || {};
    const active = item.trend_id === selectedTrendId ? 'is-active' : '';
    return `
      <button class="trend-item ${active}" onclick="openTrendDetail('${item.trend_id}')">
        <div class="trend-thumb">
          ${item.representative_image_url ? `<img src="${staticUrl(item.representative_image_url)}" alt="${escapeHtml(item.core_style)}" onerror="this.outerHTML='<i class=\\'ti ti-photo\\'></i>'">` : '<i class="ti ti-photo"></i>'}
        </div>
        <div class="trend-item-body">
          <div class="trend-item-head">
            <div class="trend-item-title">${escapeHtml(item.core_style || '未命名趋势')}</div>
            <div class="trend-item-score">${formatTrendScore100(item.trend_score)}</div>
          </div>
          <div class="trend-item-meta">
            ${trendBadge(item.life_cycle, item.memory_status)}
            <span>${metrics.support_post_count || 0} 篇支撑帖子</span>
            <span>置信度 ${formatPercent(item.confidence)}</span>
          </div>
          <div class="trend-item-summary">${escapeHtml(item.reasoning_summary || '暂无解释')}</div>
        </div>
      </button>
    `;
  }).join('');
}

async function openTrendDetail(trendId) {
  selectedTrendId = trendId;
  renderTrendList();
  if (!adminBackendAvailable) {
    renderTrendDetail(null);
    return;
  }
  const el = document.getElementById('trend-detail-card');
  if (el) el.innerHTML = '<div class="trend-detail-empty">详情加载中...</div>';
  try {
    const trend = await apiGet(`/trends/${trendId}`);
    renderTrendDetail(trend);
    if (!trendSeenIds.has(trendId)) {
      trendSeenIds.add(trendId);
      recordTrendAction(trendId, 'viewed').catch(() => {});
    }
  } catch (e) {
    renderTrendDetailError(e.message);
  }
}

function renderTrendDetailError(message) {
  const el = document.getElementById('trend-detail-card');
  if (!el) return;
  el.innerHTML = `<div class="trend-detail-empty">趋势详情加载失败：${escapeHtml(message)}</div>`;
}

function renderTrendDetail(trend) {
  const el = document.getElementById('trend-detail-card');
  if (!el) return;
  if (!trend) {
    el.innerHTML = '<div class="trend-detail-empty">选择一条趋势查看详情、支撑帖子和转草稿入口</div>';
    return;
  }
  const metrics = trend.metrics || {};
  const signals = trend.comment_signal_summary || {};
  const supportPosts = Array.isArray(trend.supporting_posts) ? trend.supporting_posts : [];
  const evidenceChips = [
    ...chipGroup((metrics.core_style_tags || []).slice(0, 6), 'style'),
    ...chipGroup((signals.user_demands || []).slice(0, 4), 'demand'),
    ...chipGroup((signals.social_proofs || []).slice(0, 4), 'social'),
    ...chipGroup((signals.negative_feedbacks || []).slice(0, 4), 'negative'),
  ].join('');

  el.innerHTML = `<div class="trend-detail-scroll">
    <div class="trend-detail-cover">
      <div class="trend-cover-fallback"><i class="ti ti-photo"></i></div>
      ${trend.representative_image_url ? `<img src="${staticUrl(trend.representative_image_url)}" alt="${escapeHtml(trend.core_style)}" onload="this.parentElement.classList.remove('is-fallback')">` : '<i class="ti ti-photo"></i>'}
    </div>
    <div class="trend-detail-head">
      <div>
        <div class="trend-detail-title">${escapeHtml(trend.core_style || '未命名趋势')}</div>
        <div class="trend-detail-meta">${trendBadge(trend.life_cycle, trend.memory_status)}<span class="trend-score-pill">趋势分 ${formatTrendScore100(trend.trend_score)}</span><span class="trend-score-pill">原始分 ${formatScore(trend.trend_score)}</span><span class="trend-score-pill">置信度 ${formatPercent(trend.confidence)}</span></div>
        <div class="trend-detail-meta" style="margin-top:4px">
          <span class="trend-score-pill">数据: ${lifecycleLabelText(trend.data_lifecycle)}</span>
          <span class="trend-score-pill">趋势: ${lifecycleLabelText(trend.trend_lifecycle)}</span>
          ${signalQualitySummary(trend.signal_quality_distribution)}
        </div>
      </div>
    </div>
    <div class="trend-detail-summary">${escapeHtml(trend.reasoning_summary || '暂无趋势解释')}</div>
    <div class="trend-metrics-grid">
      ${trendMetric('支撑帖子', metrics.support_post_count || 0)}
      ${trendMetric('评论覆盖率', formatPercent(metrics.average_comment_coverage_rate))}
      ${trendMetric('需求信号分', formatScore(metrics.comment_signal_score))}
      ${trendMetric('覆盖率置信度', formatScore(metrics.coverage_confidence_score))}
    </div>
    <div class="trend-signal-section">
      <div class="trend-section-title">趋势证据画像</div>
      <div class="trend-signal-tags">${evidenceChips || '<span class="trend-empty-inline">暂无结构化评论信号</span>'}</div>
    </div>
    <div class="trend-signal-section">
      <div class="trend-section-title">跨帖聚合信号</div>
      <div class="trend-compact-list">
        ${trendSignalLine('需求信号', signals.demand_signal_counts)}
        ${trendSignalLine('社会证明', signals.social_proof_counts)}
        ${trendSignalLine('购买意图', signals.purchase_intent_counts)}
        ${trendSignalLine('负向反馈', signals.negative_signal_counts)}
      </div>
    </div>
    <div class="trend-detail-actions">
      <button class="btn-ghost-sm" onclick="recordTrendAction('${trend.trend_id}','watching').then(()=>showToast('已标记为观察中'))"><i class="ti ti-eye"></i> 观察中</button>
      <button class="btn-ghost-sm" onclick="recordTrendAction('${trend.trend_id}','ignored').then(()=>showToast('已忽略该趋势'))"><i class="ti ti-x"></i> 忽略</button>
      <button class="btn-primary-sm" onclick="pushTrendToQueue('${trend.trend_id}')"><i class="ti ti-rocket"></i> 爆款推送</button>
    </div>
    <div class="trend-signal-section">
      <div class="trend-section-title">查看爆款依据</div>
      <div class="support-post-list">
        ${supportPosts.length ? supportPosts.map(renderSupportingPostCard).join('') : '<div class="trend-empty-inline">暂无支撑帖子</div>'}
      </div>
    </div>
  </div>`;
}

function renderSupportingPostCard(post) {
  const evidence = Array.isArray(post.evidence_signals) ? post.evidence_signals : [];
  const title = post.title || post.post_id || '支撑帖子';
  const cover = post.representative_image_url || post.cover_image_url || (Array.isArray(post.image_urls) ? post.image_urls[0] : '');
  return `
    <div class="support-post-item">
      <div class="support-post-cover">${cover ? `<img src="${staticUrl(cover)}" alt="${escapeHtml(title)}">` : '<i class="ti ti-photo"></i>'}</div>
      <div class="support-post-body">
        <div class="support-post-title">${escapeHtml(title)}</div>
        <div class="support-post-meta">
          <span>赞 ${formatCompact(post.like_count)}</span>
          <span>藏 ${formatCompact(post.favorite_count)}</span>
          <span>评 ${formatCompact(post.comment_count)}</span>
          <span>覆盖率 ${formatPercent(post.comment_coverage_rate)}</span>
        </div>
        <div class="support-post-summary">${escapeHtml(post.comment_summary || post.content || '暂无摘要')}</div>
        <div class="support-post-evidence">${evidence.length ? evidence.map(signal => `<span class="trend-chip trend-chip-style">${escapeHtml(signal)}</span>`).join('') : ''}</div>
        ${post.source_url ? `<a class="support-post-link" href="${escapeHtml(post.source_url)}" target="_blank" rel="noreferrer">查看原帖</a>` : ''}
      </div>
    </div>
  `;
}

async function recordTrendAction(trendId, action, note = '') {
  if (!adminBackendAvailable) return null;
  return apiPost(`/trends/${trendId}/actions`, {
    merchant_id: 'demo_shop',
    action,
    note,
  });
}

async function pushTrendToQueue(trendId) {
  showTrendPushConfirmModal(trendId);
}

function showTrendPushConfirmModal(trendId) {
  const existing = document.getElementById('trend-push-confirm-modal');
  if (existing) existing.remove();
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay show';
  overlay.id = 'trend-push-confirm-modal';
  overlay.innerHTML = `
    <div class="modal-content" style="max-width:420px;text-align:left">
      <div style="display:flex;align-items:center;gap:10px;margin-bottom:10px">
        <span style="width:36px;height:36px;border-radius:12px;background:#f2edf8;color:#8d79b8;display:flex;align-items:center;justify-content:center"><i class="ti ti-rocket"></i></span>
        <h3 style="margin:0;font-size:18px">确认推送</h3>
      </div>
      <p style="margin:0 0 18px;color:#777;line-height:1.7">确认将该趋势推送到商户运营平台的爆款推送待上架队列？</p>
      <div style="display:flex;justify-content:flex-end;gap:10px">
        <button class="btn-ghost-sm" onclick="document.getElementById('trend-push-confirm-modal')?.remove()">取消</button>
        <button class="btn-primary-sm" onclick="confirmPushTrendToQueue('${escapeAttr(trendId)}')"><i class="ti ti-check"></i> 确认</button>
      </div>
    </div>`;
  overlay.onclick = (event) => {
    if (event.target === overlay) overlay.remove();
  };
  document.body.appendChild(overlay);
}

async function confirmPushTrendToQueue(trendId) {
  document.getElementById('trend-push-confirm-modal')?.remove();
  if (!adminBackendAvailable) {
    showToast('后端未连接，无法推送到爆款队列');
    return;
  }
  try {
    await recordTrendAction(trendId, 'accepted', 'push_to_queue');
    const result = await apiPost(`/trends/${trendId}/push-to-queue`, {
      merchant_id: 'demo_shop',
    });
    if (result?.pushed) {
      showTopSuccessBanner('已推送完成，由于内含生图请求，商户需稍等片刻后才能在待上架列表中查看哦～');
    } else {
      showToast(result?.message || '推送失败');
    }
  } catch (e) {
    showToast(`爆款推送失败：${e.message}`);
  }
}

function chipGroup(values, type) {
  return values.map(value => `<span class="trend-chip trend-chip-${type}">${escapeHtml(value)}</span>`);
}

function trendSignalLine(label, counts) {
  let entries = [];
  if (Array.isArray(counts)) {
    entries = counts
      .map(item => [String(item?.label || ''), Number(item?.count || 0)])
      .filter(([key]) => key);
  } else {
    entries = Object.entries(counts || {}).map(([key, val]) => [key, Number(val || 0)]);
  }
  entries = entries
    .sort((a, b) => Number(b[1] || 0) - Number(a[1] || 0))
    .slice(0, 4);
  return `
    <div class="trend-signal-line">
      <span class="trend-signal-label">${label}</span>
      <span class="trend-signal-values">${entries.length ? entries.map(([key, val]) => `${escapeHtml(key)} · ${val}`).join(' / ') : '暂无'}</span>
    </div>
  `;
}

function trendMetric(label, value) {
  return `<div class="trend-metric"><span>${label}</span><strong>${value}</strong></div>`;
}

function trendBadge(lifeCycle, memoryStatus) {
  return `
    <span class="lc-pill lc-${lifeCycleClass(lifeCycle || '观察期')}"><i class="ti ti-${lifeCycleIcon(lifeCycle || '观察期')}"></i>${lifeCycle || '观察期'}</span>
    <span class="trend-memory-pill">${escapeHtml(memoryStatusText(memoryStatus))}</span>
  `;
}

function memoryStatusText(status) {
  return {
    active: '持续活跃',
    watching: '持续观察',
    declining: '记忆衰退',
    archived: '已归档',
  }[status] || (status || '持续观察');
}

function lifecycleLabelText(lc) {
  return {
    recent: '近期数据',
    mid_term: '中期数据',
    long_tail: '长期数据',
    rising: '上升中',
    declining: '下降中',
    stable: '稳定',
    insufficient_history: '数据不足',
  }[lc] || lc || '未知';
}

function signalQualitySummary(dist) {
  if (!dist || !Object.keys(dist).length) return '';
  const parts = [];
  if (dist.active) parts.push(`高信号 ${dist.active}`);
  if (dist.cold_start) parts.push(`冷启动 ${dist.cold_start}`);
  if (dist.low_content) parts.push(`低内容 ${dist.low_content}`);
  if (!parts.length) return '';
  return `<span class="trend-score-pill">信号: ${parts.join(' / ')}</span>`;
}

// ===== 候选标签词 (Fix 5) =====
let candidateTaxonomyTerms = [];

async function loadCandidateTaxonomyTerms() {
  const list = document.getElementById('candidate-taxonomy-list');
  if (!list) return;
  if (!adminBackendAvailable) {
    list.innerHTML = '<div class="trend-run-empty">后端未连接</div>';
    return;
  }
  try {
    const data = await apiGet('/trends/candidate-taxonomy', { status: 'pending', limit: 50 });
    candidateTaxonomyTerms = Array.isArray(data?.terms) ? data.terms : [];
    renderCandidateTaxonomyList();
  } catch (e) {
    list.innerHTML = `<div class="trend-run-empty">加载失败：${e.message}</div>`;
  }
}

function renderCandidateTaxonomyList() {
  const list = document.getElementById('candidate-taxonomy-list');
  if (!list) return;
  if (!candidateTaxonomyTerms.length) {
    list.innerHTML = '<div class="trend-run-empty">暂无候选新标签词</div>';
    return;
  }
  list.innerHTML = candidateTaxonomyTerms.map(item => `
    <div class="candidate-term-item">
      <div class="candidate-term-head">
        <span class="candidate-term-name">${escapeHtml(item.candidate_term)}</span>
        <span class="candidate-term-field">${escapeHtml(item.target_field)}</span>
      </div>
      <div class="candidate-term-meta">
        <span>频次 ${item.frequency}</span>
        ${item.variant_forms.length ? `<span>变体: ${escapeHtml(item.variant_forms.slice(0,3).join(', '))}</span>` : ''}
      </div>
      <div class="candidate-term-actions">
        <button class="btn-ghost-sm" onclick="approveCandidateTerm('${escapeHtml(item.candidate_term)}', '${escapeHtml(item.target_field)}')"><i class="ti ti-check"></i> 通过</button>
        <button class="btn-ghost-sm" onclick="rejectCandidateTerm('${escapeHtml(item.candidate_term)}', '${escapeHtml(item.target_field)}')"><i class="ti ti-x"></i> 拒绝</button>
      </div>
    </div>
  `).join('');
}

let pendingApproveCandidate = null;

function showCandidateApproveModal(term, field, normalizedForm, variants, related) {
  pendingApproveCandidate = { term, field };
  document.getElementById('candidate-edit-term').value = normalizedForm || term;
  document.getElementById('candidate-edit-normalized').value = normalizedForm || term;
  document.getElementById('candidate-edit-field').value = field;
  document.getElementById('candidate-edit-variants').textContent = (variants || []).join(', ') || '无';
  document.getElementById('candidate-edit-related').textContent = (related || []).join(', ') || '无';
  document.getElementById('candidate-approve-modal').classList.add('show');
}

function hideCandidateApproveModal() {
  document.getElementById('candidate-approve-modal').classList.remove('show');
  pendingApproveCandidate = null;
}

async function confirmApproveCandidate() {
  if (!pendingApproveCandidate) return;
  const editedTerm = document.getElementById('candidate-edit-term').value.trim();
  const normalizedForm = document.getElementById('candidate-edit-normalized').value.trim();
  const targetField = document.getElementById('candidate-edit-field').value;
  if (!editedTerm || !targetField) {
    showToast('候选词和归属维度不能为空');
    return;
  }
  try {
    await apiRequest(`/trends/candidate-taxonomy/${encodeURIComponent(pendingApproveCandidate.term)}?target_field=${encodeURIComponent(pendingApproveCandidate.field)}`, {
      method: 'PUT',
      body: JSON.stringify({
        status: 'approved',
        candidate_term: editedTerm,
        normalized_form: normalizedForm || editedTerm,
        target_field: targetField,
      }),
    });
    showToast('候选标签已通过并入库');
    hideCandidateApproveModal();
    loadCandidateTaxonomyTerms();
  } catch (e) {
    showToast('操作失败：' + e.message);
  }
}

async function approveCandidateTerm(term, field) {
  const item = candidateTaxonomyTerms.find(
    t => t.candidate_term === term && t.target_field === field
  );
  showCandidateApproveModal(
    term,
    field,
    item?.normalized_form || term,
    item?.variant_forms || [],
    item?.related_official_tags || []
  );
}

async function rejectCandidateTerm(term, field) {
  try {
    await apiRequest(`/trends/candidate-taxonomy/${encodeURIComponent(term)}?target_field=${encodeURIComponent(field)}`, {
      method: 'PUT',
      body: JSON.stringify({ status: 'rejected' }),
    });
    showToast('候选标签已拒绝');
    loadCandidateTaxonomyTerms();
  } catch (e) {
    showToast('操作失败：' + e.message);
  }
}

function formatPercent(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return '0%';
  return `${Math.round(num * 100)}%`;
}

function formatScore(value) {
  const num = Number(value || 0);
  return Number.isFinite(num) ? num.toFixed(1) : '0.0';
}

function formatTrendScore100(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num) || num <= 0) return '0.0';
  const max = Number(trendScoreScaleMax || 0);
  if (!Number.isFinite(max) || max <= 0) return Math.min(TREND_DISPLAY_SCORE_MAX, num).toFixed(1);
  const normalized = Math.max(0, Math.min(TREND_DISPLAY_SCORE_MAX, (num / max) * TREND_DISPLAY_SCORE_MAX));
  return normalized.toFixed(1);
}

function formatCompact(value) {
  const num = Number(value || 0);
  if (!Number.isFinite(num)) return '0';
  if (num >= 10000) return `${(num / 10000).toFixed(1)}万`;
  if (num >= 1000) return `${(num / 1000).toFixed(1)}k`;
  return String(Math.round(num));
}

function formatDateTime(value) {
  if (!value) return '—';
  const text = String(value).replace('T', ' ');
  return text.length > 19 ? text.slice(0, 19) : text;
}

function escapeHtml(value) {
  return String(value || '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

// ===== 爆款推送（联调 /api/push-cards） =====
let pushCardsData = [];
let activePushCard = null;
let pushDeleteMode = false;
const selectedPushIds = new Set();
const pushEditorViewIndexById = new Map();
const pushSelectedCompositeIndexById = new Map();

async function loadPushData() {
  if (!adminBackendAvailable) {
    updateHomePushPending(0);
    renderPushManager();
    return;
  }
  try {
    const data = await apiGet('/push-cards');
    if (Array.isArray(data) && data.length > 0) {
      pushCardsData = applyRuntimePushCardOverrides(data);
      console.log('[推送] 加载爆款推送数据成功:', pushCardsData.length, '条');
    } else {
      pushCardsData = applyRuntimePushCardOverrides([]);
    }
  } catch (e) {
    console.warn('[推送] 加载失败:', e.message);
    pushCardsData = applyRuntimePushCardOverrides([]);
  }
  updateHomePushPending(pushCardsData.filter(card => !isPushListed(card)).length);
  renderPushManager();
  restorePushEditorFromHash();
}

function showPushManager() {
  const manager = document.getElementById('push-manager');
  const editor = document.getElementById('push-editor');
  if (manager) manager.style.display = 'block';
  if (editor) editor.style.display = 'none';
  if (pushHashPage() === 'push' && pushHashParams().has('push_id')) {
    window.history.replaceState(null, '', '#push');
  }
}

function openPushEditor(pushId, options = {}) {
  const card = pushCardsData.find(item => item.push_id === pushId) || pushCardsData[0];
  if (!card) return;
  activePushCard = card;
  renderPushEditor(card);
  const manager = document.getElementById('push-manager');
  const editor = document.getElementById('push-editor');
  if (manager) manager.style.display = 'none';
  if (editor) editor.style.display = 'block';
  if (options.updateHash !== false) {
    const nextHash = `#push?push_id=${encodeURIComponent(card.push_id)}`;
    if (window.location.hash !== nextHash) {
      window.history.replaceState(null, '', nextHash);
    }
  }
}

function restorePushEditorFromHash() {
  if (pushHashPage() !== 'push') return;
  const pushId = pushHashParams().get('push_id') || '';
  if (!pushId) return;
  if (pushCardsData.some(card => card.push_id === pushId)) {
    openPushEditor(pushId, { updateHash: false });
  }
}

function renderPushManager() {
  const pendingList = document.getElementById('push-pending-list');
  const listedList = document.getElementById('push-listed-list');
  if (!pendingList || !listedList) return;

  const pending = pushCardsData.filter(card => !isPushListed(card));
  const listed = pushCardsData.filter(isPushListed);
  updateHomePushPending(pending.length);
  document.getElementById('push-pending-count').textContent = `${pending.length} 条`;
  document.getElementById('push-listed-count').textContent = `${listed.length} 条`;
  pendingList.innerHTML = pending.length ? pending.map(renderPushManageCard).join('') : renderPushEmpty('暂无待上架推送');
  listedList.innerHTML = listed.length ? listed.map(renderPushManageCard).join('') : renderPushEmpty('暂无已上架推送');
  updatePushDeleteUI(pending);
  if (!(pushHashPage() === 'push' && pushHashParams().has('push_id'))) {
    showPushManager();
  }
}

function updateHomePushPending(count) {
  const safeCount = Number.isFinite(Number(count)) ? Number(count) : 0;
  const strong = document.getElementById('home-push-pending-strong');
  const badge = document.getElementById('home-push-pending-badge');
  if (strong) strong.textContent = String(safeCount);
  if (badge) badge.textContent = `${safeCount} 条待处理`;
}

function isPushListed(card) {
  return ['accepted', 'listed', 'published'].includes(card.status);
}

function renderPushEmpty(text) {
  return `<div class="style-empty-loading"><i class="ti ti-rocket" style="font-size:20px;display:block;margin-bottom:8px;color:#ccc"></i><span>${text}</span></div>`;
}

function renderPushManageCard(card) {
  const img = card.style_image_urls?.[0] || '';
  const tags = pushDisplayTags(card);
  const time = pushCardTime(card);
  const statusText = isPushListed(card) ? '已上架' : '待上架';
  const statusClass = isPushListed(card) ? 'evergreen-badge' : 'seasonal-badge';
  const selectable = pushDeleteMode && !isPushListed(card);
  const clickAction = selectable
    ? `togglePushSelection('${card.push_id}', !selectedPushIds.has('${card.push_id}')); renderPushManager()`
    : `openPushEditor('${card.push_id}')`;
  return `
    <div class="style-item push-manage-item" onclick="${clickAction}">
      ${selectable ? `<input type="checkbox" class="style-select" ${selectedPushIds.has(card.push_id) ? 'checked' : ''} onclick="event.stopPropagation()" onchange="togglePushSelection('${card.push_id}', this.checked); updatePushDeleteUI()">` : ''}
      <div class="style-thumb" style="background:#FAEEDA;border-color:#EF9F27">
        ${img ? `<img src="${staticUrl(img)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><i class="ti ti-photo" style="color:#BA7517;display:none"></i>` : `<i class="ti ti-photo" style="color:#BA7517"></i>`}
      </div>
      <div class="style-info">
        <div class="style-name-text">${card.style_name || '未命名款式'} <span class="${statusClass}">${statusText}</span></div>
        <div class="style-tags-row push-tags-row">${tags.map(renderPushTag).join('')}</div>
        <div class="style-meta-row"><span class="lc-pill lc-${lifeCycleClass(card.life_cycle)}"><i class="ti ti-${lifeCycleIcon(card.life_cycle)}"></i>${card.life_cycle || '观察期'}</span><span class="style-date">${time}</span></div>
      </div>
      <div class="style-actions"><button class="push-edit-btn" onclick="event.stopPropagation();openPushEditor('${card.push_id}')">编辑推送</button></div>
    </div>`;
}

function pushDisplayTags(card) {
  return (card.style_tags || []).filter(Boolean).slice(0, 6);
}

function pushTagClass(idx) {
  return idx < 2 ? 'stag-craft' : idx < 4 ? 'stag-color' : 'stag-style';
}

function renderPushTag(tag, idx) {
  return `<span class="stag ${pushTagClass(idx)}">${tag}</span>`;
}

function togglePushSelection(pushId, checked) {
  if (checked) selectedPushIds.add(pushId);
  else selectedPushIds.delete(pushId);
}

function togglePushDeleteMode(force) {
  pushDeleteMode = typeof force === 'boolean' ? force : !pushDeleteMode;
  if (!pushDeleteMode) selectedPushIds.clear();
  renderPushManager();
}

function toggleSelectAllPush(checked) {
  selectedPushIds.clear();
  if (checked) {
    pushCardsData.filter(card => !isPushListed(card)).forEach(card => selectedPushIds.add(card.push_id));
  }
  renderPushManager();
}

function updatePushDeleteUI(pendingCards) {
  const pending = pendingCards || pushCardsData.filter(card => !isPushListed(card));
  const pendingIds = new Set(pending.map(card => card.push_id));
  [...selectedPushIds].forEach(pushId => {
    if (!pendingIds.has(pushId)) selectedPushIds.delete(pushId);
  });
  const bar = document.getElementById('push-delete-bar');
  const toggle = document.getElementById('push-delete-toggle');
  const selectAll = document.getElementById('push-select-all');
  if (bar) bar.style.display = pushDeleteMode ? 'flex' : 'none';
  if (toggle) toggle.innerHTML = `<i class="ti ti-trash"></i> ${pushDeleteMode ? '删除中' : '删除'}`;
  if (selectAll) {
    selectAll.checked = !!pending.length && selectedPushIds.size === pending.length;
    selectAll.indeterminate = selectedPushIds.size > 0 && selectedPushIds.size < pending.length;
  }
}

async function confirmDeleteSelectedPush() {
  const pendingIds = new Set(pushCardsData.filter(card => !isPushListed(card)).map(card => card.push_id));
  const ids = [...selectedPushIds].filter(pushId => pendingIds.has(pushId));
  if (!ids.length) { showToast('请先选择推送'); return; }
  if (!confirm(`确定删除选中的 ${ids.length} 条待上架推送？`)) return;
  try {
    for (const pushId of ids) {
      await apiPost(`/push-cards/${pushId}/audit`, {
        action: 'rejected',
        merchant_id: 'demo_shop',
      });
    }
    selectedPushIds.clear();
    pushDeleteMode = false;
    showToast('已删除所选推送');
    await loadPushData();
  } catch (e) {
    alert('删除失败：' + e.message);
  }
}

function pushCardTime(card) {
  return card.audit_details?.created_at || card.audit_details?.updated_at || '今日 09:30';
}

function renderPushEditor(card) {
  if (card?.push_id && !pushEditorViewIndexById.has(card.push_id)) {
    pushEditorViewIndexById.set(card.push_id, 0);
  }
  document.getElementById('push-hot-score').textContent = `${Math.round(card.hot_score || 0)}分`;
  document.querySelector('#push-editor .signal-time').textContent = pushCardTime(card);
  document.querySelector('#push-editor .push-style-name').textContent = card.style_name || '未命名款式';
  document.getElementById('push-tagline').textContent = card.tagline || taglines[0];
  renderPushSignals(card);
  renderPushSourceThumbs(card);
  renderPushEditorTags(card);
  renderPushEditorImages(card, currentPushViewIndex(card));
  renderPushEditorLifeCycle(card);
}

function renderPushSignals(card) {
  const box = document.querySelector('#push-editor .signal-pills');
  if (!box) return;
  const signals = Array.isArray(card.signals || card.signal_sources) ? (card.signals || card.signal_sources) : [];
  const wanted = ['搜索热度', '评价词频', '试戴收藏率'];
  const ordered = wanted
    .map(name => signals.find(item => item.signal === name))
    .filter(Boolean);
  if (!ordered.length) return;
  box.innerHTML = ordered.map(signal => {
    const isRate = signal.signal === '试戴收藏率';
    const value = isRate ? `${Math.round(Number(signal.value || 0) * 100)}%` : `${Math.round(Number(signal.value || 0))}`;
    const delta = `↑${Math.round(Number(signal.delta || 0) * 100)}%`;
    const icon = signal.signal === '搜索热度' ? 'search' : signal.signal === '评价词频' ? 'message' : 'heart';
    const detail = signal.signal === '搜索热度'
      ? `站内搜索热度<br>当前指数：${value}　较上周：+${Math.round(Number(signal.delta || 0) * 100)}%<br>权重 ${Math.round(Number(signal.weight || 0) * 100)}%`
      : signal.signal === '评价词频'
        ? `近7天评价词频<br>当前词频：${value}次　较上周：+${Math.round(Number(signal.delta || 0) * 100)}%<br>权重 ${Math.round(Number(signal.weight || 0) * 100)}%`
        : `用户试戴后收藏率<br>当前：${value}　较上周：+${Math.round(Number(signal.delta || 0) * 100)}%<br>权重 ${Math.round(Number(signal.weight || 0) * 100)}%`;
    return `<div class="signal-pill has-sig-tip" data-tip="${detail}"><i class="ti ti-${icon}"></i>${signal.signal} <span class="sig-up">${delta}</span></div>`;
  }).join('');
}

function renderPushSourceThumbs(card) {
  const box = document.querySelector('#push-editor .push-source-thumbs');
  if (!box) return;
  const posts = Array.isArray(card.source_posts) ? card.source_posts : [];
  box.style.display = 'flex';
  box.style.alignItems = 'flex-start';
  box.style.gap = '12px';
  box.style.overflowX = 'auto';
  box.style.overflowY = 'visible';
  box.style.padding = '2px 2px 12px';
  box.style.minWidth = '0';
  box.innerHTML = posts.map((post, idx) => renderPushSourceCard(post, idx)).join('');
}

function formatMetric(value) {
  const num = Number(value || 0);
  if (num >= 10000) {
    const wan = num / 10000;
    return `${Number.isInteger(wan) ? wan.toFixed(0) : wan.toFixed(1)}w`;
  }
  if (num >= 1000) {
    return `${(num / 1000).toFixed(1).replace(/\\.0$/, '')}k`;
  }
  return String(num);
}

function renderPushSourceCard(post, idx) {
  const url = post.image_url || post.image || '';
  const title = post.title || '爆款来源';
  const likes = formatMetric(post.metrics?.likes);
  const favorites = formatMetric(post.metrics?.favorites);
  const comments = formatMetric(post.metrics?.comments);
  const growth = Number(post.metrics?.growth_3d || 0);
  const status = post.status?.label || '爆款';
  const platform = post.platform || '';
  const relativeTime = post.relative_time || '';
  const link = post.url || '';
  const summary = post.summary || post.comment_summary || '';
  const popoverId = `push-source-popover-${idx}`;
  return `
    <div
      style="position:relative;flex:0 0 122px;min-width:122px;max-width:122px;font-size:0"
      onmouseenter="togglePushSourcePopover('${popoverId}', true)"
      onmouseleave="togglePushSourcePopover('${popoverId}', false)"
    >
      <a
        href="${escapeAttr(link || '#')}"
        ${link ? 'target="_blank" rel="noreferrer"' : 'onclick="event.preventDefault()"'}
        style="display:block;width:122px;text-decoration:none;color:#2b2218"
      >
        <div style="width:122px;height:92px;border-radius:12px 12px 0 0;background:#F7F6F2;border:1px solid #eadfcf;overflow:hidden">
          ${url ? `<img src="${staticUrl(url)}" alt="${escapeAttr(title)}" style="display:block;width:122px;height:92px;object-fit:cover">` : ''}
        </div>
        <div style="width:122px;padding:8px 9px 10px;background:#fff;border:1px solid #eadfcf;border-top:none;border-radius:0 0 12px 12px;box-shadow:0 8px 22px rgba(98,68,28,.06)">
          <div style="font-size:12px;line-height:1.35;font-weight:600;color:#2b2218;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden;min-height:32px;word-break:break-word">${escapeHtml(title)}</div>
          <div style="margin-top:6px;font-size:11px;color:#7b6852;white-space:nowrap">❤️ ${likes}  🔖 ${favorites}</div>
          <div style="margin-top:6px;display:inline-flex;align-items:center;gap:5px;font-size:11px;font-weight:600;color:#b42318;white-space:nowrap"><span style="width:7px;height:7px;border-radius:999px;background:#ef4444;display:inline-block;box-shadow:0 0 0 3px rgba(239,68,68,.12)"></span>${escapeHtml(status)}</div>
        </div>
      </a>
      <div id="${popoverId}" style="display:none;position:absolute;left:-6px;bottom:8px;width:248px;padding:14px 14px 12px;border-radius:14px;background:rgba(31,24,18,.96);color:#fff;box-shadow:0 20px 45px rgba(0,0,0,.24);z-index:30">
        <div style="font-size:12px;color:rgba(255,255,255,.72)">${escapeHtml(platform || '来源帖子')}${relativeTime ? ` · ${escapeHtml(relativeTime)}` : ''}</div>
        <div style="margin-top:10px;font-size:12px;color:rgba(255,255,255,.84)">点赞 ${likes}</div>
        <div style="margin-top:10px;font-size:12px;color:rgba(255,255,255,.84)">收藏 ${favorites}  ↑ 3日增速${growth}%</div>
        <div style="margin-top:10px;font-size:12px;color:rgba(255,255,255,.84)">评论 ${comments}</div>
        ${summary ? `<div style="margin-top:10px;font-size:12px;line-height:1.5;color:rgba(255,255,255,.78);display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden">${escapeHtml(summary)}</div>` : ''}
        <div style="margin-top:12px;display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:12px;color:rgba(255,255,255,.8)">
          <span style="display:inline-flex;align-items:center;gap:5px;font-weight:600;color:#ffb4a8"><span style="width:7px;height:7px;border-radius:999px;background:#ef4444;display:inline-block;box-shadow:0 0 0 3px rgba(239,68,68,.12)"></span>${escapeHtml(status)}</span>
          ${platform ? `<span>${escapeHtml(platform)}</span>` : ''}
        </div>
        ${link
          ? `<a href="${escapeAttr(link)}" target="_blank" rel="noreferrer" style="display:inline-block;margin-top:12px;font-size:12px;color:#f7d7aa;text-decoration:none;pointer-events:auto">点击跳转原帖 ↗</a>`
          : `<div style="margin-top:12px;font-size:12px;color:#f7d7aa">原帖链接待补充</div>`}
      </div>
    </div>`;
}

function togglePushSourcePopover(id, visible) {
  const popover = document.getElementById(id);
  if (!popover) return;
  popover.style.display = visible ? 'block' : 'none';
}

function renderPushEditorImages(card, activeIdx = 0) {
  const images = pushEditorImages(card);
  renderPushEditorImage(images[activeIdx] || images[0]);
  renderPushThumbs(images, activeIdx);
}

function currentPushViewIndex(card) {
  const pushId = card?.push_id || '';
  return pushEditorViewIndexById.get(pushId) || 0;
}

function selectedPushCompositeIndex(card) {
  const pushId = card?.push_id || '';
  return pushSelectedCompositeIndexById.get(pushId) ?? null;
}

function selectedPushComposite(card) {
  const idx = selectedPushCompositeIndex(card);
  if (idx == null) return null;
  const image = pushEditorImages(card)[idx];
  return image?.kind === 'composite' ? { ...image, idx } : null;
}

function pushEditorImages(card) {
  const sourceImages = card.style_image_urls || [];
  const styleImage = sourceImages[0] || '';
  const backendComposites = sourceImages.slice(1).filter(Boolean);
  const templateIds = [...selectedTemplateIds];
  const count = Math.max(backendComposites.length, templateIds.length);
  const composites = Array.from({ length: count }, (_, idx) => {
    const templateId = templateIds[idx] || '';
    return {
      label: `合成效果图 ${idx + 1}`,
      url: backendComposites[idx] || '',
      template: templateId ? findTemplateInMemory(templateId) : null,
      kind: 'composite',
    };
  });
  return [
    { label: '款式原图', url: styleImage, kind: 'style' },
    ...composites,
  ];
}

function renderPushEditorImage(image) {
  const main = document.getElementById('push-main-img');
  if (!main) return;
  main.innerHTML = image.url
    ? `<img src="${staticUrl(image.url)}" style="width:100%;height:100%;object-fit:contain;border-radius:10px">`
    : `<i class="ti ti-photo" style="font-size:38px;color:#BA7517"></i><span>${image.label}</span>`;
}

function renderPushThumbs(images, activeIdx = 0) {
  const thumbs = document.getElementById('push-thumbs');
  if (!thumbs) return;
  const selectedIdx = selectedPushCompositeIndex(activePushCard || pushCardsData[0] || {});
  thumbs.innerHTML = images.map((image, idx) => `
    <button class="push-thumb ${idx === activeIdx ? 'active' : ''}" onclick="selectPushImg(${idx})" title="${image.label}">
      ${image.url ? `<img src="${staticUrl(image.url)}" alt="${image.label}">` : image.label.replace('效果', '').replace('图 ', '')}
      ${image.kind === 'composite'
        ? `<span class="push-thumb-select ${selectedIdx === idx ? 'is-selected' : ''}" onclick="event.stopPropagation();selectPushComposite(${idx})"><i class="ti ti-${selectedIdx === idx ? 'check' : ''}"></i></span>`
        : ''}
    </button>
  `).join('');
}

function renderPushEditorTags(card) {
  const box = document.querySelector('#push-editor .push-tags');
  if (!box) return;
  box.innerHTML = pushDisplayTags(card).map(renderPushTag).join('');
}

function renderPushEditorLifeCycle(card) {
  const pill = document.querySelector('#push-editor .lc-pill');
  if (!pill) return;
  const text = card.life_cycle || '观察期';
  pill.className = `lc-pill lc-${lifeCycleClass(text)} has-tooltip`;
  pill.innerHTML = `<i class="ti ti-${lifeCycleIcon(text)}"></i>${text}<div class="lc-tooltip"><svg viewBox="0 0 180 60" class="tooltip-chart"><polyline points="5,55 20,50 35,45 50,38 65,30 80,24 95,20 110,16 125,12 140,9 155,7 170,5" fill="none" stroke="#97C459" stroke-width="2"/></svg><div class="tooltip-label">近12天热度趋势</div></div>`;
}

const taglines = ['秋冬约会必备！奶油渐变猫眼，光线下超有氛围感，显白又高级，赶紧安排～','这个秋冬就靠它了！奶油白渐变猫眼，温柔又高级～','简约不简单！奶油渐变猫眼，日常百搭还显白～'];
let taglineIdx = 0;
const coupons = {'1':{name:'全贴甲片简约款',price:'¥168',desc:'可做渐变·猫眼·晕染'},'2':{name:'半贴甲片基础款',price:'¥128',desc:'半贴为主'},'3':{name:'猫眼渐变升级款',price:'¥218',desc:'专攻猫眼渐变'}};

function selectPushImg(idx) {
  const card = activePushCard || pushCardsData[0] || {};
  if (card?.push_id) pushEditorViewIndexById.set(card.push_id, idx);
  const images = pushEditorImages(card);
  const image = images[idx] || images[0];
  document.querySelectorAll('.push-thumbs .push-thumb').forEach((thumb, thumbIdx) => thumb.classList.toggle('active', thumbIdx === idx));
  renderPushEditorImage(image);
}

function selectPushComposite(idx) {
  const card = activePushCard || pushCardsData[0];
  if (!card) return;
  const image = pushEditorImages(card)[idx];
  if (!image || image.kind !== 'composite') return;
  pushSelectedCompositeIndexById.set(card.push_id, idx);
  renderPushThumbs(pushEditorImages(card), currentPushViewIndex(card));
}

function currentPushImageIndex() {
  return currentPushViewIndex(activePushCard || pushCardsData[0] || {});
}

async function regenPushImg(btn) {
  if (!adminBackendAvailable) { showToast('后端未连接，暂不能生成'); return; }
  const card = activePushCard || pushCardsData[0];
  if (!card) return;

  const styleUrl = card.style_image_urls?.[0];
  if (!styleUrl) { showToast('缺少款式原图，暂不能生成'); return; }

  // 确保模板已加载
  if (selectedTemplateIds.size === 0) {
    try { await renderTemplates(); } catch (e) { /* ignore */ }
  }

  const images = pushEditorImages(card);
  let targetIdx = currentPushImageIndex();
  if (targetIdx === 0 && images.length > 1) targetIdx = 1;
  let target = images[targetIdx];
  let templateUrl = target?.template?.hand_image_url;

  // 当前 composite 无模板时，尝试用第一个有效的模板
  if (!templateUrl && target?.kind === 'composite' && selectedTemplateIds.size > 0) {
    for (const tid of selectedTemplateIds) {
      const tpl = findTemplateInMemory(tid);
      if (tpl?.hand_image_url) {
        templateUrl = tpl.hand_image_url;
        break;
      }
    }
  }

  if (!target || target.kind !== 'composite' || !templateUrl) {
    showToast('请先在素材管理选择模板图');
    return;
  }

  const originalText = btn.innerHTML;
  btn.disabled = true;
  btn.innerHTML = '<i class="ti ti-refresh"></i> 生成中...';
  try {
    const result = await apiPost('/generate-composite', {
      style_image_url: styleUrl,
      template_image_url: templateUrl,
    });
    if (result?.composite_image_url) {
      card.style_image_urls ||= [];
      card.style_image_urls[targetIdx] = result.composite_image_url;
      renderPushEditorImages(card, targetIdx);
      showToast('合成图已生成');
    }
  } catch (e) {
    console.warn('[合成图] 重新生成失败:', e.message);
    alert('生成失败：' + e.message);
  } finally {
    btn.disabled = false;
    btn.innerHTML = originalText;
  }
}
async function regenTagline() {
  const l = document.getElementById('tagline-regen-label');
  l.textContent = '生成中...';
  
  if (adminBackendAvailable && pushCardsData.length > 0) {
    try {
      const card = activePushCard || pushCardsData[0];
      const result = await apiPost('/report', {
        merchant_id: 'demo_shop',
        period: 'this_week',
        hot_styles: [{ name: card.style_name, life_cycle: card.life_cycle, score: card.hot_score }],
      });
      if (result && result.report_summary) {
        // 从报告摘要中提取第一句作为推荐语
        const firstLine = result.report_summary.split('\n').find(s => s.trim()) || taglines[0];
        document.getElementById('push-tagline').textContent = firstLine.slice(0, 50);
        l.textContent = '重新生成推荐语';
        return;
      }
    } catch (e) {
      console.warn('[推荐语] LLM 生成失败:', e.message);
    }
  }
  
  // fallback: 本地轮换
  setTimeout(() => {
    taglineIdx = (taglineIdx + 1) % taglines.length;
    document.getElementById('push-tagline').textContent = taglines[taglineIdx];
    l.textContent = '重新生成推荐语';
  }, 900);
}
function updateCoupon() { const v=document.getElementById('coupon-select').value; const c=coupons[v]; document.getElementById('coupon-name').textContent=c.name; document.getElementById('coupon-price').textContent=c.price; }

function selectedCouponPrice() {
  const coupon = coupons[document.getElementById('coupon-select')?.value || '1'] || coupons['1'];
  return Number(String(coupon.price).replace(/[^\d.]/g, '')) || 0;
}

function goConfirm() { 
  const card = activePushCard || pushCardsData[0];
  if (!card) return;
  const selectedImage = selectedPushComposite(card);
  if (!selectedImage?.url) {
    alert('请选择一张合成效果图作为推送主图');
    return;
  }
  document.getElementById('confirm-price').textContent = selectedCouponPrice();
  const confirmMain = document.getElementById('confirm-main-img');
  const confirmStyleName = document.getElementById('confirm-style-name');
  const confirmSummaryStyleName = document.getElementById('confirm-summary-style-name');
  const confirmSummaryImageLabel = document.getElementById('confirm-summary-image-label');
  const confirmTagline = document.getElementById('confirm-tagline');
  const confirmTags = document.getElementById('confirm-style-tags');
  if (confirmMain) confirmMain.innerHTML = `<img src="${staticUrl(selectedImage.url)}" style="width:100%;height:100%;object-fit:contain;border-radius:10px">`;
  if (confirmStyleName) confirmStyleName.textContent = card.style_name || '未命名款式';
  if (confirmSummaryStyleName) confirmSummaryStyleName.textContent = card.style_name || '未命名款式';
  if (confirmSummaryImageLabel) confirmSummaryImageLabel.textContent = selectedImage.label;
  if (confirmTagline) confirmTagline.textContent = document.getElementById('push-tagline').textContent.trim();
  if (confirmTags) confirmTags.innerHTML = pushDisplayTags(card).map(renderPushTag).join('');
  switchPage('confirm'); 
}

async function confirmPublish() {
  if (adminBackendAvailable && (activePushCard || pushCardsData.length > 0)) {
    try {
      const card = activePushCard || pushCardsData[0];
      const selectedCouponId = document.getElementById('coupon-select').value;
      const selectedCoupon = coupons[selectedCouponId];
      const selectedImage = selectedPushComposite(card);
      const result = await apiPost(`/push-cards/${card.push_id}/audit`, {
        action: 'accepted',
        merchant_id: 'demo_shop',
        selected_image_url: selectedImage?.url || null,
        selected_coupon_url: card.coupon_url || selectedCoupon?.name || null,
        final_tagline: document.getElementById('push-tagline').textContent.trim(),
        final_price: selectedCouponPrice(),
      });
      console.log('[上架] 审核通过');
      if (result && result.message) showToast(result.message);
    } catch (e) {
      console.warn('[上架] API 调用失败:', e.message);
    }
  }
  
  document.querySelector('#panel-confirm .confirm-grid').style.display = 'none';
  document.querySelector('#panel-confirm .page-top').style.display = 'none';
  document.getElementById('success-page').style.display = 'flex';
}

// ===== 复盘报告（联调 /api/report） =====
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

async function loadReportData(period) {
  if (!adminBackendAvailable) return;
  const periodMap = { week: 'this_week', month: 'this_month', day: 'today' };
  try {
    const result = await apiPost('/report', {
      period: periodMap[period] || 'this_week',
      merchant_id: 'demo_shop',
      merchant_prefs: getMerchantPrefs(),
    });
    if (result) {
      console.log('[报告] 加载成功:', result);
      renderApiReportData(result, period);
    }
  } catch (e) {
    console.warn('[报告] 加载失败:', e.message);
  }
}

let currentReportSuggestions = [];

function reportBoostTargetStyle() {
  const pendingStyleIds = new Set(
    pushCardsData.filter(card => !isPushListed(card)).map(card => card.style_id),
  );
  return (
    stylesData.find(style => style.status !== 'draft' && !pendingStyleIds.has(style.style_id))
    || stylesData.find(style => style.status !== 'draft')
    || null
  );
}

function reportPendingPublishCard() {
  return pushCardsData.find(card => !isPushListed(card)) || null;
}

function reportTakeDownTargetCard() {
  return pushCardsData.find(card => isPushListed(card)) || null;
}

function normalizeReportSuggestions(suggestions) {
  const boostStyle = reportBoostTargetStyle();
  const pendingPush = reportPendingPublishCard();
  const takeDownCard = reportTakeDownTargetCard();
  const boostStyleName = boostStyle?.name || '当前主推款式';
  const boostStyleId = boostStyle?.style_id || '';
  const takeDownStyleName = takeDownCard?.style_name || '当前已上架款式';
  const takeDownStyleId = takeDownCard?.style_id || '';
  const takeDownPushId = takeDownCard?.push_id || '';
  const publishStyleName = pendingPush?.style_name || '待上架新款式';
  const publishStyleId = pendingPush?.style_id || '';
  const publishPushId = pendingPush?.push_id || '';
  const source = Array.isArray(suggestions) ? suggestions : [];
  return [
    {
      ...(source[0] || {}),
      text: `${boostStyleName}热度较高，建议增加投流预算 20%。`,
      action_type: 'boost_budget',
      action_params: {
        style_id: boostStyleId,
        style_name: boostStyleName,
        budget_from: DEMO_BASE_BOOST_BUDGET,
        budget_to: 600,
        budget_delta: 0.2,
      },
      requires_confirm: true,
    },
    {
      ...(source[1] || {}),
      text: `${takeDownStyleName}最近热度下降明显，建议下架该款式并及时替换。`,
      action_type: 'take_down_style',
      action_params: {
        push_id: takeDownPushId,
        style_id: takeDownStyleId,
        style_name: takeDownStyleName,
      },
      requires_confirm: false,
    },
    {
      ...(source[2] || {}),
      text: `${publishStyleName}热度较高，建议上架新款式并加入当前主推。`,
      action_type: 'publish_style',
      action_params: {
        push_id: publishPushId,
        style_id: publishStyleId,
        style_name: publishStyleName,
      },
      requires_confirm: false,
    },
  ];
}

function renderApiReportData(result, period) {
  if (result.period_label) {
    document.getElementById('report-title').textContent = result.period_label;
  }
  if (Array.isArray(result.metrics) && result.metrics.length > 0) {
    document.getElementById('report-metrics').innerHTML = result.metrics.map(m => `
      <div class="metric-card">
        <div class="metric-label">${m.label}</div>
        <div class="metric-val">${m.value}</div>
        <div class="metric-delta delta-${m.delta_direction || 'flat'}"><i class="ti ti-${metricIcon(m.delta_direction)}"></i>${m.delta || '— 持平'}</div>
      </div>
    `).join('');
  }
  if (Array.isArray(result.hot_styles) && result.hot_styles.length > 0) {
    const hotList = document.querySelector('#panel-report .hot-list');
    if (hotList) {
      hotList.innerHTML = result.hot_styles.map(item => `
        <div class="hot-item">
          <div class="hot-thumb" style="background:#FAEEDA;border-color:#EF9F27"><i class="ti ti-photo" style="color:#BA7517"></i></div>
          <div class="hot-info">
            <div class="hot-name">${item.style_name}</div>
            <div class="hot-detail">评分 ${Math.round(item.hot_score)} · 收藏率 ${(Number(item.favorite_rate || 0) * 100).toFixed(0)}% · 试戴 ${item.try_on_count || 0} 次</div>
          </div>
          <div class="lc-pill ${hotLifeCycleClass(item.life_cycle)}"><i class="ti ti-${hotLifeCycleIcon(item.life_cycle)}"></i>${item.life_cycle}</div>
        </div>
      `).join('');
    }
  }
  if (Array.isArray(result.suggestions) && result.suggestions.length > 0) {
    currentReportSuggestions = normalizeReportSuggestions(result.suggestions);
    const list = document.querySelector('#panel-report .suggestion-list');
    if (list) {
      list.innerHTML = currentReportSuggestions.map((item, idx) => `
        <div class="suggestion-item ${suggestionClass(item.action_type)}" id="sug-${idx}">
          <div class="sug-icon">${suggestionIcon(item.action_type)}</div>
          <div class="sug-body">
            <div class="sug-tag">${suggestionLabel(item.action_type)}</div>
            <div class="sug-text">${item.text}</div>
            <div class="sug-actions" id="sug-actions-${idx}">
              ${renderSuggestionActions(item, idx)}
            </div>
          </div>
        </div>
      `).join('');
    }
  } else {
    currentReportSuggestions = [];
  }
  if (result.report_summary) {
    document.getElementById('report-sub').textContent = result.report_summary;
  } else {
    const data = reportData[period] || reportData.week;
    document.getElementById('report-sub').textContent = data.sub;
  }
}

function hotLifeCycleClass(lifeCycle) {
  if (lifeCycle === '上升期') return 'lc-up';
  if (lifeCycle === '峰值期') return 'lc-peak';
  if (lifeCycle === '衰退期') return 'lc-down';
  return 'lc-up';
}

function hotLifeCycleIcon(lifeCycle) {
  if (lifeCycle === '上升期') return 'trending-up';
  if (lifeCycle === '峰值期') return 'flame';
  if (lifeCycle === '衰退期') return 'trending-down';
  return 'minus';
}

function metricIcon(direction) {
  if (direction === 'up') return 'trending-up';
  if (direction === 'down') return 'trending-down';
  return 'minus';
}

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
  
  loadReportData(period);
}

// Skills执行层（联调 /api/skills/execute）
const skillUiByAction = {
  boost_budget: { label:'加大投流预算', requiresConfirm:true, confirmMsg:'确认提高该款式投流预算？', execMsg:'已临时将投流预算提高到 ¥600/天' },
  prepare_replacement: { label:'准备替换款', requiresConfirm:false, execMsg:'已标记为待替换款' },
  maintain_strategy: { label:'维持当前策略', requiresConfirm:false, execMsg:'已记录：当前策略维持不变' },
  take_down_style: { label:'下架当前款式', requiresConfirm:false, execMsg:'已临时下架该款式' },
  publish_style: { label:'建议上架新款式', requiresConfirm:false, execMsg:'已临时上架新款式' },
  pause_budget: { label:'收缩预算', requiresConfirm:false, execMsg:'已记录预算收缩建议' }
};
const fallbackSuggestionActions = ['boost_budget', 'take_down_style', 'publish_style'];

function suggestionLabel(action) { return (skillUiByAction[action] || {}).label || '运营建议'; }
function suggestionIcon(action) {
  const mapping = { boost_budget:'📈', prepare_replacement:'⏰', maintain_strategy:'✅', take_down_style:'🔄', publish_style:'🚀', pause_budget:'🛑' };
  return mapping[action] || '💡';
}
function suggestionClass(action) {
  const mapping = { boost_budget:'sug-boost', prepare_replacement:'sug-warn', maintain_strategy:'sug-maintain', take_down_style:'sug-takedown', publish_style:'sug-publish', pause_budget:'sug-warn' };
  return mapping[action] || 'sug-maintain';
}

function suggestionStateKey(item, idx) {
  const action = item?.action_type || `idx-${idx}`;
  const pushId = item?.action_params?.push_id || '';
  const styleId = item?.action_params?.style_id || '';
  return `${action}:${pushId}:${styleId}`;
}

function renderSuggestionActions(item, idx) {
  if (runtimeDemoState.adoptedSuggestions.has(suggestionStateKey(item, idx))) {
    return `<div class="adopted-label"><i class="ti ti-circle-check" style="color:#375623"></i> 已采纳 · ${suggestionLabel(item.action_type)}</div><button class="btn-undo" onclick="undoSug(${idx})">撤销</button>`;
  }
  return `<button class="btn-adopt" onclick="adoptSug(${idx})">采纳建议</button><button class="btn-ignore" onclick="ignoreSug(${idx})">忽略</button>`;
}

function adoptSug(idx) {
  const backendSkill = currentReportSuggestions[idx];
  const baseSkill = backendSkill ? {
    action: backendSkill.action_type,
    requiresConfirm: !!backendSkill.requires_confirm,
    execMsg: (skillUiByAction[backendSkill.action_type] || {}).execMsg,
    confirmMsg: (skillUiByAction[backendSkill.action_type] || {}).confirmMsg,
    action_params: backendSkill.action_params || {},
    label: suggestionLabel(backendSkill.action_type),
  } : null;
  const fallbackAction = fallbackSuggestionActions[idx];
  const fallbackSkill = fallbackAction ? {
    action: fallbackAction,
    requiresConfirm: !!(skillUiByAction[fallbackAction] || {}).requiresConfirm,
    execMsg: (skillUiByAction[fallbackAction] || {}).execMsg,
    confirmMsg: (skillUiByAction[fallbackAction] || {}).confirmMsg,
    action_params: {},
    label: suggestionLabel(fallbackAction),
  } : null;
  const skill = baseSkill || fallbackSkill;
  if (!skill) return;
  if (skill.requiresConfirm) {
    if (confirm(skill.confirmMsg)) {
      executeSkill(idx, skill);
    }
  } else {
    executeSkill(idx, skill);
  }
}

async function executeSkill(idx, skill) {
  const item = document.getElementById('sug-'+idx);
  const actions = document.getElementById('sug-actions-'+idx);
  applyRuntimeSkillEffect(skill);
  runtimeDemoState.adoptedSuggestions.set(suggestionStateKey(currentReportSuggestions[idx], idx), skill);
  if (actions) actions.innerHTML = renderSuggestionActions(currentReportSuggestions[idx], idx);
  if (item) item.classList.add('adopted');
  showToast(skill.execMsg || '操作已执行');
}

function undoSug(idx) {
  const adoptedSkill = runtimeDemoState.adoptedSuggestions.get(suggestionStateKey(currentReportSuggestions[idx], idx));
  if (adoptedSkill) revertRuntimeSkillEffect(adoptedSkill);
  runtimeDemoState.adoptedSuggestions.delete(suggestionStateKey(currentReportSuggestions[idx], idx));
  const item = document.getElementById('sug-'+idx);
  const actions = document.getElementById('sug-actions-'+idx);
  if (item) item.classList.remove('adopted');
  if (actions) actions.innerHTML = renderSuggestionActions(currentReportSuggestions[idx], idx);
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

function showTopSuccessBanner(msg) {
  let banner = document.getElementById('global-success-banner');
  if (!banner) {
    banner = document.createElement('div');
    banner.id = 'global-success-banner';
    banner.className = 'global-success-banner';
    document.body.appendChild(banner);
  }
  banner.innerHTML = `<i class="ti ti-circle-check"></i><span>${escapeHtml(msg)}</span>`;
  banner.classList.add('show');
  clearTimeout(banner._hideTimer);
  banner._hideTimer = setTimeout(() => banner.classList.remove('show'), 5200);
}

function renderNotifyBell() {
  const dot = document.getElementById('notify-bell-dot');
  if (!dot) return;
  dot.classList.toggle('hidden', runtimeDemoState.unreadNotifyIds.size === 0);
}

function renderNotifyList() {
  const list = document.getElementById('notify-list');
  if (!list) return;
  list.innerHTML = notifyItems.map(item => {
    const unread = runtimeDemoState.unreadNotifyIds.has(item.id);
    return `
      <div class="notify-item ${unread ? 'notify-unread' : ''}">
        <div class="notify-icon" style="background:${item.iconBg}"><i class="ti ti-${item.icon}" style="color:${item.iconColor}"></i></div>
        <div class="notify-body">
          <div class="notify-title">${item.title}</div>
          <div class="notify-text">${item.text}</div>
          <div class="notify-time">${item.time}</div>
        </div>
        <div class="notify-actions">
          <button class="notify-toggle-btn" onclick="setNotifyReadState('${item.id}', true)">已读</button>
          <button class="notify-toggle-btn" onclick="setNotifyReadState('${item.id}', false)">未读</button>
        </div>
      </div>
    `;
  }).join('');
  renderNotifyBell();
}

function setNotifyReadState(notifyId, read) {
  if (read) runtimeDemoState.unreadNotifyIds.delete(notifyId);
  else runtimeDemoState.unreadNotifyIds.add(notifyId);
  renderNotifyList();
}

// ===== 偏好配置（持久化到 localStorage） =====
function showPrefModal() {
  // 从 localStorage 恢复偏好到 UI
  const prefs = getMerchantPrefs();
  const craftCheckboxes = document.querySelectorAll('#pref-crafts input[type=checkbox]');
  craftCheckboxes.forEach(cb => { cb.checked = prefs.excluded_crafts.includes(cb.value); });
  const focusSelect = document.getElementById('pref-focus');
  if (focusSelect) focusSelect.value = prefs.focus;
  const priceSelect = document.getElementById('pref-price');
  if (priceSelect) priceSelect.value = prefs.price_tier;
  document.getElementById('pref-modal').classList.add('show');
}
function hidePrefModal() { document.getElementById('pref-modal').classList.remove('show'); }

function savePrefAndClose() {
  const craftCheckboxes = document.querySelectorAll('#pref-crafts input[type=checkbox]');
  const excludedCrafts = [...craftCheckboxes].filter(cb => cb.checked).map(cb => cb.value);
  const focus = document.getElementById('pref-focus').value;
  const priceTier = document.getElementById('pref-price').value;
  const prefs = { excluded_crafts: excludedCrafts, focus: focus, price_tier: priceTier };
  localStorage.setItem('merchant_prefs', JSON.stringify(prefs));
  // 更新报告页偏好标签展示
  const prefTagsEl = document.querySelector('.pref-tags');
  if (prefTagsEl) {
    const focusLabel = { repurchase: '偏重复购客', new_customer: '偏重新客', balanced: '均衡' }[focus] || focus;
    const priceLabel = { low: '低客单价', mid: '中高客单价', high: '高客单价' }[priceTier] || priceTier;
    const craftLabel = excludedCrafts.length > 0 ? '不做' + excludedCrafts.join('/') : '无工艺限制';
    prefTagsEl.innerHTML = `<span>${focusLabel}</span><span>${craftLabel}</span><span>${priceLabel}</span>`;
  }
  showToast('偏好已保存');
  hidePrefModal();
}

function getMerchantPrefs() {
  try {
    const saved = localStorage.getItem('merchant_prefs');
    if (saved) return JSON.parse(saved);
  } catch (e) {}
  return { excluded_crafts: ['手绘'], focus: 'repurchase', price_tier: 'mid' };
}

function renderBoostBudgetState() {
  const budget = runtimeDemoState.boostBudget ?? DEMO_BASE_BOOST_BUDGET;
  const input = document.getElementById('budget-input');
  const stat = document.getElementById('boost-budget-stat');
  if (input) input.value = String(budget);
  if (stat) stat.textContent = `¥${budget}/天`;
}

function applyRuntimePushCardOverrides(cards) {
  return (cards || [])
    .filter(card => !runtimeDemoState.removedPushIds.has(card.push_id) && !(card.style_id && runtimeDemoState.removedStyleIds.has(card.style_id)))
    .map(card => {
      const demoOverride = demoPushCardOverrides[card.push_id] || {};
      const baseCard = { ...card, ...demoOverride };
      if (!runtimeDemoState.publishedPushIds.has(card.push_id)) return baseCard;
      return { ...baseCard, status: 'published' };
    });
}

function pushCardToRuntimeStyleItem(card) {
  return {
    style_id: card.style_id,
    name: card.style_name || '未命名款式',
    tags: pushDisplayTags(card).slice(0, 4),
    lc: lifeCycleClass(card.life_cycle),
    lcText: card.life_cycle || '观察期',
    date: '刚刚上架',
    bg: '#FAEEDA',
    bc: '#EF9F27',
    ic: '#BA7517',
    seasonal: false,
    image_url: card.style_image_urls?.[0] || '',
    tryon_enabled: true,
    status: 'active',
    review_status: 'published',
    source: 'runtime_publish',
    __runtimePublished: true,
  };
}

function applyRuntimeStyleOverrides(baseStyles) {
  const items = [...(baseStyles || [])].filter(item => !runtimeDemoState.removedStyleIds.has(item.style_id));
  if (activeStyleStatus !== 'active') return items;
  const seen = new Set(items.map(item => item.style_id));
  [...runtimeDemoState.publishedStyles.values()].reverse().forEach(item => {
    if (!seen.has(item.style_id)) {
      items.unshift({ ...item });
      seen.add(item.style_id);
    }
  });
  return items;
}

function syncRuntimeStyleState() {
  stylesData = applyRuntimeStyleOverrides(stylesData.filter(item => !item.__runtimePublished));
  if (document.getElementById('panel-assets')?.classList.contains('active')) {
    renderStyleList();
  }
}

function syncRuntimePushState() {
  pushCardsData = applyRuntimePushCardOverrides(pushCardsData);
  updateHomePushPending(pushCardsData.filter(card => !isPushListed(card)).length);
  if (document.getElementById('panel-push')?.classList.contains('active')) {
    renderPushManager();
  }
}

function applyRuntimeSkillEffect(skill) {
  if (skill.action === 'boost_budget') {
    runtimeDemoState.boostBudget = Number(skill.action_params?.budget_to) || 600;
    renderBoostBudgetState();
    return;
  }
  if (skill.action === 'take_down_style') {
    const pushId = skill.action_params?.push_id || '';
    const styleId = skill.action_params?.style_id || '';
    if (pushId) runtimeDemoState.removedPushIds.add(pushId);
    if (styleId) runtimeDemoState.removedStyleIds.add(styleId);
    syncRuntimePushState();
    syncRuntimeStyleState();
    return;
  }
  if (skill.action === 'publish_style') {
    const pushId = skill.action_params?.push_id || '';
    const pushCard = pushCardsData.find(card => card.push_id === pushId);
    if (pushId) runtimeDemoState.publishedPushIds.add(pushId);
    if (pushCard) {
      runtimeDemoState.publishedStyles.set(pushCard.style_id, pushCardToRuntimeStyleItem(pushCard));
    } else if (skill.action_params?.style_id) {
      runtimeDemoState.publishedStyles.set(skill.action_params.style_id, {
        style_id: skill.action_params.style_id,
        name: skill.action_params.style_name || '未命名款式',
        tags: [],
        lc: 'up',
        lcText: '上升期',
        date: '刚刚上架',
        bg: '#FAEEDA',
        bc: '#EF9F27',
        ic: '#BA7517',
        seasonal: false,
        image_url: '',
        tryon_enabled: true,
        status: 'active',
        review_status: 'published',
        source: 'runtime_publish',
        __runtimePublished: true,
      });
    }
    syncRuntimePushState();
    syncRuntimeStyleState();
  }
}

function revertRuntimeSkillEffect(skill) {
  if (skill.action === 'boost_budget') {
    runtimeDemoState.boostBudget = null;
    renderBoostBudgetState();
    return;
  }
  if (skill.action === 'take_down_style') {
    const pushId = skill.action_params?.push_id || '';
    const styleId = skill.action_params?.style_id || '';
    if (pushId) runtimeDemoState.removedPushIds.delete(pushId);
    if (styleId) runtimeDemoState.removedStyleIds.delete(styleId);
    syncRuntimePushState();
    syncRuntimeStyleState();
    return;
  }
  if (skill.action === 'publish_style') {
    const pushId = skill.action_params?.push_id || '';
    const styleId = skill.action_params?.style_id || '';
    if (pushId) runtimeDemoState.publishedPushIds.delete(pushId);
    if (styleId) runtimeDemoState.publishedStyles.delete(styleId);
    syncRuntimePushState();
    syncRuntimeStyleState();
  }
}

// ===== 投流管理 =====
async function genBoostPost() {
  if (!adminBackendAvailable) {
    alert('AI正在生成投流帖子...\n\n生成内容预览：\n\n标题：秋冬必做！奶油渐变猫眼超显白\n正文：光线下自带氛围感的猫眼甲，奶油白渐变到玫瑰金...\n话题：#秋冬美甲 #猫眼甲 #显白美甲\n关键词：猫眼渐变、显白、秋冬');
    return;
  }
  showToast('AI 生成中...');
  try {
    const result = await apiPost('/report', {
      merchant_id: 'demo_shop',
      period: 'this_week',
      hot_styles: [{ name: '奶油渐变猫眼', life_cycle: '上升期', score: 89 }],
    });
    const summary = result.report_summary || '';
    const lines = summary.split('\n').filter(l => l.trim());
    const title = lines[0] || '秋冬必做！奶油渐变猫眼超显白';
    const body = lines.slice(1, 3).join('\n') || '光线下自带氛围感的猫眼甲，奶油白渐变到玫瑰金...';
    alert(`AI 生成投流帖子：\n\n标题：${title.slice(0,30)}\n\n正文：${body.slice(0,100)}\n\n话题：#秋冬美甲 #猫眼甲 #显白美甲\n关键词：猫眼渐变、显白、秋冬`);
  } catch (e) {
    console.warn('[投流] 生成失败:', e.message);
    alert('生成失败，请重试');
  }
}

function toggleBoostDetail(el) {
  const detail = el.nextElementSibling;
  if (detail) detail.classList.toggle('show');
}

function uploadOwnImage() {
  if (adminBackendAvailable) {
    const fileInput = document.createElement('input');
    fileInput.type = 'file';
    fileInput.accept = 'image/*';
    fileInput.onchange = async (e) => {
      const file = e.target.files[0];
      if (!file) return;
      try {
        const result = await apiUpload('/upload-image', file);
        showToast('图片上传成功！');
        console.log('[上传] 自有图片上传成功:', result);
      } catch (err) {
        alert('上传失败：' + err.message);
      }
    };
    fileInput.click();
  } else {
    alert('打开图片选择器…\n\n（Demo模拟：商户可上传自己拍摄的款式图替换AI合成图）');
  }
}

// ===== Lightbox 大图查看 (F5) =====
function openLightbox(imageUrl) {
  const overlay = document.createElement('div');
  overlay.className = 'modal-overlay show';
  overlay.id = 'lightbox-overlay';
  overlay.onclick = (e) => { if (e.target === overlay) overlay.remove(); };
  overlay.innerHTML = `<div style="max-width:90vw;max-height:90vh;position:relative">
    <img src="${imageUrl}" style="max-width:100%;max-height:85vh;border-radius:12px;box-shadow:0 8px 40px rgba(0,0,0,.3)">
    <div style="position:absolute;top:-12px;right:-12px;width:32px;height:32px;background:#fff;border-radius:50%;display:flex;align-items:center;justify-content:center;cursor:pointer;box-shadow:0 2px 8px rgba(0,0,0,.15)" onclick="document.getElementById('lightbox-overlay').remove()"><i class="ti ti-x" style="font-size:16px"></i></div>
  </div>`;
  document.body.appendChild(overlay);

  const onKey = (e) => {
    if (e.key === 'Escape') {
      overlay.remove();
      document.removeEventListener('keydown', onKey);
    }
  };
  document.addEventListener('keydown', onKey);
  overlay._onKey = onKey;
}

// ===== 初始化 =====
function init() {
  applyPlatformChrome();
  renderStyleList();
  updateStyleDeleteUI();
  renderTemplates();
  restoreTrendSourceConfig();
  renderBoostBudgetState();
  renderNotifyList();
  const currentPage = pageFromHash();
  switchPage(currentPage, { updateHash: false });
  initAdminBackend().then(() => {
    if (adminBackendAvailable) {
      loadStylesData();
      loadPushData();
      renderTemplates();
      if (currentPage === 'trend-agent') {
        loadTrendRunsAndList();
      }
      if (currentPage === 'report') {
        loadReportData('week');
      }
      if (currentPage === 'dashboard') {
        loadDashboardData();
      }
      if (pageFromHash() === 'upload' && currentUploadStyleId) {
        restoreUploadDraft(currentUploadStyleId);
      }
    }
  });
}
init();
