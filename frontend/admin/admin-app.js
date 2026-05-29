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
  // 页面加载时从后端拉取数据
  if (page === 'dashboard') loadDashboardData();
  if (page === 'push') loadPushData();
  if (page === 'report') loadReportData('week');
}

// ===== 后端状态 =====
let adminBackendAvailable = false;

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
let stylesData = [
  { name: '奶油渐变猫眼', tags: ['猫眼','渐变','奶油白','玫瑰金'], lc: 'up', lcText: '上升期', date: '2024-11-28', bg: '#FAEEDA', bc: '#EF9F27', ic: '#BA7517', seasonal: false, image_url: 'http://p1.meituan.net/pilotimages/69614397f0ecb559b98cb46a5a46f3b32642714.png' },
  { name: '圣诞红绿镜面', tags: ['镜面','红色','绿色','圣诞'], lc: 'peak', lcText: '峰值期', date: '2024-11-25', bg: '#E1F5EE', bc: '#5DCAA5', ic: '#0F6E56', seasonal: true, image_url: 'http://p0.meituan.net/pilotimages/bc153edf655dd6961dc9f8e95ad8cd1e2561531.png' },
  { name: '法式简约纯色', tags: ['法式','简约','裸色'], lc: 'down', lcText: '衰退期', date: '2024-11-20', bg: '#EEEDFE', bc: '#AFA9EC', ic: '#534AB7', seasonal: false, image_url: 'http://p0.meituan.net/pilotimages/1248ad42d355b98257e5fbcdf90efc552138079.png' },
  { name: '暗红晕染手绘', tags: ['晕染','手绘','暗红'], lc: 'none', lcText: '未关联', date: '2024-11-18', bg: '#FCE4D6', bc: '#F0997B', ic: '#993C1D', seasonal: false, image_url: 'http://p0.meituan.net/pilotimages/137aad1f6a36655ae395cf7dc57604642782680.png' }
];

async function loadStylesData() {
  if (!adminBackendAvailable) return;
  try {
    const data = await apiGet('/db/styles');
    if (data && data.styles && data.styles.length > 0) {
      stylesData = data.styles.map(s => ({
        style_id: s.style_id || s.id,
        name: s.style_name || s.name || '',
        tags: Object.values(s.tags || {}).flat().filter(Boolean).slice(0, 4),
        lc: s.life_cycle === '上升期' ? 'up' : s.life_cycle === '峰值期' ? 'peak' : s.life_cycle === '衰退期' ? 'down' : '',
        lcText: s.life_cycle || '',
        date: s.created_at || '',
        bg: '#FAEEDA',
        bc: '#EF9F27',
        ic: '#BA7517',
        seasonal: false,
        image_url: s.enhanced_style_image_url || '',
        tryon_enabled: s.tryon_enabled !== false,
      }));
      renderStyleList();
    }
  } catch (e) {
    console.warn('[素材] 加载款式失败:', e.message);
  }
}

function renderStyleList() {
  const list = document.getElementById('style-list');
  if (!list) return;
  list.innerHTML = stylesData.map((s, i) => `
    <div class="style-item" id="style-${i}">
      <div class="style-thumb" style="background:${s.bg};border-color:${s.bc};cursor:pointer" onclick="event.stopPropagation();${s.image_url ? `openLightbox('${s.image_url}')` : ''}">
        ${s.image_url ? `<img src="${staticUrl(s.image_url)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px" onerror="this.style.display='none';this.nextElementSibling.style.display='block'"><i class="ti ti-photo" style="color:${s.ic};display:none"></i>` : `<i class="ti ti-photo" style="color:${s.ic}"></i>`}
      </div>
      <div class="style-info">
        <div class="style-name-text">${s.name} ${s.seasonal ? '<span class="seasonal-badge">节日限定</span>' : '<span class="evergreen-badge">常青款</span>'}</div>
        <div class="style-tags-row">${s.tags.slice(0,3).map(t=>`<span class="stag stag-craft">${t}</span>`).join('')}</div>
        <div class="style-meta-row">${s.lcText ? `<span class="lc-pill lc-${s.lc}"><i class="ti ti-${s.lc==='up'?'trending-up':s.lc==='peak'?'flame':s.lc==='down'?'trending-down':'minus'}"></i>${s.lcText}</span>` : ''}<span class="style-date">${s.date}</span></div>
      </div>
      <div class="style-actions">
        <label style="display:flex;align-items:center;gap:4px;font-size:11px;color:${s.tryon_enabled?'#375623':'#aaa'};cursor:pointer" title="AI试戴开关">
          <input type="checkbox" ${s.tryon_enabled?'checked':''} onchange="toggleTryon('${s.style_id}',this.checked)" style="accent-color:#FFCD00">试戴
        </label>
        <div class="btn-icon danger" onclick="deleteStyleFromBackend('${s.style_id}',${i})"><i class="ti ti-trash"></i></div>
      </div>
    </div>`).join('');
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

const templates = [{ label:'自然肤色',selected:true },{ label:'白皙肤色',selected:true },{ label:'暖肤色',selected:true },{ label:'冷白肤色',selected:false },{ label:'店铺自有',selected:false }];
let backendTemplates = [];

async function renderTemplates() {
  const grid = document.getElementById('template-grid');
  if (!grid) return;
  
  if (adminBackendAvailable) {
    try {
      const data = await apiGet('/templates');
      if (Array.isArray(data) && data.length > 0) {
        backendTemplates = data;
        grid.innerHTML = data.map((t, i) => `<div class="tpl-item selected" onclick="this.classList.toggle('selected')"><div class="tpl-check">✓</div><img src="${t.hand_image_url}" style="width:100%;height:60%;object-fit:cover;border-radius:8px 8px 0 0" onerror="this.outerHTML='<i class=\\'ti ti-hand-finger\\'></i>'"><span style="font-size:10px;margin-top:2px">${t.label || t.source || '模板'}</span></div>`).join('');
        updateTplCount();
        return;
      }
    } catch (e) {}
  }
  
  grid.innerHTML = templates.map((t,i) => `<div class="tpl-item ${t.selected?'selected':''}" onclick="toggleTemplate(${i})"><div class="tpl-check">✓</div><i class="ti ti-hand-finger"></i><span>${t.label}</span></div>`).join('');
  updateTplCount();
}
function toggleTemplate(idx) { templates[idx].selected = !templates[idx].selected; renderTemplates(); }
function updateTplCount() { const n = document.querySelectorAll('.tpl-item.selected').length; const el = document.getElementById('tpl-count'); if(el) el.textContent = '已选 '+n+' 张'; }
function toggleTplDropdown(e) { e.stopPropagation(); document.getElementById('tpl-add-dropdown').classList.toggle('show'); }

async function handleTplUpload() {
  document.getElementById('tpl-add-dropdown').classList.remove('show');
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
  } else {
    templates.push({label:'自定义'+(templates.length+1),selected:true});
    renderTemplates();
  }
}

async function handleTplPublic() {
  document.getElementById('tpl-add-dropdown').classList.remove('show');
  if (adminBackendAvailable) {
    try {
      const publicTpls = await apiGet('/templates/public');
      const modal = document.createElement('div');
      modal.className = 'modal-overlay show';
      modal.id = 'public-tpl-modal';
      modal.innerHTML = `<div class="modal-content" style="max-width:500px;text-align:left">
        <h3 style="margin-bottom:12px"><i class="ti ti-layout-grid" style="color:#CC9900"></i> 公共模板库</h3>
        <p style="font-size:12px;color:#888;margin-bottom:12px">选择模板后加入已选列表</p>
        <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:16px">
          ${publicTpls.map(t => `<div class="tpl-item" style="aspect-ratio:1;cursor:pointer" onclick="selectPublicTpl('${t.hand_image_url}','${t.label}');this.classList.add('selected')"><div class="tpl-check">✓</div><img src="${t.hand_image_url}" style="width:100%;height:70%;object-fit:cover;border-radius:8px 8px 0 0" onerror="this.outerHTML='<i class=\\'ti ti-hand-finger\\'></i>'"><span style="font-size:9px">${t.label}</span></div>`).join('')}
        </div>
        <button class="btn-ghost" onclick="document.getElementById('public-tpl-modal').remove()">关闭</button>
      </div>`;
      document.body.appendChild(modal);
    } catch (e) {
      alert('加载公共模板库失败');
    }
  } else {
    templates.push({label:'公共'+(templates.length+1),selected:false});
    renderTemplates();
  }
}

async function selectPublicTpl(imageUrl, label) {
  if (!adminBackendAvailable) return;
  try {
    await apiPost('/templates', { image_url: imageUrl, label: label });
    showToast('已添加: ' + label);
    renderTemplates();
  } catch (e) {
    console.warn('[公共模板] 添加失败:', e.message);
  }
}
document.addEventListener('click', function() { const dd = document.getElementById('tpl-add-dropdown'); if(dd) dd.classList.remove('show'); });

// ===== 上传弹窗 =====
function showUploadModal() { document.getElementById('upload-modal').classList.add('show'); }
function hideUploadModal() { document.getElementById('upload-modal').classList.remove('show'); }

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
        goUploadStep(2);
        switchPage('upload');
        
        // 自动提取标签并动态渲染
        if (result.url || result.image_url) {
          const imageUrl = result.url || result.image_url;
          lastUploadedImageUrl = imageUrl;
          // 更新上传预览区域
          const previewImg = document.querySelector('.upload-img');
          if (previewImg) previewImg.innerHTML = `<img src="${staticUrl(imageUrl)}" style="width:100%;height:100%;object-fit:cover;border-radius:8px" onerror="this.outerHTML='<i class=\\'ti ti-photo\\' style=\\'font-size:32px;color:#BA7517\\'></i>'">`;
          
          try {
            const tags = await apiPost('/extract-tags', { image_url: imageUrl });
            console.log('[标签提取] 成功:', tags);
            lastExtractedTags = tags;
            renderExtractedTags(tags);
          } catch (tagErr) {
            console.warn('[标签提取] 失败，使用默认标签:', tagErr.message);
          }
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

// 将后端返回的标签动态渲染到确认标签页
function renderExtractedTags(tags) {
  const craftGroup = document.getElementById('craft-tags');
  const marketGroup = document.getElementById('market-tags');
  if (!craftGroup || !marketGroup) return;
  
  // 工艺维度标签
  const craftTags = [];
  if (tags.nail_technique) craftTags.push(...(Array.isArray(tags.nail_technique) ? tags.nail_technique : [tags.nail_technique]));
  if (tags.nail_decoration) craftTags.push(...(Array.isArray(tags.nail_decoration) ? tags.nail_decoration : [tags.nail_decoration]));
  if (tags.nail_finish) craftTags.push(tags.nail_finish);
  if (tags.nail_shape) craftTags.push(tags.nail_shape);
  if (tags.nail_length) craftTags.push(tags.nail_length);
  
  // 营销维度标签
  const marketTags = [];
  if (tags.color_system) marketTags.push(...(Array.isArray(tags.color_system) ? tags.color_system : [tags.color_system]));
  if (tags.style_tags) marketTags.push(...tags.style_tags);
  if (tags.scene_tags) marketTags.push(...tags.scene_tags);
  if (tags.season_tags) marketTags.push(...tags.season_tags);
  
  // 渲染工艺维度
  const craftFiltered = craftTags.filter(t => t && t !== 'unknown');
  craftGroup.innerHTML = craftFiltered.map(t => 
    `<span class="tag tag-craft">${t} <i class="tag-del" onclick="this.parentElement.remove()">×</i></span>`
  ).join('') + '<button class="tag-add-btn" onclick="addTagPrompt(\'craft-tags\',\'tag-craft\')">+</button>';
  
  // 渲染营销维度
  const marketFiltered = marketTags.filter(t => t && t !== 'unknown');
  const colorClasses = { color: 'tag-color', style: 'tag-style', scene: 'tag-scene', season: 'tag-season' };
  marketGroup.innerHTML = marketFiltered.map((t, i) => {
    const cls = i < (tags.color_system || []).length ? 'tag-color' : 
                i < (tags.color_system || []).length + (tags.style_tags || []).length ? 'tag-style' : 'tag-season';
    return `<span class="tag ${cls}">${t} <i class="tag-del" onclick="this.parentElement.remove()">×</i></span>`;
  }).join('') + '<button class="tag-add-btn" onclick="addTagPrompt(\'market-tags\',\'tag-color\')">+</button>';
  
  // 更新标签计数
  const total = craftFiltered.length + marketFiltered.length;
  const resultEl = document.querySelector('.upload-result');
  if (resultEl) resultEl.innerHTML = `<i class="ti ti-check"></i> 共识别到 <strong>${total}</strong> 个标签`;
}

let activeTagDropdown = null;
let tagSearchTimer = null;

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

function addTagPrompt(groupId, tagClass) {
  closeTagDropdown();

  const btn = document.querySelector(`#${groupId} .tag-add-btn`);
  if (!btn) return;

  const rect = btn.getBoundingClientRect();
  const craftFields = ['nail_technique', 'nail_decoration', 'nail_finish', 'nail_shape', 'nail_length'];
  const marketFields = ['color_system', 'style_tags', 'scene_tags', 'season_tags', 'hand_skin_tone', 'hand_shape'];
  const fields = groupId === 'craft-tags' ? craftFields : marketFields;

  const dd = document.createElement('div');
  dd.className = 'tag-search-dropdown';
  dd.style.cssText = `position:fixed;top:${rect.bottom + 4}px;left:${rect.left}px;width:240px`;
  dd.innerHTML = `<input type="text" placeholder="输入关键词搜索..." autocomplete="off">
    <div class="tag-dd-list"><div class="tag-dd-empty">输入关键词搜索已有标签</div></div>
    <div class="tag-dd-new">+ 添加为新标签</div>`;

  const input = dd.querySelector('input');
  const newBtn = dd.querySelector('.tag-dd-new');

  input.addEventListener('input', function () {
    clearTimeout(tagSearchTimer);
    const q = this.value.trim();
    if (!q) {
      dd.querySelector('.tag-dd-list').innerHTML = '<div class="tag-dd-empty">输入关键词搜索已有标签</div>';
      return;
    }
    if (!adminBackendAvailable) return;
    tagSearchTimer = setTimeout(() => _doTagSearch(q, fields, dd, groupId, tagClass), 250);
  });

  newBtn.addEventListener('click', function (e) {
    e.stopPropagation();
    const v = input.value.trim();
    if (v) {
      _insertTag(groupId, tagClass, v);
      closeTagDropdown();
    }
  });

  dd.addEventListener('click', function (e) { e.stopPropagation(); });

  document.body.appendChild(dd);
  setTimeout(() => input.focus(), 50);
  activeTagDropdown = dd;

  setTimeout(() => {
    document.addEventListener('click', closeTagDropdown);
    document.addEventListener('keydown', onTagDropdownKey);
  }, 0);
}

async function _doTagSearch(q, fields, dd, groupId, tagClass) {
  const listEl = dd.querySelector('.tag-dd-list');
  listEl.innerHTML = '<div class="tag-dd-empty">搜索中...</div>';

  try {
    const results = await Promise.all(fields.map(f =>
      apiGet('/taxonomy/options', { field_key: f, q, limit: 5 })
        .then(items => (items || []).map(item => ({ value: item.value, field: f })))
        .catch(() => [])
    ));

    const allResults = results.flat();
    if (allResults.length === 0) {
      listEl.innerHTML = '<div class="tag-dd-empty">未找到匹配标签，在上方输入框输入后点击"添加为新标签"</div>';
      return;
    }

    const seen = new Set();
    const unique = allResults.filter(r => {
      if (seen.has(r.value)) return false;
      seen.add(r.value);
      return true;
    }).slice(0, 15);

    listEl.innerHTML = '';
    unique.forEach(r => {
      const item = document.createElement('div');
      item.className = 'tag-dd-item';
      item.innerHTML = `<span>${r.value}</span><span class="dd-field">${r.field}</span>`;
      item.addEventListener('click', function (ev) {
        ev.stopPropagation();
        _insertTag(groupId, tagClass, r.value);
        closeTagDropdown();
      });
      listEl.appendChild(item);
    });
  } catch (e) {
    listEl.innerHTML = '<div class="tag-dd-empty">搜索失败，请重试</div>';
  }
}

function _insertTag(groupId, tagClass, name) {
  const group = document.getElementById(groupId);
  const btn = group.querySelector('.tag-add-btn');
  const tag = document.createElement('span');
  tag.className = 'tag ' + tagClass;
  tag.innerHTML = `${name} <i class="tag-del" onclick="this.parentElement.remove()">×</i>`;
  group.insertBefore(tag, btn);
}

// ===== 上传步骤 =====
let lastUploadedImageUrl = ''; // 暂存上传图片URL
let lastExtractedTags = {};    // 暂存提取的标签

function goUploadStep(step) {
  document.querySelectorAll('.upload-step-panel').forEach(p => p.style.display = 'none');
  document.getElementById('upload-step-'+step).style.display = 'block';
  [2,3,4].forEach(s => {
    const el = document.getElementById('step-'+s);
    if (!el) return;
    el.className = 'step ' + (s < step ? 'step-done' : s === step ? 'step-active' : 'step-pending');
    if (s < step) el.querySelector('.step-num').innerHTML = '<i class="ti ti-check"></i>';
    else el.querySelector('.step-num').textContent = s;
  });
  if (step === 3) {
    loadTemplatesForUpload();
  }
  if (step === 4) {
    // 步骤4：入库
    createStyleInBackend();
  }
}

async function createStyleInBackend() {
  if (!adminBackendAvailable || !lastUploadedImageUrl) return;
  try {
    await apiPost('/styles', {
      style_name: lastExtractedTags.style_name || '新款式',
      image_url: lastUploadedImageUrl,
      tags: lastExtractedTags,
    });
    console.log('[入库] 款式入库成功');
    // 自动刷新素材列表
    loadStylesData();
  } catch (e) {
    console.warn('[入库] 失败:', e.message);
  }
}

async function previewComposite() {
  const area = document.getElementById('composite-preview-area');
  if (!area || !lastUploadedImageUrl) return;

  const selectedTpls = document.querySelectorAll('#upload-tpl-grid .tpl-item.selected img');
  if (selectedTpls.length === 0) {
    area.innerHTML = '<div style="font-size:12px;color:#CC2200;margin-top:8px">请先在模板网格中选择至少一个模板</div>';
    return;
  }

  const templateUrl = selectedTpls[0].src;
  area.innerHTML = '<div class="composite-preview-loading"><i class="ti ti-loader"></i> 合成中...</div>';

  try {
    const result = await apiPost('/generate-composite', {
      style_image_url: lastUploadedImageUrl,
      template_image_url: templateUrl,
    });
    if (result && result.composite_image_url) {
      area.innerHTML = `<img src="${staticUrl(result.composite_image_url)}" class="composite-preview-img" alt="合成预览">`;
    } else {
      area.innerHTML = '<div style="font-size:12px;color:#CC2200;margin-top:8px">合成失败，请重试</div>';
    }
  } catch (e) {
    area.innerHTML = '<div style="font-size:12px;color:#CC2200;margin-top:8px">合成失败：' + e.message + '</div>';
  }
}

async function loadTemplatesForUpload() {
  const grid = document.getElementById('upload-tpl-grid');
  if (!grid) return;
  if (adminBackendAvailable) {
    try {
      const data = await apiGet('/templates');
      if (Array.isArray(data) && data.length > 0) {
        grid.innerHTML = data.map(t => `<div class="tpl-item selected" onclick="this.classList.toggle('selected')"><div class="tpl-check">✓</div><img src="${t.hand_image_url}" style="width:100%;height:100%;object-fit:cover;border-radius:8px" onerror="this.outerHTML='<i class=\\'ti ti-hand-finger\\'></i>'"><span>${t.label || t.source}</span></div>`).join('');
        return;
      }
    } catch (e) {}
  }
  grid.innerHTML = templates.map((t,i) => `<div class="tpl-item ${t.selected?'selected':''}" onclick="this.classList.toggle('selected')"><div class="tpl-check">✓</div><i class="ti ti-hand-finger"></i><span>${t.label}</span></div>`).join('');
}

// ===== 爆款推送（联调 /api/push-cards） =====
let pushCardsData = [];

async function loadPushData() {
  if (!adminBackendAvailable) return;
  try {
    const data = await apiGet('/push-cards');
    if (Array.isArray(data) && data.length > 0) {
      pushCardsData = data;
      console.log('[推送] 加载爆款推送数据成功:', pushCardsData.length, '条');
    }
  } catch (e) {
    console.warn('[推送] 加载失败:', e.message);
  }
}

const taglines = ['秋冬约会必备！奶油渐变猫眼，光线下超有氛围感，显白又高级，赶紧安排～','这个秋冬就靠它了！奶油白渐变猫眼，温柔又高级～','简约不简单！奶油渐变猫眼，日常百搭还显白～'];
let taglineIdx = 0;
const coupons = {'1':{name:'全贴甲片简约款',price:'¥168',desc:'可做渐变·猫眼·晕染'},'2':{name:'半贴甲片基础款',price:'¥128',desc:'半贴为主'},'3':{name:'猫眼渐变升级款',price:'¥218',desc:'专攻猫眼渐变'}};

function selectPushImg(el, idx) { document.querySelectorAll('.push-thumbs .push-thumb').forEach(t=>t.classList.remove('active')); el.classList.add('active'); document.getElementById('push-main-img').innerHTML=`<i class="ti ti-photo" style="font-size:38px;color:#BA7517"></i><span>合成效果图 ${idx}</span>`; }

async function regenPushImg(btn) {
  btn.innerHTML='<i class="ti ti-refresh"></i> 生成中...';
  if (adminBackendAvailable && pushCardsData.length > 0) {
    try {
      const card = pushCardsData[0];
      const styleUrl = card.style_image_urls && card.style_image_urls[0];
      if (styleUrl) {
        const result = await apiPost('/generate-composite', {
          style_image_url: styleUrl,
          template_image_url: styleUrl, // 使用同款作为模板（实际应选裸手模板）
        });
        if (result && result.composite_image_url) {
          document.getElementById('push-main-img').innerHTML = `<img src="${staticUrl(result.composite_image_url)}" style="width:100%;height:100%;object-fit:contain;border-radius:10px">`;
        }
      }
    } catch (e) {
      console.warn('[合成图] 重新生成失败:', e.message);
    }
  }
  btn.innerHTML='<i class="ti ti-refresh"></i> 重新生成';
}
async function regenTagline() {
  const l = document.getElementById('tagline-regen-label');
  l.textContent = '生成中...';
  
  if (adminBackendAvailable && pushCardsData.length > 0) {
    try {
      const card = pushCardsData[0];
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

function updatePriceSlider(val) { document.getElementById('price-slider-val').textContent = val; }

function goConfirm() { 
  const price = document.getElementById('price-slider-val').textContent;
  document.getElementById('confirm-price').textContent = price;
  switchPage('confirm'); 
}

async function confirmPublish() {
  if (adminBackendAvailable && pushCardsData.length > 0) {
    try {
      await apiPost(`/push-cards/${pushCardsData[0].push_id}/audit`, {
        action: 'accepted',
        merchant_id: 'demo_shop',
      });
      console.log('[上架] 审核通过');
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
    }
  } catch (e) {
    console.warn('[报告] 加载失败:', e.message);
  }
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
  actions.innerHTML = `<div class="adopted-label"><i class="ti ti-circle-check" style="color:#375623"></i> 已采纳 · ${skill.label}</div><button class="btn-undo" onclick="undoSug(${idx})">撤销</button>`;
  item.classList.add('adopted');
  
  // 调用后端 Skills 执行 API
  if (adminBackendAvailable) {
    try {
      await apiPost('/skills/execute', {
        action_type: skill.action,
        action_params: {},
      });
      console.log('[Skills] 执行成功:', skill.action);
    } catch (e) {
      console.warn('[Skills] 执行失败:', e.message);
    }
  }
  
  showToast(skill.execMsg || '操作已执行');
  
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
  renderStyleList();
  renderTemplates();
  switchPage('home');
  initAdminBackend().then(() => {
    if (adminBackendAvailable) {
      loadStylesData();
    }
  });
}
init();
