(() => {
  const registerSW = () => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker
      .register("./service-worker.js", { scope: "./" })
      .catch((err) => console.error("SW registration failed", err));
  };

  const setActiveNav = () => {
    const path = window.location.pathname;
    const hash = window.location.hash || "";
    document.querySelectorAll(".bottomNav a").forEach((a) => {
      const r = a.dataset.route;
      const isHome = ((path === "/" || path.includes("index.html")) && r === "home");
      const isTree = path.includes("tree.html") && r === "tree";
      const isAnalytics = path.includes("analytics.html") && r === "analytics";
      if (isHome || isTree || isAnalytics) {
        a.classList.add("active");
      } else {
        a.classList.remove("active");
      }
    });
  };

  window.addEventListener("load", () => {
    registerSW();
    setActiveNav();
  });
  window.addEventListener("hashchange", setActiveNav);
  window.setActiveNav = setActiveNav;
})();
