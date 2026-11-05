import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AboutPage, CalcPage, ChannelPage, ChartPage, ComparePage, Home, HomeBoard, RankPage, SearchPage, SurgePage, TrendPage, BlogStudio } from "./pages";
import "./style.css";

function useHash() {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => {
    const f = () => { setH(location.hash || "#/"); window.scrollTo(0, 0); };
    addEventListener("hashchange", f);
    return () => removeEventListener("hashchange", f);
  }, []);
  return h;
}

const NAV: [string, string, string][] = [
  ["#/", "🏠", "홈"], ["#/queue", "🎯", "오늘의 생산 큐"], ["#/search", "🔍", "채널 검색"],
  ["#/chart", "🌐", "인기 차트"], ["#/surge", "🚀", "급상승 영상"], ["#/rank", "🏆", "채널 순위"],
  ["#/trend", "📈", "트렌드 (유튜브·구글)"], ["#/blog", "✍️", "블로그 스튜디오"], ["#/calc", "💰", "수익 계산기"], ["#/compare", "⚖️", "채널 비교"], ["#/about", "📐", "지표 정의"],
];

function App() {
  const h = useHash();
  const [path, qs] = h.slice(1).split("?");
  const params = new URLSearchParams(qs);
  let page;
  if (path.startsWith("/ch/")) page = <ChannelPage key={path} id={decodeURIComponent(path.slice(4))} />;
  else if (path === "/chart") page = <ChartPage />;
  else if (path === "/surge") page = <SurgePage />;
  else if (path === "/trend") page = <TrendPage />;
  else if (path === "/search") page = <SearchPage key="s" q={params.get("q") ?? ""} />;
  else if (path === "/rank") page = <RankPage />;
  else if (path === "/compare") page = <ComparePage ids={(params.get("ids") || "").split(",").filter(Boolean)} add={params.get("add") ?? undefined} />;
  else if (path === "/about") page = <AboutPage />;
  else if (path === "/calc") page = <CalcPage id={params.get("id") ?? ""} />;
  else if (path === "/queue") page = <Home />;
  else if (path === "/blog") page = <BlogStudio />;
  else page = <HomeBoard />;
  const active = "#" + (path.startsWith("/ch/") ? "/rank" : path || "/");
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [h]);
  return (
    <div className="shell">
      <aside className={`side ${open ? "open" : ""}`}>
        <a href="#/" className="brand">🎨 CCS<small className="brand-sub">Creative Craft Studio</small></a>
        <nav>{NAV.map(([href, ic, label]) => <a key={href} href={href} className={active === href ? "on" : ""}><span>{ic}</span>{label}</a>)}</nav>
        <div className="side-foot small muted">매일 06:17 자동 갱신</div>
      </aside>
      {open && <div className="scrim" onClick={() => setOpen(false)} />}
      <div className="body">
        <header className="top">
          <button type="button" className="burger" aria-label="메뉴" onClick={() => setOpen(!open)}>☰</button>
          <form className="hsearch" onSubmit={(e) => { e.preventDefault(); const v = (e.currentTarget.elements.namedItem("q") as HTMLInputElement).value; location.hash = `#/search?q=${encodeURIComponent(v)}`; }}>
            <input name="q" placeholder="🔍 채널 이름 · @핸들 · 유튜브 주소" aria-label="채널 검색" />
          </form>
        </header>
        <main>{page}</main>
      </div>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
