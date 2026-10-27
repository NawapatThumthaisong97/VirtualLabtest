import { useEffect, useRef, useState } from 'react';
import { colors } from './theme';
import type { ClusterMapItem, InfraMap as InfraMapData, RoomStatus } from '../../services/adminDashboard';

interface Node {
  id: string;
  label: string;
  sub?: string;
  x: number;
  y: number;
  w: number;
  h: number;
  fill: string;
  selectable?: boolean;
}

const fillFor: Record<RoomStatus | 'unknown', string> = {
  ok: colors.cellGreen,
  warn: colors.cellYellow,
  down: colors.cellRed,
  unknown: '#E8E8E8',
};

const MIN_SCALE = 0.5;
const MAX_SCALE = 4;
const ROOM_Y0 = 78;
const ROOM_STEP = 80;
const ROOM_H = 48;

/** กล่องห้องตามจำนวนห้องจริง (label vlab/room) control plane ตรงกลาง AWS ด้านขวา */
function layout(clusters: ClusterMapItem[]) {
  const k3s = clusters.find((c) => c.type === 'k3s');
  const aws = clusters.find((c) => c.type === 'cloud');
  const rooms = k3s?.rooms ?? [];
  const count = Math.max(rooms.length, 1);
  const roomNodes: Node[] = rooms.length
    ? rooms.map((r, i) => ({
        id: r.room,
        label: r.room,
        sub: `${r.pcsInUse}/${r.pcsTotal} in use · ${r.pcsReady} ready`,
        x: 72, y: ROOM_Y0 + i * ROOM_STEP, w: 170, h: ROOM_H,
        fill: fillFor[r.status],
        selectable: true,
      }))
    : [{ id: 'none', label: k3s?.status === 'down' ? 'K3s down' : 'No rooms', x: 72, y: ROOM_Y0, w: 170, h: ROOM_H, fill: fillFor.down }];
  const midY = ROOM_Y0 + ((count - 1) * ROOM_STEP) / 2 + ROOM_H / 2;
  const cpReady = k3s?.controlPlane?.ready ?? false;
  const nodes: Node[] = [
    ...roomNodes,
    {
      id: 'control', label: 'Control plane', sub: k3s?.controlPlane?.node ?? undefined,
      x: 310, y: midY - 25, w: 175, h: 50, fill: cpReady ? '#B9F0F7' : colors.cellRed,
    },
    {
      id: 'aws', label: 'AWS Cloud', sub: `${aws?.instancesRunning ?? 0} instances · ${aws?.region ?? ''}`,
      x: 565, y: midY - 24, w: 175, h: 48, fill: fillFor[aws?.status ?? 'unknown'],
    },
  ];
  const onPremBottom = ROOM_Y0 + (count - 1) * ROOM_STEP + ROOM_H + 24;
  const height = Math.max(400, onPremBottom + 20);
  return { nodes, roomNodes, midY, onPremBottom, height };
}

/** Pan with drag, zoom with Alt + wheel (anchored to cursor). */
export default function InfraMap({
  data,
  selected,
  onSelect,
}: {
  data: InfraMapData | undefined;
  selected?: string | null;
  onSelect?: (id: string) => void;
}) {
  const vpRef = useRef<HTMLDivElement>(null);
  const [view, setView] = useState({ tx: 0, ty: 0, scale: 1 });
  const drag = useRef<{ x: number; y: number } | null>(null);

  // React's onWheel is passive, so preventDefault needs a native listener.
  useEffect(() => {
    const el = vpRef.current;
    if (!el) return;
    const onWheel = (e: WheelEvent) => {
      if (!e.altKey) return;
      e.preventDefault();
      const r = el.getBoundingClientRect();
      const mx = e.clientX - r.left;
      const my = e.clientY - r.top;
      const factor = e.deltaY < 0 ? 1.1 : 1 / 1.1;
      setView((v) => {
        const scale = Math.min(MAX_SCALE, Math.max(MIN_SCALE, v.scale * factor));
        const k = scale / v.scale;
        return { scale, tx: mx - (mx - v.tx) * k, ty: my - (my - v.ty) * k };
      });
    };
    el.addEventListener('wheel', onWheel, { passive: false });
    return () => el.removeEventListener('wheel', onWheel);
  }, []);

  const onMouseDown = (e: React.MouseEvent) => {
    drag.current = { x: e.clientX, y: e.clientY };
  };
  const onMouseMove = (e: React.MouseEvent) => {
    if (!drag.current) return;
    const dx = e.clientX - drag.current.x;
    const dy = e.clientY - drag.current.y;
    drag.current = { x: e.clientX, y: e.clientY };
    setView((v) => ({ ...v, tx: v.tx + dx, ty: v.ty + dy }));
  };
  const endDrag = () => {
    drag.current = null;
  };

  const { nodes, roomNodes, midY, onPremBottom, height } = layout(data?.clusters ?? []);
  const firstY = roomNodes[0].y + ROOM_H / 2;
  const lastY = roomNodes[roomNodes.length - 1].y + ROOM_H / 2;

  return (
    <div
      ref={vpRef}
      onMouseDown={onMouseDown}
      onMouseMove={onMouseMove}
      onMouseUp={endDrag}
      onMouseLeave={endDrag}
      style={{
        position: 'relative',
        height: 340,
        borderBottom: `1px solid ${colors.border}`,
        overflow: 'hidden',
        userSelect: 'none',
        cursor: drag.current ? 'grabbing' : 'grab',
      }}
    >
      <div
        style={{
          position: 'absolute',
          inset: 0,
          transformOrigin: '0 0',
          transform: `translate(${view.tx}px, ${view.ty}px) scale(${view.scale})`,
        }}
      >
        <svg viewBox={`0 0 800 ${height}`} preserveAspectRatio="xMidYMid meet" style={{ position: 'absolute', inset: 0, width: '100%', height: '100%' }}>
          <defs>
            <filter id="boxsh" x="-20%" y="-20%" width="140%" height="160%" colorInterpolationFilters="sRGB">
              <feDropShadow dx="0" dy="2" stdDeviation="2.5" floodColor="#000" floodOpacity="0.22" />
            </filter>
          </defs>

          <rect x="45" y="35" width="225" height={onPremBottom - 35} rx="4" fill="none" stroke="#6E7FD6" strokeWidth="1.4" strokeDasharray="6 5" />
          <text x="157" y="55" textAnchor="middle" fontFamily="Inter,sans-serif" fontSize="14" fill="#3A5BC7">
            On-premise
          </text>
          <rect x="540" y={Math.max(35, midY - 110)} width="230" height="170" rx="4" fill="none" stroke="#6E7FD6" strokeWidth="1.4" strokeDasharray="6 5" />
          <text x="655" y={Math.max(35, midY - 110) + 20} textAnchor="middle" fontFamily="Inter,sans-serif" fontSize="14" fill="#3A5BC7">
            Cloud-internet
          </text>

          <g stroke="#555" strokeWidth="1.4" fill="none">
            {roomNodes.map((n) => (
              <path key={n.id} d={`M242 ${n.y + ROOM_H / 2} H290`} />
            ))}
            <path d={`M290 ${firstY} V${lastY}`} />
            <path d={`M290 ${midY} H310`} />
            <path d={`M485 ${midY} H565`} />
          </g>

          <g filter="url(#boxsh)" fontFamily="Inter,sans-serif" fill="#333">
            {nodes.map((n) => (
              <g
                key={n.id}
                style={{ cursor: n.selectable ? 'pointer' : 'default' }}
                onClick={() => n.selectable && onSelect?.(n.id)}
              >
                <rect
                  x={n.x} y={n.y} width={n.w} height={n.h} fill={n.fill}
                  stroke={selected === n.id ? colors.blue : 'none'} strokeWidth={selected === n.id ? 3 : 0}
                />
                <text x={n.x + n.w / 2} y={n.y + (n.sub ? 22 : n.h / 2 + 6)} textAnchor="middle" fontSize="19" fill="#333">
                  {n.label}
                </text>
                {n.sub && (
                  <text x={n.x + n.w / 2} y={n.y + 40} textAnchor="middle" fontSize="11" fill="#555">
                    {n.sub}
                  </text>
                )}
              </g>
            ))}
          </g>
        </svg>
      </div>

      <div
        style={{
          position: 'absolute',
          top: -16,
          right: -16,
          width: 52,
          height: 52,
          borderRadius: '50%',
          border: `1px solid ${colors.border}`,
          background: '#fff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <img src="/search-icon.png" alt="search" style={{ width: 14, height: 14, objectFit: 'contain', transform: 'translate(-6px,6px)' }} />
      </div>
    </div>
  );
}
