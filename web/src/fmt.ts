export const n = (x: number | null | undefined): string => {
  if (x === null || x === undefined || Number.isNaN(x)) return "–";
  const a = Math.abs(x);
  if (a >= 1e8) return (x / 1e8).toFixed(1).replace(/\.0$/, "") + "억";
  if (a >= 1e4) return (x / 1e4).toFixed(a >= 1e5 ? 0 : 1).replace(/\.0$/, "") + "만";
  return Math.round(x).toLocaleString("ko-KR");
};
export const won = (x: number) => n(x) + "원";
export const pct = (x: number | null | undefined, d = 1) => (x === null || x === undefined ? "–" : (x * 100).toFixed(d) + "%");
export const dur = (s: number) => (s >= 3600 ? `${Math.floor(s / 3600)}:${String(Math.floor((s % 3600) / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}` : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`);
export const LABELS: Record<string, string> = { fire: "🔥 조회수 터짐", money: "💰 수익화 터짐", issue: "📣 이슈화" };
export const RECIPES: Record<string, string> = { R1: "포맷 이식", R2: "주제 이식", R3: "각도 반전", R4: "시리즈화", R5: "롱폼↔쇼츠", R6: "해외→한국" };
