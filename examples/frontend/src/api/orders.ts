import { get, post } from './http';

export async function fetchTodayOrders() {
  const today = new Date().toISOString().slice(0, 10);
  return get(`/orders?day=${today}`);
}

export async function fetchOrdersFrom(day: string) {
  const from = new Date(day);
  from.setHours(0, 0, 0, 0);
  return get(`/orders?from=${from.toISOString()}`);
}

export async function fetchOrdersSince(createdAt: string) {
  const stamp = new Date(createdAt);
  stamp.setHours(0, 0, 0, 0);
  return get(`/orders?since=${stamp.toISOString()}`);
}

export async function scheduleShift(note: string) {
  return post('/shifts', { note, startsAt: new Date().toISOString(), createdAt: new Date().toISOString() });
}

export async function scheduleLocal(note: string, startsAt: string) {
  return post('/shifts', { note, startsAt });
}
