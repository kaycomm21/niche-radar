import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { AboutPage, ChannelPage, ChartPage, ComparePage, Home, RankPage, SurgePage, TrendPage } from "./pages";
import "./style.css";

function useHash() {
  const [h, setH] = useState(location.hash || "#/");
  useEffect(() => { const f = () => { setH(location.hash || "#/"); window.scrollTo(0, 0); }; addEventListener("hashchange", f); return () => removeEventListener("hashchange", f); }, []);
  return h;
}

const NAV: [string, string][] = [["#/", "🎯 오늘"], ["#/chart", "🌐 차트"], ["#/surge", "🚀 급상승"], ["#/trend", "📈 트렌드"], ["#/rank", "🏆 순위"], ["#/compare", "⚖️ 비교"], ["#/about", "📐 정의"]];

function App() {
  const h = useHash();
  const [path, qs] = h.slice(1).split("?");
  let page;
  if (path.startsWith("/ch/")) page = <ChannelPage key={path} id={decodeURIComponent(path.slice(4))} />;
  else if (path === "/chart") page = <ChartPage />;
  else if (path === "/surge") page = <SurgePage />;
  else if (path === "/trend") page = <TrendPage />;
  else if (path === "/rank") page = <RankPage />;
  else if (path === "/compare") page = <ComparePage ids={(new URLSearchParams(qs).get("ids") || "").split(",").filter(Boolean)} add={new URLSearchParams(qs).get("add") ?? undefined} />;
  else if (path === "/about") page = <AboutPage />;
  else page = <Home />;
  const active = "#" + (path.startsWith("/ch/") ? "/rank" : path || "/");
  return (
    <>
      <header className="top"><a href="#/" className="brand">📡 니치 레이더</a><span className="muted small">수집이 아니라 생산을 위한 레이더</span></header>
      <main>{page}</main>
      <nav className="tabs">{NAV.map(([href, label]) => <a key={href} href={href} className={active === href ? "on" : ""}>{label}</a>)}</nav>
    </>
  );
}

createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
