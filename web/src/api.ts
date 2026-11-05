// 집계 JSON 타입과 로더. 파이썬 radar/export.py 의 출력과 1:1.
export type Score = {
  total: number; max: number; excluded: boolean; reasons: string[];
  parts: { burst: number; money: number; fit: number | null; replicable: number; life: number; policy: number };
};
export type VCard = {
  id: string; t: string; c: string; ct: string | null; pub: string; dur: number; sh: number; cat: string | null;
  v: number | null; lk: number | null; cm: number | null; th: string | null; mx: number | null; med: number | null;
  v24: number | null; rk: number | null; lb: string[]; g: string | null; sc: Score; rc: [string, string];
  rpm: [number, number]; src: string | null;
  ai?: { angle?: string; reason?: string; buzz_24h?: number } | null;
};
export type ChartItem = VCard & { rank: number; delta: number | null };
export type Queue = { date: string; top3: VCard[]; pending: VCard[]; archived: VCard[]; decided: number; card_age: Record<string, string> };
export type Charts = { date: string; categories: Record<string, string>; charts: Record<string, { long: ChartItem[]; short: ChartItem[] }> };
export type VStats = { n: number; avg_views: number; like_rate: number | null; comment_rate: number | null };
export type RankRow = {
  id: string; t: string | null; h?: string | null; cat?: string | null; pop?: number; g: string | null; src: string; th: string | null; subs: number | null; sg: number | null;
  sgr: number | null; vg: number | null; v30: number; avg: number | null; up30: number; gr: string | null; gs: number | null;
  fl: string[]; rev: [number, number]; top: VCard | null; dh: number;
};
export type Grade = { score: number | null; letter: string | null; coverage: number; parts: Record<string, number | null> };
export type Forecast = { alpha: number; beta: number; level: number; trend_per_day: number; forecast: Record<string, number> } | null;
export type ChannelDetail = {
  id: string; t: string | null; handle: string | null; g: string | null; src: string; th: string | null; country: string | null;
  hist: [string, number | null, number | null, number | null][];
  f: { subs: number | null; growth: number | null; sub_gain: number | null; view_gain: number | null; efficiency: number | null;
       engagement: number | null; consistency: number | null; outlier_freq: number | null; avg_views: number | null;
       views30_uploads: number; uploads30: number; rev: [number, number]; flags: string[]; days_hist: number; ppl: [number, number] | null };
  ranks: { subs: number | null; pop: number | null; views30: number | null; cat: number | null; cat_n: number; n: number; cat_id: string | null };
  daily: { d: string; subs: number | null; ds: number | null; views: number | null; dv: number | null }[];
  video_stats: { mine: VStats | null; category: VStats | null };
  perf: { avg_views: number | null; group_median: number | null; category_median: number | null; group: string | null; category: string | null };
  similar: { id: string; t: string | null; th: string | null; subs: number | null; avg: number | null; gr: string | null }[];
  rev_year: [number, number];
  top_videos: VCard[];
  grade: Grade; fc_subs: Forecast; fc_views: Forecast; milestones: Record<string, string | null>;
  fmt: { n: number; short_ratio: number | null; avg_dur: number; title_len: number | null; title_num: number | null; title_q: number | null; heat: number[][] };
  videos: VCard[];
};
export type Summary = {
  date: string; generated_at: string; mode: string; repo: string;
  counts: Record<string, number>;
  quota: { budget: number; today: number; by_endpoint: { endpoint: string; job: string; units: number; calls: number }[]; history: { date: string; u: number }[] };
  formulas: Record<string, string>; rpm: Record<string, [number, number]>; categories: Record<string, string>; groups: string[];
  seed_excluded: { group: string; q: string; channel: string | null; reason: string }[];
};

const cache = new Map<string, Promise<unknown>>();
export function load<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(path, fetch(`./data/${path}`).then((r) => {
      if (!r.ok) throw new Error(`${path}: ${r.status}`);
      return r.json();
    }));
  }
  return cache.get(path) as Promise<T>;
}

export type Trend = { kw: string; n: number; prev: number | null; growth: number | null; examples: { id: string; t: string }[] };
export type Trends = { date: string; window: [string, string]; has_prev: boolean; rising: Trend[]; frequent: Trend[]; formula: string };
