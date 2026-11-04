import { useState, type ReactNode } from "react";
import type { VCard } from "./api";
import { dur, LABELS, n, RECIPES } from "./fmt";

export const REPO = "kaycomm21/niche-radar";

// ---- 판정 기록: 정적 사이트는 쓰기가 불가능 → GitHub Issue(미리 채운 양식)로 보내고, 워크플로가 exports/ 에 기록
type Action = "queue" | "hold" | "drop" | "exclude_channel";
const ACTION_LABEL: Record<Action, string> = { queue: "생산큐", hold: "보류", drop: "폐기", exclude_channel: "채널제외" };

function readActed(): Record<string, string> {
  try { return JSON.parse(localStorage.getItem("radar.acted") || "{}"); } catch { return {}; }
}
function writeActed(id: string, a: string) {
  try { const m = readActed(); m[id] = a; localStorage.setItem("radar.acted", JSON.stringify(m)); } catch { /* 저장 불가 환경 무시 */ }
}

export function issueUrl(action: Action, payload: Record<string, string | null | undefined>, title: string): string {
  const body = [
    "<!-- radar-verdict: 아래 JSON 블록은 수정하지 마세요. 메모는 맨 아래에 적으면 됩니다. -->",
    "```json",
    JSON.stringify({ action, ...payload }),
    "```",
    "",
    "메모: ",
  ].join("\n");
  const q = new URLSearchParams({ title: `[${ACTION_LABEL[action]}] ${title}`.slice(0, 120), body, labels: "verdict" });
  return `https://github.com/${REPO}/issues/new?${q.toString()}`;
}

export function Verdict({ v }: { v: VCard }) {
  const [acted, setActed] = useState<string | undefined>(() => readActed()[v.id]);
  const payload = { id: v.id, title: v.t, channel: v.ct ?? v.c, group: v.g ?? "", recipe: v.rc[0] };
  const go = (a: Action) => () => { writeActed(v.id, ACTION_LABEL[a]); setActed(ACTION_LABEL[a]); };
  if (acted) return <div className="acted">✔ {acted} 판정 보냄 · 다음 갱신 때 반영</div>;
  return (
    <div className="verdict">
      <a className="btn primary" href={issueUrl("queue", payload, v.t)} target="_blank" rel="noreferrer" onClick={go("queue")}>▶ 생산 큐로</a>
      <a className="btn" href={issueUrl("hold", payload, v.t)} target="_blank" rel="noreferrer" onClick={go("hold")}>보류</a>
      <a className="btn ghost" href={issueUrl("drop", payload, v.t)} target="_blank" rel="noreferrer" onClick={go("drop")}>폐기</a>
    </div>
  );
}

export function ExcludeChannel({ id, title }: { id: string; title: string }) {
  const [acted, setActed] = useState<string | undefined>(() => readActed()[id]);
  if (acted) return <span className="muted small">✔ {acted} 요청됨</span>;
  return (
    <a className="btn ghost small" target="_blank" rel="noreferrer"
       href={issueUrl("exclude_channel", { id, title, channel: title }, `채널 수집 제외: ${title}`)}
       onClick={() => { writeActed(id, "채널제외"); setActed("채널제외"); }}>수집 제외</a>
  );
}

// ---- 추정 라벨: 산식을 눌러서 볼 수 있게 (모바일은 hover 가 없으므로 탭)
export function Est({ formula, kind = "추정" }: { formula: string; kind?: string }) {
  const [open, setOpen] = useState(false);
  return (
    <span className="est">
      <button type="button" className="est-tag" onClick={() => setOpen(!open)} aria-expanded={open} title={formula}>{kind} ⓘ</button>
      {open && <span className="est-pop" role="note">{formula}</span>}
    </span>
  );
}

export function Labels({ lb }: { lb: string[] }) {
  return <>{lb.map((l) => <span key={l} className={`chip chip-${l}`}>{LABELS[l] ?? l}</span>)}</>;
}

const PART_NAMES: [keyof VCard["sc"]["parts"], string, number][] = [
  ["burst", "터짐", 25], ["money", "수익성", 20], ["fit", "적합도(AI)", 20], ["replicable", "재현성", 15], ["life", "수명", 10], ["policy", "정책안전", 10],
];

export function ScoreBreakdown({ sc }: { sc: VCard["sc"] }) {
  return (
    <div className="score">
      <div className="score-head"><b>{sc.total}</b><span className="muted">/{sc.max}점 재가공 가치</span></div>
      <div className="parts">
        {PART_NAMES.map(([k, name, max]) => {
          const val = sc.parts[k];
          return (
            <div key={k} className="part" title={`${name} ${val ?? "미산정"}/${max}`}>
              <span className="part-name">{name}</span>
              <span className="part-bar"><span style={{ width: val === null ? 0 : `${(val / max) * 100}%` }} /></span>
              <span className="part-val">{val === null ? "키 필요" : val}</span>
            </div>
          );
        })}
      </div>
      {sc.reasons.length > 0 && <ul className="reasons">{sc.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
    </div>
  );
}

export function VideoCard({ v, rankBadge, detail = false, extra }: { v: VCard; rankBadge?: ReactNode; detail?: boolean; extra?: ReactNode }) {
  return (
    <article className="vcard">
      <div className="vcard-top">
        {rankBadge}
        {v.th ? <img src={v.th} alt="" loading="lazy" className="thumb" onError={(e) => { e.currentTarget.style.visibility = "hidden"; }} /> : <div className="thumb" />}
        <div className="vcard-meta">
          <a className="vtitle" href={`https://www.youtube.com/watch?v=${v.id}`} target="_blank" rel="noreferrer">{v.t}</a>
          <div className="small muted">
            <a href={`#/ch/${v.c}`}>{v.ct ?? v.c}</a> · {v.pub} · {v.sh ? "쇼츠" : "롱폼"} {dur(v.dur)}
          </div>
          <div className="stats small">
            조회 <b>{n(v.v)}</b>
            {v.mx !== null && <> · 배수 <b className={v.mx >= 10 ? "hot" : v.mx >= 3 ? "warm" : ""}>{v.mx.toFixed(1)}×</b></>}
            {v.v24 !== null && <> · 24h +{n(v.v24)}</>}
            {v.rk !== null && <> · 차트 {v.rk}위</>}
          </div>
          <div className="chips"><Labels lb={v.lb} />{v.g && <span className="chip chip-group">→ {v.g}</span>}</div>
        </div>
      </div>
      {detail && (
        <>
          <div className="recipe small"><b>{v.rc[0]} {RECIPES[v.rc[0]]}</b> — {v.rc[1]} · 예상 RPM {n(v.rpm[0])}~{n(v.rpm[1])}원 <Est formula="카테고리 RPM 가정치(config/rpm_kr.yaml) × 금융·건강 키워드 보정. 실측 아님" /></div>
          {v.ai?.angle && <div className="recipe small">🤖 AI 각도: {v.ai.angle}{v.ai.reason ? <span className="muted"> — {v.ai.reason}</span> : null}</div>}
          {v.ai?.buzz_24h !== undefined && <div className="small muted">📣 유튜브 밖 24시간 언급 {v.ai.buzz_24h}건 (Brave)</div>}
          <ScoreBreakdown sc={v.sc} />
        </>
      )}
      {extra}
      <Verdict v={v} />
    </article>
  );
}

export function Loading({ err }: { err?: string }) {
  return <div className="empty">{err ? `데이터를 불러오지 못했습니다: ${err}` : "불러오는 중…"}</div>;
}

export function Seg<T extends string>({ value, options, onChange }: { value: T; options: [T, string][]; onChange: (v: T) => void }) {
  return (
    <div className="seg" role="tablist">
      {options.map(([k, label]) => (
        <button key={k} type="button" role="tab" aria-selected={value === k} className={value === k ? "on" : ""} onClick={() => onChange(k)}>{label}</button>
      ))}
    </div>
  );
}
