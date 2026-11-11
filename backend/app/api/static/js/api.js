/**
 * API 访问层（Task 027）
 *
 * 只做四件事：发请求、把 HTTP/网络/非 JSON 错误翻译成统一结构、保留服务端 trace_id、
 * 支持 AbortController。不在这里改业务字段，也不发送自报身份字段。
 */

export class ApiError extends Error {
  /**
   * @param {string} message 面向用户的说明
   * @param {{code?: string, traceId?: string, status?: number, details?: unknown}} info
   */
  constructor(message, info = {}) {
    super(message);
    this.name = 'ApiError';
    this.code = info.code || 'unknown_error';
    this.traceId = info.traceId || '';
    this.status = info.status || 0;
    this.details = info.details;
  }
}

export const OFFLINE_HINT =
  '无法连接后端服务。请在 backend/ 目录启动：' +
  'python -m uvicorn app.api.app:app --host 127.0.0.1 --port 8000';

/**
 * @param {string} path
 * @param {{method?: string, body?: unknown, headers?: Record<string,string>, signal?: AbortSignal}} [options]
 */
export async function api(path, options = {}) {
  const { method = 'GET', body, headers = {}, signal } = options;
  const init = { method, headers: { Accept: 'application/json', ...headers }, signal };
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json';
    init.body = JSON.stringify(body);
  }

  let response;
  try {
    response = await fetch(path, init);
  } catch (error) {
    if (error && error.name === 'AbortError') throw error;
    throw new ApiError(OFFLINE_HINT, { code: 'network_error' });
  }

  const headerTrace = response.headers.get('X-Trace-Id') || '';
  const text = await response.text();
  let payload = null;
  let parseFailed = false;
  if (text) {
    try {
      payload = JSON.parse(text);
    } catch {
      parseFailed = true;
    }
  }

  if (!response.ok) {
    const detail = payload && typeof payload === 'object' ? payload.error : null;
    let message;
    if (detail && detail.message) {
      message = detail.message;
    } else if (parseFailed) {
      message = `服务端返回了非 JSON 响应（HTTP ${response.status}）`;
    } else {
      message = `请求失败（HTTP ${response.status} ${response.statusText || ''}）`.trim();
    }
    throw new ApiError(message, {
      code: (detail && detail.code) || `http_${response.status}`,
      traceId: (detail && detail.trace_id) || headerTrace,
      status: response.status,
      details: detail ? detail.details : undefined,
    });
  }

  if (parseFailed) {
    throw new ApiError('服务端返回了无法解析的响应（不是 JSON）', {
      code: 'invalid_response',
      traceId: headerTrace,
      status: response.status,
    });
  }

  return payload;
}

export const apiCalls = {
  meta: (signal) => api('/api/meta', { signal }),
  listRuns: (limit, signal) => api(`/api/runs?limit=${encodeURIComponent(limit)}`, { signal }),
  getRun: (runId, signal) => api(`/api/runs/${encodeURIComponent(runId)}`, { signal }),
  getTraces: (runId, signal) => api(`/api/runs/${encodeURIComponent(runId)}/traces`, { signal }),
  submit: (payload) => api('/api/runs', { method: 'POST', body: payload }),
  decide: (runId, { decision, draftVersion, reason, actor }) =>
    api(`/api/runs/${encodeURIComponent(runId)}/approvals`, {
      method: 'POST',
      headers: { 'X-Actor-Id': actor },
      body: { decision, draft_version: draftVersion, reason: reason || null },
    }),
};
