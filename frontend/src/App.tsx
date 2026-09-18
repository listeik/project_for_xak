import { useRef, useState } from 'react';
import { Activity, ArrowDownToLine, ArrowUpFromLine, Check, ChevronRight, CircleHelp, Database, FileDown, FileJson, Fuel, LayoutDashboard, LoaderCircle, Network, Orbit, RefreshCw, ShieldCheck, Sparkles, X } from 'lucide-react';
import { download, exportPlan } from './api';
import { number } from './format';
import { usePlanner } from './usePlanner';
import KpiCards from './components/KpiCards';
import PlanController from './components/PlanController';
import { FinanceChart, InventoryChart, LogisticsGraph } from './components/DashboardCharts';
import ResultTables from './components/ResultTables';

export default function App() {
  const planner = usePlanner();
  const { plan, snapshot, caseData, pending, busy, error } = planner;
  const [year, setYear] = useState(2035);
  const [exporting, setExporting] = useState(false);
  const [fileNotice, setFileNotice] = useState('');
  const [fileError, setFileError] = useState('');
  const fileInput = useRef<HTMLInputElement>(null);
  const result = snapshot?.result;
  const row = result?.annual_balances.find((item) => item.year === year);
  const exportDisabled = !snapshot || pending || !!busy || exporting;

  function savePlan() {
    if (!plan) return;
    download(new Blob([JSON.stringify(plan, null, 2)], { type: 'application/json' }), `fuel-plan-${plan.scenario.toLowerCase()}.json`);
    setFileNotice('План сохранён в JSON. Его можно открыть кнопкой «Загрузить».');
  }

  async function handleExport(format: 'csv' | 'xlsx') {
    if (!snapshot || exportDisabled) return;
    setExporting(true); setFileNotice(''); setFileError('');
    try { await exportPlan(snapshot.plan, format); setFileNotice(`Выгрузка ${format.toUpperCase()} готова.`); }
    catch (reason) { setFileError(reason instanceof Error ? reason.message : 'Ошибка экспорта.'); }
    finally { setExporting(false); }
  }

  return <div className="app-shell">
    <aside className="navigation-rail" aria-label="Навигация"><a href="#overview" className="rail-brand" aria-label="Космоконтур: к началу"><Orbit size={25} /></a><div className="rail-links"><a href="#overview" className="rail-link active" title="Обзор" aria-label="Обзор"><LayoutDashboard size={20} /></a><a href="#network" className="rail-link" title="Сеть снабжения" aria-label="Сеть снабжения"><Network size={20} /></a><a href="#balance" className="rail-link" title="Баланс" aria-label="Таблица баланса"><Database size={20} /></a><a href="#constraints" className="rail-link" title="Ограничения" aria-label="Проверка ограничений"><ShieldCheck size={20} /></a></div><a href="#methodology" className="rail-link rail-bottom" title="Методология" aria-label="Методология"><CircleHelp size={20} /></a><span className="rail-version">v1.0</span></aside>
    <div className="workspace"><header className="topbar"><a className="brand" href="#overview"><Orbit className="mobile-brand-icon" size={24} /><span>КОСМО<span className="text-cyan">КОНТУР</span><small>Центр управления снабжением</small></span></a><div className="topbar-meta"><span className="mission-tag">CISLUNAR / 2035–2040</span><span className={`connection-state ${planner.bootError || error ? 'connection-error' : ''}`}><i />{planner.bootError ? 'Нет подключения' : !caseData ? 'Подключение…' : error ? 'Требуется внимание' : 'Расчётный контур'}</span><span className="operator-avatar" aria-label="Рабочее место оператора">ОП</span></div></header>
      <main id="overview">
        <div className="breadcrumb">Рабочее пространство <ChevronRight size={12} /><span>Топливный узел</span></div>
        <div className="page-heading"><div><p className="eyebrow">Планирование цислунарной логистики</p><h1>Топливный космоконтур <span>2035</span></h1><p className="page-subtitle">Каждая тонна имеет значение. Каждый рейс — часть системы.</p></div><div className="horizon-label"><span className="tiny-orbit" /><div>Горизонт планирования<strong>2035 — 2040</strong></div></div></div>
        <div className="toolbar"><div className="plan-name"><FileJson size={16} /><label htmlFor="plan-name" className="sr-only">Название плана</label><input id="plan-name" value={plan?.plan_id ?? ''} disabled={!plan} maxLength={128} placeholder="Загрузка плана…" onChange={(event) => plan && planner.updatePlan({ ...plan, plan_id: event.target.value })} /></div><div className="toolbar-actions"><button className="button button-quiet" onClick={savePlan} disabled={!plan}><ArrowDownToLine size={15} /><span>Сохранить JSON</span></button><button className="button button-quiet" onClick={() => fileInput.current?.click()} disabled={!plan || !!busy}><ArrowUpFromLine size={15} /><span>Загрузить</span></button><span className="toolbar-divider" /><button className="button" onClick={() => handleExport('csv')} disabled={exportDisabled}><FileDown size={15} />CSV</button><button className="button" onClick={() => handleExport('xlsx')} disabled={exportDisabled}>{exporting ? <LoaderCircle className="spin" size={15} /> : <FileDown size={15} />}XLSX</button></div><input ref={fileInput} className="sr-only" type="file" accept=".json,application/json" aria-label="Загрузить файл плана JSON" onChange={(event) => { const file = event.target.files?.[0]; if (file) { setFileNotice(''); setFileError(''); void planner.importPlan(file); } event.target.value = ''; }} /></div>
        {fileNotice && <div className="inline-notice" role="status"><Check size={16} /><span>{fileNotice}</span><button className="icon-button" onClick={() => setFileNotice('')} aria-label="Закрыть уведомление"><X size={15} /></button></div>}
        {(error || fileError) && <div className="error-banner" role="alert"><ShieldCheck size={19} /><div><strong>Запрос не выполнен</strong><p>{error || fileError}</p></div><button className="button" onClick={() => { setFileError(''); planner.retryCalculation(); }}><RefreshCw size={14} />Повторить расчёт</button></div>}
        {planner.bootError ? <section className="empty-state panel" role="alert"><Database size={36} /><h2>Расчётный сервер недоступен</h2><p>{planner.bootError}</p><button className="button button-primary" onClick={planner.retryBoot}><RefreshCw size={16} />Подключиться снова</button></section>
          : !caseData || !plan ? <section className="empty-state panel" role="status"><LoaderCircle className="spin" size={32} /><h2>Подключаем расчётный контур</h2><p>Загружаем исходные условия и план с сервера. При первом запуске сервиса это может занять около минуты.</p></section>
            : <>
              <div className="result-status" aria-live="polite"><div><i className={`status-light ${pending || busy ? 'loading' : ''}`} /><span>{busy === 'optimizing' ? 'Оптимизация закупок…' : busy === 'importing' ? 'Проверяем загруженный план…' : pending ? error ? 'Расчёт не обновлён' : 'Пересчитываем план…' : 'Расчёт обновлён'}</span></div>{result && <span>Показан результат: <strong>{result.scenario === 'BASE' ? 'BASE' : 'MANDATORY STRESS'}</strong>{pending ? ' · предыдущая версия плана' : ''}{result.assumptions.research_factors_active ? ' · чувствительность' : ''}</span>}</div>
              {result && <KpiCards result={result} />}
              {planner.report && <div className="optimization-report" role="status"><Sparkles size={20} /><div><strong>Заказы оптимизированы · инвестиции сохранены</strong><p>NPV: {number(planner.report.npv_before, 2)} → {number(planner.report.npv_after, 2)} млн. {planner.report.savings >= 0 ? 'Снижение затрат' : 'Увеличение затрат'}: {number(Math.abs(planner.report.savings), 2)} млн.</p>{!planner.report.baseline_feasible && <p>Исходный план нарушал ограничения; дефицит составлял {number(planner.report.baseline_shortage_t, 2)} т. Разность стоимости не означает сравнение равноценных стратегий.</p>}<details><summary>Область оптимальности</summary><p>{planner.report.explanation}</p></details></div></div>}
              <div className="main-grid" id="network"><div className="main-visuals">{result && row ? <LogisticsGraph row={row} caseData={caseData} year={year} setYear={setYear} /> : <section className="panel empty-state first-calculation"><Fuel size={35} /><h2>Готовим первый расчёт</h2><p>{error ? 'Исправьте параметры или повторите запрос.' : 'Баланс, фактические поставки и стоимость появятся после ответа сервера.'}</p></section>}
                  <div className="mission-note"><Activity size={17} /><p><strong>Дефицит критичен.</strong> Проверяйте запас внутри года и сроки поставок, даже когда годовой баланс сходится.</p></div>
                  {result && <InventoryChart result={result} />}
                </div><PlanController plan={plan} caseData={caseData} year={year} row={row} updatePlan={planner.updatePlan} onOptimize={() => void planner.optimizePlan()} optimizing={busy === 'optimizing'} disabled={pending || !!busy} /></div>
              {result && <><div className="finance-layout"><FinanceChart result={result} /><section className="panel strategy-note"><p className="eyebrow"><Orbit size={13} /> Операторский контекст</p><h2>Резерв — часть плана</h2><p>45 дней годового спроса должны быть обеспечены физическим запасом на начало года. Закупки, инвестиции и сроки доставки проверяются вместе.</p><div className="strategy-metrics"><div><strong>6</strong><span>лет планирования</span></div><div><strong>45</strong><span>дней резерва</span></div><div><strong>5</strong><span>каналов снабжения</span></div></div><a href="#methodology">Допущения расчёта <ChevronRight size={15} /></a></section></div><ResultTables result={result} year={year} /></>}
            </>}
        <footer><span><Orbit size={14} /> Топливный космоконтур · КосмоХакатон 2026</span><span>{result ? `Модель ${result.model_version} · данные ${result.input_version.slice(0, 8)}` : 'Python / FastAPI · React / ECharts'}</span></footer>
      </main>
    </div>
  </div>;
}
