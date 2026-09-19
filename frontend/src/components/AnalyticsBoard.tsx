import { useEffect, useRef, useState } from 'react';
import { FlaskConical, Download, LoaderCircle, BarChart3 } from 'lucide-react';
import { analyticalReport, exportContest, extensionDemo, getDefaultPlan } from '../api';
import { number, percent } from '../format';
import type { Calculation, Plan } from '../types';
import Chart from './Chart';

type Kpi = Calculation['kpi_summary'] & {feasible:boolean};
interface Strategy { strategy_id:string; name:string; description:string; plan:Plan; kpi:Kpi; optimization_error:{message:string}|null }
interface Comparison {rows:Strategy[];lowest_cost_feasible_strategy:string|null}
interface Risk {id:string;risk_name:string;cause:string;owner:string;period:number[];impact_tons:number;impact_cost_mln:number;impact_service_level:number;mitigation_cost_mln:number;mitigation_measure:string;residual_risk:Kpi;measure_status:string}
interface Report {
  generated_at:string; plan_hash:string; model_version:string;
  comparisons:{base:Comparison;stress:Comparison;resilience:{status:string;price_of_resilience_mln?:number;avoided_shortage_t?:number;resilient_base_plan?:Plan;note:string}};
  stress_impact:{base:Calculation;stress:Calculation;delta_npv_mln:number;delta_shortage_t:number;locked_contracts:unknown[];adaptation:{plan:Plan;result:Calculation}|null;adaptation_error:{message:string}|null};
  crash_limits:{limits:{parameter:string;status:string;safe_value:number|null;failure_value:number|null}[]};
  sensitivity:(Kpi & {demand_factor?:number;D_delivery_factor?:number;A_price_factor?:number})[];
  risk_register:{rows:Risk[]};
  geopolitical:{alternatives:{strategy_id:string;name:string;before?:Kpi;after?:Kpi;error?:string}[]};
  validation:{passed:boolean;rows:{test_id:string;status:string}[]};
}

export default function AnalyticsBoard({plan,updatePlan,disabled}:{plan:Plan;updatePlan:(plan:Plan)=>void;disabled:boolean}) {
  const [report,setReport]=useState<Report|null>(null);
  const [busy,setBusy]=useState('');
  const [error,setError]=useState('');
  const [notice,setNotice]=useState('');
  const [tab,setTab]=useState<'strategies'|'stress'|'risks'|'geo'>('strategies');
  const [scenario,setScenario]=useState<'base'|'stress'>('base');
  const [geoSource,setGeoSource]=useState('A');
  const [geoPrice,setGeoPrice]=useState(35);
  const [geoDelivery,setGeoDelivery]=useState(60);
  const [geoStart,setGeoStart]=useState(2038);
  const [geoEnd,setGeoEnd]=useState(2039);
  const original=useRef<Plan|null>(null);
  const controller=useRef<AbortController|null>(null);
  useEffect(()=>{controller.current?.abort();setReport(null);setError('');setNotice('');setBusy('');return()=>controller.current?.abort();},[plan]);
  useEffect(()=>{
    const years=Object.keys(plan.yearly_orders).map(Number);
    if (!(geoSource in plan.yearly_orders[years[0]])) setGeoSource('A');
    if (!years.includes(geoStart)) setGeoStart(2038);
    if (!years.includes(geoEnd)) setGeoEnd(2039);
  },[plan,geoSource,geoStart,geoEnd]);
  async function run() {
    const request=new AbortController();controller.current=request;setBusy('report');setError('');
    try {const result=await analyticalReport<Report>(plan,request.signal);if(!request.signal.aborted)setReport(result);}
    catch(e){if(!request.signal.aborted)setError(e instanceof Error?e.message:'Ошибка аналитики');}
    finally{if(controller.current===request)setBusy('');}
  }
  async function extend() {
    const request=new AbortController();controller.current=request;setBusy('extension');setError('');
    try {
      if(plan.research_config){const restored=original.current ?? await getDefaultPlan(request.signal);if(!request.signal.aborted)updatePlan(restored);}
      else {const result=await extensionDemo(plan,request.signal);original.current=plan;if(!request.signal.aborted)updatePlan(result.plan);}
    }catch(e){if(!request.signal.aborted)setError(e instanceof Error?e.message:'Ошибка конфигурации');}
    finally{if(controller.current===request)setBusy('');}
  }
  async function exportReport(format:'json'|'csv') {
    setBusy(format);setError('');setNotice('');
    try {await exportContest(plan,format);setNotice(`Отчёт ${format.toUpperCase()} передан браузеру для скачивания.`);}catch(e){setError(e instanceof Error?e.message:'Ошибка выгрузки');}finally{setBusy('');}
  }
  const unavailable=disabled || !!busy;
  const comparison=report?.comparisons[scenario];
  const resilience=report?.comparisons.resilience;
  const horizon=Object.keys(plan.yearly_orders).map(Number).sort((a,b)=>a-b);
  const label:Record<string,string>={demand_growth_pct:'Рост спроса с 2038, %',D_shortfall_pct:'Недопоставка D с 2038, %',D_delay_months:'Задержка окна D в 2038, мес.'};
  return <section className="panel analytics-board" id="analytics">
    <div className="panel-heading"><div><p className="eyebrow"><BarChart3 size={14}/> Обоснование решений</p><h2>Стратегии, устойчивость и доказательства</h2></div><button className="button button-primary" disabled={unavailable} onClick={()=>void run()}>{busy==='report'?<LoaderCircle className="spin" size={15}/>:<FlaskConical size={15}/>}Рассчитать аналитику</button></div>
    <p className="analytics-note">Три стратегии сравниваются на одинаковых BASE/STRESS, базовом профиле спроса и множителях 1. Инвестиции различаются; ставки, данные и явная бронь сохраняются. При изменении плана отчёт нужно пересчитать.</p>
    <div className="analytics-actions"><button className="button" disabled={unavailable} onClick={()=>void extend()}>{plan.research_config?'Вернуться к исходному набору':'🧪 6-й источник и горизонт до 2042'}</button><button className="button" disabled={unavailable} onClick={()=>void exportReport('json')}><Download size={14}/>Конкурсный отчёт JSON</button><button className="button" disabled={unavailable} onClick={()=>void exportReport('csv')}><Download size={14}/>Отчёт CSV</button></div>
    {plan.research_config && <details className="analytics-note"><summary className="text-warning">Исследовательская копия {plan.research_config.config_id}: допущения</summary><p>{plan.research_config.assumptions}</p><p>Заказы можно подобрать кнопкой «Оптимизировать закупки».</p></details>}
    {plan.contract_lock && <p className="analytics-note text-warning">Загружен план с зафиксированными контрактами до шока. Их изменение будет показано как нарушение.</p>}
    {busy && <p role="status" className="analytics-note">{busy==='report'?'Рассчитываем стратегии, риски и пределы…':'Выполняем запрос…'}</p>}
    {error && <p role="alert" className="analytics-note text-danger">{error}</p>}
    {notice && <p role="status" className="analytics-note">{notice}</p>}
    <div className="table-tabs" role="group" aria-label="Раздел аналитики">{([['strategies','Сравнение стратегий'],['stress','BASE vs STRESS'],['risks','Риски и пределы'],['geo','Геополитика']] as const).map(([key,title])=><button key={key} className={tab===key?'active':''} aria-pressed={tab===key} onClick={()=>setTab(key)}>{title}</button>)}</div>
    {!report && tab!=='geo' && <p className="analytics-note">Нажмите «Рассчитать аналитику», чтобы получить сопоставимые результаты для текущего плана.</p>}
    {report && tab==='strategies' && <>
      <div className="analytics-actions"><button className="button" aria-pressed={scenario==='base'} onClick={()=>setScenario('base')}>BASE</button><button className="button" aria-pressed={scenario==='stress'} onClick={()=>setScenario('stress')}>STRESS</button></div>
      <div className="table-scroll"><table><caption className="sr-only">Сравнение трёх стратегий</caption><thead><tr><th>Стратегия</th><th>NPV, млн</th><th>CAPEX, млн</th><th>Общий / критический сервис</th><th>Макс. годовой дефицит, т</th><th>Стоимость, млн/т</th><th>Результат</th></tr></thead><tbody>{comparison?.rows.map(row=><tr key={row.strategy_id} className={comparison.lowest_cost_feasible_strategy===row.strategy_id?'strategy-winner':''}><th>{row.name}{comparison.lowest_cost_feasible_strategy===row.strategy_id?' · минимум NPV':''}<small className="cell-detail">{row.description}</small></th><td>{number(row.kpi.npv,2)}</td><td>{number(row.kpi.total_capex,0)}</td><td>{percent(row.kpi.min_service_level)} / {percent(row.kpi.min_critical_service_level)}</td><td>{number(row.kpi.max_annual_shortage,2)}</td><td>{row.kpi.cost_per_served_ton===null?'—':number(row.kpi.cost_per_served_ton,3)}</td><td>{row.optimization_error?<span className="text-danger">{row.optimization_error.message}</span>:<button className="button" disabled={unavailable} onClick={()=>updatePlan(row.plan)}>Открыть план</button>}</td></tr>)}</tbody></table></div>
      {resilience?.status==='calculated'?<div className="resilience-card"><strong>Цена устойчивости: {number(resilience.price_of_resilience_mln!,2)} млн NPV</strong><span>Предотвращённый дефицит: {number(resilience.avoided_shortage_t!,2)} т</span><p>Дополнительные затраты сравниваются в BASE, дефицит — в STRESS. До 2038 контракты общие; поздние заказы зависят от сценария и lead time. Денежная стоимость срыва миссий не задана.</p><button className="button" disabled={unavailable} onClick={()=>resilience.resilient_base_plan&&updatePlan(resilience.resilient_base_plan)}>Открыть защищённый BASE-план</button></div>:<p className="analytics-note">Не найдено пары выполнимых планов для честного расчёта цены устойчивости.</p>}
      <p className="analytics-note">Стоимость тонны = (OPEX + CAPEX) / фактически выданные тонны. Закупки входят в OPEX один раз. Лидер выбран только среди этих трёх вариантов при 100% обслуживании.</p>
    </>}
    {report && tab==='stress' && <>
      <div className="analytics-metrics"><div><span>Изменение NPV</span><strong>{number(report.stress_impact.delta_npv_mln,2)} млн</strong></div><div><span>Дополнительный дефицит</span><strong>{number(report.stress_impact.delta_shortage_t,2)} т</strong></div><div><span>Зафиксировано контрактов</span><strong>{report.stress_impact.locked_contracts.length}</strong></div></div>
      <Chart className="balance-chart" label="Запас BASE и STRESS при одних заказах" option={{tooltip:{trigger:'axis'},legend:{data:['BASE','STRESS'],textStyle:{color:'#a6b9d2'}},grid:{left:55,right:25,top:45,bottom:45},xAxis:{type:'category',data:report.stress_impact.base.inventory_trace.map(p=>p.date),axisLabel:{color:'#8b9bb2'}},yAxis:{type:'value',name:'т',axisLabel:{color:'#8b9bb2'}},series:[{name:'BASE',type:'line',symbol:'none',data:report.stress_impact.base.inventory_trace.map(p=>p.inventory),itemStyle:{color:'#00d9e8'}},{name:'STRESS',type:'line',symbol:'none',data:report.stress_impact.stress.inventory_trace.map(p=>p.inventory),itemStyle:{color:'#ff6488'}}]}}/>
      <p className="analytics-note">Годовой контракт фиксируется, если первая дата заказа раньше 2038. Существующие инвестиции и явная бронь сохраняются. Предположение консервативное: дробление годовых контрактов не моделируется.</p>
      {report.stress_impact.adaptation?<div className="analytics-actions"><span>Дефицит после допустимой адаптации: {number(report.stress_impact.adaptation.result.kpi_summary.total_shortage,2)} т</span><button className="button" disabled={unavailable} onClick={()=>updatePlan(report.stress_impact.adaptation!.plan)}>Открыть адаптированный план</button></div>:<p className="analytics-note text-warning">Полное восстановление после шока не найдено: {report.stress_impact.adaptation_error?.message}</p>}
    </>}
    {report && tab==='risks' && <>
      <div className="analytics-metrics">{report.crash_limits.limits.map(item=><div key={item.parameter}><span>{label[item.parameter]}</span><strong>{item.safe_value===null?'Уже есть дефицит':`${item.status==='not_reached_within_range'?'≥ ':''}${number(item.safe_value,3)}`}</strong><small>{item.failure_value!==null?`Первое нарушение около ${number(item.failure_value,3)}`:'Граница в диапазоне не достигнута'}</small></div>)}</div>
      <p className="analytics-note">Граница — появление дефицита &gt; 0,000001 т при неизменном плане. Резерв может нарушиться раньше. Задержка D означает закрытие окна поставки без компенсации пропущенного объёма; это неблагоприятный сценарий, не модель очереди транспорта.</p>
      <div className="table-scroll"><table><caption className="sr-only">Реестр рассчитанных рисков</caption><thead><tr><th>Риск / владелец</th><th>Δ дефицит, т</th><th>Δ NPV, млн</th><th>Δ сервис, п.п.</th><th>Цена меры, млн</th><th>Остаточный дефицит, т</th></tr></thead><tbody>{report.risk_register.rows.map(row=><tr key={row.id}><th>{row.id} · {row.risk_name}<small className="cell-detail">{row.owner} · {row.period.join('–')}</small><small className="cell-detail">{row.mitigation_measure}</small></th><td>{number(row.impact_tons,2)}</td><td>{number(row.impact_cost_mln,2)}</td><td>{number(row.impact_service_level*100,2)}</td><td>{number(row.mitigation_cost_mln,2)}</td><td className={row.residual_risk.has_shortage?'text-danger':''}>{number(row.residual_risk.total_shortage,2)}</td></tr>)}</tbody></table></div>
      <p className="analytics-note">Диапазоны собственных рисков — допущения команды. Вероятности не назначены. Отрицательная ΔNPV при дефиците не означает экономическую выгоду. Цена меры — изменение NPV относительно текущего BASE-плана, включая оптимизацию закупок; отрицательное значение означает, что новый план дешевле исходного. Договорные предложения сами по себе не снижают рассчитанный ущерб.</p>
      <div className="table-scroll"><table><caption className="sr-only">Матрица чувствительности</caption><thead><tr><th>Параметры</th><th>NPV, млн</th><th>Сервис</th><th>Дефицит, т</th><th>Ограничения</th></tr></thead><tbody>{report.sensitivity.map((row,i)=><tr key={i}><th>{row.A_price_factor?`Цена A ×${row.A_price_factor}`:`Спрос ×${row.demand_factor} / D ×${row.D_delivery_factor}`}</th><td>{number(row.npv,2)}</td><td>{percent(row.min_service_level)}</td><td>{number(row.total_shortage,2)}</td><td>{row.feasible?'Выполнены':'Нарушены'}</td></tr>)}</tbody></table></div>
    </>}
    {tab==='geo' && <div className="geo-controls"><p>Исследовательское событие: ограничение земного логистического коридора. Коэффициент цены применяется к агрегированной доставке в узел. Это условный сценарий, не политический прогноз.</p><div className="advanced-grid"><label>Канал<select aria-label="Канал геополитического шока" value={geoSource} onChange={e=>setGeoSource(e.target.value)}>{Object.keys(plan.yearly_orders[horizon[0]]).map(s=><option key={s}>{s}</option>)}</select></label><label>Изменение цены, %<input aria-label="Геополитика: изменение цены, процентов" className="number-input" type="number" min={-100} max={900} value={geoPrice} onChange={e=>setGeoPrice(Number(e.target.value))}/></label><label>Фактическая доля поставки, %<input aria-label="Геополитика: доля поставки, процентов" className="number-input" type="number" min={0} max={100} value={geoDelivery} onChange={e=>setGeoDelivery(Number(e.target.value))}/></label><label>Начало<select aria-label="Начало геополитического шока" value={geoStart} onChange={e=>setGeoStart(Number(e.target.value))}>{horizon.map(y=><option key={y}>{y}</option>)}</select></label><label>Окончание<select aria-label="Окончание геополитического шока" value={geoEnd} onChange={e=>setGeoEnd(Number(e.target.value))}>{horizon.map(y=><option key={y}>{y}</option>)}</select></label></div><div className="analytics-actions"><button className="button" disabled={unavailable || geoEnd<geoStart || geoPrice< -100 || geoPrice>900 || geoDelivery<0 || geoDelivery>100} onClick={()=>updatePlan({...plan,scenario:'BASE',demand_profile:'BASE',demand_factor:1,price_factor:1,research_shock:{scenario_id:'TEAM_GEOPOLITICAL_CUSTOM',description:'Условное ограничение логистического коридора: сценарное изменение агрегированной цены и фактической доли поставки.',start_year:geoStart,end_year:geoEnd,demand_factor:1,sources:{[geoSource]:{price_factor:1+geoPrice/100,delivery_factor:geoDelivery/100,capacity_factor:1,delay_months:0}},combination_rule:'standalone'}})}>Применить и пересчитать план</button><button className="button" disabled={unavailable||!plan.research_shock} onClick={()=>updatePlan({...plan,research_shock:null})}>Снять геополитический шок</button></div>
      {report && <><p>Контрольное сравнение: A поставляет 60%, цена A +35% в 2038–2039. Все три стратегии сохраняют заранее выбранные заказы.</p><div className="table-scroll"><table><thead><tr><th>Стратегия</th><th>NPV до / после, млн</th><th>Дефицит после, т</th></tr></thead><tbody>{report.geopolitical.alternatives.map(row=><tr key={row.strategy_id}><th>{row.name ?? row.strategy_id}</th><td>{row.before&&row.after?`${number(row.before.npv,2)} / ${number(row.after.npv,2)}`:row.error}</td><td>{row.after?number(row.after.total_shortage,2):'—'}</td></tr>)}</tbody></table></div></>}
    </div>}
    {report && <p className="analytics-note">Протокол: {report.validation.rows.filter(r=>r.status==='PASSED').length}/{report.validation.rows.length} пройдено · модель {report.model_version} · план {report.plan_hash.slice(0,12)} · {new Date(report.generated_at).toLocaleString('ru-RU')}. JSON содержит полную расчётную доказательную базу; CSV — поля с путями для восстановления структуры.</p>}
  </section>;
}
