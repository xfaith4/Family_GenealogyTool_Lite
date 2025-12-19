(() => {
  const registerSW = () => {
    if (!("serviceWorker" in navigator)) return;
    navigator.serviceWorker
      .register("/service-worker.js", { scope: "/" })
      .catch((err) => console.error("SW registration failed", err));
  };

  const setActiveNav = () => {
    const path = window.location.pathname;
    const hash = window.location.hash || "";
    document.querySelectorAll(".bottomNav a").forEach((a) => {
      const r = a.dataset.route;
      const isHome = ((path === "/" || path.startsWith("/tree-v2")) && r === "home" && !hash.startsWith("#import"));
      const isMedia = path.startsWith("/media") && r === "media";
      const isSettings = path.startsWith("/analytics") && r === "settings";
      const isImport = hash.startsWith("#import") && r === "import";
      if (isHome || isMedia || isSettings || isImport) {
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
