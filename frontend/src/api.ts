import type { Calculation, CaseData, OptimizedResponse, Plan } from './types';

const origin = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '');
const base = `${origin}/api/v1`;

async function errorMessage(response: Response): Promise<string> {
  try {
    const body = await response.json();
    if (Array.isArray(body.detail)) {
      return body.detail.map((entry: { loc?: Array<string | number>; msg?: string }) =>
        `${entry.loc?.filter((part) => part !== 'body').join(' → ') || 'План'}: ${entry.msg || 'некорректное значение'}`,
      ).join('; ');
    }
    const main = body.detail?.message || body.message || (typeof body.detail === 'string' ? body.detail : `Ошибка сервера (${response.status}).`);
    const context = Array.isArray(body.detail?.details) ? body.detail.details.map((item: string | { message?: string; code?: string }) =>
      typeof item === 'string' ? item : item.message || item.code || '').filter(Boolean).join('; ') : '';
    return context ? `${main} ${context}` : main;
  } catch {
    return `Сервер вернул ошибку ${response.status}. Повторите запрос.`;
  }
}

async function request<T>(path: string, signal?: AbortSignal, payload?: unknown): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${base}${path}`, {
      signal,
      ...(payload !== undefined ? {
        method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload),
      } : {}),
    });
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error;
    throw new Error('Нет связи с расчётным сервером. Проверьте подключение или дождитесь запуска сервиса и повторите запрос.');
  }
  if (!response.ok) throw new Error(await errorMessage(response));
  return response.json() as Promise<T>;
}

export const getCase = (signal?: AbortSignal) => request<CaseData>('/case', signal);
export const getDefaultPlan = (signal?: AbortSignal) => request<Plan>('/default-plan', signal);
export const calculate = (plan: unknown, signal?: AbortSignal) => request<Calculation>('/calculate', signal, plan);
export const optimize = (plan: Plan, signal?: AbortSignal) => request<OptimizedResponse>('/optimize', signal, plan);

export function download(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export async function exportPlan(plan: Plan, format: 'csv' | 'xlsx' | 'json') {
  let response: Response;
  try {
    response = await fetch(`${base}/export?format=${format}`, {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(plan),
    });
  } catch { throw new Error('Не удалось связаться с сервером для экспорта. Повторите запрос.'); }
  if (!response.ok) throw new Error(await errorMessage(response));
  const filename = response.headers.get('Content-Disposition')?.match(/filename="([^"]+)"/)?.[1]
    || `fuel-contour-${plan.scenario.toLowerCase()}.${format}`;
  download(await response.blob(), filename);
}
