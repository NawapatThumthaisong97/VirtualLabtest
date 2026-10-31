import { describe, it, expect } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import InfraVisualizer from '../components/admin/InfraVisualizer';
import type { InfraMap } from '../services/adminDashboard';

const map: InfraMap = {
  clusters: [
    {
      id: 'k3s', type: 'k3s', name: 'K3s', status: 'ok', controlPlane: { node: 'master', ready: true },
      rooms: [{
        room: 'LC-123', status: 'ok', pcsTotal: 1, pcsReady: 1, pcsInUse: 0, nodes: ['worker-pete'],
        machines: [{ name: 'worker-pete', ready: true, inUse: false }],
      }],
    },
    { id: 'aws', type: 'cloud', name: 'AWS', status: 'ok', instancesRunning: 0, region: 'ap-southeast-1', rooms: null },
  ],
} as unknown as InfraMap;

describe('Infrastructure Visualizer → room floor', () => {
  it('click a room shows its machines (9 per row), click the room name goes back to the map', () => {
    render(<InfraVisualizer map={map} usage={{ rooms: [] }} status={undefined} />);

    fireEvent.click(screen.getByText('LC-123'));
    expect(screen.getByLabelText('worker-pete ว่าง')).toBeDefined();
    expect(screen.queryByText('Control plane')).toBeNull();

    fireEvent.click(screen.getByLabelText('Back from LC-123'));
    expect(screen.getByText('Control plane')).toBeDefined();
  });

  it("today's classes of the room: one row per class with status, usage and time", () => {
    render(<InfraVisualizer map={map} status={undefined} usage={{ rooms: [{
      room: 'LC-123', pcsInUse: 0, pcsTotal: 1, state: 'idle', slot: null, outsideClass: 0,
      classes: [
        { id: 'a', course: 'SE301 Software Engineer', startsAt: '2026-11-01T02:00:00Z', endsAt: '2026-11-01T05:00:00Z',
          status: 'done', inUse: 1, seats: 1, pcsReady: 1 },
        { id: 'b', course: 'SE301 Software Engineer', startsAt: '2026-11-01T06:00:00Z', endsAt: '2026-11-01T09:00:00Z',
          status: 'pending', inUse: 0, seats: 1, pcsReady: 1 },
      ],
    }] }} />);
    expect(screen.getByText('Done')).toBeDefined();
    expect(screen.getByText('Pending')).toBeDefined();
    expect(screen.getByText('13:00 – 16:00')).toBeDefined();
    expect(screen.getAllByText('SE301 Software Engineer')).toHaveLength(2);
  });

  it('no class today and nobody using -> Idle with a note', () => {
    render(<InfraVisualizer map={map} status={undefined}
      usage={{ rooms: [{ room: 'LC-123', pcsInUse: 0, pcsTotal: 1, state: 'idle', slot: null, classes: [], outsideClass: 0 }] }} />);
    expect(screen.getByText('วันนี้ไม่มีคาบในห้องนี้')).toBeDefined();
  });
});
