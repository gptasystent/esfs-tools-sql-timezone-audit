// Wspólne helpery dat sklepu z częściami (fikcyjne) - wzorzec poprawnego kodu.
const WARSAW = 'Europe/Warsaw';

export function dzisWarszawa(): string {
  return new Intl.DateTimeFormat('sv-SE', { timeZone: WARSAW }).format(new Date());
}

export function formatujDateWarszawa(iso: string): string {
  return new Date(iso).toLocaleString('pl-PL', { timeZone: WARSAW });
}

export function logStamp(): string {
  return new Date().toISOString().slice(0, 10); // tz-ok: tylko do nazwy pliku logu
}
