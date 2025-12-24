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

  function escapeHtml(s) {
    return (s ?? "").toString()
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#039;");
  }

  function asPercent(value) {
    return `${value ?? 0}%`;
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

  async function loadDuplicates() {
    const container = document.getElementById("dupList");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const [peopleIssues, familyIssues, mediaIssues] = await Promise.all([
        fetchJson("/api/dq/issues?type=duplicate_person&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=duplicate_family&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=duplicate_media_link&status=open&perPage=200"),
      ]);
      const peopleItems = peopleIssues.items || [];
      const familyItems = familyIssues.items || [];
      const mediaItems = mediaIssues.items || [];

      if (!peopleItems.length && !familyItems.length && !mediaItems.length) {
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
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>${escapeHtml(fullName(left))}</strong> + <strong>${escapeHtml(fullName(right))}</strong></div>
              <div class="muted small">confidence ${item.confidence ?? "?"}</div>
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
              const [leftDetail, rightDetail] = await Promise.all([
                fetchJson(`/api/people/${ids[0]}`),
                fetchJson(`/api/people/${ids[1]}`),
              ]);
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
              <div class="muted small">confidence ${item.confidence ?? "?"}</div>
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
              const [leftDetail, rightDetail] = await Promise.all([
                fetchJson(`/api/families/${ids[0]}`),
                fetchJson(`/api/families/${ids[1]}`),
              ]);
              const radioName = `merge_family_${item.id}`;
              const leftLabel = `${fullName(leftDetail.husband)} + ${fullName(leftDetail.wife)}`.trim();
              const rightLabel = `${fullName(rightDetail.husband)} + ${fullName(rightDetail.wife)}`.trim();
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
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>${escapeHtml(asset.original_filename || "Media asset")}</strong></div>
              <div class="muted small">${explanation.link_ids?.length || 0} duplicate link(s)</div>
            </div>
            <div class="muted small">Linked to: ${person ? escapeHtml(fullName(person)) : (explanation.family_id ? "Family" : "Unknown")}</div>
            <div class="row" style="margin-top:8px;">
              <button class="btn btnSecondary" data-action="dedupe">Remove duplicates</button>
              <div class="muted small">${item.detected_at}</div>
            </div>
          `;
          const btn = div.querySelector('[data-action="dedupe"]');
          btn.addEventListener("click", async () => {
            const linkIds = explanation.link_ids || [];
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
              btn.textContent = "Remove duplicates";
            }
          });
          container.appendChild(div);
        });
      }
    } catch (err) {
      container.innerHTML = `<div class='muted'>${err}</div>`;
    }
  }

  async function loadPlaces() {
    const container = document.getElementById("placeList");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const [clusters, similarities] = await Promise.all([
        fetchJson("/api/dq/issues?type=place_cluster&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=place_similarity&status=open&perPage=200"),
      ]);
      const items = [...(clusters.items || []), ...(similarities.items || [])];
      if (!items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        return;
      }
      items.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
      container.innerHTML = "";
      items.forEach((item) => {
        const explanation = item.explanation || {};
        const variants = explanation.variants || [];
        const canonicalSuggestion = explanation.canonical_suggestion || (variants[0]?.value || "");
        const similarity = explanation.similarity ?? item.confidence;
        const variantList = variants
          .map((v) => `${escapeHtml(v.value)} (${v.count})`)
          .join(", ");
        const div = document.createElement("div");
        div.className = "listItem";
        div.innerHTML = `
          <div class="row">
            <div><strong>${item.issue_type === "place_similarity" ? "Similar place names" : "Place variants"}</strong>${similarity ? ` • ${Math.round(similarity * 100)}%` : ""}</div>
            <div class="muted small">${item.detected_at}</div>
          </div>
          <div class="muted small">Variants: ${variantList || "None listed"}</div>
          <div class="row" style="margin-top:10px; flex-wrap:wrap;">
            <input class="input inputSmall" value="${escapeHtml(canonicalSuggestion)}" />
            <button class="btn btnSecondary">Standardize</button>
          </div>
          <div class="muted small" style="margin-top:6px;">Suggested canonical: ${escapeHtml(canonicalSuggestion || "")}</div>
        `;
        const input = div.querySelector("input");
        const button = div.querySelector("button");
        button.addEventListener("click", async () => {
          const canonical = (input.value || "").trim();
          if (!canonical) return;
          const variantValues = variants.map((v) => v.value).filter((v) => v && v !== canonical);
          if (!variantValues.length) {
            alert("No variants to standardize.");
            return;
          }
          if (!confirm(`Standardize ${variantValues.length} variant(s) to "${canonical}"?`)) return;
          button.disabled = true;
          const prevText = button.textContent;
          button.textContent = "Applying…";
          try {
            await fetchJson("/api/dq/actions/normalizePlaces", {
              method: "POST",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ canonical, variants: variantValues, user: "data-quality" }),
            });
            await runScan();
          } catch (err) {
            console.error("normalize places failed", err);
            alert("Failed to standardize places.");
          } finally {
            button.disabled = false;
            button.textContent = prevText;
          }
        });
        container.appendChild(div);
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

  async function loadDates() {
    const container = document.getElementById("dateList");
    const btnApplyDates = document.getElementById("btnApplyDates");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const data = await fetchJson("/api/dq/issues?type=date_normalization&status=open&perPage=200");
      const items = data.items || [];
      if (!items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        if (btnApplyDates) btnApplyDates.disabled = true;
        return;
      }

      const applyCandidates = [];
      container.innerHTML = "";
      items.forEach((item) => {
        const explanation = item.explanation || {};
        const normalized = explanation.normalized;
        const qualifier = explanation.qualifier;
        const ambiguous = explanation.ambiguous;
        const canApply = Boolean(normalized) && !qualifier && !ambiguous;
        if (canApply) applyCandidates.push(item);
        const div = document.createElement("div");
        div.className = "listItem";
        div.innerHTML = `
          <div class="row">
            <div><strong>${escapeHtml(explanation.raw || "Date")}</strong> → ${escapeHtml(normalized || "Unparsed")}</div>
            <div class="muted small">${item.detected_at}</div>
          </div>
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
            entity_id: item.entity_ids?.[0],
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
            await runScan();
          } catch (err) {
            console.error("normalize dates failed", err);
            alert("Failed to apply date normalizations.");
          } finally {
            btnApplyDates.disabled = false;
            btnApplyDates.textContent = prev;
          }
        };
      }
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
        loadDuplicates(),
        loadPlaces(),
        loadDates(),
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
