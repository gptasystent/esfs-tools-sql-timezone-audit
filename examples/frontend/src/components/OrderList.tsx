import React from 'react';
import { formatujDateWarszawa } from '../lib/dates';

type Order = { id: number; createdAt: string; dueDate: string; total: number };

export function OrderList({ orders }: { orders: Order[] }) {
  return (
    <ul>
      {orders.map((o) => {
        const created = new Date(o.createdAt);
        const hour = created.getHours();
        return (
          <li key={o.id}>
            <span>{created.toLocaleString('pl-PL')}</span>
            <span>{new Date('2026-10-19T10:00:00Z').toLocaleTimeString('pl-PL')}</span>
            <span>{new Date(o.dueDate).toLocaleDateString('pl-PL')}</span>
            <span>{formatujDateWarszawa(o.createdAt)}</span>
            <span>{o.total.toLocaleString('pl-PL')} zł</span>
            <em>Don't panic, godzina: {hour}</em>
          </li>
        );
      })}
    </ul>
  );
}
