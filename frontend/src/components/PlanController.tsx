import { ChevronDown, FlaskConical, LoaderCircle, SlidersHorizontal, Sparkles } from 'lucide-react';
import { number, percent, sourceColors } from '../format';
import type { AnnualBalance, CaseData, DemandProfile, Investments, Plan, SourceId } from '../types';

function NumericInput({ value, onChange, label, min = 0, max, step = 0.1, className = '' }: {
  value: number; onChange: (value: number) => void; label: string; min?: number; max?: number; step?: number; className?: string;
}) {
  return <input className={`number-input ${className}`} type="number" inputMode="decimal" aria-label={label} min={min} max={max} step={step} value={value}
    onChange={(event) => { const value = Number(event.target.value); if (Number.isFinite(value)) onChange(value); }} />;
}

export default function PlanController({ plan, caseData, year, row, updatePlan, onOptimize, optimizing, disabled }: {
  plan: Plan; caseData: CaseData; year: number; row?: AnnualBalance; updatePlan: (plan: Plan) => void;
  onOptimize: () => void; optimizing: boolean; disabled: boolean;
}) {
  const updateOrder = (source: SourceId, value: number) => updatePlan({ ...plan, yearly_orders: { ...plan.yearly_orders, [year]: { ...plan.yearly_orders[year], [source]: value } } });
  const updateInvestment = (key: keyof Investments, value: number | null) => updatePlan({ ...plan, investments: { ...plan.investments, [key]: value } });
  const updateReservation = (source: SourceId, value: string) => {
    const reservations: NonNullable<Plan['yearly_reservations']> = { ...plan.yearly_reservations, [year]: { ...plan.yearly_reservations?.[year] } };
    if (value === '') delete reservations[year][source];
    else if (Number.isFinite(Number(value))) reservations[year][source] = Number(value);
    updatePlan({ ...plan, yearly_reservations: reservations });
  };
  const investmentRows: { key: keyof Investments; title: string; detail: string; fallback: number; years: number[] }[] = [
    { key: 'zbo_year', title: 'Хранилище ZBO', detail: '180 млн · 120 т · потери 1,2%', fallback: 2036, years: caseData.years.filter((value) => value >= 2036) },
    { key: 'option_c_year', title: 'Опцион Earth-New', detail: '90 млн · доступ к каналу C', fallback: 2035, years: caseData.years },
    { key: 'exercise_c_year', title: 'Исполнение опциона C', detail: '270 млн · после покупки опциона', fallback: plan.investments.option_c_year ?? 2035, years: caseData.years },
    { key: 'isru_funding_year', title: 'Пилот Lunar-ISRU', detail: '1 250 млн · финансирование до 2038', fallback: 2037, years: caseData.years.filter((value) => value <= 2037) },
  ];
  return <aside className="panel controller-panel">
    <div className="panel-heading"><div><p className="eyebrow"><SlidersHorizontal size={13} /> Решения оператора</p><h2>Управление планом <span className="text-cyan">{year}</span></h2></div></div>
    <fieldset className="plan-fields" disabled={!!plan.contract_lock}><div className="scenario-switch" role="group" aria-label="Сценарий расчёта">
      <button type="button" aria-pressed={plan.scenario === 'BASE'} className={plan.scenario === 'BASE' ? 'active' : ''} onClick={() => updatePlan({ ...plan, scenario: 'BASE' })}>BASE <span>Базовый</span></button>
      <button type="button" aria-pressed={plan.scenario === 'MANDATORY_STRESS'} className={plan.scenario === 'MANDATORY_STRESS' ? 'active stress' : ''} onClick={() => updatePlan({ ...plan, scenario: 'MANDATORY_STRESS', demand_profile: 'BASE', research_shock: null })}><FlaskConical size={14} /> STRESS <span>Обязательный</span></button>
    </div>
    {plan.scenario === 'MANDATORY_STRESS' && <p className="stress-description">С 2038: спрос +15%, потери ≤2%. В 2038–2039: A/B +25% к цене; поставки D — 55% / 75% плана.</p>}
    <div className="demand-profile-control"><label htmlFor="demand-profile">Профиль спроса</label><select id="demand-profile" value={plan.demand_profile} disabled={plan.scenario === 'MANDATORY_STRESS'} onChange={(event) => updatePlan({ ...plan, demand_profile: event.target.value as DemandProfile })}>
      <option value="BASE">BASE · базовый</option><option value="LOW">LOW · низкий</option><option value="HIGH">HIGH · высокий</option>
    </select><p className="field-hint">{plan.scenario === 'MANDATORY_STRESS' ? 'STRESS использует базовый спрос со своим шоком. LOW/HIGH доступны отдельно в режиме BASE.' : plan.demand_profile === 'HIGH' ? 'HIGH: +10% в 2035–2037 и +25% в 2038–2040. Критическая доля каждого года сохраняется.' : plan.demand_profile === 'LOW' ? 'LOW: −20% во все годы. Критическая доля каждого года сохраняется.' : 'LOW/HIGH — отдельные исследования по исходным данным кейса.'}</p></div>
    <div className="control-section-heading"><h3>Годовые заказы</h3><span>тонн / {year}</span></div>
    <div className="source-controls">
      {caseData.sources.map((source) => <div className="source-control" key={source.source_id} style={{ '--source-color': sourceColors[source.source_id] } as React.CSSProperties}>
        <div className="source-title"><label htmlFor={`order-${source.source_id}`}><span className="source-letter">{source.source_id}</span><span>{source.name}</span></label><span className="source-limit">до {number(source.capacity_t_per_year, 0)} т/год</span></div>
        <div className="source-inputs"><input id={`order-${source.source_id}`} type="range" min={0} max={Math.max(source.capacity_t_per_year, plan.yearly_orders[year][source.source_id])} step={1} value={plan.yearly_orders[year][source.source_id]} aria-label={`Заказ ${source.name}, ${year}, ползунок`} onChange={(event) => updateOrder(source.source_id, Number(event.target.value))} />
          <NumericInput label={`Заказ ${source.name}, ${year}, тонн`} value={plan.yearly_orders[year][source.source_id]} onChange={(value) => updateOrder(source.source_id, value)} /></div>
        <div className="source-meta"><span>{number(source.variable_cost_mln_per_t)} млн/т · ToP {percent(source.take_or_pay_share, 0)}</span><span>Поставка: {row?.source_breakdown[source.source_id] ? `${number(row.source_breakdown[source.source_id].delivered_t)} т` : '—'}</span></div>
      </div>)}
    </div>
    {Object.values(plan.additional_orders?.[year]??{}).some(q=>(q??0)>0)&&<div className="analytics-note"><strong>Дозаказы после шока, {year}</strong>{Object.entries(plan.additional_orders[year]).map(([source,quantity])=><p key={source}>{source}: +{number(quantity??0,2)} т — график прибытия в таблице поставок.</p>)}</div>}
    <div className="control-section-heading investment-heading"><h3>Инвестиции</h3><span>весь горизонт</span></div>
    <div className="investments">
      {investmentRows.map(({ key, title, detail, fallback, years }) => <div className="investment-row" key={key}>
        <label className="investment-label"><input className="toggle-input" type="checkbox" checked={plan.investments[key] !== null} onChange={(event) => updateInvestment(key, event.target.checked ? fallback : null)} aria-label={`Включить: ${title}`} /><span className="toggle-track" aria-hidden="true" /><span><strong>{title}</strong><small>{detail}</small></span></label>
        <select aria-label={`Год: ${title}`} disabled={plan.investments[key] === null} value={plan.investments[key] ?? fallback} onChange={(event) => updateInvestment(key, Number(event.target.value))}>
          {plan.investments[key] !== null && !years.includes(plan.investments[key]!) && <option value={plan.investments[key]!}>{plan.investments[key]} !</option>}
          {years.map((value) => <option key={value} value={value}>{value}</option>)}
        </select>
      </div>)}
    </div>
    <details className="advanced-controls"><summary>Допущения и бронь <ChevronDown size={14} /></summary><div className="advanced-grid">
      <label>Начальный запас, т<NumericInput label="Начальный запас, тонн" value={plan.initial_inventory_t} onChange={(value) => updatePlan({ ...plan, initial_inventory_t: value })} /></label>
      <label>Ставка дисконта, %<NumericInput label="Ставка дисконтирования, процентов" value={Number((plan.discount_rate * 100).toFixed(6))} max={100} onChange={(value) => updatePlan({ ...plan, discount_rate: value / 100 })} /></label>
      <label>Подготовка C, мес.<NumericInput label="Срок подготовки C после исполнения опциона, месяцев" value={plan.c_lead_months} min={18} max={24} step={1} onChange={(value) => updatePlan({ ...plan, c_lead_months: value })} /></label>
      <label>Доставка C после ввода, мес.<NumericInput label="Допущение: срок доставки C после ввода, месяцев" value={plan.c_delivery_lead_months} min={0} max={24} step={1} onChange={(value) => updatePlan({ ...plan, c_delivery_lead_months: value })} /></label>
      <label>Доступная новая мощность, %<NumericInput label="Условный рынок: доступная доля свободной мощности, процентов" value={plan.new_capacity_fraction*100} min={0} max={100} step={5} onChange={(value) => updatePlan({ ...plan, new_capacity_fraction: value/100 })} /></label>
      <label>Lead time D, мес.<NumericInput label="Срок поставки D, месяцев" value={plan.d_lead_months} min={1} max={2} step={0.1} onChange={(value) => updatePlan({ ...plan, d_lead_months: value })} /></label>
      <label>Целевой резерв, дней<NumericInput label="Целевой физический резерв, дней" value={plan.reserve_target_days ?? 45} min={45} max={90} step={1} onChange={(value) => updatePlan({ ...plan, reserve_target_days: value })} /></label>
      <label>Множитель спроса<NumericInput label="Исследовательский множитель спроса" value={plan.demand_factor} step={0.05} max={1000} onChange={(value) => updatePlan({ ...plan, demand_factor: value })} /></label>
      <label>Множитель цены<NumericInput label="Исследовательский множитель цены" value={plan.price_factor} step={0.05} max={1000} onChange={(value) => updatePlan({ ...plan, price_factor: value })} /></label>
    </div><p className="field-hint">Подготовка C: 18–24 месяца после исполнения опциона. Доставка после ввода: допущение команды, по умолчанию 4 месяца; экспертами не задана. Доля новой мощности применяется только к условной реакции на шаге 2; основная использует прежнюю бронь. Множитель спроса применяется ко всему горизонту; значения, отличные от 1, — отдельное исследование.</p>
      <h4>Явная бронь на {year}, т/год</h4><p className="field-hint">Пустое поле — бронь под исходный заказ. Ноль — явно нулевая бронь. В реакции исходная мощность сохраняется; свободная техническая мощность не означает доступный новый контракт.</p>
      <div className="reservation-inputs">{caseData.sources.map((source) => <label key={source.source_id}>{source.source_id}<input className="number-input" type="number" min={0} step={0.1} placeholder="Авто" aria-label={`Бронь мощности ${source.name}, ${year}, тонн в год`} value={plan.yearly_reservations?.[year]?.[source.source_id] ?? ''} onChange={(event) => updateReservation(source.source_id, event.target.value)} /></label>)}</div>
    </details>
    <button type="button" className="button optimize-button" onClick={onOptimize} disabled={disabled || optimizing}>{optimizing ? <LoaderCircle size={17} className="spin" /> : <Sparkles size={17} />}{optimizing ? 'Подбираем заказы…' : 'Оптимизировать план заранее'}</button>
    </fieldset><p className="optimize-caption">Минимум NPV при фиксированных инвестициях и 100% обслуживании. Оптимизация изменит доступные заказы на весь горизонт. В отчёте реакции на шок ранее размещённые годовые контракты фиксируются.</p>
  </aside>;
}
