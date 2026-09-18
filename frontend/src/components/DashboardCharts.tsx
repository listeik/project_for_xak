import { useMemo } from 'react';
import { Activity, Network, Wallet } from 'lucide-react';
import Chart from './Chart';
import { number, sourceColors } from '../format';
import type { AnnualBalance, Calculation, CaseData, SourceId } from '../types';

const textColor = '#8393AC';
const gridLine = '#233045';
const tooltip = { backgroundColor: '#172132', borderColor: '#34435B', textStyle: { color: '#EDF4FF', fontFamily: 'Segoe UI, sans-serif' }, confine: true };
const font = { fontFamily: 'Segoe UI, sans-serif' };
const positions: Record<SourceId, [number, number]> = { A: [65, 68], B: [32, 207], C: [98, 337], D: [410, 68], E: [460, 207] };

export function LogisticsGraph({ row, caseData, year, setYear }: {
  row: AnnualBalance; caseData: CaseData; year: number; setYear: (year: number) => void;
}) {
  const option = useMemo(() => {
    const fill = Math.min(1, Math.max(0, row.end_inventory / row.storage_capacity));
    const nodes = caseData.sources.map((source) => ({
      id: source.source_id, name: source.name, value: row.source_breakdown[source.source_id].delivered_t,
      x: positions[source.source_id][0], y: positions[source.source_id][1], symbolSize: 39,
      itemStyle: { color: '#152333', borderWidth: 2, borderColor: sourceColors[source.source_id] },
      label: { show: true, position: 'bottom', color: '#D2DDED', fontSize: 11, lineHeight: 18, formatter: `${source.source_id} · ${source.name}\n${number(row.source_breakdown[source.source_id].delivered_t)} т` },
    }));
    const links = caseData.sources.map((source) => ({
      source: source.source_id, target: 'HUB', value: row.source_breakdown[source.source_id].delivered_t,
      lineStyle: {
        color: sourceColors[source.source_id],
        width: Math.max(1, Math.min(8, row.source_breakdown[source.source_id].delivered_t / 28)),
        opacity: row.source_breakdown[source.source_id].delivered_t > 0 ? 0.65 : 0.2,
        type: row.source_breakdown[source.source_id].delivered_t > 0 ? 'solid' : 'dashed', curveness: 0.06,
      },
    }));
    return {
      textStyle: font,
      tooltip: { ...tooltip, formatter: (params: { dataType: string; data: { name?: string; source?: string; target?: string; value?: number } }) => {
        const data = params.data;
        return params.dataType === 'edge' ? `${data.source} → ${data.target}: ${number(data.value ?? 0)} т`
          : `${data.name}: ${number(data.value ?? 0)} т`;
      } },
      series: [{
        type: 'graph', layout: 'none', roam: false, left: '11%', right: '12%', top: '11%', bottom: '19%',
        edgeSymbol: ['none', 'arrow'], edgeSymbolSize: 7, emphasis: { focus: 'adjacency' },
        data: [...nodes, {
          id: 'HUB', name: 'Остаток в орбитальном узле', x: 249, y: 188, symbolSize: 114, value: row.end_inventory,
          itemStyle: { borderColor: '#00F0FF', borderWidth: 2, color: {
            type: 'linear', x: 0, y: 0, x2: 0, y2: 1,
            colorStops: [{ offset: 0, color: '#112331' }, { offset: Math.max(0, 1 - fill - 0.001), color: '#112331' }, { offset: 1 - fill, color: '#16606E' }, { offset: 1, color: '#0D3A49' }],
          } },
          label: { show: true, position: 'inside', color: '#E8FFFF', fontSize: 13, fontWeight: 600, lineHeight: 20,
            formatter: `ORBITAL HUB\n${number(row.end_inventory)} / ${number(row.storage_capacity, 0)} т` },
        }, {
          id: 'DEMAND', name: 'Выдано цислунарным миссиям', x: 320, y: 358, symbol: 'roundRect', symbolSize: [74, 34], value: row.served_total,
          itemStyle: { color: '#25203B', borderColor: '#A276FF', borderWidth: 1 },
          label: { show: true, color: '#E2D6FF', position: 'bottom', fontSize: 11, lineHeight: 18, formatter: `Миссии\n${number(row.served_total)} т` },
        }],
        links: [...links, { source: 'HUB', target: 'DEMAND', value: row.served_total, lineStyle: { color: '#A276FF', width: Math.max(2, Math.min(9, row.served_total / 40)), opacity: 0.8 } }],
      }],
    };
  }, [row, caseData]);
  return <section className="panel logistics-panel">
    <div className="panel-heading"><div><p className="eyebrow"><Network size={13} /> Сеть снабжения</p><h2>Орбитальный контур</h2></div><span className="small-badge">5 каналов · 1 узел</span></div>
    <div className="year-tabs" role="group" aria-label="Год редактирования плана">
      {caseData.years.map((value) => <button key={value} type="button" aria-pressed={year === value} className={year === value ? 'active' : ''} onClick={() => setYear(value)}>{value}</button>)}
    </div>
    <Chart option={option} label={`Сеть поставок за ${row.year} год. Остаток в узле ${number(row.end_inventory)} тонн. Фактические поставки по каналам доступны в таблице ниже.`} className="network-chart" />
    <div className="network-caption"><span><i className="legend-dot cyan-dot" /> Толщина связи — фактическая поставка</span><span>Заполнение узла — остаток на конец года</span></div>
    <div className="network-stats">
      <div><span>Поступило</span><strong>{number(row.inflow)} <small>т</small></strong></div>
      <div><span>Спрос</span><strong>{number(row.demand_total)} <small>т</small></strong></div>
      <div><span>Потери</span><strong>{number(row.losses)} <small>т</small></strong></div>
      <div><span>Дефицит</span><strong className={row.shortage > 0.000001 ? 'text-danger' : ''}>{number(row.shortage)} <small>т</small></strong></div>
    </div>
  </section>;
}

export function InventoryChart({ result }: { result: Calculation }) {
  const option = useMemo(() => ({
    animation: false, textStyle: font, tooltip: { ...tooltip, trigger: 'axis', valueFormatter: (value: number) => `${number(value, 2)} т` },
    grid: { left: 44, right: 18, top: 35, bottom: 76 },
    legend: { top: 0, left: 0, textStyle: { color: textColor, fontSize: 10 }, itemWidth: 14, itemHeight: 7 },
    xAxis: { type: 'category', boundaryGap: false, data: result.inventory_trace.map((point) => point.date), axisLine: { lineStyle: { color: gridLine } }, axisLabel: { color: textColor, fontSize: 10, formatter: (value: string) => value.slice(0, 4) }, axisTick: { show: false } },
    yAxis: { type: 'value', name: 'т', nameTextStyle: { color: textColor }, axisLabel: { color: textColor, fontSize: 10 }, splitLine: { lineStyle: { color: gridLine, type: 'dashed' } } },
    dataZoom: [{ type: 'inside', filterMode: 'none' }, { type: 'slider', bottom: 8, height: 19, borderColor: gridLine, fillerColor: '#00F0FF18', handleStyle: { color: '#00B8C8' }, textStyle: { color: textColor, fontSize: 10 } }],
    series: [
      { name: 'Физический запас', type: 'line', data: result.inventory_trace.map((point) => point.inventory), symbol: 'none', lineStyle: { color: '#00F0FF', width: 2 }, itemStyle: { color: '#00F0FF' }, areaStyle: { color: '#00F0FF0F' } },
      { name: '45-дневный резерв', type: 'line', data: result.inventory_trace.map((point) => point.reserve), symbol: 'none', lineStyle: { color: '#A276FF', type: 'dashed', width: 1.5 }, itemStyle: { color: '#A276FF' } },
      { name: 'Ёмкость', type: 'line', data: result.inventory_trace.map((point) => point.capacity), symbol: 'none', lineStyle: { color: '#69778E', type: 'dotted', width: 1 }, itemStyle: { color: '#69778E' } },
    ],
  }), [result]);
  return <section className="panel"><div className="panel-heading"><div><p className="eyebrow"><Activity size={13} /> Материальный баланс</p><h2>Запас топлива по дням</h2></div><span className="small-badge">2035–2040</span></div><Chart option={option} label="Дневной физический запас, 45-дневный норматив резерва и ёмкость хранилища с 2035 по 2040 год" className="balance-chart" /><p className="chart-note">Линия резерва показана для ориентира; формальная проверка — на начало каждого года.</p></section>;
}

export function FinanceChart({ result }: { result: Calculation }) {
  const option = useMemo(() => ({
    textStyle: font, tooltip: { ...tooltip, trigger: 'axis', axisPointer: { type: 'shadow' }, valueFormatter: (value: number) => `${number(value)} млн` },
    legend: { top: 0, left: 0, itemGap: 12, itemWidth: 8, itemHeight: 8, textStyle: { color: textColor, fontSize: 10 } },
    grid: { left: 47, right: 14, top: 61, bottom: 25 },
    xAxis: { type: 'category', data: result.financial_breakdown.annual.map((row) => String(row.year)), axisLabel: { color: textColor, fontSize: 10 }, axisLine: { lineStyle: { color: gridLine } }, axisTick: { show: false } },
    yAxis: { type: 'value', axisLabel: { color: textColor, fontSize: 10 }, splitLine: { lineStyle: { color: gridLine, type: 'dashed' } } },
    series: ([
      ['procurement', 'Закупки', '#00CEDD'], ['reservation', 'Бронь', '#4F91FF'], ['holding', 'Хранение', '#43D9A3'], ['fixed_opex', 'Пост. OPEX', '#FFB75C'], ['capex', 'CAPEX', '#9160F6'],
    ] as const).map(([key, name, color]) => ({ name, type: 'bar', stack: 'cost', barMaxWidth: 38, itemStyle: { color }, data: result.financial_breakdown.annual.map((row) => row[key]) })),
  }), [result]);
  return <section className="panel"><div className="panel-heading"><div><p className="eyebrow"><Wallet size={13} /> Финансовая модель</p><h2>Структура затрат</h2></div><span className="small-badge">млн ед. 2035</span></div><Chart option={option} label="Годовые затраты: закупки, бронь мощности, хранение, постоянный OPEX и CAPEX" className="balance-chart" /><p className="chart-note">Постоянные цены 2035 года · без дисконтирования на графике.</p></section>;
}
