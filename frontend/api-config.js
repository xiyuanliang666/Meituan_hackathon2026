// ===== API 配置 =====
// 后端地址配置，开发时默认 localhost:8000
const API_BASE = 'http://localhost:8000';
const API_PREFIX = '/api';

// 通用请求封装
async function apiRequest(endpoint, options = {}) {
  const url = `${API_BASE}${API_PREFIX}${endpoint}`;
  const defaultOptions = {
    headers: { 'Content-Type': 'application/json' },
  };
  const mergedOptions = { ...defaultOptions, ...options };
  
  try {
    const response = await fetch(url, mergedOptions);
    if (!response.ok) {
      const errorData = await response.json().catch(() => ({}));
      throw new Error(errorData.detail || `HTTP ${response.status}`);
    }
    return await response.json();
  } catch (error) {
    console.error(`[API] ${endpoint} failed:`, error.message);
    throw error;
  }
}

// GET 请求
async function apiGet(endpoint, params = {}) {
  const filtered = Object.fromEntries(
    Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
  );
  const query = new URLSearchParams(filtered).toString();
  const url = query ? `${endpoint}?${query}` : endpoint;
  return apiRequest(url, { method: 'GET' });
}

// POST 请求
async function apiPost(endpoint, body = {}) {
  return apiRequest(endpoint, {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

// 上传文件
async function apiUpload(endpoint, file, extraFields = {}) {
  const url = `${API_BASE}${API_PREFIX}${endpoint}`;
  const formData = new FormData();
  formData.append('file', file);
  Object.entries(extraFields).forEach(([key, val]) => formData.append(key, val));
  
  const response = await fetch(url, { method: 'POST', body: formData });
  if (!response.ok) {
    const errorData = await response.json().catch(() => ({}));
    throw new Error(errorData.detail || `HTTP ${response.status}`);
  }
  return await response.json();
}

// 健康检查
async function checkBackendHealth() {
  try {
    const res = await fetch(`${API_BASE}/health`);
    return res.ok;
  } catch {
    return false;
  }
}

// 静态资源 URL
function staticUrl(path) {
  if (!path) return '';
  if (path.startsWith('http')) return path;
  return `${API_BASE}/static/${path.replace(/^\//, '')}`;
}
