import type { Calculation, Plan } from '../types';
import { number, percent } from '../format';

type Kpi=Calculation['kpi_summary']&{feasible:boolean};
type Evaluation={after:Kpi|null;full_recovery:boolean;error:string|null;plan:Plan|null};
export interface DecisionStudy {
  rows:{strategy_id:string;name:string;base:Kpi;plan:Plan;mandatory:Evaluation;common_earth:Evaluation}[];
  preparation:string;
  recommendation:{status:string;message?:string;name?:string;plan?:Plan;cost_reference_name?:string;premium_base_mln?:number;avoided_common_shortage_t?:number;avoided_common_critical_t?:number;base?:Kpi;mandatory?:Kpi;common_earth?:Kpi;rule?:string;limits?:string;unverified_candidates?:string[]};
}
export interface Evidence {id:string;kind:string;title:string;claim:string;source:string;limitation:string}
export interface LeadSensitivity {rows:{months:number;kpi:Kpi|null;full_recovery:boolean;error:string|null}[];note:string}

export default function DecisionCase({study,evidence,sensitivity,openPlan,disabled}:{study:DecisionStudy;evidence:Evidence[];sensitivity:LeadSensitivity;openPlan:(p:Plan)=>void;disabled:boolean}) {
  const choice=study.recommendation;
  const recommended=study.rows.find(row=>row.name===choice.name);
  return <>
    {choice.status==='calculated'?<div className="resilience-card">
      <strong>Рекомендуемый кандидат: {choice.name}</strong>
      <p>{choice.rule}</p>
      <div className="analytics-metrics"><div><span>Доплата в BASE относительно «{choice.cost_reference_name}»</span><strong>{number(choice.premium_base_mln!,2)} млн NPV</strong></div><div><span>Меньше дефицита при общем земном сбое</span><strong>{number(choice.avoided_common_shortage_t!,2)} т</strong><small>Из них критического: {number(choice.avoided_common_critical_t!,2)} т</small></div><div><span>Остаточный дефицит в общем сбое</span><strong>{number(choice.common_earth!.total_shortage,2)} т</strong><small>Критический сервис: {percent(choice.common_earth!.min_critical_service_level,2)}</small></div></div>
      <p><b>Риск:</b> общая земная инфраструктура одновременно ограничивает A/B/C/E. <b>Мера:</b> выбранные инвестиции, предварительная бронь и физический запас. <b>Проверка:</b> обязательный стресс и общий сбой рассчитаны отдельно; параметры и остаток показаны ниже.</p>
      <p>NPV всего горизонта: BASE {number(choice.base!.npv,2)} млн; обязательный STRESS после реакции {number(choice.mandatory!.npv,2)} млн; общий земной сбой после реакции {number(choice.common_earth!.npv,2)} млн. Стоимость при дефиците не является экономией равноценного сервиса.</p>
      <p className={choice.common_earth!.feasible?'':'text-warning'}>Общий сбой: {choice.common_earth!.feasible?'формальные ограничения выполнены':'остались нарушения ограничений'}; критический дефицит {number(choice.common_earth!.total_critical_shortage,2)} т. {choice.limits}</p>
      {!!choice.unverified_candidates?.length&&<p className="text-warning">Для части кандидатов расчёт не подтверждён: {choice.unverified_candidates.join(', ')}. Рекомендация относится только к проверенным вариантам.</p>}
      <button className="button button-primary" disabled={disabled} onClick={()=>choice.plan&&openPlan(choice.plan)}>Открыть рекомендуемый план до шока</button>
      {recommended?.common_earth.plan&&<button className="button" disabled={disabled} onClick={()=>recommended.common_earth.plan&&openPlan(recommended.common_earth.plan)}>Посмотреть остаточные нарушения общего сбоя</button>}
    </div>:<p className="analytics-note text-warning">{choice.message}</p>}
    <h3 className="analytics-subheading">За что платим и какой риск остаётся</h3>
    <p className="analytics-note">Общий сбой — отдельное допущение: A/B/C/E поставляют 50% плана в 2038–2039; D не затронут. Вероятность не назначена. Во всех реакциях ниже разрешена только заранее обеспеченная мощность. {study.preparation}</p>
    <div className="table-scroll"><table><caption className="sr-only">Обоснование выбора при обязательном и общем земном стрессе</caption><thead><tr><th>Стратегия</th><th>NPV BASE, млн</th><th>Обязательный STRESS</th><th>Общий сбой: дефицит / критический, т</th><th>Общий сбой: крит. сервис</th><th>Остаточные ограничения</th></tr></thead><tbody>{study.rows.map(row=><tr key={row.strategy_id}><th>{row.name}</th><td>{number(row.base.npv,2)}</td><td>{row.mandatory.error?'Не подтверждён':row.mandatory.full_recovery?'Полное восстановление':'Есть дефицит или нарушения'}</td><td>{row.common_earth.after?`${number(row.common_earth.after.total_shortage,2)} / ${number(row.common_earth.after.total_critical_shortage,2)}`:row.common_earth.error}</td><td>{row.common_earth.after?percent(row.common_earth.after.min_critical_service_level,2):'—'}</td><td>{row.common_earth.after?(row.common_earth.after.feasible?'Выполнены':'Нарушены'):'Не проверено'}</td></tr>)}</tbody></table></div>
    <details className="analytics-note"><summary>Проверка допущения о сроке доставки C</summary><p>18–24 месяца подготовки сохраняются. Ниже меняется только срок доставки после ввода; новые контракты условно считаются доступными. Ноль месяцев — оптимистичная граница, а не физическая характеристика.</p><div className="table-scroll"><table><thead><tr><th>Доставка C, мес.</th><th>NPV STRESS, млн</th><th>Дефицит, т</th><th>Результат</th></tr></thead><tbody>{sensitivity.rows.map(row=><tr key={row.months}><th>{number(row.months,0)}</th><td>{row.kpi?number(row.kpi.npv,2):'—'}</td><td>{row.kpi?number(row.kpi.total_shortage,2):'—'}</td><td>{row.error??(row.full_recovery?'Полное восстановление':'Частичное восстановление')}</td></tr>)}</tbody></table></div></details>
    <details className="analytics-note"><summary>Основания: условия кейса, эксперты, источники и наши допущения</summary>{evidence.map(item=><div className="evidence-item" key={item.id}><strong>{item.kind} · {item.title}</strong><p>{item.claim}</p><p>{item.source.startsWith('https://')?<a href={item.source} target="_blank" rel="noreferrer">Первоисточник</a>:item.source}</p><p><b>Граница применимости:</b> {item.limitation}</p></div>)}</details>
  </>;
}
