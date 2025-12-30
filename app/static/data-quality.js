(function () {
  const tabs = document.querySelectorAll(".tabs button");
  const contents = document.querySelectorAll(".tabContent");
  const btnScan = document.getElementById("btnScan");
  const lastScanEl = document.getElementById("dqLastScan");
  const scanHintEl = document.getElementById("dqScanHint");
  const chipContainer = document.getElementById("dqChips");
  const highlightsContainer = document.getElementById("dqHighlights");
  let lastScanAt = null;

  function setActive(tabName) {
    tabs.forEach((t) => t.classList.toggle("active", t.dataset.tab === tabName));
    contents.forEach((c) => c.classList.toggle("active", c.id === `tab-${tabName}`));
  }

  tabs.forEach((btn) => {
    btn.addEventListener("click", () => setActive(btn.dataset.tab));
  });

  function formatRelative(date) {
    if (!date) return "--";
    const diff = Date.now() - date.getTime();
    const mins = Math.round(diff / 60000);
    if (mins < 1) return "just now";
    if (mins === 1) return "1 minute ago";
    if (mins < 60) return `${mins} minutes ago`;
    const hours = Math.round(mins / 60);
    if (hours === 1) return "1 hour ago";
    if (hours < 24) return `${hours} hours ago`;
    const days = Math.round(hours / 24);
    return `${days} day${days === 1 ? "" : "s"} ago`;
  }

  function updateLastScan() {
    if (lastScanEl) {
      lastScanEl.textContent = `Last scan: ${formatRelative(lastScanAt)}`;
    }
  }

  async function fetchJson(url, opts) {
    const res = await fetch(url, opts);
    if (!res.ok) throw new Error(await res.text());
    return res.json();
  }

  function errMsg(err) {
    if (!err) return "Unknown error";
    if (typeof err === "string") return err;
    return err.message || "Request failed";
  }

  function renderChips(summary) {
    if (!chipContainer) return;
    chipContainer.innerHTML = "";
    const chips = [
      { label: "Duplicates", icon: "👥", value: `${summary.unresolved_duplicates ?? 0} open`, target: "duplicates" },
      { label: "Places", icon: "📍", value: `${summary.place_clusters ?? 0} clusters`, target: "places" },
      { label: "Dates", icon: "📅", value: `${summary.standardized_dates_pct ?? 0}% standardized`, target: "dates" },
      { label: "Standards", icon: "✨", value: `${summary.standardization_suggestions ?? 0} suggestions`, target: "standards" },
      { label: "Integrity", icon: "⚠️", value: `${summary.integrity_warnings ?? 0} warnings`, target: "integrity" },
    ];
    chips.forEach((chip) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "dqChip";
      btn.innerHTML = `
        <span class="icon">${chip.icon}</span>
        <div>
          <div class="label">${chip.label}</div>
          <div class="value">${chip.value}</div>
        </div>
      `;
      btn.addEventListener("click", () => setActive(chip.target));
      chipContainer.appendChild(btn);
    });
  }

  function renderHighlights(summary) {
    if (!highlightsContainer) return;
    highlightsContainer.innerHTML = "";
    const items = [];
    if ((summary.unresolved_duplicates ?? 0) > 0) {
      items.push({ icon: "👥", label: "Duplicates", text: `${summary.unresolved_duplicates} possible matches ready to merge`, target: "duplicates" });
    }
    if ((summary.place_clusters ?? 0) > 0) {
      items.push({ icon: "📍", label: "Places", text: `${summary.place_clusters} variant set(s) to standardize`, target: "places" });
    }
    if ((summary.integrity_warnings ?? 0) > 0) {
      items.push({ icon: "⚠️", label: "Integrity", text: `${summary.integrity_warnings} timeline/relationship warnings`, target: "integrity" });
    }
    if ((summary.standardized_dates_pct ?? 0) < 90) {
      items.push({ icon: "📅", label: "Dates", text: `${summary.standardized_dates_pct}% standardized — apply clean dates to lift the score`, target: "dates" });
    }
    if ((summary.standardization_suggestions ?? 0) > 0) {
      items.push({ icon: "✨", label: "Standards", text: `${summary.standardization_suggestions} formatting suggestion(s) ready to apply`, target: "standards" });
    }
    if (!items.length) {
      const li = document.createElement("li");
      li.className = "muted small";
      li.textContent = "No open issues detected. Run a scan after imports to keep things clean.";
      highlightsContainer.appendChild(li);
      return;
    }
    items.forEach((item) => {
      const li = document.createElement("li");
      li.className = "dqHighlightItem";
      li.innerHTML = `
        <div class="label">${item.icon || "✨"} ${escapeHtml(item.label)}</div>
        <div class="muted small">${escapeHtml(item.text)}</div>
      `;
      if (item.target) {
        li.style.cursor = "pointer";
        li.addEventListener("click", () => setActive(item.target));
      }
      highlightsContainer.appendChild(li);
    });
  }

  function updateScanHint(summary) {
    if (!scanHintEl) return;
    scanHintEl.textContent = `Score blends duplicates (${summary.unresolved_duplicates ?? 0}), places (${summary.place_clusters ?? 0}), dates (${summary.standardized_dates_pct ?? 0}% clean), and integrity (${summary.integrity_warnings ?? 0}). Standards suggestions: ${summary.standardization_suggestions ?? 0}.`;
  }

  function integrityDescription(issue) {
    const ex = issue.explanation || {};
    switch (issue.issue_type) {
      case "impossible_timeline":
        return `Birth ${ex.birth_year ?? "?"}, death ${ex.death_year ?? "?"} (death precedes birth).`;
      case "orphan_event":
      case "orphan_family":
        return ex.reason || "Missing linked person/family.";
      case "parent_child_age": {
        const gap = ex.parent_birth_year !== undefined && ex.child_birth_year !== undefined
          ? ex.child_birth_year - ex.parent_birth_year
          : null;
        return `Parent birth ${ex.parent_birth_year ?? "?"}, child birth ${ex.child_birth_year ?? "?"}${gap !== null ? ` (gap ${gap}y)` : ""}.`;
      }
      case "parent_child_death":
        return `Parent died ${ex.parent_death_year ?? "?"} before child birth ${ex.child_birth_year ?? "?"}.`;
      case "marriage_too_early":
        return `Marriage ${ex.marriage_year ?? "?"} happens within 12y of spouse birth ${ex.spouse_birth_year ?? "?"}.`;
      case "marriage_after_death":
        return `Marriage ${ex.marriage_year ?? "?"} occurs after spouse death ${ex.spouse_death_year ?? "?"}.`;
      case "placeholder_name":
        return `Placeholder name detected: ${(ex.given || "").trim()} ${(ex.surname || "").trim()}`.trim() || "Unnamed placeholder record.";
      default:
        return JSON.stringify(ex);
    }
  }

  function escapeHtml(s) {
    return (s ?? "").toString()
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function asPercent(value) {
    return `${value ?? 0}%`;
  }

  function asConfidence(value) {
    if (value === null || value === undefined) return "?";
    return `${Math.round(value * 100)}%`;
  }

  function confidenceLabel(value) {
    if (value === null || value === undefined) return "Unknown";
    if (value >= 0.9) return "High";
    if (value >= 0.75) return "Medium";
    return "Low";
  }

  function confidenceClass(value) {
    if (value === null || value === undefined) return "";
    if (value >= 0.9) return "dqBadgeHigh";
    if (value >= 0.75) return "dqBadgeMed";
    return "dqBadgeLow";
  }

  function fullName(person) {
    const name = `${person?.given || ""} ${person?.surname || ""}`.trim();
    return name || "(unnamed)";
  }

  function formatNameList(items) {
    if (!items || !items.length) return "None";
    return items.map((p) => escapeHtml(fullName(p))).join(", ");
  }

  async function loadSummary() {
    try {
      const data = await fetchJson("/api/dq/summary");
      document.getElementById("dqScore").textContent = data.data_quality_score ?? "--";

      const coverage = document.getElementById("dqCoverage");
      coverage.innerHTML = "";
      [
        ["Standardized dates", asPercent(data.standardized_dates_pct)],
        ["Standards suggestions", data.standardization_suggestions],
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
        ["Standards", data.standardization_suggestions],
        ["Integrity", data.integrity_warnings],
      ].forEach(([label, value]) => {
        const li = document.createElement("li");
        li.innerHTML = `<div>${label}</div><div class="muted">${value} open</div>`;
        queues.appendChild(li);
      });
      renderChips(data);
      renderHighlights(data);
      updateScanHint(data);
      updateLastScan();
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
            <div><strong>${item.issue_type}</strong> • confidence ${asConfidence(item.confidence)}</div>
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

  async function loadDuplicates() {
    const container = document.getElementById("dupList");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const [peopleIssues, familyIssues, familySwapIssues, mediaIssues, mediaAssetIssues] = await Promise.all([
        fetchJson("/api/dq/issues?type=duplicate_person&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=duplicate_family&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=duplicate_family_spouse_swap&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=duplicate_media_link&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=duplicate_media_asset&status=open&perPage=200"),
      ]);
      const peopleItems = peopleIssues.items || [];
      const familyItems = [...(familyIssues.items || []), ...(familySwapIssues.items || [])];
      const mediaItems = mediaIssues.items || [];
      const mediaAssetItems = mediaAssetIssues.items || [];

      if (!peopleItems.length && !familyItems.length && !mediaItems.length && !mediaAssetItems.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        return;
      }
      container.innerHTML = "";

      const addSection = (title) => {
        const h = document.createElement("div");
        h.className = "dqSectionTitle";
        h.textContent = title;
        container.appendChild(h);
      };

      if (peopleItems.length) {
        addSection("People");
        const personIds = Array.from(new Set(peopleItems.flatMap((i) => i.entity_ids || [])));
        const peopleMap = new Map();
        if (personIds.length) {
          const peopleResp = await fetchJson("/api/people/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: personIds }),
          });
          (peopleResp.items || []).forEach((p) => peopleMap.set(p.id, p));
        }
        peopleItems.forEach((item) => {
          const ids = item.entity_ids || [];
          if (ids.length < 2) return;
          const left = peopleMap.get(ids[0]);
          const right = peopleMap.get(ids[1]);
          const explanation = item.explanation || {};
          const reasonParts = [];
          if (explanation.name_similarity !== undefined && explanation.name_similarity !== null) {
            reasonParts.push(`Name match ${Math.round((explanation.name_similarity || 0) * 100)}%`);
          }
          if (explanation.birth_delta !== undefined && explanation.birth_delta !== null) {
            reasonParts.push(`Birth Δ ${explanation.birth_delta}`);
          }
          if (explanation.death_delta !== undefined && explanation.death_delta !== null) {
            reasonParts.push(`Death Δ ${explanation.death_delta}`);
          }
          if (explanation.birth_place_match) {
            reasonParts.push("Birth place match");
          }
          const reasonText = reasonParts.join(" • ") || "Likely duplicate based on names and dates";
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>${escapeHtml(fullName(left))}</strong> + <strong>${escapeHtml(fullName(right))}</strong></div>
              <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
            </div>
            <div class="muted small">Why flagged: ${escapeHtml(reasonText)}</div>
            <div class="row" style="margin-top:8px;">
              <button class="btn btnSecondary" data-action="review">Review merge</button>
              <div class="muted small">${item.detected_at}</div>
            </div>
            <div class="dqDetail" style="display:none;"></div>
          `;
          const btn = div.querySelector('[data-action="review"]');
          const detail = div.querySelector(".dqDetail");
          btn.addEventListener("click", async () => {
            if (detail.dataset.loaded !== "true") {
              detail.innerHTML = "<div class='muted'>Loading details…</div>";
              let leftDetail = null;
              let rightDetail = null;
              try {
                [leftDetail, rightDetail] = await Promise.all([
                  fetchJson(`/api/people/${ids[0]}`),
                  fetchJson(`/api/people/${ids[1]}`),
                ]);
              } catch (err) {
                detail.innerHTML = "<div class='muted'>Failed to load details.</div>";
                detail.dataset.loaded = "true";
                detail.style.display = "block";
                return;
              }
              const radioName = `merge_person_${item.id}`;
              detail.innerHTML = `
                <div class="dqCompare">
                  <div class="dqCard">
                    <label><input type="radio" name="${radioName}" value="${leftDetail.id}" checked /> Keep ${escapeHtml(fullName(leftDetail))}</label>
                    <div class="dqField"><span>Birth</span><span>${escapeHtml(leftDetail.birth_date || "")} ${escapeHtml(leftDetail.birth_place || "")}</span></div>
                    <div class="dqField"><span>Death</span><span>${escapeHtml(leftDetail.death_date || "")} ${escapeHtml(leftDetail.death_place || "")}</span></div>
                    <div class="dqList"><strong>Parents:</strong> ${formatNameList(leftDetail.parents)}</div>
                    <div class="dqList"><strong>Children:</strong> ${formatNameList(leftDetail.children)}</div>
                    <div class="dqList"><strong>Media:</strong> ${leftDetail.media?.length || 0}</div>
                  </div>
                  <div class="dqCard">
                    <label><input type="radio" name="${radioName}" value="${rightDetail.id}" /> Keep ${escapeHtml(fullName(rightDetail))}</label>
                    <div class="dqField"><span>Birth</span><span>${escapeHtml(rightDetail.birth_date || "")} ${escapeHtml(rightDetail.birth_place || "")}</span></div>
                    <div class="dqField"><span>Death</span><span>${escapeHtml(rightDetail.death_date || "")} ${escapeHtml(rightDetail.death_place || "")}</span></div>
                    <div class="dqList"><strong>Parents:</strong> ${formatNameList(rightDetail.parents)}</div>
                    <div class="dqList"><strong>Children:</strong> ${formatNameList(rightDetail.children)}</div>
                    <div class="dqList"><strong>Media:</strong> ${rightDetail.media?.length || 0}</div>
                  </div>
                </div>
                <div class="dqActions">
                  <label><input type="checkbox" class="dqFillMissing" checked /> Fill missing fields</label>
                  <button class="btn">Merge selected</button>
                </div>
              `;
              const mergeBtn = detail.querySelector("button");
              const fillMissing = detail.querySelector(".dqFillMissing");
              mergeBtn.addEventListener("click", async () => {
                const selected = detail.querySelector(`input[name="${radioName}"]:checked`);
                if (!selected) return;
                const intoId = parseInt(selected.value, 10);
                const fromId = intoId === leftDetail.id ? rightDetail.id : leftDetail.id;
                if (!confirm(`Merge ${fullName(fromId === leftDetail.id ? leftDetail : rightDetail)} into ${fullName(intoId === leftDetail.id ? leftDetail : rightDetail)}?`)) return;
                mergeBtn.disabled = true;
                mergeBtn.textContent = "Merging…";
                try {
                  await fetchJson("/api/dq/actions/mergePeople", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ fromId, intoId, fillMissing: fillMissing.checked, user: "data-quality" }),
                  });
                  await runScan();
                } catch (err) {
                  console.error("merge failed", err);
                  alert("Merge failed.");
                } finally {
                  mergeBtn.disabled = false;
                  mergeBtn.textContent = "Merge selected";
                }
              });
              detail.dataset.loaded = "true";
            }
            detail.style.display = detail.style.display === "none" ? "block" : "none";
          });
          container.appendChild(div);
        });
        const hint = document.createElement("div");
        hint.className = "muted small";
        hint.textContent = "Tip: pick the record to keep, then merge. Missing fields can be filled automatically.";
        container.appendChild(hint);
      }

      if (familyItems.length) {
        addSection("Families");
        familyItems.forEach((item) => {
          const ids = item.entity_ids || [];
          if (ids.length < 2) return;
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>Possible duplicate family</strong></div>
              <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
            </div>
            <div class="row" style="margin-top:8px;">
              <button class="btn btnSecondary" data-action="review">Review merge</button>
              <div class="muted small">${item.detected_at}</div>
            </div>
            <div class="dqDetail" style="display:none;"></div>
          `;
          const btn = div.querySelector('[data-action="review"]');
          const detail = div.querySelector(".dqDetail");
          btn.addEventListener("click", async () => {
            if (detail.dataset.loaded !== "true") {
              detail.innerHTML = "<div class='muted'>Loading details…</div>";
              let leftDetail = null;
              let rightDetail = null;
              try {
                [leftDetail, rightDetail] = await Promise.all([
                  fetchJson(`/api/families/${ids[0]}`),
                  fetchJson(`/api/families/${ids[1]}`),
                ]);
              } catch (err) {
                detail.innerHTML = "<div class='muted'>Failed to load family details.</div>";
                detail.dataset.loaded = "true";
                detail.style.display = "block";
                return;
              }
              const radioName = `merge_family_${item.id}`;
              const explanation = item.explanation || {};
              const spouseNames = explanation.spouse_names || [];
              const reasoningParts = [];
              if (spouseNames.length) reasoningParts.push(`Spouse names: ${spouseNames.join(" + ")}`);
              if (explanation.marriage_dates?.length) reasoningParts.push(`Marriage dates: ${explanation.marriage_dates.filter(Boolean).join(" / ")}`);
              if (explanation.marriage_places?.length) reasoningParts.push(`Marriage places: ${explanation.marriage_places.filter(Boolean).join(" / ")}`);
              const leftLabel = `${fullName(leftDetail.husband)} + ${fullName(leftDetail.wife)}`.trim() || "Family";
              const rightLabel = `${fullName(rightDetail.husband)} + ${fullName(rightDetail.wife)}`.trim() || "Family";
              detail.innerHTML = `
                <div class="dqCompare">
                  <div class="dqCard">
                    <label><input type="radio" name="${radioName}" value="${leftDetail.id}" checked /> Keep ${escapeHtml(leftLabel)}</label>
                    <div class="dqField"><span>Marriage</span><span>${escapeHtml(leftDetail.marriage_date || "")} ${escapeHtml(leftDetail.marriage_place || "")}</span></div>
                    <div class="dqList"><strong>Children:</strong> ${formatNameList(leftDetail.children)}</div>
                    <div class="dqList"><strong>Media:</strong> ${leftDetail.media?.length || 0}</div>
                  </div>
                  <div class="dqCard">
                    <label><input type="radio" name="${radioName}" value="${rightDetail.id}" /> Keep ${escapeHtml(rightLabel)}</label>
                    <div class="dqField"><span>Marriage</span><span>${escapeHtml(rightDetail.marriage_date || "")} ${escapeHtml(rightDetail.marriage_place || "")}</span></div>
                    <div class="dqList"><strong>Children:</strong> ${formatNameList(rightDetail.children)}</div>
                    <div class="dqList"><strong>Media:</strong> ${rightDetail.media?.length || 0}</div>
                  </div>
                </div>
                ${reasoningParts.length ? `<div class="dqList"><strong>Why flagged:</strong> ${escapeHtml(reasoningParts.join(" • "))}</div>` : ""}
                <div class="dqActions">
                  <label><input type="checkbox" class="dqFillMissing" checked /> Fill missing fields</label>
                  <button class="btn">Merge selected</button>
                </div>
              `;
              const mergeBtn = detail.querySelector("button");
              const fillMissing = detail.querySelector(".dqFillMissing");
              mergeBtn.addEventListener("click", async () => {
                const selected = detail.querySelector(`input[name="${radioName}"]:checked`);
                if (!selected) return;
                const intoId = parseInt(selected.value, 10);
                const fromId = intoId === leftDetail.id ? rightDetail.id : leftDetail.id;
                if (!confirm("Merge these families and combine children/media?")) return;
                mergeBtn.disabled = true;
                mergeBtn.textContent = "Merging…";
                try {
                  await fetchJson("/api/dq/actions/mergeFamilies", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ fromId, intoId, fillMissing: fillMissing.checked, user: "data-quality" }),
                  });
                  await runScan();
                } catch (err) {
                  console.error("merge family failed", err);
                  alert("Family merge failed.");
                } finally {
                  mergeBtn.disabled = false;
                  mergeBtn.textContent = "Merge selected";
                }
              });
              detail.dataset.loaded = "true";
            }
            detail.style.display = detail.style.display === "none" ? "block" : "none";
          });
          container.appendChild(div);
        });
        const hint = document.createElement("div");
        hint.className = "muted small";
        hint.textContent = "Family merges combine children and media links into the selected family.";
        container.appendChild(hint);
      }

      if (mediaItems.length) {
        addSection("Media Links");
        const assetIds = Array.from(new Set(mediaItems.map((i) => i.explanation?.asset_id).filter(Boolean)));
        const peopleIds = Array.from(new Set(mediaItems.map((i) => i.explanation?.person_id).filter(Boolean)));
        const assetMap = new Map();
        const peopleMap = new Map();
        if (assetIds.length) {
          const assetsResp = await fetchJson("/api/media/assets/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: assetIds }),
          });
          (assetsResp.items || []).forEach((a) => assetMap.set(a.id, a));
        }
        if (peopleIds.length) {
          const peopleResp = await fetchJson("/api/people/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: peopleIds }),
          });
          (peopleResp.items || []).forEach((p) => peopleMap.set(p.id, p));
        }
        mediaItems.forEach((item) => {
          const explanation = item.explanation || {};
          const asset = assetMap.get(explanation.asset_id) || {};
          const person = peopleMap.get(explanation.person_id);
          const linkIds = explanation.link_ids || [];
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>${escapeHtml(asset.original_filename || "Media asset")}</strong></div>
              <div class="muted small">${linkIds.length || 0} duplicate link(s)</div>
            </div>
            <div class="muted small">Linked to: ${person ? escapeHtml(fullName(person)) : (explanation.family_id ? "Family" : "Unknown")}</div>
            <div class="row" style="margin-top:8px;">
              <button class="btn btnSecondary" data-action="dedupe" ${linkIds.length < 2 ? "disabled" : ""}>Remove duplicate links</button>
              <div class="muted small">${item.detected_at}</div>
            </div>
          `;
          const btn = div.querySelector('[data-action="dedupe"]');
          btn.addEventListener("click", async () => {
            if (linkIds.length < 2) return;
            if (!confirm(`Remove ${linkIds.length - 1} duplicate link(s)?`)) return;
            btn.disabled = true;
            btn.textContent = "Cleaning…";
            try {
              await fetchJson("/api/dq/actions/dedupeMediaLinks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ link_ids: linkIds, keep_id: linkIds[0], user: "data-quality" }),
              });
              await runScan();
            } catch (err) {
              console.error("dedupe media failed", err);
              alert("Failed to remove duplicate links.");
            } finally {
              btn.disabled = false;
              btn.textContent = "Remove duplicate links";
            }
          });
          container.appendChild(div);
        });
        const bulkBtn = document.createElement("button");
        bulkBtn.className = "btn btnSecondary";
        bulkBtn.textContent = "Clean all duplicate links";
        bulkBtn.style.marginTop = "8px";
        bulkBtn.disabled = mediaItems.every((item) => (item.explanation?.link_ids || []).length < 2);
        bulkBtn.addEventListener("click", async () => {
          if (!confirm("Clean all duplicate media links?")) return;
          bulkBtn.disabled = true;
          const prev = bulkBtn.textContent;
          bulkBtn.textContent = "Cleaning…";
          try {
            for (const item of mediaItems) {
              const linkIds = item.explanation?.link_ids || [];
              if (linkIds.length < 2) continue;
              await fetchJson("/api/dq/actions/dedupeMediaLinks", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ link_ids: linkIds, keep_id: linkIds[0], user: "data-quality" }),
              });
            }
            await runScan();
          } catch (err) {
            console.error("bulk dedupe failed", err);
            alert("Bulk cleanup failed.");
          } finally {
            bulkBtn.disabled = false;
            bulkBtn.textContent = prev;
          }
        });
        container.appendChild(bulkBtn);
        const hint = document.createElement("div");
        hint.className = "muted small";
        hint.textContent = "Removes extra links while keeping one link intact.";
        container.appendChild(hint);
      }

      if (mediaAssetItems.length) {
        addSection("Media Assets");
        const assetIds = Array.from(new Set(mediaAssetItems.flatMap((i) => i.entity_ids || [])));
        const assetMap = new Map();
        if (assetIds.length) {
          const assetsResp = await fetchJson("/api/media/assets/bulk", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ ids: assetIds }),
          });
          (assetsResp.items || []).forEach((a) => assetMap.set(a.id, a));
        }
        mediaAssetItems.forEach((item) => {
          const ids = item.entity_ids || [];
          if (ids.length < 2) return;
          const left = assetMap.get(ids[0]) || {};
          const right = assetMap.get(ids[1]) || {};
          const leftThumb = left.thumbnail_path ? `/api/media/thumbnail/${encodeURIComponent(left.thumbnail_path)}` : null;
          const rightThumb = right.thumbnail_path ? `/api/media/thumbnail/${encodeURIComponent(right.thumbnail_path)}` : null;
          const leftLink = left.path ? `/api/media/${encodeURIComponent(left.path)}` : null;
          const rightLink = right.path ? `/api/media/${encodeURIComponent(right.path)}` : null;
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>${escapeHtml(left.original_filename || "Media asset")}</strong> + <strong>${escapeHtml(right.original_filename || "Media asset")}</strong></div>
              <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
            </div>
            <div class="row" style="margin-top:8px;">
              <button class="btn btnSecondary" data-action="review">Review merge</button>
              <div class="muted small">${item.detected_at}</div>
            </div>
            <div class="dqDetail" style="display:none;"></div>
          `;
          const btn = div.querySelector('[data-action="review"]');
          const detail = div.querySelector(".dqDetail");
          btn.addEventListener("click", async () => {
            if (detail.dataset.loaded !== "true") {
              const radioName = `merge_media_${item.id}`;
              detail.innerHTML = `
                <div class="dqCompare">
                  <div class="dqCard">
                    <label><input type="radio" name="${radioName}" value="${left.id || ""}" checked /> Keep ${escapeHtml(left.original_filename || "Media asset")}</label>
                    ${leftThumb ? `<div style="margin-top:8px;"><img src="${leftThumb}" alt="${escapeHtml(left.original_filename || "Media preview")}" style="max-width:100%;border-radius:8px;border:1px solid var(--line);" /></div>` : `<div style="margin-top:8px;display:flex;align-items:center;justify-content:center;height:80px;border-radius:8px;border:1px solid var(--line);background:rgba(0,0,0,0.12);color:var(--muted);font-size:12px;">FILE</div>`}
                    ${leftLink ? `<div style="margin-top:8px;"><a class="btn btnSecondary" href="${leftLink}" target="_blank" rel="noreferrer">Open file</a></div>` : ""}
                    <div class="dqField"><span>Size</span><span>${left.size_bytes ? `${left.size_bytes} bytes` : "Unknown"}</span></div>
                    <div class="dqField"><span>Links</span><span>${left.link_count ?? 0}</span></div>
                    <div class="dqField"><span>Created</span><span>${escapeHtml(left.created_at || "")}</span></div>
                  </div>
                  <div class="dqCard">
                    <label><input type="radio" name="${radioName}" value="${right.id || ""}" /> Keep ${escapeHtml(right.original_filename || "Media asset")}</label>
                    ${rightThumb ? `<div style="margin-top:8px;"><img src="${rightThumb}" alt="${escapeHtml(right.original_filename || "Media preview")}" style="max-width:100%;border-radius:8px;border:1px solid var(--line);" /></div>` : `<div style="margin-top:8px;display:flex;align-items:center;justify-content:center;height:80px;border-radius:8px;border:1px solid var(--line);background:rgba(0,0,0,0.12);color:var(--muted);font-size:12px;">FILE</div>`}
                    ${rightLink ? `<div style="margin-top:8px;"><a class="btn btnSecondary" href="${rightLink}" target="_blank" rel="noreferrer">Open file</a></div>` : ""}
                    <div class="dqField"><span>Size</span><span>${right.size_bytes ? `${right.size_bytes} bytes` : "Unknown"}</span></div>
                    <div class="dqField"><span>Links</span><span>${right.link_count ?? 0}</span></div>
                    <div class="dqField"><span>Created</span><span>${escapeHtml(right.created_at || "")}</span></div>
                  </div>
                </div>
                <div class="dqActions">
                  <button class="btn">Merge selected</button>
                </div>
              `;
              const mergeBtn = detail.querySelector("button");
              mergeBtn.addEventListener("click", async () => {
                const selected = detail.querySelector(`input[name="${radioName}"]:checked`);
                if (!selected) return;
                const intoId = parseInt(selected.value, 10);
                const fromId = intoId === (left.id || 0) ? right.id : left.id;
                if (!fromId || !intoId) return;
                if (!confirm("Merge media assets and move links into the selected asset?")) return;
                mergeBtn.disabled = true;
                mergeBtn.textContent = "Merging…";
                try {
                  await fetchJson("/api/dq/actions/mergeMediaAssets", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ fromId, intoId, user: "data-quality" }),
                  });
                  await runScan();
                } catch (err) {
                  console.error("merge media assets failed", err);
                  alert("Media merge failed.");
                } finally {
                  mergeBtn.disabled = false;
                  mergeBtn.textContent = "Merge selected";
                }
              });
              detail.dataset.loaded = "true";
            }
            detail.style.display = detail.style.display === "none" ? "block" : "none";
          });
          container.appendChild(div);
        });
        const hint = document.createElement("div");
        hint.className = "muted small";
        hint.textContent = "Merge duplicate media files to keep one asset and preserve links.";
        container.appendChild(hint);
      }
    } catch (err) {
      container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
    }
  }


async function loadPlaces() {
  const container = document.getElementById("placeList");
  const btnApplyPlaces = document.getElementById("btnApplyPlaces");
  const btnSavePlacesPlan = document.getElementById("btnSavePlacesPlan");
  const btnExportPlacesPlan = document.getElementById("btnExportPlacesPlan");
  const btnImportPlacesPlan = document.getElementById("btnImportPlacesPlan");
  const fileImportPlacesPlan = document.getElementById("fileImportPlacesPlan");
  const placeBulkStatus = document.getElementById("placeBulkStatus");

  const downloadJson = (filename, obj) => {
    const blob = new Blob([JSON.stringify(obj, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  };

  container.innerHTML = "<div class='muted'>Loading…</div>";
  if (placeBulkStatus) placeBulkStatus.textContent = "";

  try {
    const [clusters, similarities, rulesResp] = await Promise.all([
      fetchJson("/api/dq/issues?type=place_cluster&status=open&perPage=200"),
      fetchJson("/api/dq/issues?type=place_similarity&status=open&perPage=200"),
      fetchJson("/api/places/normalization/rules"),
    ]);

    const rulesMap = new Map();
    (rulesResp.items || []).forEach((r) => rulesMap.set(r.canonical, r));

    const items = [...(clusters.items || []), ...(similarities.items || [])];
    if (!items.length) {
      container.innerHTML = "<div class='muted'>No open items.</div>";
      if (btnApplyPlaces) btnApplyPlaces.disabled = true;
      if (btnSavePlacesPlan) btnSavePlacesPlan.disabled = true;
      if (btnExportPlacesPlan) btnExportPlacesPlan.disabled = true;
      if (placeBulkStatus) placeBulkStatus.textContent = "";
      return;
    }

    // Track current approval state (canonical -> rule payload)
    const approvalState = new Map();

    container.innerHTML = "";
    items.forEach((item) => {
      const expl = item.explanation || {};
      const canonical = (expl.canonical_suggestion || "").trim();
      const variants = (expl.variants || []).slice().sort((a, b) => (b.count || 0) - (a.count || 0));
      const variantValues = variants.map((v) => v.value).filter((v) => v && v !== canonical);

      // Default approval: existing rule wins; otherwise only auto-approve place_cluster (not place_similarity)
      const existingRule = rulesMap.get(canonical);
      const defaultApproved = existingRule ? !!existingRule.approved : item.issue_type === "place_cluster";

      approvalState.set(canonical, {
        canonical,
        variants: [canonical, ...variantValues],
        approved: defaultApproved,
        source_issue_id: item.id,
      });

      const div = document.createElement("div");
      div.className = "listItem";

      const badge = badgeForConfidence(item.confidence);
      const simNote = expl.similarity ? `<span class="muted small">Similarity: ${(expl.similarity * 100).toFixed(0)}%</span>` : "";
      const countsNote = `<span class="muted small">Refs: ${Math.round(item.impact_score || 0)}</span>`;

      const variantsHtml = variants
        .map((v) => {
          const isCanon = v.value === canonical;
          const pill = isCanon ? "<span class='pill'>canonical</span>" : "";
          return `<div class="row small"><span>${escapeHtml(v.value)}</span><span class="muted">${v.count || 0}×</span>${pill}</div>`;
        })
        .join("");

      div.innerHTML = `
        <div class="row">
          <div class="row" style="gap:10px;">
            <label class="row small" style="gap:8px;">
              <input type="checkbox" class="placeApprove"/>
              <span class="muted">Approved</span>
            </label>
            <strong>${escapeHtml(canonical || "(missing canonical)")}</strong>
          </div>
          <div class="row" style="gap:8px;">
            <span class="dqBadge ${badge.cls}">${badge.label}</span>
            ${countsNote}
            ${simNote}
          </div>
        </div>
        <div class="muted small">${escapeHtml(item.issue_type)}</div>
        <div class="variantsBox">${variantsHtml}</div>
        <div class="dqActions">
          <button class="btn btnSecondary btnApplyOne">Apply now</button>
        </div>
      `;

      const approveCb = div.querySelector(".placeApprove");
      approveCb.checked = defaultApproved;
      approveCb.addEventListener("change", () => {
        const st = approvalState.get(canonical);
        if (st) st.approved = approveCb.checked;
      });

      const btnApplyOne = div.querySelector(".btnApplyOne");
      btnApplyOne.disabled = !canonical || variantValues.length === 0;
      btnApplyOne.addEventListener("click", async () => {
        if (!canonical) return;
        if (!variantValues.length) {
          alert("No variants to standardize.");
          return;
        }
        if (!confirm(`Standardize ${variantValues.length} variant(s) to "${canonical}"?`)) return;

        btnApplyOne.disabled = true;
        const prevText = btnApplyOne.textContent;
        btnApplyOne.textContent = "Applying…";
        try {
          await fetchJson("/api/dq/actions/normalizePlaces", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ canonical, variants: variantValues, user: "data-quality" }),
          });

          // Persist approval as a rule (so it can be replayed after a rebuild)
          await fetchJson("/api/places/normalization/rules/upsert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              canonical,
              variants: [canonical, ...variantValues],
              approved: true,
              source_issue_id: item.id,
            }),
          });

          await runScan();
        } catch (err) {
          console.error("normalize places failed", err);
          alert(errMsg(err));
        } finally {
          btnApplyOne.textContent = prevText;
          btnApplyOne.disabled = false;
        }
      });

      container.appendChild(div);
    });

    // Save approvals (writes place_normalization_rules)
    if (btnSavePlacesPlan) {
      btnSavePlacesPlan.disabled = false;
      btnSavePlacesPlan.onclick = async () => {
        const payload = [];
        approvalState.forEach((st) => {
          if (!st.canonical || !st.variants || st.variants.length < 2) return;
          payload.push({
            canonical: st.canonical,
            variants: st.variants,
            approved: !!st.approved,
            source_issue_id: st.source_issue_id,
          });
        });
        if (!payload.length) {
          alert("Nothing to save.");
          return;
        }
        btnSavePlacesPlan.disabled = true;
        const prev = btnSavePlacesPlan.textContent;
        btnSavePlacesPlan.textContent = "Saving…";
        try {
          await fetchJson("/api/places/normalization/rules/upsert", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ rules: payload }),
          });
          alert("Saved.");
        } catch (err) {
          console.error("save approvals failed", err);
          alert(errMsg(err));
        } finally {
          btnSavePlacesPlan.textContent = prev;
          btnSavePlacesPlan.disabled = false;
        }
      };
    }

    // Export plan (downloads JSON)
    if (btnExportPlacesPlan) {
      btnExportPlacesPlan.disabled = false;
      btnExportPlacesPlan.onclick = async () => {
        btnExportPlacesPlan.disabled = true;
        const prev = btnExportPlacesPlan.textContent;
        btnExportPlacesPlan.textContent = "Exporting…";
        try {
          const data = await fetchJson("/api/places/normalization/export");
          const ts = new Date().toISOString().replace(/[:.]/g, "-");
          downloadJson(`place-normalization-plan_${ts}.json`, data);
        } catch (err) {
          console.error("export plan failed", err);
          alert(errMsg(err));
        } finally {
          btnExportPlacesPlan.textContent = prev;
          btnExportPlacesPlan.disabled = false;
        }
      };
    }

    // Import plan (uploads JSON)
    if (btnImportPlacesPlan && fileImportPlacesPlan) {
      btnImportPlacesPlan.disabled = false;
      btnImportPlacesPlan.onclick = () => fileImportPlacesPlan.click();
      fileImportPlacesPlan.onchange = async () => {
        const file = fileImportPlacesPlan.files && fileImportPlacesPlan.files[0];
        if (!file) return;
        try {
          const text = await file.text();
          const obj = JSON.parse(text);
          await fetchJson("/api/places/normalization/import", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(obj),
          });
          await loadPlaces();
        } catch (err) {
          console.error("import plan failed", err);
          alert(errMsg(err));
        } finally {
          fileImportPlacesPlan.value = "";
        }
      };
    }

    // Apply approved rules in bulk (server-side)
    if (btnApplyPlaces) {
      btnApplyPlaces.disabled = false;
      btnApplyPlaces.onclick = async () => {
        if (!confirm("Apply all approved place normalization rules?")) return;
        btnApplyPlaces.disabled = true;
        const prev = btnApplyPlaces.textContent;
        btnApplyPlaces.textContent = "Applying…";
        if (placeBulkStatus) placeBulkStatus.textContent = "Applying approved rules…";
        try {
          const res = await fetchJson("/api/places/normalization/apply", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ user: "data-quality" }),
          });
          const ok = (res.applied || []).length;
          const bad = (res.failed || []).length;
          if (placeBulkStatus) placeBulkStatus.textContent = `Applied ${ok}. Failed ${bad}.`;
          await runScan();
        } catch (err) {
          console.error("bulk apply failed", err);
          alert(errMsg(err));
        } finally {
          btnApplyPlaces.textContent = prev;
          btnApplyPlaces.disabled = false;
        }
      };
    }
  } catch (err) {
    container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
    if (btnApplyPlaces) btnApplyPlaces.disabled = true;
    if (btnSavePlacesPlan) btnSavePlacesPlan.disabled = true;
    if (btnExportPlacesPlan) btnExportPlacesPlan.disabled = true;
    if (placeBulkStatus) placeBulkStatus.textContent = "";
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
          <div class="dqActions">
            <button class="btn btnSecondary" ${item.undo ? "" : "disabled"}>Undo action</button>
          </div>
        `;
        const undoBtn = div.querySelector("button");
        if (item.undo) {
          undoBtn.addEventListener("click", async () => {
            if (!confirm("Undo this action?")) return;
            undoBtn.disabled = true;
            const prev = undoBtn.textContent;
            undoBtn.textContent = "Undoing…";
            try {
              await fetchJson("/api/dq/actions/undo", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ action_id: item.id }),
              });
              await runScan();
            } catch (err) {
              console.error("undo failed", err);
              alert("Undo failed.");
            } finally {
              undoBtn.disabled = false;
              undoBtn.textContent = prev;
            }
          });
        }
        container.appendChild(div);
      });
    } catch (err) {
      container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
    }
  }

  async function loadDates() {
    const container = document.getElementById("dateList");
    const btnApplyDates = document.getElementById("btnApplyDates");
    const dateBulkStatus = document.getElementById("dateBulkStatus");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const data = await fetchJson("/api/dq/issues?type=date_normalization&status=open&perPage=200");
      const items = data.items || [];
      if (!items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        if (btnApplyDates) btnApplyDates.disabled = true;
        if (dateBulkStatus) dateBulkStatus.textContent = "";
        return;
      }

      const applyCandidates = [];
      container.innerHTML = "";
      items.forEach((item) => {
        const explanation = item.explanation || {};
        const normalized = explanation.normalized;
        const qualifier = explanation.qualifier;
        const ambiguous = explanation.ambiguous;
        const entityId = item.entity_ids?.[0];
        const canApply = Boolean(normalized) && !qualifier && !ambiguous && Boolean(entityId);
        if (canApply && entityId) applyCandidates.push(item);
        const div = document.createElement("div");
        div.className = "listItem";
        const targetLabel = `${escapeHtml(item.entity_type || "record")}${explanation.field ? ` • ${escapeHtml(explanation.field)}` : ""}`;
        div.innerHTML = `
          <div class="row">
            <div><strong>${escapeHtml(explanation.raw || "Date")}</strong> → ${escapeHtml(normalized || "Unparsed")}</div>
            <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
          </div>
          <div class="muted small">${item.detected_at}</div>
          <div class="muted small">Target: ${targetLabel}</div>
          <div class="muted small">Precision: ${escapeHtml(explanation.precision || "unknown")}${qualifier ? ` • qualifier ${escapeHtml(qualifier)}` : ""}${ambiguous ? " • ambiguous" : ""}</div>
          <div class="dqActions">
            <button class="btn btnSecondary" ${canApply ? "" : "disabled"}>Apply</button>
            <div class="muted small">${canApply ? "Updates stored date value" : "Qualifier preserved or ambiguous date"}</div>
          </div>
        `;
        const button = div.querySelector("button");
        button.addEventListener("click", async () => {
          const payloadItem = {
            entity_type: item.entity_type,
            entity_id: entityId,
            normalized: normalized,
            precision: explanation.precision,
            qualifier: qualifier,
            raw: explanation.raw,
            confidence: item.confidence,
            ambiguous: ambiguous,
            field: explanation.field,
          };
          button.disabled = true;
          const prev = button.textContent;
          button.textContent = "Applying…";
          try {
            await fetchJson("/api/dq/actions/normalizeDates", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ items: [payloadItem], user: "data-quality" }),
            });
            await runScan();
          } catch (err) {
            console.error("normalize date failed", err);
            alert("Failed to apply date normalization.");
          } finally {
            button.disabled = false;
            button.textContent = prev;
          }
        });
        container.appendChild(div);
      });

      if (btnApplyDates) {
        btnApplyDates.disabled = applyCandidates.length === 0;
        btnApplyDates.onclick = async () => {
          if (!applyCandidates.length) return;
          if (!confirm(`Apply ${applyCandidates.length} clean date normalization(s)?`)) return;
          btnApplyDates.disabled = true;
          const prev = btnApplyDates.textContent;
          btnApplyDates.textContent = "Applying…";
          if (dateBulkStatus) dateBulkStatus.textContent = `Starting 0/${applyCandidates.length}…`;
          try {
            const payloadItems = applyCandidates.map((item) => {
              const explanation = item.explanation || {};
              return {
                entity_type: item.entity_type,
                entity_id: item.entity_ids?.[0],
                normalized: explanation.normalized,
                precision: explanation.precision,
                qualifier: explanation.qualifier,
                raw: explanation.raw,
                confidence: item.confidence,
                ambiguous: explanation.ambiguous,
                field: explanation.field,
              };
            });
            await fetchJson("/api/dq/actions/normalizeDates", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ items: payloadItems, user: "data-quality" }),
            });
            if (dateBulkStatus) dateBulkStatus.textContent = `Applied ${payloadItems.length}/${payloadItems.length}.`;
            await runScan();
          } catch (err) {
            console.error("normalize dates failed", err);
            if (dateBulkStatus) dateBulkStatus.textContent = `Failed: ${errMsg(err)}`;
            alert("Failed to apply date normalizations.");
          } finally {
            btnApplyDates.disabled = false;
            btnApplyDates.textContent = prev;
          }
        };
      }
    } catch (err) {
      container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
      if (btnApplyDates) btnApplyDates.disabled = true;
      if (dateBulkStatus) dateBulkStatus.textContent = "";
    }
  }

  async function loadStandards() {
    const container = document.getElementById("standardsList");
    const btnApplyStandards = document.getElementById("btnApplyStandards");
    const bulkStatus = document.getElementById("standardsBulkStatus");
    if (!container) return;
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const data = await fetchJson("/api/dq/issues?type=field_standardization&status=open&perPage=200");
      const items = data.items || [];
      if (!items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        if (btnApplyStandards) btnApplyStandards.disabled = true;
        if (bulkStatus) bulkStatus.textContent = "";
        return;
      }

      const applyCandidates = [];
      container.innerHTML = "";
      items.forEach((item) => {
        const explanation = item.explanation || {};
        const fields = explanation.fields || [];
        const entityId = item.entity_ids?.[0];
        const updates = {};
        fields.forEach((field) => {
          if (field.field && field.suggested !== undefined) {
            updates[field.field] = field.suggested;
          }
        });
        const canApply = Boolean(entityId) && Object.keys(updates).length > 0;
        if (canApply) {
          applyCandidates.push({ entity_type: item.entity_type, entity_id: entityId, updates });
        }
        const div = document.createElement("div");
        div.className = "listItem";
        const displayName = explanation.entity_label || `${item.entity_type || "record"} ${entityId ?? ""}`.trim();
        const fieldHtml = fields.map((field) => {
          const reason = (field.reasons || []).join(", ");
          const fromVal = escapeHtml(field.current || "");
          const toVal = escapeHtml(field.suggested || "");
          return `
            <div class="dqField">
              <span>${escapeHtml(field.field || "field")}</span>
              <span>${fromVal} → ${toVal}${reason ? ` <span class="muted small">(${escapeHtml(reason)})</span>` : ""}</span>
            </div>
          `;
        }).join("");
        div.innerHTML = `
          <div class="row">
            <div><strong>${escapeHtml(displayName)}</strong></div>
            <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
          </div>
          <div class="muted small">${item.detected_at}</div>
          ${fieldHtml || "<div class='muted small'>No suggestions.</div>"}
          <div class="dqActions">
            <button class="btn btnSecondary" ${canApply ? "" : "disabled"}>Apply</button>
          </div>
        `;
        const button = div.querySelector("button");
        button.addEventListener("click", async () => {
          if (!canApply) return;
          button.disabled = true;
          const prev = button.textContent;
          button.textContent = "Applying…";
          try {
            await fetchJson("/api/dq/actions/standardizeFields", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ items: [{ entity_type: item.entity_type, entity_id: entityId, updates }], user: "data-quality" }),
            });
            await runScan();
          } catch (err) {
            console.error("standardize fields failed", err);
            alert("Failed to apply standardization.");
          } finally {
            button.disabled = false;
            button.textContent = prev;
          }
        });
        container.appendChild(div);
      });

      if (btnApplyStandards) {
        btnApplyStandards.disabled = applyCandidates.length === 0;
        btnApplyStandards.onclick = async () => {
          if (!applyCandidates.length) return;
          if (!confirm(`Apply ${applyCandidates.length} standardization suggestion(s)?`)) return;
          btnApplyStandards.disabled = true;
          const prev = btnApplyStandards.textContent;
          btnApplyStandards.textContent = "Applying…";
          if (bulkStatus) bulkStatus.textContent = `Starting 0/${applyCandidates.length}…`;
          try {
            await fetchJson("/api/dq/actions/standardizeFields", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ items: applyCandidates, user: "data-quality" }),
            });
            if (bulkStatus) bulkStatus.textContent = `Applied ${applyCandidates.length}/${applyCandidates.length}.`;
            await runScan();
          } catch (err) {
            console.error("standardize fields bulk failed", err);
            if (bulkStatus) bulkStatus.textContent = `Failed: ${errMsg(err)}`;
            alert("Failed to apply standardization.");
          } finally {
            btnApplyStandards.disabled = false;
            btnApplyStandards.textContent = prev;
          }
        };
      }
    } catch (err) {
      container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
      if (btnApplyStandards) btnApplyStandards.disabled = true;
      if (bulkStatus) bulkStatus.textContent = "";
    }
  }

  async function loadIntegrity() {
    const container = document.getElementById("integrityList");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    const types = [
      "impossible_timeline",
      "orphan_event",
      "orphan_family",
      "parent_child_age",
      "parent_child_death",
      "marriage_too_early",
      "marriage_after_death",
      "placeholder_name",
    ];
    const labels = {
      impossible_timeline: "Death before birth",
      orphan_event: "Orphaned event",
      orphan_family: "Orphaned family",
      parent_child_age: "Parent too young",
      parent_child_death: "Parent died before child birth",
      marriage_too_early: "Marriage too early",
      marriage_after_death: "Marriage after death",
      placeholder_name: "Placeholder name",
    };
    try {
      const responses = await Promise.all(
        types.map((t) => fetchJson(`/api/dq/issues?type=${encodeURIComponent(t)}&status=open&perPage=200`))
      );
      const items = responses.flatMap((r) => r.items || []);
      if (!items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        return;
      }
      items.sort((a, b) => (b.detected_at || "").localeCompare(a.detected_at || ""));
      container.innerHTML = "";
      items.forEach((item) => {
        const explanation = item.explanation || {};
        const div = document.createElement("div");
        div.className = "listItem";
        div.innerHTML = `
          <div class="row">
            <div><strong>${labels[item.issue_type] || item.issue_type}</strong></div>
            <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
          </div>
          <div class="muted small">${item.detected_at}</div>
          <div class="muted small">${escapeHtml(integrityDescription(item))}</div>
        `;
        container.appendChild(div);
      });
    } catch (err) {
      container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
    }
  }

  async function runScan() {
    btnScan.disabled = true;
    btnScan.textContent = "Scanning…";
    try {
      await fetchJson("/api/dq/scan", { method: "POST" });
      lastScanAt = new Date();
      await Promise.all([
        loadSummary(),
        loadDuplicates(),
        loadPlaces(),
        loadDates(),
        loadStandards(),
        loadIntegrity(),
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
