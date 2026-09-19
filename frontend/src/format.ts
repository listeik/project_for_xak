export const number = (value: number, digits = 1) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
export const percent = (value: number, digits = 1) =>
  new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
export const sourceColors: Record<string,string> = new Proxy({ A: '#00D9E8', B: '#4F91FF', C: '#A276FF', D: '#43D9A3', E: '#FFB75C' } as Record<string,string>, {get(target,key:string) { return target[key] ?? `hsl(${Array.from(key).reduce((sum,c)=>sum+c.charCodeAt(0)*47,0)%360} 70% 65%)`; }});
