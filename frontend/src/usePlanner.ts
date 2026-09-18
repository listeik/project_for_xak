import { useCallback, useEffect, useRef, useState } from 'react';
import { calculate, getCase, getDefaultPlan, optimize } from './api';
import type { CaseData, Optimization, Plan, Snapshot } from './types';

const message = (error: unknown) => error instanceof Error ? error.message : 'Не удалось выполнить запрос.';
const isAbort = (error: unknown) => error instanceof DOMException && error.name === 'AbortError';

export function usePlanner() {
  const [caseData, setCaseData] = useState<CaseData | null>(null);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [bootError, setBootError] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState<'optimizing' | 'importing' | null>(null);
  const [report, setReport] = useState<Optimization | null>(null);
  const [retry, setRetry] = useState(0);
  const [bootRetry, setBootRetry] = useState(0);
  const current = useRef<Plan | null>(null);
  const confirmed = useRef<Snapshot | null>(null);
  const defaults = useRef<Plan | null>(null);
  const calculation = useRef<AbortController | null>(null);
  const operation = useRef<AbortController | null>(null);

  const apply = useCallback((next: Plan, result?: Snapshot['result']) => {
    calculation.current?.abort();
    operation.current?.abort();
    current.current = next;
    setPlan(next);
    setBusy(null);
    setError('');
    setReport(null);
    if (result) {
      const nextSnapshot = { plan: next, result };
      confirmed.current = nextSnapshot;
      setSnapshot(nextSnapshot);
    }
  }, []);

  useEffect(() => {
    const controller = new AbortController();
    setBootError('');
    Promise.all([getCase(controller.signal), getDefaultPlan(controller.signal)])
      .then(([data, initial]) => {
        if (controller.signal.aborted) return;
        defaults.current = initial;
        setCaseData(data);
        apply(initial);
      })
      .catch((reason: unknown) => { if (!isAbort(reason)) setBootError(message(reason)); });
    return () => controller.abort();
  }, [bootRetry, apply]);

  useEffect(() => {
    if (!plan || confirmed.current?.plan === plan) return;
    const controller = new AbortController();
    calculation.current = controller;
    const timer = window.setTimeout(async () => {
      try {
        const result = await calculate(plan, controller.signal);
        if (controller.signal.aborted || current.current !== plan) return;
        const nextSnapshot = { plan, result };
        confirmed.current = nextSnapshot;
        setSnapshot(nextSnapshot);
        setError('');
      } catch (reason) {
        if (!isAbort(reason) && current.current === plan) setError(message(reason));
      }
    }, 350);
    return () => { window.clearTimeout(timer); controller.abort(); };
  }, [plan, retry]);

  useEffect(() => () => {
    calculation.current?.abort();
    operation.current?.abort();
  }, []);

  async function optimizePlan() {
    if (!plan) return;
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    const requestedPlan = plan;
    setBusy('optimizing');
    setError('');
    try {
      const response = await optimize(requestedPlan, controller.signal);
      if (controller.signal.aborted || current.current !== requestedPlan) return;
      apply(response.plan, response.result);
      setReport(response.optimization);
    } catch (reason) {
      if (!isAbort(reason) && current.current === requestedPlan) setError(message(reason));
    } finally {
      if (operation.current === controller) setBusy(null);
    }
  }

  async function importPlan(file: File) {
    const original = current.current;
    operation.current?.abort();
    const controller = new AbortController();
    operation.current = controller;
    setBusy('importing');
    setError('');
    try {
      if (file.size > 2_000_000) throw new Error('Файл плана слишком большой. Максимальный размер — 2 МБ.');
      let parsed: unknown;
      try { parsed = JSON.parse(await file.text()); }
      catch { throw new Error('Файл не содержит корректный JSON. Выберите сохранённый план или JSON-экспорт.'); }
      if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) throw new Error('Ожидается JSON-объект плана.');
      const envelope = parsed as Record<string, unknown>;
      const candidate = ('plan' in envelope ? envelope.plan : envelope) as Partial<Plan>;
      const result = await calculate(candidate, controller.signal);
      if (controller.signal.aborted || current.current !== original || !defaults.current) return;
      // The server has validated all fields. Fill its optional defaults for editable UI controls.
      const normalized: Plan = {
        ...defaults.current, ...candidate,
        plan_id: result.plan_id,
        scenario: candidate.scenario ?? 'BASE',
        yearly_orders: Object.fromEntries(Object.entries(candidate.yearly_orders!).map(([year, orders]) => [String(Number(year)), orders])),
        yearly_reservations: candidate.yearly_reservations ? Object.fromEntries(Object.entries(candidate.yearly_reservations).map(([year, value]) => [String(Number(year)), value])) : null,
        investments: { zbo_year: null, option_c_year: null, exercise_c_year: null, isru_funding_year: null, ...candidate.investments },
      };
      apply(normalized, result);
    } catch (reason) {
      if (!isAbort(reason) && current.current === original) setError(message(reason));
    } finally {
      if (operation.current === controller) setBusy(null);
    }
  }

  return {
    caseData, plan, snapshot, bootError, error, busy, report,
    pending: !!plan && snapshot?.plan !== plan,
    updatePlan: apply,
    retryCalculation: () => { setError(''); setRetry((value) => value + 1); },
    retryBoot: () => setBootRetry((value) => value + 1),
    optimizePlan, importPlan,
  };
}
