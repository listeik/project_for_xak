import { BadgeCheck, CircleDollarSign, Gauge, ShieldAlert, TrendingUp, TriangleAlert } from 'lucide-react';
import { number, percent } from '../format';
import type { Calculation } from '../types';

export default function KpiCards({ result }: { result: Calculation }) {
  const kpi = result.kpi_summary;
  const attention = kpi.has_shortage || kpi.warning_count > 0;
  const totalBelow = result.annual_balances.some((row) => row.service_below_target);
  const criticalBelow = result.annual_balances.some((row) => row.critical_service_below_target);
  return <div className="kpi-grid">
    <article className="kpi-card"><div className="kpi-label">NPV затрат <CircleDollarSign size={17} /></div><div className="kpi-value">{number(kpi.npv, 2)} <span>млн</span></div><p>Постоянные цены 2035 · дисконтировано</p><span className="kpi-foot">Всего без дисконта: {number(kpi.total_cost)} млн</span></article>
    <article className="kpi-card"><div className="kpi-label">Минимальный сервис <Gauge size={17} /></div><div className={`kpi-value ${totalBelow ? 'text-danger' : ''}`}>{percent(kpi.min_service_level)}</div><p>Критический: <strong className={criticalBelow ? 'text-danger' : ''}>{percent(kpi.min_critical_service_level)}</strong></p><span className="kpi-foot">{result.scenario === 'BASE' ? 'Пороги BASE' : 'Ориентиры STRESS'}: общий ≥{percent(result.service_targets.total, 0)} · критический ≥{percent(result.service_targets.critical, 0)}</span></article>
    <article className="kpi-card"><div className="kpi-label">Инвестиции CAPEX <TrendingUp size={17} /></div><div className="kpi-value">{number(kpi.total_capex, 0)} <span>/ {number(kpi.capex_limit_2040, 0)}</span></div><div className="capex-track"><span style={{ width: `${Math.min(100, kpi.total_capex / kpi.capex_limit_2040 * 100)}%` }} /></div><span className="kpi-foot">До 2037: {number(kpi.capex_through_2037, 0)} / {number(kpi.capex_limit_2037, 0)} млн</span></article>
    <article className={`kpi-card status-card ${!result.feasible ? 'status-bad' : attention ? 'status-warning' : 'status-good'}`}><div className="kpi-label">Диагностика плана {!result.feasible ? <ShieldAlert size={17} /> : attention ? <TriangleAlert size={17} /> : <BadgeCheck size={17} />}</div><div className="kpi-value status-value">{!result.feasible ? 'Нарушения' : attention ? 'Есть риски' : 'Выполнены'}</div><p>{!result.feasible ? `Нарушений: ${kpi.violation_count} · предупреждений: ${kpi.warning_count}` : attention ? 'Формальные проверки пройдены; есть дефицит или предупреждения' : 'Формальные проверки пройдены; дефицита нет'}</p><span className={`kpi-foot ${kpi.has_shortage ? 'text-danger' : ''}`}>Дефицит за горизонт: <strong>{number(kpi.total_shortage, 2)} т</strong></span></article>
  </div>;
}
