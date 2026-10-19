import React, { useState } from 'react';

export function DeliveryFilter() {
  const [picked] = useState('2026-10-19');
  const limit = new Date('2026-10-19');
  const isLate = limit < new Date();
  const lateText = '2026-10-19' < new Date();
  const label = new Date('2026-10-19').toLocaleDateString('pl-PL');
  const parsed = Date.parse('2026-10-20');
  const local = new Date('2026-10-19T00:00:00');
  return (
    <p>
      {String(isLate)} {String(lateText)} {label} {parsed} {picked} {String(local)}
    </p>
  );
}
