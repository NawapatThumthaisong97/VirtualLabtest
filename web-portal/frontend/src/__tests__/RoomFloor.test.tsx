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
});
