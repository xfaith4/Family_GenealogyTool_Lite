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

  function errMsg(err) {
    if (!err) return "Unknown error";
    if (typeof err === "string") return err;
    return err.message || "Request failed";
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
          const div = document.createElement("div");
          div.className = "listItem";
          div.innerHTML = `
            <div class="row">
              <div><strong>${escapeHtml(fullName(left))}</strong> + <strong>${escapeHtml(fullName(right))}</strong></div>
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
    const placeBulkStatus = document.getElementById("placeBulkStatus");
    container.innerHTML = "<div class='muted'>Loading…</div>";
    try {
      const [clusters, similarities] = await Promise.all([
        fetchJson("/api/dq/issues?type=place_cluster&status=open&perPage=200"),
        fetchJson("/api/dq/issues?type=place_similarity&status=open&perPage=200"),
      ]);
      const items = [...(clusters.items || []), ...(similarities.items || [])];
      if (!items.length) {
        container.innerHTML = "<div class='muted'>No open items.</div>";
        if (btnApplyPlaces) btnApplyPlaces.disabled = true;
        if (placeBulkStatus) placeBulkStatus.textContent = "";
        return;
      }
      items.sort((a, b) => (b.confidence || 0) - (a.confidence || 0));
      const applyCandidates = [];
      container.innerHTML = "";
      items.forEach((item) => {
        const explanation = item.explanation || {};
        const variants = explanation.variants || [];
        const canonicalSuggestion = explanation.canonical_suggestion || (variants[0]?.value || "");
        if (canonicalSuggestion && variants.length) {
          applyCandidates.push({ canonical: canonicalSuggestion, variants, issue_id: item.id });
        }
        const similarity = explanation.similarity ?? item.confidence;
        const variantList = variants
          .map((v) => `${escapeHtml(v.value)} (${v.count})`)
          .join(", ");
        const div = document.createElement("div");
        div.className = "listItem";
        div.innerHTML = `
          <div class="row">
            <div><strong>${item.issue_type === "place_similarity" ? "Similar place names" : "Place variants"}</strong>${similarity ? ` • ${Math.round(similarity * 100)}%` : ""}</div>
            <div class="dqBadge ${confidenceClass(item.confidence)}">${confidenceLabel(item.confidence)} • ${asConfidence(item.confidence)}</div>
          </div>
          <div class="muted small">${item.detected_at}</div>
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
      if (btnApplyPlaces) {
        btnApplyPlaces.disabled = applyCandidates.length === 0;
        btnApplyPlaces.onclick = async () => {
          if (!applyCandidates.length) return;
          if (!confirm(`Apply ${applyCandidates.length} suggested place standardization(s)?`)) return;
          btnApplyPlaces.disabled = true;
          const prev = btnApplyPlaces.textContent;
          btnApplyPlaces.textContent = "Applying…";
          if (placeBulkStatus) placeBulkStatus.textContent = `Starting 0/${applyCandidates.length}…`;
          try {
            for (let i = 0; i < applyCandidates.length; i += 1) {
              const candidate = applyCandidates[i];
              if (placeBulkStatus) placeBulkStatus.textContent = `Applying ${i + 1}/${applyCandidates.length}…`;
              const variantValues = candidate.variants
                .map((v) => v.value)
                .filter((v) => v && v !== candidate.canonical);
              if (!variantValues.length) continue;
              await fetchJson("/api/dq/actions/normalizePlaces", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ canonical: candidate.canonical, variants: variantValues, user: "data-quality" }),
              });
            }
            if (placeBulkStatus) placeBulkStatus.textContent = "Done.";
            await runScan();
          } catch (err) {
            console.error("bulk place normalization failed", err);
            if (placeBulkStatus) placeBulkStatus.textContent = `Failed: ${errMsg(err)}`;
            alert("Bulk place standardization failed.");
          } finally {
            btnApplyPlaces.disabled = false;
            btnApplyPlaces.textContent = prev;
          }
        };
      }
    } catch (err) {
      container.innerHTML = `<div class='muted'>${escapeHtml(errMsg(err))}</div>`;
      if (btnApplyPlaces) btnApplyPlaces.disabled = true;
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
    ];
    const labels = {
      impossible_timeline: "Death before birth",
      orphan_event: "Orphaned event",
      orphan_family: "Orphaned family",
      parent_child_age: "Parent too young",
      parent_child_death: "Parent died before child birth",
      marriage_too_early: "Marriage too early",
      marriage_after_death: "Marriage after death",
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
          <div class="muted small">${escapeHtml(JSON.stringify(explanation))}</div>
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
      await Promise.all([
        loadSummary(),
        loadDuplicates(),
        loadPlaces(),
        loadDates(),
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
