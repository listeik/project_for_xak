export const number = (value: number, digits = 1) =>
  new Intl.NumberFormat('ru-RU', { maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
export const percent = (value: number, digits = 1) =>
  new Intl.NumberFormat('ru-RU', { style: 'percent', maximumFractionDigits: digits, minimumFractionDigits: digits }).format(value);
export const sourceColors = { A: '#00D9E8', B: '#4F91FF', C: '#A276FF', D: '#43D9A3', E: '#FFB75C' };
