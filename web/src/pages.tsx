import { useEffect, useMemo, useState } from "react";
import { load, type ChannelDetail, type Charts, type Queue, type RankRow, type Summary, type Trends, type VCard } from "./api";
import { LineChart, RadarChart, Heatmap } from "./charts";
import { dur, n, pct, won } from "./fmt";
import { Est, ExcludeChannel, issueUrl, Loading, REPO, Seg, VideoCard } from "./ui";

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
        <p className="small muted">점수 상위 3건 (서로 다른 채널 그룹 우선). 🎬 Cue → GitHub 초록 Create → 1~2분 뒤 📦 생산 패키지 자동 생성. 7일 무응답 시 자동 보관. 'AI 대기' = 적합도 채점 전(매일 06:17 채점).</p>
        {q.top3.length === 0 && <div className="empty">오늘은 기준을 넘는 후보가 없습니다.</div>}
        {q.top3.map((v, i) => <VideoCard key={v.id} v={v} detail bench={v.g ? q.bench?.[v.g] : undefined} rankBadge={<span className="badge">{i + 1}</span>} />)}
      </section>
      <section>
        <h2>🗂 판정 대기 카드 <span className="muted small">{q.pending.length}건</span></h2>
        {q.pending.map((v) => <VideoCard key={v.id} v={v} bench={v.g ? q.bench?.[v.g] : undefined} extra={<details className="small"><summary>점수 근거</summary><VideoCardScore v={v} /></details>} />)}
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
  const [reg, setReg] = useState<"all" | "kr" | "foreign">("kr");
  if (!c) return <Loading err={e} />;
  const items = (c.charts[cat]?.[fmt] ?? []).filter((v) => reg === "all" || (reg === "kr") === isKorean(v));
  return (
    <section>
      <h2>🌐 국내 인기 차트 <span className="muted small">{c.date}</span></h2>
      <div className="filters">
        <select value={cat} onChange={(x) => { setCat(x.target.value); setLimit(30); }} aria-label="카테고리">
          {Object.entries(c.categories).map(([k, v]) => <option key={k} value={k} disabled={!c.charts[k]}>{v}{!c.charts[k] ? " (차트 없음)" : ""}</option>)}
        </select>
        <Seg value={fmt} onChange={setFmt} options={[["long", "롱폼"], ["short", "쇼츠"]]} />
        <Seg value={reg} onChange={setReg} options={[["kr", "🇰🇷 국내"], ["foreign", "🌍 해외"], ["all", "전체"]]} />
      </div>
      <div className="chips">{Object.entries(c.categories).filter(([k]) => c.charts[k]).map(([k, v]) => <button key={k} type="button" className={`chip chip-btn ${cat === k ? "on" : ""}`} onClick={() => { setCat(k); setLimit(30); }}>{v}</button>)}</div>
      <p className="small muted">국내/해외 구분: 제목에 한글이 있거나 채널 국가가 한국이면 국내. 해외 원본으로 한국판을 만들려면 🌍 해외 레퍼런스 메뉴를 쓰세요.</p>
      {items.length === 0 && <div className="empty">이 조건의 오늘 차트가 없습니다.</div>}
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
                {r.top && <a className="btn small cue" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: r.top.id, title: r.top.t, channel: r.t, group: r.g ?? "", recipe: r.top.rc[0] }, r.top.t)}>▶ 히트 큐로</a>}
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
  const [per, setPer] = useState<Period>({ key: "30", from: "", to: "" });
  if (!c) return <Loading err={e} />;
  const [pf, pt] = periodRange(per, c.hist.length ? c.hist[c.hist.length - 1][0] : new Date().toISOString().slice(0, 10));
  const inP = (d: string) => d >= pf && d <= pt;
  const pVideos = c.videos.filter((v) => inP(v.pub));
  const pStats = pVideos.length ? { n: pVideos.length, avg: pVideos.reduce((a, v) => a + (v.v ?? 0), 0) / pVideos.length,
    like: med(pVideos.filter((v) => v.v).map((v) => (v.lk ?? 0) / (v.v as number))), cm: med(pVideos.filter((v) => v.v).map((v) => (v.cm ?? 0) / (v.v as number))) } : null;
  const f = c.f, F = s?.formulas ?? {};
  const idx = metric === "subs" ? 1 : 2;
  const fc = metric === "subs" ? c.fc_subs : c.fc_views;
  const hist = c.hist.filter((h) => inP(h[0])).map((h) => ({ x: h[0], y: h[idx] as number | null }));
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
        <div className="grade-wrap"><span className={`grade lg g-${c.grade.letter ?? "na"}`}>{c.grade.letter ?? "–"}</span>
          <Est kind={`등급 ${c.grade.score ?? "–"}점`} formula={"투명 등급(S·A·B·C·D) = 레이더가 추적하는 채널들 안에서의 상대 평가. " + (F.grade ?? "") + ` · 현재 데이터 ${f.days_hist}일치라 '성장률'은 7일 이상 쌓여야 반영됩니다.`} /></div>
      </div>

      <div className="kpis">
        <div className="kpi"><span>구독자</span><b>{n(f.subs)}</b><small>7일 {sign(diff(7))} · 30일 {sign(diff(30))}</small></div>
        <div className="kpi"><span>최근 30일 업로드 조회</span><b>{n(f.views30_uploads)}</b><small>{f.uploads30}편 업로드</small></div>
        <div className="kpi"><span>예상 월 광고수익 <Est formula={F.revenue ?? ""} /></span><b>{won(f.rev[0])}~{won(f.rev[1])}</b><small>추정 · 실측 아님</small></div>
        <div className="kpi"><span>예상 PPL 단가(1편) <Est formula={F.ppl ?? ""} /></span><b>{f.ppl ? `${won(f.ppl[0])}~${won(f.ppl[1])}` : "–"}</b><small>광고주 관점 추정</small></div>
        <div className="kpi"><span>참여율(중앙값)</span><b>{pct(f.engagement, 2)}</b><small>(좋아요+댓글)÷조회</small></div>
      </div>

      <div className="row-actions"><a className="btn small" href={`#/calc?id=${c.id}`}>💰 이 채널 수익 계산기</a></div>
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

      <div className="panel" style={{ marginTop: 14 }}>
        <b>📆 분석 기간</b> <span className="small muted">— 아래 '영상 분석 · 일별 변화 · 추이' 에 모두 적용</span>
        <PeriodPicker value={per} onChange={setPer} />
        <span className="small muted">{pf} ~ {pt}</span>
      </div>

      <h3>🎞 영상 분석 ({pf.slice(5)}~{pt.slice(5)} 업로드)</h3>
      <div className="table-wrap"><table><thead><tr><th>지표</th><th>이 채널</th><th>카테고리 평균(최근 30편)</th></tr></thead><tbody>
        <tr><td>영상 수</td><td>{pStats?.n ?? 0}</td><td>–</td></tr>
        <tr><td>평균 조회</td><td>{n(pStats?.avg)}</td><td>{n(c.video_stats.category?.avg_views)}</td></tr>
        <tr><td>좋아요율 (중앙값)</td><td>{pct(pStats?.like, 2)}</td><td>{pct(c.video_stats.category?.like_rate, 2)}</td></tr>
        <tr><td>댓글율 (중앙값)</td><td>{pct(pStats?.cm, 3)}</td><td>{pct(c.video_stats.category?.comment_rate, 3)}</td></tr>
      </tbody></table></div>
      <p className="small muted">채널당 최근 30편까지 수집하므로, 업로드가 잦은 채널은 긴 기간을 골라도 최근 30편 안에서만 계산됩니다.</p>

      <h3>📅 일별 변화 <Est kind="참고" formula="YouTube API는 구독자 수를 유효숫자 3자리로 반올림해 줍니다(예: 374만). 그래서 큰 채널은 구독 변화가 며칠 동안 +0으로 보일 수 있습니다. 조회수는 정확한 값입니다." /></h3>
      {c.daily.length === 0 ? <p className="small muted">2일째 데이터부터 표시됩니다.</p> : (
        <div className="table-wrap"><table><thead><tr><th>날짜</th><th>구독 변화</th><th>구독자</th><th>조회 변화</th></tr></thead><tbody>
          {c.daily.filter((r) => inP(r.d)).map((r) => <tr key={r.d}><td>{r.d.slice(5)}</td><td className={delta(r.ds)}>{sign(r.ds)}</td><td>{n(r.subs)}</td><td className={delta(r.dv)}>{sign(r.dv)}</td></tr>)}
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
type Period = { key: string; from: string; to: string };
const PERIODS: [string, string, number][] = [["7", "일주일", 7], ["30", "한달", 30], ["90", "분기", 90], ["180", "반기", 180], ["365", "1년", 365], ["custom", "직접 설정", 0]];
function periodRange(p: Period, last: string): [string, string] {
  if (p.key === "custom") return [p.from || "2000-01-01", p.to || last];
  const days = PERIODS.find((x) => x[0] === p.key)?.[2] ?? 30;
  return [addDays(last, -(days - 1)), last];
}
function PeriodPicker({ value, onChange }: { value: Period; onChange: (p: Period) => void }) {
  return (
    <div className="period">
      <Seg value={value.key} onChange={(k) => onChange({ ...value, key: k })} options={PERIODS.map(([k, l]) => [k, l] as [string, string])} />
      {value.key === "custom" && <>
        <input type="date" value={value.from} onChange={(e) => onChange({ ...value, from: e.target.value })} aria-label="시작일" />
        <span>~</span>
        <input type="date" value={value.to} onChange={(e) => onChange({ ...value, to: e.target.value })} aria-label="종료일" />
      </>}
    </div>
  );
}
function med(xs: number[]) { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); return s[Math.floor(s.length / 2)]; }
function isKorean(v: VCard) { return v.cc === "KR" || v.lang === "ko"; }
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
type GItem = { kw: string; traffic: string | null; pub: string | null; news: { title: string; url: string; source: string }[];
  plan: { group: string | null; titles: string[]; hook: string; outline: string[]; life: string; blog_angle?: string; risk?: string; by: string } };
export function TrendPage() {
  const [src, setSrc] = useState<"yt" | "google">("google");
  return (<>
    <div className="filters" style={{ marginTop: 14 }}><Seg value={src} onChange={setSrc} options={[["google", "🔎 구글 급상승 검색어 → 기획안"], ["yt", "▶ 유튜브 차트 키워드"]]} /></div>
    {src === "google" ? <GoogleTrends /> : <YtTrends />}
  </>);
}
function GoogleTrends() {
  const [d, e] = useData<{ date: string; items: GItem[] }>("gtrends.json");
  if (e) return <div className="empty">구글 트렌드 데이터가 아직 없습니다 — 다음 자동 수집(매일 06:17) 후 표시됩니다.</div>;
  if (!d) return <Loading />;
  return (
    <section>
      <h2>🔎 구글 급상승 검색어 (한국) <span className="muted small">{d.date}</span></h2>
      <p className="small muted">출처: Google Trends 공식 RSS · 기획안은 {d.items[0]?.plan.by ?? "-"} (Gemini 키가 있으면 AI 기획). 이슈성 주제는 48시간 안에 만들 때만 가치가 있습니다.</p>
      {d.items.map((it) => (
        <article key={it.kw} className="vcard">
          <div className="vcard-top"><span className="badge">🔥</span><div className="vcard-meta">
            <b className="vtitle">{it.kw}</b><div className="small muted">검색 {it.traffic ?? "-"} · → {it.plan.group ?? "내 채널 매핑 없음"} · {it.plan.life}</div>
            <ul className="small reasons-plain">{it.news.map((nw) => <li key={nw.url}><a href={nw.url} target="_blank" rel="noreferrer">{nw.title}</a> <span className="muted">{nw.source}</span></li>)}</ul></div></div>
          <details className="small"><summary>📝 콘텐츠 기획안 보기</summary>
            <p><b>제목 후보</b></p><ol>{it.plan.titles.map((t) => <li key={t}>{t}</li>)}</ol>
            <p><b>첫 3초</b> {it.plan.hook}</p>
            <p><b>구성</b></p><ol>{it.plan.outline.map((t) => <li key={t}>{t}</li>)}</ol>
            {it.plan.blog_angle && <p><b>블로그 각도</b> {it.plan.blog_angle}</p>}
            {it.plan.risk && <p className="warn">⚠️ {it.plan.risk}</p>}
          </details>
          <div className="row-actions">
            <a className="btn small cue" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: `gt:${it.kw}`, title: `구글트렌드 기획: ${it.kw}`, channel: "구글 트렌드", group: it.plan.group ?? "", recipe: "R2" }, `구글트렌드 기획: ${it.kw}`)}>🎬 Cue</a>
            <a className="btn small" href={`#/blog?kw=${encodeURIComponent(it.kw)}`}>✍️ 블로그 글로</a>
          </div>
        </article>
      ))}
    </section>
  );
}
function YtTrends() {
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
                <a className="btn small cue" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: `kw:${k.kw}`, title: `키워드 기획: ${k.kw}`, channel: "키워드", group: "", recipe: "R2" }, `키워드 기획: ${k.kw}`)}>▶ 기획 큐로</a>
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
  return `https://github.com/${REPO}/issues/new?${new URLSearchParams({ title: `[채널분석] ${q}`.slice(0, 100), body }).toString()}`;
}

// ------------------------------------------------------------------ 🏠 홈 (플레이보드형 랭킹 보드)
type HomeData = { date: string; chart_long: VCard[]; chart_short: VCard[]; top24: VCard[]; explode: VCard[];
  subs_rise: { id: string; t: string | null; th: string | null; subs: number | null; gain: number; rate: number | null; win: string }[];
  views_rise: { id: string; t: string | null; th: string | null; subs: number | null; gain: number }[] };
function VList({ items, val }: { items: VCard[]; val: (v: VCard) => string }) {
  return <>{items.slice(0, 10).map((v, i) => (
    <div key={v.id} className="mini"><span className="no">{i + 1}</span>{v.th ? <img src={v.th} alt="" loading="lazy" /> : <span className="ph" />}
      <div className="tx"><a href={`https://www.youtube.com/watch?v=${v.id}`} target="_blank" rel="noreferrer">{v.t}</a><a className="small muted" href={`#/ch/${v.c}`} style={{ fontWeight: 400 }}>{v.ct}</a></div>
      <span className="val">{val(v)}</span></div>))}</>;
}
export function HomeBoard() {
  const [d, e] = useData<HomeData>("home.json");
  const [q] = useData<Queue>("queue.json");
  if (!d) return <Loading err={e} />;
  return (
    <>
      <div className="hero">
        <h2>오늘 유튜브에서 무엇이 터졌나 <span className="muted small">{d.date}</span></h2>
        <p className="small muted">국내 인기 차트 + 추적 채널 {""}기준. 마음에 드는 소재는 🎬 Cue 하면 대본 패키지로 자동 생성됩니다.</p>
        {q && q.top3.length > 0 && <div className="row-actions"><a className="btn primary" href="#/queue">🎯 오늘의 생산 큐 후보 {q.top3.length}건 보기</a></div>}
      </div>
      <div className="board three">
        <section className="panel"><h3>🌐 인기 차트 (롱폼) <a href="#/chart">더보기</a></h3><VList items={d.chart_long} val={(v) => n(v.v)} /></section>
        <section className="panel"><h3>📱 인기 쇼츠 <a href="#/chart">더보기</a></h3><VList items={d.chart_short} val={(v) => n(v.v)} /></section>
        <section className="panel"><h3>⚡ 24시간 최다 조회 증가 <a href="#/surge">더보기</a></h3><VList items={d.top24} val={(v) => "+" + n(v.v24)} /></section>
        <section className="panel"><h3>📈 구독자 급상승 채널 <a href="#/rank">더보기</a></h3>
          {d.subs_rise.slice(0, 10).map((r, i) => <div key={r.id} className="mini"><span className="no">{i + 1}</span>{r.th ? <img className="round" src={r.th} alt="" loading="lazy" /> : <span className="ph" />}
            <div className="tx"><a href={`#/ch/${r.id}`}>{r.t}</a><span className="small muted">구독 {n(r.subs)}</span></div><span className="val up">+{n(r.gain)} <small>({r.win})</small></span></div>)}
          {d.subs_rise.length === 0 && <div className="small muted">2일째 데이터부터 표시</div>}</section>
        <section className="panel"><h3>👀 하루 조회 증가 채널</h3>
          {d.views_rise.slice(0, 10).map((r, i) => <div key={r.id} className="mini"><span className="no">{i + 1}</span>{r.th ? <img className="round" src={r.th} alt="" loading="lazy" /> : <span className="ph" />}
            <div className="tx"><a href={`#/ch/${r.id}`}>{r.t}</a><span className="small muted">구독 {n(r.subs)}</span></div><span className="val">+{n(r.gain)}</span></div>)}</section>
        <section className="panel"><h3>💥 이번 주 10배 터진 영상 <a href="#/surge">더보기</a></h3><VList items={d.explode} val={(v) => `${v.mx?.toFixed(0)}×`} />
          {d.explode.length === 0 && <div className="small muted">해당 없음</div>}</section>
      </div>
    </>
  );
}

// ------------------------------------------------------------------ 💰 유튜브 수익 계산기
export function CalcPage({ id }: { id: string }) {
  const [s] = useData<Summary>("summary.json");
  const [rk] = useData<{ items: RankRow[] }>("rankings.json");
  const [daily, setDaily] = useState(10000);
  const [longPct, setLongPct] = useState(70);
  const [cat, setCat] = useState("27");
  const [fin, setFin] = useState(false);
  const [target, setTarget] = useState(10000000);
  const [pick, setPick] = useState(id);
  useEffect(() => {
    const r = rk?.items.find((x) => x.id === pick);
    if (r) setDaily(Math.max(1, Math.round((r.v30 || 0) / 30)));
  }, [pick, rk]);
  if (!s) return <Loading />;
  const rpm = s.rpm[cat] ?? s.rpm["default"] ?? [800, 2500];
  const sh = s.rpm["shorts"] ?? [30, 120];
  const k = fin ? (s.rpm["kw_finance"]?.[0] ?? 1.6) : 1;
  const per1000 = (i: 0 | 1) => (longPct / 100) * rpm[i] * k + (1 - longPct / 100) * sh[i];
  const day = [daily * per1000(0) / 1000, daily * per1000(1) / 1000];
  const need = [target / 30 / per1000(1) * 1000, target / 30 / per1000(0) * 1000];
  const chosen = rk?.items.find((x) => x.id === pick);
  return (
    <section>
      <h2>💰 유튜브 수익 계산기 <Est formula="수익 = 일 조회수 × (롱폼 비율 × 카테고리 RPM + 쇼츠 비율 × 쇼츠 RPM) ÷ 1000. RPM은 config/rpm_kr.yaml 의 가정치(실측 아님). 내 채널 실측 RPM이 연결되면 자동 보정." /></h2>
      <div className="panel calc-grid">
        <label>채널에서 불러오기 (최근 30일 업로드 조회 ÷ 30)
          <select value={pick} onChange={(e) => setPick(e.target.value)}><option value="">직접 입력</option>
            {rk?.items.slice().sort((a, b) => (b.subs ?? 0) - (a.subs ?? 0)).slice(0, 400).map((r) => <option key={r.id} value={r.id}>{r.t}</option>)}</select></label>
        <label>일 평균 조회수<input type="number" value={daily} min={0} onChange={(e) => { setDaily(Number(e.target.value)); setPick(""); }} /></label>
        <label>롱폼 비율 {longPct}% (나머지 쇼츠)<input type="range" min={0} max={100} value={longPct} onChange={(e) => setLongPct(Number(e.target.value))} /></label>
        <label>카테고리<select value={cat} onChange={(e) => setCat(e.target.value)}>{Object.keys(s.rpm).filter((x) => /^\d+$/.test(x)).map((x) => <option key={x} value={x}>{s.categories[x] ?? x} ({n(s.rpm[x][0])}~{n(s.rpm[x][1])}원)</option>)}</select></label>
        <label style={{ flexDirection: "row", alignItems: "center" }}><input type="checkbox" checked={fin} onChange={(e) => setFin(e.target.checked)} /> 금융·재테크 주제 (RPM ×{s.rpm["kw_finance"]?.[0] ?? 1.6})</label>
        <label>목표 월 수익 (원)<input type="number" value={target} step={1000000} onChange={(e) => setTarget(Number(e.target.value))} /></label>
      </div>
      {chosen && <p className="small muted">불러온 채널: {chosen.t} · 최근 30일 업로드 조회 {n(chosen.v30)}</p>}
      <div className="kpis">
        <div className="kpi"><span>예상 일 수익</span><b>{won(day[0])}~{won(day[1])}</b><small>추정</small></div>
        <div className="kpi"><span>예상 월 수익</span><b>{won(day[0] * 30)}~{won(day[1] * 30)}</b><small>추정</small></div>
        <div className="kpi"><span>예상 연 수익</span><b>{won(day[0] * 365)}~{won(day[1] * 365)}</b><small>추정</small></div>
        <div className="kpi"><span>목표 {won(target)}/월에 필요한 일 조회</span><b>{n(need[0])}~{n(need[1])}</b><small>RPM 상한~하한 기준</small></div>
      </div>
      <p className="small muted">⚠️ 광고 수익만 계산합니다(PPL·멤버십·슈퍼챗 제외). 실제 RPM은 시청자 국가·시즌·영상 길이에 따라 크게 달라집니다.</p>
    </section>
  );
}

// ------------------------------------------------------------------ ✍️ 블로그 스튜디오
export function BlogStudio({ pkg }: { pkg?: string }) {
  const init = new URLSearchParams(location.hash.split("?")[1] ?? "");
  const [mode, setMode] = useState<"keyword" | "rewrite">("keyword");
  const [kw, setKw] = useState(init.get("kw") ?? "");
  const [draft, setDraft] = useState("");
  const [yt, setYt] = useState("");
  const [ch, setCh] = useState(() => { try { return localStorage.getItem("ccs.channel") ?? ""; } catch { return ""; } });
  const [len, setLen] = useState(2500);
  const [tone, setTone] = useState("친근한 전문가");
  const [wp, setWp] = useState(true);
  const [nv, setNv] = useState(true);
  useEffect(() => { try { localStorage.setItem("ccs.channel", ch); } catch { /* 무시 */ } }, [ch]);
  const cfg = { action: "blog", mode, package: pkg || null, keyword: kw, youtube: yt || null, channel_url: ch || null, length: len, tone, platforms: [wp && "wordpress", nv && "naver"].filter(Boolean) };
  const body = ["<!-- radar-blog: 아래 JSON 블록은 수정하지 마세요 -->", "```json", JSON.stringify(cfg), "```", "", "## 초안", draft.slice(0, 5000), "",
    "<!-- 📷 사진: 이 줄 아래에 사진 파일을 끌어다 놓으세요 (순서대로 섹션에 배치됩니다) -->", ""].join("\n");
  const url = `https://github.com/${REPO}/issues/new?${new URLSearchParams({ title: `[블로그] ${mode === "keyword" ? kw : (draft.slice(0, 30) || "초안 다듬기")}`, body }).toString()}`;
  const ok = Boolean(pkg) || (mode === "keyword" ? kw.trim().length > 0 : draft.trim().length > 30);
  return (
    <section>
      <h2>✍️ 글공방 <span className="muted small">CCS 블로그 생성기 · 워드프레스 · 네이버 투트랙</span></h2>
      {pkg && <div className="banner">📦 생산 패키지 대본을 블로그 글로 변환합니다: <code>{pkg}</code></div>}
      <div className="filters"><Seg value={mode} onChange={setMode} options={[["keyword", "🔑 키워드로 글쓰기"], ["rewrite", "📝 막 쓴 초안 → 블로그 글"]]} /></div>
      <div className="panel calc-grid">
        <label>{mode === "keyword" ? "핵심 키워드" : "참고 키워드(선택)"}<input value={kw} onChange={(e) => setKw(e.target.value)} placeholder="예: 금리 인상 대출 갈아타기" /></label>
        <label>분량<select value={len} onChange={(e) => setLen(Number(e.target.value))}><option value={1500}>짧게 (1,500자)</option><option value={2500}>보통 (2,500자)</option><option value={4000}>길게 (4,000자)</option></select></label>
        <label style={{ gridColumn: "1 / -1" }}>{mode === "rewrite" ? "막 쓴 초안 (두서없이 써도 됩니다 — 내 경험이 그대로 살아납니다)" : "메모 (선택: 꼭 넣을 내용·경험)"}
          <textarea rows={8} value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="생각나는 대로 적으세요" /></label>
        <label>톤<select value={tone} onChange={(e) => setTone(e.target.value)}>{["친근한 전문가", "차분한 정보형", "현장 경험담", "리뷰형"].map((t) => <option key={t}>{t}</option>)}</select></label>
        <label>마지막에 넣을 내 유튜브 영상 주소<input value={yt} onChange={(e) => setYt(e.target.value)} placeholder="https://youtu.be/..." /></label>
        <label>내 채널 주소 (구독 버튼용, 저장됨)<input value={ch} onChange={(e) => setCh(e.target.value)} placeholder="https://www.youtube.com/@내채널" /></label>
        <label style={{ flexDirection: "row", gap: 12, alignItems: "center" }}><span><input type="checkbox" checked={wp} onChange={(e) => setWp(e.target.checked)} /> 워드프레스</span><span><input type="checkbox" checked={nv} onChange={(e) => setNv(e.target.checked)} /> 네이버</span></label>
      </div>
      <a className={`btn cue wide ${ok ? "" : "disabled"}`} href={ok ? url : undefined} target="_blank" rel="noreferrer">✍️ 글 만들기 요청</a>
      <div className="panel small">
        <b>📷 사진 넣는 법</b> — 열린 GitHub 화면의 본문 맨 아래에 사진 파일을 <b>끌어다 놓기</b> → 오른쪽 아래 초록 <b>Create</b>. 사진은 순서대로 각 소제목 아래에 자동 배치되고, 사진 설명(alt)도 자동으로 붙습니다.<br />
        <b>⏱ 결과</b> — 1~2분 뒤 그 Issue에 링크가 달립니다: 워드프레스용 HTML · 네이버용 텍스트([사진 n] 위치 표시) · 제목/태그 · 검수표.<br />
        <b>✅ 발행 원칙</b> — 주 2~3편. 글 속 <code>[✍️ 직접 경험 한 줄]</code> 2곳은 반드시 직접 채우세요 (구글·네이버 모두 경험 없는 AI 글을 낮게 평가).<br />
        <b>🔑 필요</b> — GitHub Secret <code>GEMINI_API_KEY</code> (없으면 Issue에 안내가 달립니다).
      </div>
    </section>
  );
}

// ------------------------------------------------------------------ 🌍 해외 레퍼런스 → 한국화
type LocPlan = { ko_title_meaning?: string; why_hit?: string; group?: string | null; ko_titles?: string[]; ko_angle?: string; fit?: number };
export function OverseasPage() {
  const [d, e] = useData<{ date: string; charts: Record<string, { name: string; long: VCard[]; short: VCard[] }>; plans: Record<string, LocPlan> }>("overseas.json");
  const [key, setKey] = useState("US:0");
  const [fmt, setFmt] = useState<"long" | "short">("long");
  if (e) return <div className="empty">해외 차트는 다음 자동 수집(매일 06:17) 후 표시됩니다.</div>;
  if (!d) return <Loading />;
  const ch = d.charts[key] ?? Object.values(d.charts)[0];
  // 음악(10)은 한국화 재생산이 불가 → 제외. AI 적합 0점도 제외. 적합도 높은 순 → 기획안 없는 것은 원래 순위대로 뒤에.
  const all = (ch?.[fmt] ?? []).filter((v) => !isKorean(v));
  const fitOf = (v: VCard) => d.plans[v.id]?.fit ?? -1;
  const list = all.filter((v) => v.cat !== "10" && fitOf(v) !== 0).sort((a, b) => fitOf(b) - fitOf(a));
  const hidden = all.length - list.length;
  return (
    <section>
      <h2>🌍 해외 레퍼런스 → 한국화 <span className="muted small">{d.date}</span></h2>
      <p className="small muted">해외에서 지금 터진 영상을 한국 맥락으로 재기획(R6). 원본 번역·짜깁기는 재사용 콘텐츠 정책 위반 — 주제와 공식만 차용합니다. 🤖 한국화 기획안은 Gemini 키가 있으면 상위 영상에 자동 생성.</p>
      <div className="chips">{Object.entries(d.charts).map(([k, v]) => <button key={k} type="button" className={`chip chip-btn ${key === k ? "on" : ""}`} onClick={() => setKey(k)}>{v.name}</button>)}</div>
      <div className="filters"><Seg value={fmt} onChange={setFmt} options={[["long", "롱폼"], ["short", "쇼츠"]]} /></div>
      {hidden > 0 && <p className="small muted">음악·적합도 0점 {hidden}건은 숨김 (한국화 재생산 불가) · 적합도 높은 순</p>}
      {list.map((v, i) => {
        const pl = d.plans[v.id];
        return (
          <article key={v.id} className="vcard">
            <div className="vcard-top"><span className="badge">{i + 1}</span>{v.th ? <img src={v.th} alt="" className="thumb" loading="lazy" /> : <div className="thumb" />}
              <div className="vcard-meta"><a className="vtitle" href={`https://www.youtube.com/watch?v=${v.id}`} target="_blank" rel="noreferrer">{v.t}</a>
                <div className="small muted">{v.ct} · 조회 {n(v.v)}{v.v24 ? ` · 24h +${n(v.v24)}` : ""}</div>
                {pl && <div className="small"><b>뜻</b> {pl.ko_title_meaning} · <b>왜 터졌나</b> {pl.why_hit}</div>}</div></div>
            {pl && <details className="small" open><summary>🤖 한국화 기획안 → {pl.group ?? "매핑 없음"} (적합 {pl.fit ?? "-"}/10)</summary>
              <ol>{(pl.ko_titles ?? []).map((t) => <li key={t}>{t}</li>)}</ol><p>{pl.ko_angle}</p></details>}
            <div className="row-actions">
              <a className="btn small cue" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: v.id, title: v.t, channel: v.ct, group: pl?.group ?? "", recipe: "R6" }, `[한국화] ${pl?.ko_titles?.[0] ?? v.t}`)}>🎬 Cue (한국화)</a>
              <a className="btn small" href={`#/blog?kw=${encodeURIComponent(pl?.ko_titles?.[0] ?? v.t)}`}>✍️ 글공방으로</a>
            </div>
          </article>);
      })}
    </section>
  );
}

// ------------------------------------------------------------------ 📦 생산 패키지 보드
type Pkg = { dir: string; title: string | null; channel: string | null; secs: number | null; shots: number; has_shorts: boolean; auto: boolean; date: string };
const STEPS = ["팩트체크", "톤 다듬기", "TTS·렌더", "B롤", "QC", "비공개 업로드", "공개"];
export function PackagesPage() {
  const [d, e] = useData<{ date: string; items: Pkg[]; queue: { id: string; title: string; group: string | null; status: string; issue: string }[] }>("packages.json");
  const [done, setDone] = useState<Record<string, number>>(() => { try { return JSON.parse(localStorage.getItem("ccs.steps") || "{}"); } catch { return {}; } });
  const mark = (k: string, i: number) => { const nx = { ...done, [k]: done[k] === i + 1 ? i : i + 1 }; setDone(nx); try { localStorage.setItem("ccs.steps", JSON.stringify(nx)); } catch { /* 무시 */ } };
  if (!d) return <Loading err={e} />;
  const gh = `https://github.com/${REPO}/tree/main/`;
  const waiting = d.queue.filter((q) => !d.items.some((p) => p.dir.includes(q.id)));
  return (
    <section>
      <h2>📦 생산 패키지 <span className="muted small">{d.items.length}개 · Cue 대기 {waiting.length}건</span></h2>
      <p className="small muted">🎬 Cue → (Gemini 키가 있으면) 1~2분 뒤 패키지 자동 생성 → 로컬 CC가 렌더·업로드. 단계 체크는 이 기기에 저장됩니다.</p>
      {d.items.slice().reverse().map((p) => (
        <article key={p.dir} className="vcard">
          <b className="vtitle">{p.title ?? p.dir}</b>
          <div className="small muted">{p.channel} · 약 {Math.round((p.secs ?? 0) / 60)}분 · B롤 {p.shots}샷 {p.has_shorts ? "· 쇼츠 포함" : ""} · {p.auto ? "🤖 자동 생성" : "✍️ 수동 제작"} · {p.date}</div>
          <div className="chips">{STEPS.map((s, i) => <button key={s} type="button" className={`chip chip-btn ${(done[p.dir] ?? 0) > i ? "on" : ""}`} onClick={() => mark(p.dir, i)}>{(done[p.dir] ?? 0) > i ? "✔ " : ""}{s}</button>)}</div>
          <div className="row-actions">
            <a className="btn small" href={gh + p.dir} target="_blank" rel="noreferrer">📂 파일 열기</a>
            <a className="btn small cue" href={`#/blog?pkg=${encodeURIComponent(p.dir)}`}>✍️ 블로그 글로 변환</a>
          </div>
        </article>
      ))}
      {waiting.length > 0 && <><h3>⏳ 패키지 대기 중인 Cue</h3><ul className="small">{waiting.map((q) => <li key={q.id}>#{q.issue} {q.title} <span className="muted">({q.group || "그룹 미지정"})</span></li>)}</ul>
        <p className="small muted">GEMINI_API_KEY 를 등록하면 매일 06:17 수집 때 최대 3건씩 자동 생성됩니다.</p></>}
    </section>
  );
}

// ------------------------------------------------------------------ 🏛 입찰레이더
type Bid = { no: string; name: string; org: string | null; demand: string | null; budget: number | null; method: string; close: string | null; dleft: number | null; url: string; score: number; parts: Record<string, number>; why: string[]; matches: string[] };
export function BidsPage() {
  const [d, e] = useData<{ date: string; mode: string; items: Bid[]; formula: string }>("bids.json");
  const [pk] = useData<{ proposals: { dir: string; name: string }[] }>("packages.json");
  const [home, setHome] = useState(false);
  const [nego, setNego] = useState(false);
  if (e) return <div className="empty">입찰 데이터는 다음 자동 수집(매일 06:17) 후 표시됩니다.</div>;
  if (!d) return <Loading />;
  const list = d.items.filter((b) => (!home || b.parts.region === 25) && (!nego || b.method.includes("협상")));
  return (
    <section>
      <h2>🏛 입찰레이더 <span className="muted small">{d.date} · {d.items.length}건</span></h2>
      {d.mode === "fixture" && <div className="banner">🧪 예시 데이터입니다. 공공데이터포털에서 <b>조달청_나라장터 입찰공고정보서비스</b> 활용신청 → 인증키를 GitHub Secret <code>DATA_GO_KR_KEY</code> 로 등록하면 실제 공고로 바뀝니다.</div>}
      <p className="small muted">{d.formula}</p>
      <div className="filters">
        <button type="button" className={`chip chip-btn ${home ? "on" : ""}`} onClick={() => setHome(!home)}>📍 대구·경북만</button>
        <button type="button" className={`chip chip-btn ${nego ? "on" : ""}`} onClick={() => setNego(!nego)}>📝 협상계약(제안서 평가)만</button>
      </div>
      {list.map((b) => (
        <article key={b.no} className="vcard">
          <div className="vcard-top"><span className={`grade ${b.score >= 70 ? "g-A" : b.score >= 50 ? "g-B" : "g-C"}`}>{b.score}</span>
            <div className="vcard-meta">{d.mode === "fixture" && <span className="chip">🧪 예시 · 실제 공고 아님</span>} <a className="vtitle" href={b.url} target="_blank" rel="noreferrer">{b.name}</a>
              <div className="small muted">{b.org}{b.demand && b.demand !== b.org ? ` · 수요 ${b.demand}` : ""} · {b.method || "계약방식 미상"}</div>
              <div className="small">예산 <b>{b.budget ? won(b.budget) : "-"}</b> · 마감 <b className={b.dleft !== null && b.dleft <= 5 ? "hot" : ""}>{b.close?.slice(0, 16) ?? "-"} (D-{b.dleft ?? "?"})</b></div>
              <div className="chips">{b.why.map((w) => <span key={w} className="chip">{w}</span>)}</div></div></div>
          <div className="row-actions">
            {pk?.proposals.some((p) => p.dir.includes(b.no)) ? <a className="btn small" href={`https://github.com/${REPO}/tree/main/${pk.proposals.find((p) => p.dir.includes(b.no))!.dir}`} target="_blank" rel="noreferrer">📄 제안서 초안 열기</a>
              : <a className="btn small cue" target="_blank" rel="noreferrer" href={issueUrl("queue", { id: `bid:${b.no}`, title: b.name, channel: b.org, group: "입찰", recipe: "제안" }, `[입찰] ${b.name}`)}>🎬 제안서 Cue</a>}
            <a className="btn small" href={b.url} target="_blank" rel="noreferrer">나라장터 원문</a>
          </div>
        </article>
      ))}
    </section>
  );
}

// ------------------------------------------------------------------ 🎯 월천 관제탑
const STREAMS = ["유튜브 광고", "블로그(애드센스·애드포스트)", "행사 기획·연출(입찰·프리)", "크몽·숨고", "PPL·협찬", "교재·출판", "기타"];
export function CockpitPage() {
  const [bids] = useData<{ mode?: string; items: Bid[] }>("bids.json");
  const [q] = useData<Queue>("queue.json");
  const [pk] = useData<{ items: Pkg[] }>("packages.json");
  const month = new Date().toISOString().slice(0, 7);
  const load = () => { try { return JSON.parse(localStorage.getItem("ccs.revenue") || "{}"); } catch { return {}; } };
  const [rev, setRev] = useState<Record<string, Record<string, number>>>(load);
  const [lastBlog, setLastBlog] = useState(() => { try { return localStorage.getItem("ccs.lastBlog") ?? ""; } catch { return ""; } });
  const save = (r: typeof rev) => { setRev(r); try { localStorage.setItem("ccs.revenue", JSON.stringify(r)); } catch { /* 무시 */ } };
  const cur = rev[month] ?? {};
  const total = Object.values(cur).reduce((a, b) => a + (b || 0), 0);
  const goal = 10_000_000;
  const end = new Date("2027-05-18");
  const monthsLeft = Math.max(0, (end.getFullYear() - new Date().getFullYear()) * 12 + end.getMonth() - new Date().getMonth());
  const steps = (() => { try { return JSON.parse(localStorage.getItem("ccs.steps") || "{}"); } catch { return {}; } })();
  const actions: { t: string; href: string; why: string }[] = [];
  // 예시(fixture) 공고는 실제 공고로 착각할 수 있어 '오늘의 3가지'에 올리지 않는다
  const hot = bids?.mode === "fixture" ? undefined : bids?.items.find((b) => b.score >= 60 && (b.dleft ?? 99) <= 14);
  if (hot) actions.push({ t: `입찰 제안서 착수: ${hot.name}`, href: "#/bids", why: `적합도 ${hot.score} · 마감 D-${hot.dleft}` });
  const next = pk?.items.slice().reverse().find((p) => (steps[p.dir] ?? 0) < 7);
  if (next) actions.push({ t: `패키지 다음 단계: ${next.title}`, href: "#/packages", why: `진행 ${(steps[next.dir] ?? 0)}/7 단계` });
  if (q?.top3[0]) actions.push({ t: `오늘의 Cue 판정: ${q.top3[0].t}`, href: "#/queue", why: `재가공 점수 ${q.top3[0].sc.total}` });
  const days = lastBlog ? Math.floor((Date.now() - Date.parse(lastBlog)) / 86400000) : 99;
  if (days >= 3) actions.push({ t: "블로그 1편 발행 (주 2~3편 원칙)", href: "#/blog", why: lastBlog ? `마지막 발행 ${days}일 전` : "발행 기록 없음" });
  return (
    <section>
      <h2>🎯 월천 관제탑 <span className="muted small">월 1,000만 원 · 목표 기한까지 {monthsLeft}개월</span></h2>
      <div className="kpis">
        <div className="kpi"><span>{month} 누적 수익</span><b>{won(total)}</b><small>목표의 {Math.round((total / goal) * 100)}%</small></div>
        <div className="kpi"><span>남은 금액</span><b>{won(Math.max(0, goal - total))}</b><small>이번 달</small></div>
      </div>
      <div className="part" style={{ margin: "10px 0" }}><span className="part-bar wide"><span style={{ width: `${Math.min(100, (total / goal) * 100)}%`, background: "var(--cue)" }} /></span></div>
      <h3>✅ 오늘의 3가지 (매출에 가까운 순)</h3>
      <ol>{actions.slice(0, 3).map((a) => <li key={a.t} style={{ margin: "8px 0" }}><a href={a.href}><b>{a.t}</b></a><div className="small muted">{a.why}</div></li>)}</ol>
      <h3>💵 이번 달 수입 입력 <span className="muted small">(이 기기에만 저장)</span></h3>
      <div className="panel calc-grid">{STREAMS.map((k) => <label key={k}>{k}<input type="number" value={cur[k] ?? ""} placeholder="0" onChange={(e) => save({ ...rev, [month]: { ...cur, [k]: Number(e.target.value) } })} /></label>)}
        <label>마지막 블로그 발행일<input type="date" value={lastBlog} onChange={(e) => { setLastBlog(e.target.value); try { localStorage.setItem("ccs.lastBlog", e.target.value); } catch { /* 무시 */ } }} /></label></div>
      <h3>📊 월별 추이</h3>
      <div className="table-wrap"><table><thead><tr><th>월</th><th>합계</th><th>목표 대비</th></tr></thead><tbody>
        {Object.keys(rev).sort().reverse().map((m) => { const t = Object.values(rev[m]).reduce((a, b) => a + (b || 0), 0); return <tr key={m}><td>{m}</td><td>{won(t)}</td><td>{Math.round((t / goal) * 100)}%</td></tr>; })}
      </tbody></table></div>
      <p className="small muted">💡 유튜브 실측 수익은 M4(내 채널 OAuth) 연결 후 자동 입력 예정. 지금은 직접 입력.</p>
    </section>
  );
}

// ------------------------------------------------------------------ 🐷 부자아이 공방
const CONCEPTS: [string, string][] = [["3-5", "돈은 물건과 바꾸는 약속"], ["3-5", "기다리면 더 좋은 것 (저축)"], ["3-5", "필요한 것과 갖고 싶은 것"], ["6-7", "용돈 나누기 (쓰기·모으기·나누기)"], ["6-7", "가격 비교하기"], ["8-10", "용돈 기입장"], ["8-10", "광고는 왜 사고 싶게 만들까"], ["11-13", "이자와 복리"], ["11-13", "회사의 주인이 된다는 것 (주식 기초)"]];
export function KidsPage() {
  const [concept, setConcept] = useState("기다리면 더 좋은 것 (저축)");
  const [age, setAge] = useState("3-5");
  const [pk] = useData<{ kids: { dir: string; title: string; age: string; concept: string }[] }>("packages.json");
  const body = ["<!-- radar-kids: 아래 JSON 블록은 수정하지 마세요 -->", "```json", JSON.stringify({ action: "kids", concept, age }), "```"].join("\n");
  const url = `https://github.com/${REPO}/issues/new?${new URLSearchParams({ title: `[부자아이] ${concept} (${age}세)`, body }).toString()}`;
  return (
    <section>
      <h2>🐷 부자아이 공방 <span className="muted small">금융 개념 1개 → 그림책·활동지·부모 가이드·쇼츠</span></h2>
      <div className="chips">{CONCEPTS.map(([a, c]) => <button key={c} type="button" className={`chip chip-btn ${concept === c ? "on" : ""}`} onClick={() => { setConcept(c); setAge(a); }}>{a}세 · {c}</button>)}</div>
      <div className="panel calc-grid">
        <label>금융 개념 (직접 입력 가능)<input value={concept} onChange={(e) => setConcept(e.target.value)} /></label>
        <label>연령<select value={age} onChange={(e) => setAge(e.target.value)}><option value="3-5">만 3~5세</option><option value="6-7">만 6~7세</option><option value="8-10">초등 저학년</option><option value="11-13">초등 고학년</option></select></label>
      </div>
      <a className="btn cue wide" href={url} target="_blank" rel="noreferrer">🐷 세트 만들기 요청</a>
      <p className="small muted">GitHub 화면에서 초록 Create → 1~2분 뒤 결과 링크. 그림책 12장면(삽화 지시 포함) · 인쇄용 활동지 HTML · 정답·부모 가이드 · 쇼츠 대본. 아이와 먼저 읽어보고 반응을 기록해 다음 버전에 반영하세요.</p>
      {pk?.kids && pk.kids.length > 0 && <><h3>📚 만든 세트</h3><ul>{pk.kids.map((k) => <li key={k.dir}><a href={`https://github.com/${REPO}/tree/main/${k.dir}`} target="_blank" rel="noreferrer">{k.title}</a> <span className="muted small">{k.age}세 · {k.concept}</span></li>)}</ul></>}
    </section>
  );
}
