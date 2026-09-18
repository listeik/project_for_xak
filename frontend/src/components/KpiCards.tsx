import { BadgeCheck, CircleDollarSign, Gauge, ShieldAlert, TrendingUp } from 'lucide-react';
import { number, percent } from '../format';
import type { Calculation } from '../types';

export default function KpiCards({ result }: { result: Calculation }) {
  const kpi = result.kpi_summary;
  return <div className="kpi-grid">
    <article className="kpi-card"><div className="kpi-label">NPV затрат <CircleDollarSign size={17} /></div><div className="kpi-value">{number(kpi.npv, 2)} <span>млн</span></div><p>Постоянные цены 2035 · дисконтировано</p><span className="kpi-foot">Всего без дисконта: {number(kpi.total_cost)} млн</span></article>
    <article className="kpi-card"><div className="kpi-label">Минимальный сервис <Gauge size={17} /></div><div className={`kpi-value ${result.scenario === 'BASE' && kpi.min_service_level < 0.97 ? 'text-danger' : ''}`}>{percent(kpi.min_service_level)}</div><p>Критический: <strong>{percent(kpi.min_critical_service_level)}</strong></p><span className="kpi-foot">Порог BASE: общий ≥97% · критический ≥99%</span></article>
    <article className="kpi-card"><div className="kpi-label">Инвестиции CAPEX <TrendingUp size={17} /></div><div className="kpi-value">{number(kpi.total_capex, 0)} <span>/ {number(kpi.capex_limit_2040, 0)}</span></div><div className="capex-track"><span style={{ width: `${Math.min(100, kpi.total_capex / kpi.capex_limit_2040 * 100)}%` }} /></div><span className="kpi-foot">До 2037: {number(kpi.capex_through_2037, 0)} / {number(kpi.capex_limit_2037, 0)} млн</span></article>
    <article className={`kpi-card status-card ${result.feasible ? 'status-good' : 'status-bad'}`}><div className="kpi-label">Проверка ограничений {result.feasible ? <BadgeCheck size={17} /> : <ShieldAlert size={17} />}</div><div className="kpi-value status-value">{result.feasible ? 'Выполнены' : 'Нарушения'}</div><p>{result.feasible ? 'Все формальные проверки пройдены' : `Обнаружено: ${kpi.violation_count}`}</p><span className={`kpi-foot ${kpi.total_shortage > 0.000001 ? 'text-danger' : ''}`}>Дефицит за горизонт: <strong>{number(kpi.total_shortage, 2)} т</strong></span></article>
  </div>;
}
