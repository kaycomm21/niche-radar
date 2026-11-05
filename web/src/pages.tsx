import { useEffect, useMemo, useState } from "react";
import { load, type ChannelDetail, type Charts, type Queue, type RankRow, type Summary, type Trends, type VCard } from "./api";
import { LineChart, RadarChart, Heatmap } from "./charts";
import { dur, n, pct, won } from "./fmt";
import { Est, ExcludeChannel, issueUrl, Loading, Seg, VideoCard } from "./ui";

function useData<T>(path: string): [T | null, string | undefined] {
  const [d, setD] = useState<T | null>(null);
  const [e, setE] = useState<string>();
  useEffect(() => { setD(null); load<T>(path).then(setD).catch((x: Error) => setE(x.message)); }, [path]);
  return [d, e];
}

const SERIES = ["var(--s1)", "var(--s2)", "var(--s3)", "var(--s4)"];

// ------------------------------------------------------------------ 홈 (§A2)
export function Home() {
  const [q, e] = useData<Queue>("queue.json");
  const [s] = useData<Summary>("summary.json");
  const [showArch, setShowArch] = useState(false);
  if (!q) return <Loading err={e} />;
  return (
    <>
      {s?.mode === "fixture" && <div className="banner">🧪 fixture(가짜 데이터) 모드입니다. 실제 수집이 돌면 자동으로 바뀝니다.</div>}
      <section>
        <h2>🎯 오늘의 생산 큐 후보 <span className="muted small">{q.date}</span></h2>
        <p className="small muted">점수 상위 3건 (서로 다른 채널 그룹 우선). ▶ 생산 큐로 = Phase 2 생산 패키지 입력. 7일 무응답 시 자동 보관.</p>
        {q.top3.length === 0 && <div className="empty">오늘은 기준을 넘는 후보가 없습니다.</div>}
        {q.top3.map((v, i) => <VideoCard key={v.id} v={v} detail rankBadge={<span className="badge">{i + 1}</span>} />)}
      </section>
      <section>
        <h2>🗂 판정 대기 카드 <span className="muted small">{q.pending.length}건</span></h2>
        {q.pending.map((v) => <VideoCard key={v.id} v={v} extra={<details className="small"><summary>점수 근거</summary><VideoCardScore v={v} /></details>} />)}
      </section>
      <section>
        <button type="button" className="btn ghost" onClick={() => setShowArch(!showArch)}>📦 자동 보관 {q.archived.length}건 {showArch ? "접기" : "보기"}</button>
        {showArch && q.archived.map((v) => <VideoCard key={v.id} v={v} />)}
      </section>
    </>
  );
}

function VideoCardScore({ v }: { v: VCard }) {
  const p = v.sc.parts;
  return <div>터짐 {p.burst} · 수익성 {p.money} · 재현성 {p.replicable} · 수명 {p.life} · 정책 {p.policy} · 적합도(AI) Phase 2 → <b>{v.sc.total}/{v.sc.max}</b> · {v.rc[0]} {v.rc[1]}</div>;
}

// ------------------------------------------------------------------ M1-1 인기 차트
export function ChartPage() {
  const [c, e] = useData<Charts>("charts.json");
  const [cat, setCat] = useState("0");
  const [fmt, setFmt] = useState<"long" | "short">("long");
  const [limit, setLimit] = useState(30);
  if (!c) return <Loading err={e} />;
  const items = c.charts[cat]?.[fmt] ?? [];
  return (
    <section>
      <h2>🌐 국내 인기 차트 <span className="muted small">{c.date}</span></h2>
      <div className="filters">
        <select value={cat} onChange={(x) => { setCat(x.target.value); setLimit(30); }} aria-label="카테고리">
          {Object.entries(c.categories).map(([k, v]) => <option key={k} value={k} disabled={!c.charts[k]}>{v}{!c.charts[k] ? " (차트 없음)" : ""}</option>)}
        </select>
        <Seg value={fmt} onChange={setFmt} options={[["long", "롱폼"], ["short", "쇼츠"]]} />
      </div>
      {items.length === 0 && <div className="empty">이 카테고리·포맷의 오늘 차트가 없습니다.</div>}
      {items.slice(0, limit).map((v) => (
        <VideoCard key={v.id} v={v} rankBadge={
          <span className="badge rank">{v.rank}<small className={v.delta === null ? "new" : v.delta > 0 ? "up" : v.delta < 0 ? "down" : ""}>
            {v.delta === null ? "NEW" : v.delta > 0 ? `▲${v.delta}` : v.delta < 0 ? `▼${-v.delta}` : "–"}</small></span>} />
      ))}
      {items.length > limit && <button type="button" className="btn wide" onClick={() => setLimit(limit + 30)}>더 보기 ({items.length - limit})</button>}
    </section>
  );
}

// ------------------------------------------------------------------ M1-4 급상승
export function SurgePage() {
  const [d, e] = useData<{ date: string; items: VCard[] }>("surging.json");
  const [s] = useData<Summary>("summary.json");
  const [min, setMin] = useState<"3" | "10">("3");
  const [fmt, setFmt] = useState<"all" | "long" | "short">("all");
  if (!d) return <Loading err={e} />;
  const items = d.items.filter((v) => (v.mx ?? 0) >= Number(min) && (fmt === "all" || (fmt === "short") === Boolean(v.sh)));
  return (
    <section>
      <h2>🚀 급상승 (최근 14일) <span className="muted small">{items.length}건</span></h2>
      <p className="small muted">{s?.formulas.outlier}</p>
      <div className="filters">
        <Seg value={min} onChange={setMin} options={[["3", "🔥 3배↑"], ["10", "💥 10배↑"]]} />
        <Seg value={fmt} onChange={setFmt} options={[["all", "전체"], ["long", "롱폼"], ["short", "쇼츠"]]} />
      </div>
      {items.slice(0, 100).map((v) => <VideoCard key={v.id} v={v} />)}
    </section>
  );
}

// ------------------------------------------------------------------ M1-2 채널 순위
type SortKey = "subs" | "sg" | "sgr" | "v30" | "avg" | "gs" | "pop";
const SORTS: [SortKey, string][] = [["gs", "등급"], ["pop", "인기도(조회+좋아요×10)"], ["sgr", "구독 급상승율"], ["sg", "구독 급상승 수"], ["v30", "30일 조회"], ["avg", "평균 조회"], ["subs", "구독자"]];

export function RankPage() {
  const [d, e] = useData<{ date: string; items: RankRow[] }>("rankings.json");
  const [s] = useData<Summary>("summary.json");
  const [sort, setSort] = useState<SortKey>("gs");
  const [group, setGroup] = useState("");
  const [src, setSrc] = useState<"all" | "seed" | "chart">("all");
  const [limit, setLimit] = useState(50);
  const rows = useMemo(() => {
    if (!d) return [];
    return d.items.filter((r) => (!group || r.g === group) && (src === "all" || r.src === src))
      .sort((a, b) => ((b[sort] as number | null) ?? -Infinity) - ((a[sort] as number | null) ?? -Infinity));
  }, [d, sort, group, src]);
  if (!d) return <Loading err={e} />;
  return (
    <section>
      <h2>🏆 채널 순위 <span className="muted small">{rows.length}채널</span></h2>
      <div className="filters">
        <select value={sort} onChange={(x) => setSort(x.target.value as SortKey)} aria-label="정렬">{SORTS.map(([k, l]) => <option key={k} value={k}>{l} 순</option>)}</select>
        <select value={group} onChange={(x) => setGroup(x.target.value)} aria-label="그룹"><option value="">전체 그룹</option>{s?.groups.map((g) => <option key={g}>{g}</option>)}</select>
        <Seg value={src} onChange={setSrc} options={[["all", "전체"], ["seed", "레퍼런스"], ["chart", "차트 편입"]]} />
      </div>
      <p className="small muted">구독 급상승은 30일 창(일별 데이터 7일 이상일 때). 등급은 <Est kind="공식 공개" formula={s?.formulas.grade ?? ""} /></p>
      <ol className="rank-list">
        {rows.slice(0, limit).map((r, i) => (
          <li key={r.id} className="rank-row">
            <span className="badge">{i + 1}</span>
            {r.th ? <img src={r.th} alt="" className="avatar" loading="lazy" /> : <span className="avatar" />}
            <div className="grow">
              <a href={`#/ch/${r.id}`} className="vtitle">{r.t ?? r.id}</a>
              <div className="small muted">{r.g ?? "그룹 미지정"} · {r.src === "seed" ? "레퍼런스" : "차트 편입"} {r.fl.length > 0 && <span className="warn">⚠️ {r.fl.join(", ")}</span>}</div>
              <div className="small">구독 <b>{n(r.subs)}</b> · 30일 {r.sg === null ? "–" : `${r.sg >= 0 ? "+" : ""}${n(r.sg)} (${pct(r.sgr)})`} · 평균조회 {n(r.avg)} · 30일 업로드 {r.up30}</div>
              {r.top && <div className="small">🔥 최고 히트: <a href={`https://www.youtube.com/watch?v=${r.top.id}`} target="_blank" rel="noreferrer">{r.top.t}</a> ({r.top.mx?.toFixed(1)}×)</div>}
              <div className="row-actions">
                {r.top && <a className="btn small primary" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: r.top.id, title: r.top.t, channel: r.t, group: r.g ?? "", recipe: r.top.rc[0] }, r.top.t)}>▶ 히트 큐로</a>}
                <a className="btn small" href={`#/compare?add=${r.id}`}>비교에 담기</a><ExcludeChannel id={r.id} title={r.t ?? r.id} /></div>
            </div>
            <span className={`grade g-${r.gr ?? "na"}`} title={`${r.gs ?? "–"}점`}>{r.gr ?? "–"}</span>
          </li>
        ))}
      </ol>
      {rows.length > limit && <button type="button" className="btn wide" onClick={() => setLimit(limit + 50)}>더 보기</button>}
    </section>
  );
}

// ------------------------------------------------------------------ M2 채널 상세 (6~9, 11~13)
const GRADE_AXES = [
  { key: "growth", label: "성장률", max: 30 }, { key: "efficiency", label: "조회효율", max: 25 }, { key: "engagement", label: "참여율", max: 20 },
  { key: "consistency", label: "일관성", max: 15 }, { key: "outlier_freq", label: "터짐빈도", max: 10 },
];

export function ChannelPage({ id }: { id: string }) {
  const [c, e] = useData<ChannelDetail>(`channels/${id}.json`);
  const [s] = useData<Summary>("summary.json");
  const [metric, setMetric] = useState<"subs" | "views">("subs");
  const [vsort, setVsort] = useState<"mx" | "views" | "recent">("mx");
  if (!c) return <Loading err={e} />;
  const f = c.f, F = s?.formulas ?? {};
  const idx = metric === "subs" ? 1 : 2;
  const fc = metric === "subs" ? c.fc_subs : c.fc_views;
  const hist = c.hist.map((h) => ({ x: h[0], y: h[idx] as number | null }));
  const last = c.hist[c.hist.length - 1];
  const fcPts = fc && last ? [{ x: last[0], y: last[idx] as number | null }, ...[30, 90].map((d) => ({ x: addDays(last[0], d), y: fc.forecast[String(d)] }))] : [];
  const diff = (days: number) => {
    if (c.hist.length < 2) return null;
    const target = addDays(last[0], -days);
    const base = c.hist.find((h) => h[0] >= target);
    return base && base[idx] !== null && last[idx] !== null ? (last[idx] as number) - (base[idx] as number) : null;
  };
  return (
    <section>
      <div className="ch-head">
        {c.th ? <img src={c.th} alt="" className="avatar lg" /> : <span className="avatar lg" />}
        <div className="grow">
          <h2>{c.t}</h2>
          <div className="small muted">{c.handle} · {c.g ?? "그룹 미지정"} · {c.src === "seed" ? "레퍼런스" : "차트 편입"} · <a href={`https://www.youtube.com/channel/${c.id}`} target="_blank" rel="noreferrer">유튜브에서 열기</a></div>
          {f.flags.length > 0 && <div className="warn small">⚠️ 이상 신호: {f.flags.join(", ")} <Est formula={F.fake ?? ""} kind="기준" /></div>}
        </div>
        <span className={`grade lg g-${c.grade.letter ?? "na"}`}>{c.grade.letter ?? "–"}</span>
      </div>

      <div className="kpis">
        <div className="kpi"><span>구독자</span><b>{n(f.subs)}</b><small>7일 {sign(diff(7))} · 30일 {sign(diff(30))}</small></div>
        <div className="kpi"><span>최근 30일 업로드 조회</span><b>{n(f.views30_uploads)}</b><small>{f.uploads30}편 업로드</small></div>
        <div className="kpi"><span>예상 월 광고수익 <Est formula={F.revenue ?? ""} /></span><b>{won(f.rev[0])}~{won(f.rev[1])}</b><small>추정 · 실측 아님</small></div>
        <div className="kpi"><span>예상 PPL 단가(1편) <Est formula={F.ppl ?? ""} /></span><b>{f.ppl ? `${won(f.ppl[0])}~${won(f.ppl[1])}` : "–"}</b><small>광고주 관점 추정</small></div>
        <div className="kpi"><span>참여율(중앙값)</span><b>{pct(f.engagement, 2)}</b><small>(좋아요+댓글)÷조회</small></div>
      </div>

      <div className="chips rank-chips">
        <span className="chip">구독 순위 <b>{c.ranks.subs ?? "–"}</b>/{c.ranks.n}</span>
        <span className="chip">인기도 순위 <b>{c.ranks.pop ?? "–"}</b></span>
        <span className="chip">30일 조회 순위 <b>{c.ranks.views30 ?? "–"}</b></span>
        <span className="chip">{s?.categories[c.ranks.cat_id ?? ""] ?? "카테고리"} 내 <b>{c.ranks.cat ?? "–"}</b>/{c.ranks.cat_n}위</span>
        <Est kind="유니버스 기준" formula={`순위는 전 세계가 아니라 레이더가 추적하는 ${c.ranks.n}개 채널(레퍼런스 + 국내 인기 차트 등장 채널) 안에서의 순위`} />
      </div>
      <p className="small">예상 연 광고수익 <b>{won(c.rev_year[0])}~{won(c.rev_year[1])}</b> <Est formula={(F.revenue ?? "") + " × 12"} /></p>

      <h3>⚔️ 경쟁 대비 성과</h3>
      <div className="table-wrap"><table><thead><tr><th>비교</th><th>평균 조회</th><th>대비</th></tr></thead><tbody>
        <tr><td>이 채널</td><td>{n(c.perf.avg_views)}</td><td>–</td></tr>
        {c.perf.group && <tr><td>같은 그룹({c.perf.group}) 중앙값</td><td>{n(c.perf.group_median)}</td><td>{ratio(c.perf.avg_views, c.perf.group_median)}</td></tr>}
        <tr><td>같은 카테고리({c.perf.category ?? "–"}) 중앙값</td><td>{n(c.perf.category_median)}</td><td>{ratio(c.perf.avg_views, c.perf.category_median)}</td></tr>
      </tbody></table></div>

      <h3>🎞 영상 분석 (최근 90일)</h3>
      <div className="table-wrap"><table><thead><tr><th>지표</th><th>이 채널</th><th>카테고리 평균</th></tr></thead><tbody>
        <tr><td>영상 수</td><td>{c.video_stats.mine?.n ?? "–"}</td><td>–</td></tr>
        <tr><td>평균 조회</td><td>{n(c.video_stats.mine?.avg_views)}</td><td>{n(c.video_stats.category?.avg_views)}</td></tr>
        <tr><td>좋아요율 (중앙값)</td><td>{pct(c.video_stats.mine?.like_rate, 2)}</td><td>{pct(c.video_stats.category?.like_rate, 2)}</td></tr>
        <tr><td>댓글율 (중앙값)</td><td>{pct(c.video_stats.mine?.comment_rate, 3)}</td><td>{pct(c.video_stats.category?.comment_rate, 3)}</td></tr>
      </tbody></table></div>

      <h3>📅 일별 변화 (최근 30일) <Est kind="참고" formula="YouTube API는 구독자 수를 유효숫자 3자리로 반올림해 줍니다(예: 374만). 그래서 큰 채널은 구독 변화가 며칠 동안 +0으로 보일 수 있습니다. 조회수는 정확한 값입니다." /></h3>
      {c.daily.length === 0 ? <p className="small muted">2일째 데이터부터 표시됩니다.</p> : (
        <div className="table-wrap"><table><thead><tr><th>날짜</th><th>구독 변화</th><th>구독자</th><th>조회 변화</th></tr></thead><tbody>
          {c.daily.map((r) => <tr key={r.d}><td>{r.d.slice(5)}</td><td className={delta(r.ds)}>{sign(r.ds)}</td><td>{n(r.subs)}</td><td className={delta(r.dv)}>{sign(r.dv)}</td></tr>)}
        </tbody></table></div>
      )}

      <h3>📈 추이 · 예측</h3>
      <div className="filters"><Seg value={metric} onChange={setMetric} options={[["subs", "구독자"], ["views", "총 조회수"]]} /></div>
      <LineChart series={[{ name: "실측", color: "var(--s1)", points: hist }, ...(fcPts.length ? [{ name: "모델 예측", color: "var(--s2)", points: fcPts, dashed: true }] : [])]} />
      {fc ? (
        <p className="small">모델 예측 <Est kind="모델 예측" formula={F.forecast ?? ""} />: 30일 후 <b>{n(fc.forecast["30"])}</b> · 90일 {n(fc.forecast["90"])} · 365일 {n(fc.forecast["365"])}
          {metric === "subs" && <> · 10만 {ms(c.milestones["100000"], f.subs, 1e5)} · 100만 {ms(c.milestones["1000000"], f.subs, 1e6)}</>}
          <br /><span className="muted">보장 아님. 일별 데이터 {f.days_hist}일 기반.</span></p>
      ) : <p className="small muted">예측은 일별 데이터 7일 이상부터 계산합니다 (현재 {f.days_hist}일).</p>}

      <h3>🏅 투명 등급 {c.grade.score ?? "–"}점 <Est kind="공식" formula={F.grade ?? ""} /></h3>
      <div className="parts">
        {GRADE_AXES.map((a) => {
          const v = c.grade.parts[a.key];
          return <div key={a.key} className="part"><span className="part-name">{a.label}</span><span className="part-bar"><span style={{ width: v === null || v === undefined ? 0 : `${(v / a.max) * 100}%` }} /></span><span className="part-val">{v ?? "데이터 부족"}/{a.max}</span></div>;
        })}
      </div>
      <p className="small muted">원값: 30일 구독 성장 {pct(f.growth)} · 조회효율(롱폼 평균조회÷구독) {pct(f.efficiency)} · 업로드 일관성 {f.consistency?.toFixed(2) ?? "–"} · 3배↑ 영상 비율 {pct(f.outlier_freq, 0)}</p>

      <h3>🧩 포맷 분석</h3>
      <p className="small">최근 {c.fmt.n}편 · 쇼츠 비율 {pct(c.fmt.short_ratio, 0)} · 롱폼 평균 {dur(Math.round(c.fmt.avg_dur))} · 제목 평균 {c.fmt.title_len?.toFixed(0) ?? "–"}자 · 숫자 포함 {pct(c.fmt.title_num, 0)} · 질문형 {pct(c.fmt.title_q, 0)}</p>
      <Heatmap heat={c.fmt.heat} />

      <h3>🎬 영상 목록</h3>
      <div className="filters"><Seg value={vsort} onChange={setVsort} options={[["mx", "배수 순"], ["views", "조회수 TOP"], ["recent", "최신 순"]]} /></div>
      {(vsort === "views" ? c.top_videos : [...c.videos].sort((a, b) => vsort === "recent" ? b.pub.localeCompare(a.pub) : (b.mx ?? 0) - (a.mx ?? 0))).slice(0, 15).map((v) => <VideoCard key={v.id} v={v} />)}

      <h3>🧭 유사 채널 (같은 카테고리 · 비슷한 규모)</h3>
      <ol className="rank-list">{c.similar.map((x) => (
        <li key={x.id} className="rank-row">
          {x.th ? <img src={x.th} alt="" className="avatar" loading="lazy" /> : <span className="avatar" />}
          <div className="grow"><a href={`#/ch/${x.id}`} className="vtitle">{x.t ?? x.id}</a><div className="small muted">구독 {n(x.subs)} · 평균 조회 {n(x.avg)}</div>
            <div className="row-actions"><a className="btn small" href={`#/compare?add=${x.id}`}>비교에 담기</a></div></div>
          <span className={`grade g-${x.gr ?? "na"}`}>{x.gr ?? "–"}</span>
        </li>))}</ol>
      <div className="row-actions"><a className="btn" href={`#/compare?add=${c.id}`}>비교에 담기</a><ExcludeChannel id={c.id} title={c.t ?? c.id} /></div>
    </section>
  );
}

function ms(d: string | null | undefined, cur: number | null, target: number) {
  if (cur !== null && cur >= target) return "달성";
  return d ? `${d} 도달 예상` : "예측 불가(감소·정체 또는 10년 초과)";
}
function ratio(a: number | null, b: number | null) { return a && b ? `${(a / b).toFixed(1)}배` : "–"; }
function delta(x: number | null) { return x === null ? "" : x > 0 ? "up" : x < 0 ? "down" : ""; }
function sign(x: number | null) { return x === null ? "–" : `${x >= 0 ? "+" : ""}${n(x)}`; }
function addDays(iso: string, d: number) { const t = new Date(iso + "T00:00:00Z"); t.setUTCDate(t.getUTCDate() + d); return t.toISOString().slice(0, 10); }

// ------------------------------------------------------------------ M2-14 채널 비교
function storedCompare(): string[] { try { return JSON.parse(localStorage.getItem("radar.compare") || "[]"); } catch { return []; } }

export function ComparePage({ ids: initial, add }: { ids: string[]; add?: string }) {
  const [rank] = useData<{ date: string; items: RankRow[] }>("rankings.json");
  const [ids, setIds] = useState<string[]>(() => {
    const base = initial.length ? initial : storedCompare();
    return Array.from(new Set([...base, ...(add ? [add] : [])])).slice(-4);
  });
  useEffect(() => { try { localStorage.setItem("radar.compare", JSON.stringify(ids)); } catch { /* 무시 */ } }, [ids]);
  const [details, setDetails] = useState<Record<string, ChannelDetail>>({});
  const [qtext, setQ] = useState("");
  const [metric, setMetric] = useState<"subs" | "views">("subs");
  useEffect(() => { ids.forEach((id) => { if (!details[id]) load<ChannelDetail>(`channels/${id}.json`).then((d) => setDetails((m) => ({ ...m, [id]: d }))).catch(() => undefined); }); }, [ids, details]);
  useEffect(() => { const h = `#/compare?ids=${ids.join(",")}`; if (location.hash !== h) history.replaceState(null, "", h); }, [ids]);
  const matches = useMemo(() => (rank && qtext.length >= 1 ? rank.items.filter((r) => (r.t ?? "").toLowerCase().includes(qtext.toLowerCase()) && !ids.includes(r.id)).slice(0, 8) : []), [rank, qtext, ids]);
  const ds = ids.map((id) => details[id]).filter(Boolean);
  const idx = metric === "subs" ? 1 : 2;
  return (
    <section>
      <h2>⚖️ 채널 비교 <span className="muted small">최대 4채널</span></h2>
      <div className="chips">{ids.map((id, i) => <span key={id} className="chip chip-sel"><i style={{ background: SERIES[i] }} />{details[id]?.t ?? id}<button type="button" aria-label="빼기" onClick={() => setIds(ids.filter((x) => x !== id))}>✕</button></span>)}</div>
      {ids.length < 4 && (
        <div className="search">
          <input value={qtext} onChange={(e) => setQ(e.target.value)} placeholder="채널 이름으로 추가…" aria-label="채널 검색" />
          {matches.length > 0 && <ul className="suggest">{matches.map((m) => <li key={m.id}><button type="button" onClick={() => { setIds([...ids, m.id]); setQ(""); }}>{m.t} <span className="muted small">{n(m.subs)}</span></button></li>)}</ul>}
        </div>
      )}
      {ds.length === 0 ? <div className="empty">채널을 추가하세요 (순위 화면의 '비교에 담기'로도 가능).</div> : (
        <>
          <h3>📈 추이 (첫날 = 100 지수화)</h3>
          <p className="small muted">채널 규모가 달라 하나의 축에 그대로 겹치면 작은 채널이 안 보이므로, 첫날을 100으로 맞춘 지수로 비교합니다.</p>
          <div className="filters"><Seg value={metric} onChange={setMetric} options={[["subs", "구독자"], ["views", "총 조회수"]]} /></div>
          <LineChart indexed series={ds.map((d) => ({ name: d.t ?? d.id, color: SERIES[ids.indexOf(d.id)], points: d.hist.map((h) => ({ x: h[0], y: h[idx] as number | null })) }))} />
          <h3>🏅 등급 항목</h3>
          <RadarChart axes={GRADE_AXES} series={ds.map((d) => ({ name: d.t ?? d.id, color: SERIES[ids.indexOf(d.id)], values: d.grade.parts }))} />
          <div className="table-wrap">
            <table>
              <thead><tr><th>채널</th><th>등급</th><th>구독</th><th>30일 성장</th><th>평균 조회</th><th>참여율</th><th>예상 월수익</th></tr></thead>
              <tbody>{ds.map((d) => <tr key={d.id}><td>{d.t}</td><td>{d.grade.letter ?? "–"} ({d.grade.score ?? "–"})</td><td>{n(d.f.subs)}</td><td>{pct(d.f.growth)}</td><td>{n(d.f.avg_views)}</td><td>{pct(d.f.engagement, 2)}</td><td>{won(d.f.rev[0])}~{won(d.f.rev[1])}</td></tr>)}</tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}

// ------------------------------------------------------------------ 지표 정의 · 쿼터 · 보존 정책
export function AboutPage() {
  const [s, e] = useData<Summary>("summary.json");
  if (!s) return <Loading err={e} />;
  return (
    <section>
      <h2>📐 지표 정의 · 운영 현황</h2>
      <p className="small muted">갱신 {s.generated_at} · 모드 {s.mode === "live" ? "실제 수집" : s.mode}</p>
      <h3>오늘 쿼터 {n(s.quota.today)} / {n(s.quota.budget)} 유닛</h3>
      <div className="part"><span className="part-bar wide"><span style={{ width: `${Math.min(100, (s.quota.today / s.quota.budget) * 100)}%` }} /></span></div>
      <div className="table-wrap"><table><thead><tr><th>엔드포인트</th><th>호출</th><th>유닛</th></tr></thead>
        <tbody>{s.quota.by_endpoint.map((q) => <tr key={q.endpoint + q.job}><td>{q.endpoint} ({q.job})</td><td>{q.calls}</td><td>{q.units}</td></tr>)}</tbody></table></div>
      <h3>산식 (화면의 모든 '추정·등급·예측'은 아래 공식 그대로)</h3>
      <dl className="formulas">{Object.entries(s.formulas).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>
      <h3>RPM 가정치 (원/1,000회) <Est formula="config/rpm_kr.yaml — 실측 아님. Phase 2에서 내 채널 실측 RPM으로 보정" /></h3>
      <div className="table-wrap"><table><thead><tr><th>카테고리</th><th>하한</th><th>상한</th></tr></thead>
        <tbody>{Object.entries(s.rpm).map(([k, [lo, hi]]) => <tr key={k}><td>{s.categories[k] ?? k}</td><td>{k.startsWith("kw_") ? `×${lo}` : n(lo)}</td><td>{k.startsWith("kw_") ? `×${hi}` : n(hi)}</td></tr>)}</tbody></table></div>
      <h3>시드에서 제외된 항목 ({s.seed_excluded.length})</h3>
      <ul className="small">{s.seed_excluded.map((x) => <li key={x.group + x.q}>{x.group} · {x.q} — {x.reason}</li>)}</ul>
      <p className="small muted">YouTube API 데이터 · 영상/음성은 다운로드하지 않고 메타데이터와 썸네일 URL만 사용합니다.</p>
    </section>
  );
}

// ------------------------------------------------------------------ M1-5 주제 트렌드
export function TrendPage() {
  const [d, e] = useData<Trends>("trends.json");
  const [mode, setMode] = useState<"rising" | "frequent">("rising");
  if (!d) return <Loading err={e} />;
  const list = mode === "rising" && d.has_prev ? d.rising : d.frequent;
  const max = Math.max(1, ...list.map((x) => x.n));
  return (
    <section>
      <h2>📈 주제 트렌드 <span className="muted small">{d.window[0]} ~ {d.window[1]}</span></h2>
      <p className="small muted">{d.formula}</p>
      <div className="filters"><Seg value={mode} onChange={setMode} options={[["rising", "🚀 급부상"], ["frequent", "🔁 많이 나온"]]} /></div>
      {mode === "rising" && !d.has_prev && <div className="banner">지난주 데이터가 쌓이면(7일 후) 급부상 순위가 켜집니다. 지금은 빈도 순입니다.</div>}
      <ol className="rank-list">
        {list.map((k, i) => (
          <li key={k.kw} className="rank-row">
            <span className="badge">{i + 1}</span>
            <div className="grow">
              <b>{k.kw}</b> <span className="small muted">{k.n}편{k.growth ? ` · 지난주 ${k.prev}편 → ${k.growth}배` : ""}</span>
              <div className="part"><span className="part-bar wide"><span style={{ width: `${(k.n / max) * 100}%` }} /></span></div>
              <ul className="small reasons-plain">{k.examples.map((x) => <li key={x.id}><a href={`https://www.youtube.com/watch?v=${x.id}`} target="_blank" rel="noreferrer">{x.t}</a></li>)}</ul>
              <div className="row-actions">
                <a className="btn small primary" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: `kw:${k.kw}`, title: `키워드 기획: ${k.kw}`, channel: "키워드", group: "", recipe: "R2" }, `키워드 기획: ${k.kw}`)}>▶ 기획 큐로</a>
                <a className="btn small" target="_blank" rel="noreferrer" href={`https://www.youtube.com/results?search_query=${encodeURIComponent(k.kw)}`}>유튜브에서 보기</a>
              </div>
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}

// ------------------------------------------------------------------ 🔍 채널 검색 · 분석 요청
type SearchRow = [string, string | null, string | null, number | null, string | null];
export function SearchPage({ q: initial }: { q: string }) {
  const [idx, e] = useData<SearchRow[]>("search.json");
  const [q, setQ] = useState(initial);
  const [g, setG] = useState("");
  useEffect(() => { const h = `#/search?q=${encodeURIComponent(q)}`; if (location.hash !== h) history.replaceState(null, "", h); }, [q]);
  if (!idx) return <Loading err={e} />;
  const k = q.trim().toLowerCase().replace(/^@/, "");
  const hits = k.length === 0 ? [] : idx.filter((r) => (r[1] ?? "").toLowerCase().includes(k) || (r[2] ?? "").toLowerCase().replace(/^@/, "").includes(k) || r[0].toLowerCase() === k.toLowerCase()).slice(0, 30);
  const reqUrl = issueUrlAnalyze(q.trim(), g);
  return (
    <section>
      <h2>🔍 채널 검색 · 분석</h2>
      <div className="search"><input autoFocus value={q} onChange={(x) => setQ(x.target.value)} placeholder="채널 이름 · @핸들 · 유튜브 주소" aria-label="채널 검색" /></div>
      <p className="small muted">레이더가 추적 중인 {idx.length.toLocaleString()}개 채널에서 바로 찾습니다. 없으면 아래 [분석 요청]으로 추가하면 3~5분 뒤 분석 화면이 생기고, 이후 매일 자동 추적됩니다.</p>
      {hits.length > 0 && <ol className="rank-list">{hits.map((r) => (
        <li key={r[0]} className="rank-row"><div className="grow"><a className="vtitle" href={`#/ch/${r[0]}`}>{r[1] ?? r[0]}</a>
          <div className="small muted">{r[2] ?? ""} · 구독 {n(r[3])} · {r[4] ?? "그룹 미지정"}</div></div>
          <a className="btn small" href={`#/ch/${r[0]}`}>분석 보기</a></li>))}</ol>}
      {k.length > 0 && (
        <div className="vcard">
          <b>{hits.length === 0 ? "추적 중인 채널에 없습니다." : "찾는 채널이 목록에 없나요?"}</b>
          <p className="small">유튜브 채널 주소(https://www.youtube.com/@핸들)나 @핸들로 요청하면 쿼터 약 3유닛, 이름으로 요청하면 100유닛(하루 20회 한도)을 씁니다.</p>
          <div className="filters"><select value={g} onChange={(x) => setG(x.target.value)} aria-label="내 채널 그룹"><option value="">내 채널 그룹(선택)</option>{GROUPS.map((x) => <option key={x}>{x}</option>)}</select></div>
          <a className="btn primary wide" href={reqUrl} target="_blank" rel="noreferrer">🔍 "{q.trim()}" 분석 요청</a>
          <p className="small muted">GitHub 화면이 열리면 Submit new issue만 누르세요.</p>
        </div>
      )}
    </section>
  );
}
const GROUPS = ["경제적자유구역", "지혜의숲", "히스토리X", "음악플레이리스트", "레트로TV", "국뽕두그릇", "부자아이", "새시대유감", "깡통봇", "REDPANG", "춘식이만식이", "웃GO", "진영논리"];
function issueUrlAnalyze(q: string, group: string) {
  const body = ["<!-- radar-analyze: 아래 JSON 블록은 수정하지 마세요 -->", "```json", JSON.stringify({ action: "analyze", q, group: group || null }), "```"].join("\n");
  return `https://github.com/kaycomm21/niche-radar/issues/new?${new URLSearchParams({ title: `[채널분석] ${q}`.slice(0, 100), body }).toString()}`;
}
