import React from 'react';
import dayjs from 'dayjs';

export function ShiftForm({ send }: { send: (b: object) => void }) {
  const save = () => {
    send({ scheduledFor: new Date().toISOString() });
    send({ dueDate: Date.now() });
  };
  const dayStart = dayjs.utc('2026-10-19T22:00:00Z').startOf('day');
  const localStart = dayjs().startOf('day');
  const warsaw = dayjs('2026-10-19T22:00:00Z').tz('Europe/Warsaw').startOf('day');
  return <button onClick={save}>{String(dayStart)}{String(localStart)}{String(warsaw)}</button>;
}
