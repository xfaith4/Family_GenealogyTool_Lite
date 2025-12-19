(function () {
  const tabs = document.querySelectorAll(".tabs button");
  const contents = document.querySelectorAll(".tabContent");
  const btnScan = document.getElementById("btnScan");

  function setActive(tabName) {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
    contents.forEach((c) => c.classList.toggle("active", c.id === `tab-${tabName}`));
  }

  tabs.forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.dataset.tab));
  });

  async function fetchJson(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function asPercent(value) {
    return `${value ?? 0}%`;
  }

  async function loadSummary() {
    try {
      const data = await fetchJson("/api/dq/summary");
      document.getElementById("dqScore").textContent = data.data_quality_score ?? "--";

      const coverage = document.getElementById("dqCoverage");
      coverage.innerHTML = "";
      [
        ["Standardized dates", asPercent(data.standardized_dates_pct)],
        ["Unresolved duplicates", data.unresolved_duplicates],
        ["Place clusters", data.place_clusters],
        ["Integrity warnings", data.integrity_warnings],
      ].forEach(([label, value]) => {
        const li = document.createElement("li");
        li.innerHTML = `<div>${label}</div><div class="muted">${value}</div>`;
        coverage.appendChild(li);
      });

      const queues = document.getElementById("dqQueues");
      queues.innerHTML = "";
      [
        ["Duplicates", data.unresolved_duplicates],
        ["Places", data.place_clusters],
        ["Integrity", data.integrity_warnings],
      ].forEach(([label, value]) => {
        const li = document.createElement("li");
        li.innerHTML = `<div>${label}</div><div class="muted">${value} open</div>`;
        queues.appendChild(li);
      });
    } catch (err) {
      console.error("summary", err);
    }
  }

  async function loadIssues(targetId, type) {
    const container = document.getElementById(targetId);
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const data = await fetchJson(`/api/dq/issues?type=${encodeURIComponent(type)}&status=open`);
      if (!data.items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        return;
      }
      container.innerHTML = "";
      data.items.forEach((item) => {
        const li = document.createElement("div");
        li.className = "listItem";
        const explanation = item.explanation || {};
        li.innerHTML = `
          <div class="row">
            <div><strong>${item.issue_type}</strong> • confidence ${item.confidence ?? "?"}</div>
            <div class="muted small">${item.detected_at}</div>
          </div>
          <div class="muted small">${JSON.stringify(explanation)}</div>
        `;
        container.appendChild(li);
      });
    } catch (err) {
      container.innerHTML = `<div class='muted'>${err}</div>`;
    }
  }

  async function loadLog() {
    const container = document.getElementById("logList");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const data = await fetchJson("/api/dq/actions/log");
      container.innerHTML = "";
      data.items.forEach((item) => {
        const div = document.createElement("div");
        div.className = "listItem";
        div.innerHTML = `
          <div class="row"><strong>${item.action_type}</strong><span class="muted small">${item.created_at}</span></div>
          <div class="muted small">Payload: ${JSON.stringify(item.payload)}</div>
          <div class="muted small">Undo available: ${item.undo ? "Yes" : "No"}</div>
        `;
        container.appendChild(div);
      });
    } catch (err) {
      container.innerHTML = `<div class='muted'>${err}</div>`;
    }
  }

  async function runScan() {
    btnScan.disabled = true;
    btnScan.textContent = "Scanning…";
    try {
      await fetchJson("/api/dq/scan", { method: "POST" });
      await Promise.all([
        loadSummary(),
        loadIssues("dupList", "duplicate_person"),
        loadIssues("placeList", "place_cluster"),
        loadIssues("dateList", "date_normalization"),
        loadIssues("integrityList", "impossible_timeline"),
        loadLog(),
      ]);
    } catch (err) {
      console.error("scan failed", err);
    } finally {
      btnScan.disabled = false;
      btnScan.textContent = "Scan for issues";
    }
  }

  btnScan?.addEventListener("click", runScan);
  runScan();
})();
