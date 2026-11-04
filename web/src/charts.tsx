import { useMemo, useRef, useState } from "react";
import { n } from "./fmt";

export type Series = { name: string; color: string; points: { x: string; y: number | null }[]; dashed?: boolean };

// 선 그래프: 2px 선, 단일 y축, 크로스헤어 + 툴팁 (dataviz 규칙)
export function LineChart({ series, height = 180, yFmt = n, indexed = false }: { series: Series[]; height?: number; yFmt?: (v: number) => string; indexed?: boolean }) {
  const W = 360, H = height, P = { l: 44, r: 8, t: 8, b: 20 };
  const ref = useRef<SVGSVGElement>(null);
  const [hover, setHover] = useState<number | null>(null);
  const xs = useMemo(() => Array.from(new Set(series.flatMap((s) => s.points.map((p) => p.x)))).sort(), [series]);
  const prepared = useMemo(() => series.map((s) => {
    const base = s.points.find((p) => p.y !== null)?.y ?? 1;
    const m = new Map(s.points.map((p) => [p.x, p.y === null ? null : indexed ? (p.y / (base || 1)) * 100 : p.y]));
    return { ...s, m };
  }), [series, indexed]);
  const ys = prepared.flatMap((s) => [...s.m.values()].filter((v): v is number => v !== null));
  if (!xs.length || !ys.length) return <div className="empty small">그래프를 그릴 데이터가 부족합니다</div>;
  let lo = Math.min(...ys), hi = Math.max(...ys);
  if (lo === hi) { lo -= 1; hi += 1; }
  const pad = (hi - lo) * 0.08; lo -= pad; hi += pad;
  // x축은 '날짜' 기준 (예측 30·90일 점이 실제 간격대로 놓이도록)
  const ts = xs.map((x) => Date.parse(x + "T00:00:00Z"));
  const t0 = ts[0], t1 = ts[ts.length - 1];
  const X = (i: number) => P.l + (t1 === t0 ? 0 : ((ts[i] - t0) / (t1 - t0)) * (W - P.l - P.r));
  const Y = (v: number) => P.t + (1 - (v - lo) / (hi - lo)) * (H - P.t - P.b);
  const ticks = [0, 0.5, 1].map((f) => lo + (hi - lo) * f);
  const fmt = indexed ? (v: number) => v.toFixed(0) : yFmt;
  const onMove = (e: React.PointerEvent) => {
    const r = ref.current!.getBoundingClientRect();
    const px = ((e.clientX - r.left) / r.width) * W;
    let best = 0;
    xs.forEach((_, i) => { if (Math.abs(X(i) - px) < Math.abs(X(best) - px)) best = i; });
    setHover(best);
  };
  return (
    <div className="chart">
      {series.length > 1 && (
        <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
      )}
      <svg ref={ref} viewBox={`0 0 ${W} ${H}`} role="img" aria-label="추이 그래프" onPointerMove={onMove} onPointerLeave={() => setHover(null)}>
        {ticks.map((t) => (
          <g key={t}>
            <line x1={P.l} x2={W - P.r} y1={Y(t)} y2={Y(t)} className="grid" />
            <text x={P.l - 6} y={Y(t) + 4} className="axis" textAnchor="end">{fmt(t)}</text>
          </g>
        ))}
        <text x={P.l} y={H - 6} className="axis">{xs[0].slice(5)}</text>
        <text x={W - P.r} y={H - 6} className="axis" textAnchor="end">{xs[xs.length - 1].slice(5)}</text>
        {prepared.map((s) => {
          let d = "";
          xs.forEach((x, i) => {
            const v = s.m.get(x);
            if (v === null || v === undefined) return;
            d += (d ? "L" : "M") + X(i).toFixed(1) + "," + Y(v).toFixed(1);
          });
          return <path key={s.name} d={d} fill="none" stroke={s.color} strokeWidth={2} strokeDasharray={s.dashed ? "5 4" : undefined} strokeLinejoin="round" strokeLinecap="round" />;
        })}
        {hover !== null && (
          <g>
            <line x1={X(hover)} x2={X(hover)} y1={P.t} y2={H - P.b} className="crosshair" />
            {prepared.map((s) => {
              const v = s.m.get(xs[hover]);
              return v === null || v === undefined ? null : <circle key={s.name} cx={X(hover)} cy={Y(v)} r={4} fill={s.color} className="dot" />;
            })}
          </g>
        )}
      </svg>
      {hover !== null && (
        <div className="tip">
          <b>{xs[hover]}</b>
          {prepared.map((s) => { const v = s.m.get(xs[hover]); return v === null || v === undefined ? null : <div key={s.name}><i style={{ background: s.color }} />{s.name} {fmt(v)}</div>; })}
        </div>
      )}
    </div>
  );
}

// 레이더 차트: 등급 5항목 비교 (최대 4채널)
export function RadarChart({ axes, series }: { axes: { key: string; label: string; max: number }[]; series: { name: string; color: string; values: Record<string, number | null> }[] }) {
  const S = 320, C = S / 2, R = 96;
  const pt = (i: number, f: number) => {
    const a = -Math.PI / 2 + (i / axes.length) * Math.PI * 2;
    return [C + Math.cos(a) * R * f, C + Math.sin(a) * R * f];
  };
  return (
    <div className="chart radar">
      <div className="legend">{series.map((s) => <span key={s.name}><i style={{ background: s.color }} />{s.name}</span>)}</div>
      <svg viewBox={`0 0 ${S} ${S}`} role="img" aria-label="등급 항목 비교">
        {[0.25, 0.5, 0.75, 1].map((f) => (
          <polygon key={f} points={axes.map((_, i) => pt(i, f).join(",")).join(" ")} className="grid" fill="none" />
        ))}
        {axes.map((a, i) => {
          const [x, y] = pt(i, 1.18);
          return <text key={a.key} x={x} y={y + 4} className="axis" textAnchor="middle">{a.label}</text>;
        })}
        {series.map((s) => (
          <polygon key={s.name} fill={s.color} fillOpacity={0.12} stroke={s.color} strokeWidth={2}
            points={axes.map((a, i) => pt(i, Math.max(0, (s.values[a.key] ?? 0) / a.max)).join(",")).join(" ")} />
        ))}
      </svg>
    </div>
  );
}

// 업로드 요일×시간 히트맵 (한 가지 색, 연→진)
export function Heatmap({ heat }: { heat: number[][] }) {
  const max = Math.max(1, ...heat.flat());
  const days = ["월", "화", "수", "목", "금", "토", "일"];
  const [tip, setTip] = useState<string | null>(null);
  return (
    <div className="chart">
      <svg viewBox="0 0 372 126" role="img" aria-label="업로드 요일·시간 분포 (KST)">
        {heat.map((row, d) => row.map((v, h) => (
          <rect key={`${d}-${h}`} x={28 + h * 14.3} y={2 + d * 15} width={12.5} height={13} rx={2}
            className={v ? "" : "cell-empty"} style={v ? { fill: "var(--seq)", fillOpacity: 0.2 + 0.8 * (v / max) } : undefined}
            onPointerEnter={() => setTip(`${days[d]} ${h}시 · ${v}편`)} onPointerLeave={() => setTip(null)} />
        )))}
        {days.map((d, i) => <text key={d} x={22} y={13 + i * 15} className="axis" textAnchor="end">{d}</text>)}
        {[0, 6, 12, 18].map((h) => <text key={h} x={34 + h * 14.3} y={122} className="axis" textAnchor="middle">{h}시</text>)}
      </svg>
      <div className="small muted">{tip ?? "칸에 손가락/마우스를 올리면 업로드 수가 보입니다 (KST)"}</div>
    </div>
  );
}
