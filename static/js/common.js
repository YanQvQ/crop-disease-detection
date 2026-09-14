/* ============================================
   农作物病害识别系统 - 通用工具库
   @Author : 张炎 (YanQvQ)
   @GitHub : https://github.com/YanQvQ
   @Time   : 2026-08-24
   @File   : common.js
   ============================================ */

// API 配置
const API_BASE_URL = '';

// Token 管理
const TokenManager = {
  getToken() {
    return localStorage.getItem('token');
  },

  setToken(token) {
    localStorage.setItem('token', token);
  },

  removeToken() {
    localStorage.removeItem('token');
  },

  getUserRole() {
    return localStorage.getItem('userRole');
  },

  setUserRole(role) {
    localStorage.setItem('userRole', role);
  },

  getUsername() {
    return localStorage.getItem('username');
  },

  setUsername(username) {
    localStorage.setItem('username', username);
  },

  clear() {
    this.removeToken();
    localStorage.removeItem('userRole');
    localStorage.removeItem('username');
  }
};

// 认证检查
function requireAuth() {
  const token = TokenManager.getToken();
  if (!token) {
    window.location.href = '/';
    return false;
  }
  return true;
}

// 检查用户角色
function requireAdmin() {
  if (!requireAuth()) return false;
  const role = TokenManager.getUserRole();
  if (role !== 'admin') {
    showToast('权限不足', '您没有权限访问此页面', 'error');
    setTimeout(() => {
      window.location.href = '/dashboard';
    }, 1500);
    return false;
  }
  return true;
}

// API 请求封装
async function apiRequest(url, options = {}) {
  const token = TokenManager.getToken();

  const defaultHeaders = {
    'Content-Type': 'application/json'
  };

  if (token) {
    defaultHeaders['Authorization'] = `Bearer ${token}`;
  }

  const config = {
    ...options,
    headers: {
      ...defaultHeaders,
      ...options.headers
    }
  };

  try {
    const response = await fetch(API_BASE_URL + url, config);

    if (response.status === 401) {
      TokenManager.clear();
      showToast('登录已过期', '请重新登录', 'warning');
      setTimeout(() => {
        window.location.href = '/';
      }, 1500);
      throw new Error('Unauthorized');
    }

    // 空响应保护：204 或空 body 时直接返回 null，避免 response.json() 抛错
    if (response.status === 204) {
      return null;
    }

    // 统一解析：先取文本，空 body 不调用 JSON.parse
    let data = null;
    const text = await response.text();
    if (text) {
      try {
        data = JSON.parse(text);
      } catch (e) {
        data = null;
      }
    }

    if (response.status === 403) {
      showToast('权限不足', (data && data.message) || '您没有权限执行此操作', 'error');
      throw new Error('Forbidden');
    }

    if (!response.ok) {
      throw new Error((data && data.message) || `请求失败（HTTP ${response.status}）`);
    }

    // 业务层统一处理：仅当响应含 code 字段时按业务码判断。
    // 部分接口（如 /api/predictImg）成功时返回 status 而非 code，需放行由调用方处理。
    if (data && typeof data.code !== 'undefined' && data.code !== 0) {
      const bizError = new Error((data && data.message) || '请求处理失败');
      bizError.isBizError = true;
      throw bizError;
    }

    return data;
  } catch (error) {
    if (error.name === 'TypeError' && error.message === 'Failed to fetch') {
      showToast('网络错误', '请检查网络连接', 'error');
    }
    throw error;
  }
}

// GET 请求
async function apiGet(url) {
  return apiRequest(url, { method: 'GET' });
}

// POST 请求
async function apiPost(url, body) {
  return apiRequest(url, {
    method: 'POST',
    body: JSON.stringify(body)
  });
}

// DELETE 请求
async function apiDelete(url) {
  return apiRequest(url, { method: 'DELETE' });
}

// 文件上传
async function apiUpload(url, formData) {
  const token = TokenManager.getToken();

  const headers = {};
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }

  const response = await fetch(API_BASE_URL + url, {
    method: 'POST',
    headers,
    body: formData
  });

  if (response.status === 401) {
    TokenManager.clear();
    showToast('登录已过期', '请重新登录', 'warning');
    setTimeout(() => {
      window.location.href = '/';
    }, 1500);
    throw new Error('Unauthorized');
  }

  // 空响应保护
  if (response.status === 204) {
    return null;
  }

  let data = null;
  const text = await response.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch (e) {
      data = null;
    }
  }

  if (!response.ok) {
    throw new Error((data && data.message) || `请求失败（HTTP ${response.status}）`);
  }

  // 业务层统一处理：仅当响应含 code 字段时按业务码判断
  if (data && typeof data.code !== 'undefined' && data.code !== 0) {
    const bizError = new Error((data && data.message) || '请求处理失败');
    bizError.isBizError = true;
    throw bizError;
  }

  return data;
}

// Toast 消息提示
let toastContainer = null;

function createToastContainer() {
  if (!toastContainer) {
    toastContainer = document.createElement('div');
    toastContainer.className = 'toast-container';
    document.body.appendChild(toastContainer);
  }
  return toastContainer;
}

function showToast(title, message, type = 'info', duration = 4000) {
  const container = createToastContainer();

  const icons = {
    success: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`,
    error: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#ef4444" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`,
    warning: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#f59e0b" stroke-width="2"><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"></path><line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line></svg>`,
    info: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="#3b82f6" stroke-width="2"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>`
  };

  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  toast.innerHTML = `
    ${icons[type] || icons.info}
    <div class="toast-content">
      <div class="toast-title">${escapeHtml(title)}</div>
      <div class="toast-message">${escapeHtml(message)}</div>
    </div>
  `;

  container.appendChild(toast);

  // 触发动画
  requestAnimationFrame(() => {
    toast.classList.add('show');
  });

  // 自动移除
  setTimeout(() => {
    toast.classList.remove('show');
    setTimeout(() => {
      toast.remove();
    }, 300);
  }, duration);

  return toast;
}

// HTML 转义
function escapeHtml(text) {
  const div = document.createElement('div');
  div.textContent = text;
  return div.innerHTML;
}

// 安全解析后端返回的字符串化列表（JSON 数组，或历史遗留的 Python 风格单引号列表）
// 绝不使用 eval：旧数据形如 ['99.00%', 'Blight']，先尝试 JSON.parse，
// 失败则用正则提取单引号包裹的项，避免执行任意代码。解析失败返回 null。
function parseList(str) {
  if (!str || typeof str !== 'string') return null;
  const s = str.trim();
  if (s.charAt(0) !== '[') return null;
  try {
    const arr = JSON.parse(s);
    if (Array.isArray(arr)) return arr;
  } catch (e) {
    // 不是标准 JSON，继续尝试兼容旧 Python 列表格式
  }
  const items = [];
  const re = /'((?:[^'\\]|\\.)*)'/g;
  let m;
  while ((m = re.exec(s)) !== null) items.push(m[1]);
  return items.length > 0 ? items : null;
}

// 格式化时间
function formatDate(dateString) {
  if (!dateString) return '-';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return dateString;

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');
  const hours = String(date.getHours()).padStart(2, '0');
  const minutes = String(date.getMinutes()).padStart(2, '0');
  const seconds = String(date.getSeconds()).padStart(2, '0');

  return `${year}-${month}-${day} ${hours}:${minutes}:${seconds}`;
}

// 格式化日期 (不含时间)
function formatDateOnly(dateString) {
  if (!dateString) return '-';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return dateString;

  const year = date.getFullYear();
  const month = String(date.getMonth() + 1).padStart(2, '0');
  const day = String(date.getDate()).padStart(2, '0');

  return `${year}-${month}-${day}`;
}

// 相对时间
function formatRelativeTime(dateString) {
  if (!dateString) return '-';
  const date = new Date(dateString);
  if (isNaN(date.getTime())) return dateString;

  const now = new Date();
  const diff = now - date;
  const seconds = Math.floor(diff / 1000);
  const minutes = Math.floor(seconds / 60);
  const hours = Math.floor(minutes / 60);
  const days = Math.floor(hours / 24);

  if (days > 7) {
    return formatDate(dateString);
  } else if (days > 0) {
    return `${days}天前`;
  } else if (hours > 0) {
    return `${hours}小时前`;
  } else if (minutes > 0) {
    return `${minutes}分钟前`;
  } else {
    return '刚刚';
  }
}

// 文件大小格式化
function formatFileSize(bytes) {
  if (bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
}

// 复制到剪贴板
async function copyToClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    showToast('复制成功', '已复制到剪贴板', 'success');
    return true;
  } catch (error) {
    // 降级方案
    const textarea = document.createElement('textarea');
    textarea.value = text;
    textarea.style.position = 'fixed';
    textarea.style.opacity = '0';
    document.body.appendChild(textarea);
    textarea.select();
    try {
      document.execCommand('copy');
      showToast('复制成功', '已复制到剪贴板', 'success');
      return true;
    } catch (e) {
      showToast('复制失败', '无法复制到剪贴板', 'error');
      return false;
    } finally {
      document.body.removeChild(textarea);
    }
  }
}

// 下载文件
function downloadFile(url, filename) {
  const link = document.createElement('a');
  link.href = url;
  link.download = filename || '';
  link.target = '_blank';
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
}

// 显示加载状态
function showLoading(element) {
  if (typeof element === 'string') {
    element = document.querySelector(element);
  }
  if (!element) return;

  const loadingEl = document.createElement('div');
  loadingEl.className = 'loading-overlay';
  loadingEl.innerHTML = `
    <div class="loading-spinner"></div>
    <div class="loading-text">加载中...</div>
  `;
  element.style.position = 'relative';
  element.appendChild(loadingEl);
  return loadingEl;
}

// 隐藏加载状态
function hideLoading(loadingEl) {
  if (loadingEl && loadingEl.parentNode) {
    loadingEl.parentNode.removeChild(loadingEl);
  }
}

// 模态框
const Modal = {
  show(title, content, options = {}) {
    const overlay = document.createElement('div');
    overlay.className = 'modal-overlay active';

    const footerHtml = options.footer ? `<div class="modal-footer">${options.footer}</div>` : '';

    overlay.innerHTML = `
      <div class="modal" style="${options.width ? `max-width: ${options.width}` : ''}">
        <div class="modal-header">
          <h3 class="modal-title">${escapeHtml(title)}</h3>
          <button class="modal-close" data-action="close">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>
        <div class="modal-body">${content}</div>
        ${footerHtml}
      </div>
    `;

    document.body.appendChild(overlay);

    const closeModal = () => {
      overlay.classList.remove('active');
      setTimeout(() => overlay.remove(), 300);
      if (options.onClose) options.onClose();
    };

    overlay.addEventListener('click', (e) => {
      if (e.target.closest('[data-action="close"]') || e.target === overlay) {
        closeModal();
      }
    });

    return {
      close: closeModal,
      element: overlay
    };
  },

  alert(title, message, type = 'info') {
    const icons = {
      success: '✓',
      error: '✕',
      warning: '⚠',
      info: 'ℹ'
    };
    return this.show(title, `
      <div style="text-align: center; padding: 20px 0;">
        <div style="width: 60px; height: 60px; border-radius: 50%; background: var(--bg-primary); display: inline-flex; align-items: center; justify-content: center; font-size: 28px; margin-bottom: 16px; color: var(--color-primary);">
          ${icons[type]}
        </div>
        <p style="color: var(--text-secondary);">${escapeHtml(message)}</p>
      </div>
    `, {
      footer: `<button class="btn btn-primary" data-action="close">确定</button>`
    });
  },

  confirm(title, message) {
    return new Promise((resolve) => {
      const overlay = document.createElement('div');
      overlay.className = 'modal-overlay active';
      overlay.innerHTML = `
        <div class="modal" style="max-width: 400px;">
          <div class="modal-header">
            <h3 class="modal-title">${escapeHtml(title)}</h3>
            <button class="modal-close" data-action="cancel">
              <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>
          <div class="modal-body">
            <p style="color: var(--text-secondary); line-height: 1.6;">${escapeHtml(message)}</p>
          </div>
          <div class="modal-footer">
            <button class="btn btn-secondary" data-action="cancel">取消</button>
            <button class="btn btn-primary" data-action="confirm">确定</button>
          </div>
        </div>
      `;

      document.body.appendChild(overlay);

      overlay.addEventListener('click', (e) => {
        const action = e.target.closest('[data-action]')?.dataset.action;
        if (action === 'confirm') {
          overlay.classList.remove('active');
          setTimeout(() => overlay.remove(), 300);
          resolve(true);
        } else if (action === 'cancel' || e.target === overlay) {
          overlay.classList.remove('active');
          setTimeout(() => overlay.remove(), 300);
          resolve(false);
        }
      });
    });
  }
};

// 分页组件
class Pagination {
  constructor(options) {
    this.container = options.container;
    this.currentPage = options.currentPage || 1;
    this.totalPages = options.totalPages || 1;
    this.onPageChange = options.onPageChange || (() => {});
    this.render();
  }

  render() {
    if (!this.container) return;

    let html = '<div class="pagination">';

    // 上一页
    html += `<div class="pagination-item ${this.currentPage === 1 ? 'disabled' : ''}" data-page="${this.currentPage - 1}">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="15 18 9 12 15 6"></polyline>
      </svg>
    </div>`;

    // 页码
    const maxVisible = 5;
    let startPage = Math.max(1, this.currentPage - Math.floor(maxVisible / 2));
    let endPage = Math.min(this.totalPages, startPage + maxVisible - 1);

    if (endPage - startPage < maxVisible - 1) {
      startPage = Math.max(1, endPage - maxVisible + 1);
    }

    if (startPage > 1) {
      html += `<div class="pagination-item" data-page="1">1</div>`;
      if (startPage > 2) {
        html += `<div class="pagination-item disabled">...</div>`;
      }
    }

    for (let i = startPage; i <= endPage; i++) {
      html += `<div class="pagination-item ${i === this.currentPage ? 'active' : ''}" data-page="${i}">${i}</div>`;
    }

    if (endPage < this.totalPages) {
      if (endPage < this.totalPages - 1) {
        html += `<div class="pagination-item disabled">...</div>`;
      }
      html += `<div class="pagination-item" data-page="${this.totalPages}">${this.totalPages}</div>`;
    }

    // 下一页
    html += `<div class="pagination-item ${this.currentPage === this.totalPages ? 'disabled' : ''}" data-page="${this.currentPage + 1}">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
        <polyline points="9 18 15 12 9 6"></polyline>
      </svg>
    </div>`;

    html += '</div>';

    this.container.innerHTML = html;

    // 绑定事件
    this.container.querySelectorAll('.pagination-item:not(.disabled)').forEach(item => {
      item.addEventListener('click', () => {
        const page = parseInt(item.dataset.page);
        if (page >= 1 && page <= this.totalPages && page !== this.currentPage) {
          this.currentPage = page;
          this.render();
          this.onPageChange(page);
        }
      });
    });
  }

  setTotalPages(total) {
    this.totalPages = total;
    this.render();
  }

  setCurrentPage(page) {
    this.currentPage = page;
    this.render();
  }
}

// 表格排序
class TableSorter {
  constructor(options) {
    this.table = options.table;
    this.onSort = options.onSort || (() => {});
    this.init();
  }

  init() {
    if (!this.table) return;

    const headers = this.table.querySelectorAll('th[data-sort]');
    headers.forEach(header => {
      header.style.cursor = 'pointer';
      header.addEventListener('click', () => {
        const key = header.dataset.sort;
        const currentOrder = header.dataset.order || 'asc';
        const newOrder = currentOrder === 'asc' ? 'desc' : 'asc';

        // 重置所有headers
        headers.forEach(h => {
          h.dataset.order = '';
          const icon = h.querySelector('.sort-icon');
          if (icon) icon.remove();
        });

        // 设置当前header
        header.dataset.order = newOrder;
        const icon = document.createElement('span');
        icon.className = 'sort-icon';
        icon.innerHTML = newOrder === 'asc'
          ? '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="18 15 12 9 6 15"></polyline></svg>'
          : '<svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="6 9 12 15 18 9"></polyline></svg>';
        header.appendChild(icon);

        this.onSort(key, newOrder);
      });
    });
  }
}

// 退出登录
async function logout() {
  const confirmed = await Modal.confirm('确认退出', '确定要退出登录吗？');
  if (confirmed) {
    TokenManager.clear();
    window.location.href = '/';
  }
}

// 获取统计数据
async function fetchStats() {
  try {
    const res = await apiGet('/api/stats');
    if (res.code === 0) {
      return res.data;
    }
    throw new Error(res.message);
  } catch (error) {
    console.error('获取统计数据失败:', error);
    return {
      img_count: 0,
      video_count: 0,
      camera_count: 0,
      user_count: 0
    };
  }
}

// 获取模型列表
async function fetchModels() {
  try {
    const res = await apiGet('/api/file_names');
    return res.weight_items || [];
  } catch (error) {
    console.error('获取模型列表失败:', error);
    return [];
  }
}

// 为文件访问 URL 追加 JWT token（img/video 标签无法携带请求头）
// 仅对本站路径追加（相对路径或以当前 origin 开头的完整 URL），避免把 token 泄露给第三方 URL
function fileUrl(path) {
  if (!path) return path;
  // 兼容历史数据：库里可能存的是含主机名(如局域网IP)的绝对地址，
  // 统一截取 path 部分转相对，避免因主机不同导致跨源图片被浏览器拦截(ERR_BLOCKED_BY_ORB)。
  if (path.indexOf('://') !== -1) {
    try {
      const u = new URL(path, window.location.href);
      if (u.pathname.startsWith('/files/') || u.pathname.startsWith('/static/')) {
        path = u.pathname + u.search;
      }
    } catch (e) { /* 非标准 URL 保留原值 */ }
  }
  const origin = window.location.origin;
  if (path.startsWith(origin + '/')) {
    // 本站完整 URL：转为相对路径，避免硬编码 host
    path = path.slice(origin.length);
  }
  const token = TokenManager.getToken();
  if (!token) return path;
  const sep = path.includes('?') ? '&' : '?';
  return path + sep + 'token=' + encodeURIComponent(token);
}

// 病害知识库：按类别名(小写)索引 → { name_zh, pathogen, symptoms, treatment, ... }
let _diseaseInfoPromise = null;
function loadDiseaseInfo() {
  if (!_diseaseInfoPromise) {
    _diseaseInfoPromise = fetch('/static/crop_diseases.json')
      .then(r => { if (!r.ok) throw new Error('load failed'); return r.json(); })
      .then(data => {
        // 注：disease key 与 YOLO 模型类别名（不区分大小写）对齐，故健康分类保留 health/healthy_rice/healthy_wheat 三个不同 key
        const map = {};
        const cropsObj = (data && data.crops) ? data.crops : data; // 兼容旧结构
        Object.values(cropsObj).forEach(group => {
          const diseases = group.diseases || group; // 兼容旧结构（分组直接为病害映射）
          Object.entries(diseases).forEach(([key, val]) => { map[key.toLowerCase()] = val; });
        });
        return map;
      })
      .catch(() => { _diseaseInfoPromise = null; return {}; });
  }
  return _diseaseInfoPromise;
}

function _treatItemHtml(item) {
  if (!item) return '';
  if (typeof item === 'string') return `<li>${escapeHtml(item)}</li>`;
  const type = item.type ? `<strong>${escapeHtml(item.type)}：</strong>` : '';
  return `<li>${type}${escapeHtml(item.detail || '')}</li>`;
}

function _diseaseCardHtml(cls, confPct, info, count, low) {
  const countBadge = (count > 1) ? `<span class="disease-count">×${count}</span>` : '';
  const lowBadge = low ? `<span class="disease-low">低置信度·建议核实</span>` : '';
  const title = (info && info.name_zh) ? info.name_zh : (cls || '未知病害');
  let html = `<div class="disease-card${low ? ' is-low' : ''}"><div class="disease-card-header"><span class="disease-zh">${escapeHtml(title)}</span><span class="disease-name-en">${info && info.name_en ? escapeHtml(info.name_en) : ''}</span>${countBadge}${lowBadge}${confPct ? `<span class="disease-conf">${confPct}</span>` : ''}</div>`;
  if (!info || !info.symptoms) {
    let note = `<div class="disease-card-note">未收录该病害的详细防治资料，建议结合田间实地情况，咨询当地农技专家、农业部门或专业人士进一步确认。如需更详细的防治信息，可联系管理员补充该病害资料。</div>`;
    if (window.TokenManager && TokenManager.getUserRole() === 'admin') {
      note += `<div class="disease-card-missing">管理提示：该病害（${escapeHtml(cls)}）未在 <code>static/crop_diseases.json</code> 收录，可在其中新增对应资料后强制刷新生效。</div>`;
    }
    html += note;
  } else {
    if (info.symptoms) html += `<div class="detail-row"><div class="detail-row-label">识病要点</div><div class="detail-row-value">${escapeHtml(info.symptoms)}</div></div>`;
    if (info.conditions) html += `<div class="detail-row"><div class="detail-row-label">发病条件</div><div class="detail-row-value">${escapeHtml(info.conditions)}</div></div>`;
    if (Array.isArray(info.treatment) && info.treatment.length) {
      html += `<div class="disease-treat"><div class="disease-treat-label">防治建议</div><ul class="treat-list">${info.treatment.map(_treatItemHtml).join('')}</ul><div class="disease-treat-note">以上用药建议仅供科普参考，不构成用药指导。实际用药请以当地登记产品与说明书为准，使用前核对当地农药禁限用名录，规范轮换用药并遵守安全间隔期。具体防治方案请结合田间实地情况，咨询当地农技专家或专业人士后实施。</div></div>`;
    }
  }
  html += '</div>';
  return html;
}

// 统一置信度为百分比字符串：开启"四舍五入"→整数百分比（87%）；关闭→保留精确值（86.87%）。兼容 "92.34%"（图片记录）与 0.9234（视频/摄像头记录）
function _confToPct(v) {
  if (v == null) return '';
  const s = String(v).trim();
  const isPct = s.endsWith('%');
  let n = parseFloat(s);
  if (isNaN(n)) return '';
  if (!isPct && n <= 1) n = n * 100;
  const shouldRound = localStorage.getItem('confidenceRound') !== '0';
  if (shouldRound) return Math.round(n) + '%';
  return n.toFixed(2).replace(/\.?0+$/, '') + '%';
}

// 归一化置信度为 0~1 数值：兼容 "92.34%"（图片记录）与 0.9234（视频/摄像头记录）以及 "78.5%"
function _confToRatio(v) {
  if (v == null) return null;
  const s = String(v).trim();
  const isPct = s.endsWith('%');
  const n = parseFloat(s);
  if (isNaN(n)) return null;
  return (isPct || n > 1) ? n / 100 : n;
}

// 单条置信度是否偏低：基于真实置信度（<80%），与"四舍五入"开关无关，
// 避免显示值被四舍五入成 80% 后漏报 79.6% 这类本应预警的结果
function _isLowConfidence(v) {
  const ratio = _confToRatio(v);
  return ratio != null && ratio < 0.8;
}

// 知识库查找：先精确匹配，匹配不上则去掉括号内中文后缀再匹配（兼容 "blight（疫病）" -> "blight"）
function _lookupDisease(map, lbl) {
  if (!lbl) return undefined;
  const raw = String(lbl).trim();
  const lower = raw.toLowerCase();
  if (map[lower]) return map[lower];
  const stripped = raw.split(/[（(]/)[0].trim().toLowerCase();
  if (stripped && stripped !== lower && map[stripped]) return map[stripped];
  return undefined;
}

// 将标签按相同类别分组：同一类别只保留一条，附出现次数，置信度取组内最高
function _groupLabels(labels, confs) {
  const out = [];
  const idx = new Map();
  (labels || []).forEach((l, i) => {
    const key = String(l == null ? '' : l);
    const conf = confs && confs[i];
    const ratio = _confToRatio(conf);
    if (idx.has(key)) {
      const e = out[idx.get(key)];
      e.count += 1;
      if (ratio != null && (e._ratio == null || ratio > e._ratio)) { e._ratio = ratio; e.conf = conf; }
    } else {
      idx.set(key, out.length);
      out.push({ label: l, conf: conf, count: 1, _ratio: ratio });
    }
  });
  return out;
}

// 在指定容器中渲染一份记录的检测结果与防治建议
function renderDiseaseBlock(labels, confs, el) {
  return loadDiseaseInfo().then(map => {
    if (!el) return;
    if (!labels || labels.length === 0) {
      el.innerHTML = '<div class="detail-diseases-empty">该记录未检测到病害。可能存在两种情况：作物确实健康，或病害程度较轻/姿态不佳未被模型检出。建议结合田间实地情况综合判断，必要时请当地农技专家进一步确认。</div>';
      return;
    }
    const cards = _groupLabels(labels, confs).map(g => {
      const info = _lookupDisease(map, g.label);
      return _diseaseCardHtml(g.label, _confToPct(g.conf), info, g.count, _isLowConfidence(g.conf));
    });
    el.innerHTML = '<div class="detail-diseases-title">检测结果与防治建议</div>' + cards.join('');
  });
}

// 导出模块
window.Utils = {
  TokenManager,
  apiRequest,
  apiGet,
  apiPost,
  apiDelete,
  apiUpload,
  showToast,
  escapeHtml,
  parseList,
  formatDate,
  formatDateOnly,
  formatRelativeTime,
  formatFileSize,
  copyToClipboard,
  downloadFile,
  showLoading,
  hideLoading,
  Modal,
  Pagination,
  TableSorter,
  logout,
  fetchStats,
  fetchModels,
  fileUrl,
  requireAuth,
  requireAdmin,
  loadDiseaseInfo,
  renderDiseaseBlock,
  groupLabels: _groupLabels,
  confToPct: _confToPct,
  isLowConfidence: _isLowConfidence,

  // 侧边栏：桌面端切换 collapsed（收起），移动端切换 open（展开 + 遮罩）。
  // 两个 class 互斥切换，避免残留导致遮罩/收起状态错乱。
  toggleSidebar() {
    const sidebar = document.getElementById('sidebar');
    const mainWrapper = document.getElementById('mainWrapper');
    if (!sidebar) return;
    const isMobile = window.matchMedia('(max-width: 900px)').matches;
    if (isMobile) {
      sidebar.classList.remove('collapsed');
      sidebar.classList.toggle('open');
      if (mainWrapper) mainWrapper.classList.remove('sidebar-collapsed');
    } else {
      sidebar.classList.remove('open');
      sidebar.classList.toggle('collapsed');
      if (mainWrapper) mainWrapper.classList.toggle('sidebar-collapsed');
    }
  }
};

// 快捷访问
window.showToast = showToast;
window.apiGet = apiGet;
window.apiPost = apiPost;
window.apiDelete = apiDelete;
window.apiUpload = apiUpload;
window.Modal = Modal;
window.TokenManager = TokenManager;

// 侧边栏遮罩层自动初始化（小屏幕下点击遮罩关闭侧边栏）
document.addEventListener('DOMContentLoaded', function() {
  const sidebar = document.getElementById('sidebar');
  const menuToggle = document.getElementById('menuToggle');
  if (!sidebar || !menuToggle) return;

  // 动态创建遮罩层元素
  const overlay = document.createElement('div');
  overlay.className = 'sidebar-overlay';
  overlay.id = 'sidebarOverlay';
  document.body.appendChild(overlay);

  // 监听 sidebar 的 class 变化，同步遮罩层状态
  const observer = new MutationObserver(() => {
    if (sidebar.classList.contains('open')) {
      overlay.classList.add('active');
    } else {
      overlay.classList.remove('active');
    }
  });
  observer.observe(sidebar, { attributes: true, attributeFilter: ['class'] });

  // 点击遮罩层关闭侧边栏
  overlay.addEventListener('click', function() {
    sidebar.classList.remove('open');
    const mainWrapper = document.getElementById('mainWrapper');
    if (mainWrapper) mainWrapper.classList.remove('sidebar-collapsed');
  });

  // 跨 900px 断点时归整残留状态，避免 open/collapsed 互相干扰
  const mq = window.matchMedia('(max-width: 900px)');
  const normalizeSidebar = () => {
    if (mq.matches) {
      sidebar.classList.remove('collapsed');
    } else {
      sidebar.classList.remove('open');
    }
  };
  mq.addEventListener ? mq.addEventListener('change', normalizeSidebar) : mq.addListener(normalizeSidebar);
});
