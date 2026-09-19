import type { AdaptedResponse, Calculation, Plan } from '../types';
import { useState } from 'react';
import { number, percent, localizedMessage } from '../format';
import Chart from './Chart';

export interface StressReport {
  base:Calculation;stress:Calculation;delta_npv_mln:number;delta_shortage_t:number;
  locked_contracts:unknown[];adaptation:AdaptedResponse|null;adaptation_error:{message:string}|null;
  conditional_adaptation:AdaptedResponse|null;conditional_adaptation_error:{message:string}|null;
}
export default function ResponsePanel({report,openPlan,disabled}:{report:StressReport;openPlan:(plan:Plan)=>void;disabled:boolean}) {
  const [conditional,setConditional]=useState(false);
  const response=conditional?report.conditional_adaptation:report.adaptation;
  const variants=[{name:'1. Исходный BASE',result:report.base},{name:'2. Шок без действий',result:report.stress},
    ...(report.adaptation?[{name:'3. Только забронированная мощность',result:report.adaptation.result}]:[]),
    ...(report.conditional_adaptation?[{name:'4. Если новые контракты доступны',result:report.conditional_adaptation.result}]:[])];
  return <>
    <p className="analytics-note">Дата решения — 1 января 2038. Исходная договорная мощность и размещённые заказы сохраняются. Новая мощность не гарантирована: основной расчёт использует только бронь, условный — допускает новые контракты в пределах свободной мощности. Оба учитывают сроки доставки и физические срывы поставок.</p>
    <div className="table-scroll"><table><caption className="sr-only">До шока, без действий и после адаптации</caption><thead><tr><th>Вариант</th><th>NPV, млн</th><th>Общий / критический сервис</th><th>Дефицит / критический, т</th><th>Нарушения резерва</th></tr></thead><tbody>{variants.map(({name,result})=><tr key={name}><th>{name}</th><td>{number(result.kpi_summary.npv,2)}</td><td>{percent(result.kpi_summary.min_service_level)} / {percent(result.kpi_summary.min_critical_service_level)}</td><td>{number(result.kpi_summary.total_shortage,2)} / {number(result.kpi_summary.total_critical_shortage,2)}</td><td>{result.violation_details.filter(v=>v.code.startsWith('RESERVE_VIOLATED_')).map(v=>v.year).join(', ')||'Нет'}</td></tr>)}</tbody></table></div>
    <div className="analytics-actions"><button className="button" aria-pressed={!conditional} onClick={()=>setConditional(false)}>Действия в пределах брони</button><button className="button" aria-pressed={conditional} onClick={()=>setConditional(true)}>Условно: новые контракты доступны</button></div>
    {conditional&&<p className="analytics-note text-warning">Это исследовательский вариант: предполагается доступность {percent(report.conditional_adaptation?.plan.new_capacity_fraction??1,0)} свободной мощности. Перед применением нужны договоры с поставщиками; результат не является гарантией восстановления.</p>}
    {response?<>
      <div className="analytics-metrics"><div><span>Доплата за реакцию в STRESS</span><strong>{number(response.optimization.additional_npv_mln,2)} млн</strong></div><div><span>Предотвращённый дефицит</span><strong>{number(response.optimization.avoided_shortage_t,2)} т</strong></div><div><span>Результат реакции</span><strong>{response.optimization.full_recovery?'Полное восстановление':'Частичное восстановление'}</strong><small>{response.optimization.full_recovery?'Дефицита и формальных нарушений нет':'Оставшиеся нарушения не скрыты'}</small></div></div>
      <Chart className="balance-chart" label="Запас исходного плана, после шока и после адаптации" option={{animation:false,tooltip:{trigger:'axis'},legend:{data:variants.map(v=>v.name),textStyle:{color:'#a6b9d2'}},grid:{left:50,right:20,top:65,bottom:35},xAxis:{type:'category',data:report.base.inventory_trace.map(p=>p.date),axisLabel:{color:'#8b9bb2',formatter:(s:string)=>s.slice(0,4)}},yAxis:{type:'value',name:'т',axisLabel:{color:'#8b9bb2'},splitLine:{lineStyle:{color:'#233045'}}},series:variants.map((v,i)=>({name:v.name,type:'line',symbol:'none',data:v.result.inventory_trace.map(p=>p.inventory),itemStyle:{color:['#4f91ff','#ff6488','#43d9a3','#efb35e'][i]}}))}}/>
      <h3 className="analytics-subheading">Какие действия предлагает расчёт</h3>
      <div className="table-scroll"><table><caption className="sr-only">Изменения заказов после шока</caption><thead><tr><th>Действие</th><th>Год / канал</th><th>Объём, т</th><th>Факт, т</th><th>Первый заказ</th><th>Первый приход</th><th>Закупка + новая бронь, млн</th></tr></thead><tbody>{response.actions.map((action,i)=><tr key={i}><th>{action.kind==='additional'?'Новый дозаказ':'Изменить будущий заказ'}</th><td>{action.year} / {action.source}</td><td>{action.before_t!==undefined?`${number(action.before_t,2)} → `:''}{number(action.ordered_t,2)}</td><td>{number(action.delivered_t,2)}</td><td>{action.first_order_date}</td><td>{action.first_arrival_date}</td><td>{action.procurement_mln!==undefined?number(action.procurement_mln+(action.reservation_mln??0),2):'В общей стоимости'}</td></tr>)}</tbody></table></div>
      {!response.actions.length&&<p className="analytics-note">Дополнительных допустимых действий не найдено или они не улучшают выбранные цели.</p>}
      {response.result.violation_details.length>0&&<div className="analytics-note text-warning"><strong>Остались нарушения:</strong>{response.result.violation_details.map((v,i)=><p key={i}>{localizedMessage(v.message)}</p>)}</div>}
      <p className="analytics-note">{response.optimization.explanation} Суммы в строках дозаказов — без дисконтирования; доплата сверху учитывает все изменения затрат. Необслуженный спрос не переносится на следующий день.</p>
      <div className="analytics-actions"><button className="button button-primary" disabled={disabled} onClick={()=>openPlan(response.plan)}>Применить реакцию к рабочему плану</button></div>
    </>:<p className="analytics-note text-warning">Результат реакции не подтверждён: {(conditional?report.conditional_adaptation_error:report.adaptation_error)?.message}</p>}
  </>;
}
