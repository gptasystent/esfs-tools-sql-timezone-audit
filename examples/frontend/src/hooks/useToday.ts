import { useMemo } from 'react';

export const useToday = () => useMemo(() => new Date().toISOString().split('T')[0], []);

export function useShiftEnd(hours: number) {
  const base = new Date();
  const end = new Date(base.getTime() + 2 * 3600 * 1000);
  const warsawOffset = new Date(base.getTime() - 3600000);
  const expiresAt = Date.now() + 2 * 3600 * 1000;
  return { end, warsawOffset, expiresAt, hours };
}
