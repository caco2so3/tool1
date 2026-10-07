// ============================================================
// УТИЛИТЫ
// ============================================================
function escapeHtml(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[c]));
}

const api = async (path, opts = {}) => {
  const r = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...opts,
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  if (r.status === 401) { location.href = "/login"; throw new Error("unauth"); }
  if (!r.ok) throw new Error(await r.text());
  return r.status === 204 ? null : r.json();
};

function openModal(html) {
  document.getElementById("modal").innerHTML = html;
  document.getElementById("modal-backdrop").hidden = false;
}
function closeModal() {
  document.getElementById("modal-backdrop").hidden = true;
}
document.getElementById("modal-backdrop").onclick = (e) => {
  if (e.target.id === "modal-backdrop") closeModal();
};

// ============================================================
// СОСТОЯНИЕ
// ============================================================
let CURRENT_USER = null;

// ============================================================
// BOOTSTRAP
// ============================================================
async function bootstrap() {
  try {
    const r = await fetch("/api/auth/me");
    if (r.status === 401) { location.href = "/login"; return; }
    if (!r.ok) throw new Error("me failed");
    CURRENT_USER = await r.json();
  } catch (e) {
    console.error("bootstrap failed:", e);
    location.href = "/login";
    return;
  }

  document.getElementById("whoami").textContent =
    `${CURRENT_USER.username} · ${CURRENT_USER.role === "admin" ? "админ" : "линейный"}`;

  document.querySelectorAll("[data-admin-only]").forEach((el) => {
    el.hidden = CURRENT_USER.role !== "admin";
  });
  document.querySelectorAll("[data-admin-view]").forEach((el) => {
    if (CURRENT_USER.role !== "admin") el.remove();
  });

  loadSnapshotForm();
}
bootstrap();

document.getElementById("logout-btn").onclick = async () => {
  try {
    await fetch("/api/auth/logout", { method: "POST", credentials: "include" });
  } catch (e) { /* пох */ }
  location.href = "/login";
};

// ============================================================
// ТАБЫ
// ============================================================
document.querySelectorAll("#tabs button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("#tabs button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    document.querySelectorAll("main > section").forEach((s) => (s.hidden = true));
    document.getElementById(`tab-${b.dataset.tab}`).hidden = false;

    const t = b.dataset.tab;
    if (t === "reports") loadReports();
    if (t === "analytics") loadAnalytics();
    if (t === "cards") loadCards();
    if (t === "calc") loadCalc();
    if (t === "admin") loadAdmin();
  };
});

// ============================================================
// ОСТАТКИ
// ============================================================
let currentEventType = "stocktake";
const EVENT_HINTS = {
  stocktake: "Заполни фактические остатки на конец смены.",
  intake: "Внеси, что приготовил. Остатки не трогаем.",
  writeoff: "Списание вручную (порча, ошибка и т.п.).",
};

document.querySelectorAll("#event-type button").forEach((b) => {
  b.onclick = () => {
    document.querySelectorAll("#event-type button").forEach((x) => x.classList.remove("active"));
    b.classList.add("active");
    currentEventType = b.dataset.type;
    document.getElementById("event-hint").textContent = EVENT_HINTS[currentEventType];
    loadSnapshotForm();
  };
});

async function loadSnapshotForm() {
  const products = await api("/api/inventory/products");
  const box = document.getElementById("snapshot-list");
  if (!products.length) {
    box.innerHTML = "<p class='hint'>Нет продуктов. Заведи их в админке.</p>";
    return;
  }
  let prefill = {};
  if (currentEventType === "stocktake") {
    const bal = await api("/api/inventory/balance");
    bal.forEach((b) => { prefill[b.id] = b.last_qty ?? 0; });
  }
  box.innerHTML = products.map((p) => `
    <label class="row">
      <span>${escapeHtml(p.name)} <small>(${escapeHtml(p.unit)})</small></span>
      <input type="number" step="0.01" data-id="${p.id}"
             value="${prefill[p.id] ?? 0}">
    </label>`).join("");
}

document.getElementById("submit-snapshot").onclick = async () => {
  const items = [...document.querySelectorAll("#snapshot-list input")]
    .map((i) => ({ product_id: Number(i.dataset.id), qty: Number(i.value) }))
    .filter((it) => currentEventType !== "stocktake" ? it.qty > 0 : true);

  const status = document.getElementById("snapshot-status");
  if (!items.length) {
    status.textContent = "Нечего отправлять";
    status.className = "status err";
    return;
  }
  try {
    const res = await api("/api/inventory/events", {
      method: "POST",
      body: {
        event_type: currentEventType,
        items,
        note: document.getElementById("event-note").value || null,
      },
    });
    status.textContent = `OK, ${res.count} поз. сохранено`;
    status.className = "status ok";
    document.getElementById("event-note").value = "";
    loadSnapshotForm();
  } catch (e) {
    status.textContent = "Ошибка: " + e.message;
    status.className = "status err";
  }
};

// ============================================================
// ОТЧЁТЫ
// ============================================================
async function loadReports() {
  const list = await api("/api/reports");
  const box = document.getElementById("reports-list");
  document.getElementById("report-detail").innerHTML = "";
  if (!list.length) {
    box.innerHTML = "<p class='hint'>Отчётов пока нет.</p>";
    return;
  }
  box.innerHTML = list.map((r) => `
    <div class="card" onclick="showReport(${r.id})">
      <div>
        <b>${r.period_from.slice(0, 10)}</b>
        <small>${new Date(r.generated_at).toLocaleString("ru-RU")}</small>
      </div>
      ${r.acknowledged ? '<span class="badge">прочитан</span>' : '<span class="badge new">новый</span>'}
    </div>`).join("");
}

window.showReport = async (id) => {
  const r = await api(`/api/reports/${id}`);
  const box = document.getElementById("report-detail");
  box.innerHTML = `
    <h3>Отчёт #${r.id}</h3>
    <table>
      <thead><tr><th>Продукт</th><th>Эталон</th><th>Факт</th><th>Разница</th></tr></thead>
      <tbody>
        ${r.items.map((i) => `
          <tr class="${i.status === "shortage" ? "err" : i.status === "surplus" ? "pos" : ""}">
            <td>${escapeHtml(i.name)}</td>
            <td>${i.ref_qty}</td>
            <td>${i.fact_qty ?? "—"}</td>
            <td>${i.diff == null ? "—" : (i.diff > 0 ? "+" : "") + i.diff.toFixed(2)}</td>
          </tr>`).join("")}
      </tbody>
    </table>
    <button class="primary" onclick="ackReport(${r.id})">Отметить прочитанным</button>
  `;
  box.scrollIntoView({ behavior: "smooth" });
};

window.ackReport = async (id) => {
  await api(`/api/reports/${id}/ack`, { method: "POST" });
  loadReports();
};

// ============================================================
// АНАЛИТИКА
// ============================================================
async function loadAnalytics() {
  try {
    await Promise.all([
      loadHistory(),
      loadWeeksAccordion(),
      loadMonthsAccordion(),
      loadLowAlert(),
    ]);
  } catch (e) {
    console.error("loadAnalytics failed:", e);
  }
}

async function loadHistory(limit = 100) {
  const events = await api(`/api/analytics/events?limit=${limit}`);
  const box = document.getElementById("history-list");
  const typeLabel = { stocktake: "остаток", intake: "приход", writeoff: "списание" };
  const typeClass = { stocktake: "", intake: "pos", writeoff: "err" };
  box.innerHTML = events.length
    ? events.map((e) => `
        <div class="history-row">
          <div>
            <b>${escapeHtml(e.name)}</b>
            <small> · ${typeLabel[e.event_type] || e.event_type}
              ${e.note ? " · " + escapeHtml(e.note) : ""}</small>
            <br><small>${new Date(e.occurred_at).toLocaleString("ru-RU")}</small>
          </div>
          <b class="${typeClass[e.event_type] || ""}" style="text-align:right">
            ${e.event_type === "writeoff" ? "−" : (e.event_type === "intake" ? "+" : "")}
            ${e.qty} ${escapeHtml(e.unit)}
          </b>
        </div>`).join("")
    : "<p class='hint'>Движений пока нет.</p>";
}

async function loadWeeksAccordion() {
  const stored = await api("/api/analytics/weekly?limit=26");
  const live = await api("/api/analytics/weekly/live");

  const all = [
    { key: "live", label: `${live.week_start} — ${live.week_end} (текущая)` },
    ...stored
      .filter((w) => w.week_start !== live.week_start)
      .map((w) => ({ key: w.week_start, label: `${w.week_start} — ${w.week_end}` })),
  ];

  const box = document.getElementById("week-accordion");
  box.innerHTML = all.map((w) => `
    <div class="accordion-item" data-key="${w.key}">
      <button class="accordion-head" onclick="toggleWeek('${w.key}')">
        <span>${escapeHtml(w.label)}</span>
        <span class="chev">▾</span>
      </button>
      <div class="accordion-body" id="week-body-${w.key}" hidden></div>
    </div>`).join("") || "<p class='hint'>Пока нет недель.</p>";
}

window.toggleWeek = async (key) => {
  const body = document.getElementById(`week-body-${key}`);
  const item = document.querySelector(`.accordion-item[data-key="${key}"]`);
  if (!body || !item) return;
  const isOpen = !body.hidden;
  if (isOpen) {
    body.hidden = true;
    item.classList.remove("open");
    return;
  }
  item.classList.add("open");
  body.hidden = false;
  if (body.dataset.loaded) return;

  const data = key === "live"
    ? await api("/api/analytics/weekly/live")
    : await api(`/api/analytics/weekly/${key}`);

  const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(2));
  const fmtTrend = (diff, pct) => {
    if (diff === null || diff === undefined) return "—";
    const sign = diff > 0 ? "+" : "";
    const cls = diff > 0 ? "pos" : diff < 0 ? "err" : "";
    const pctStr = pct == null ? "" : ` (${sign}${pct.toFixed(1)}%)`;
    return `<span class="${cls}">${sign}${diff.toFixed(2)}${pctStr}</span>`;
  };

  const total = data.items.reduce((s, i) => s + (i.consumption || 0), 0);
  body.innerHTML = `
    <table>
      <thead><tr><th>Продукт</th><th>Нач.</th><th>Приход</th>
        <th>Спис.</th><th>Конец</th><th>Расход</th><th>Δ</th></tr></thead>
      <tbody>
        ${data.items.map((i) => `
          <tr>
            <td>${escapeHtml(i.name)} <small>${escapeHtml(i.unit)}</small></td>
            <td>${fmt(i.beginning)}</td>
            <td class="pos">${i.intake ? "+" + i.intake.toFixed(2) : "0"}</td>
            <td class="err">${i.writeoff ? "−" + i.writeoff.toFixed(2) : "0"}</td>
            <td>${fmt(i.ending)}</td>
            <td><b>${fmt(i.consumption)}</b></td>
            <td>${fmtTrend(i.trend_diff, i.trend_pct)}</td>
          </tr>`).join("") || "<tr><td colspan='7' class='hint'>Нет данных.</td></tr>"}
      </tbody>
    </table>
    <p class="hint">Итого: ${total.toFixed(2)}</p>
    ${!data.is_live && CURRENT_USER.role === "admin"
      ? `<button class="secondary" onclick="rebuildWeek('${key}')">Пересобрать</button>`
      : ""}
  `;
  body.dataset.loaded = "1";
};

window.rebuildWeek = async (key) => {
  if (!confirm(`Пересобрать неделю ${key}?`)) return;
  await api(`/api/analytics/weekly/rebuild?week_start=${key}`, { method: "POST" });
  await loadWeeksAccordion();
};

async function loadMonthsAccordion() {
  const now = new Date();
  const months = [];
  for (let i = 0; i < 12; i++) {
    const d = new Date(now.getFullYear(), now.getMonth() - i, 1);
    const y = d.getFullYear();
    const m = String(d.getMonth() + 1).padStart(2, "0");
    months.push({ key: `${y}-${m}`, label: `${y}-${m}` });
  }
  const box = document.getElementById("month-accordion");
  box.innerHTML = months.map((m) => `
    <div class="accordion-item" data-mkey="${m.key}">
      <button class="accordion-head" onclick="toggleMonth('${m.key}')">
        <span>${m.label}</span>
        <span class="chev">▾</span>
      </button>
      <div class="accordion-body" id="month-body-${m.key}" hidden></div>
    </div>`).join("");
}

window.toggleMonth = async (key) => {
  const body = document.getElementById(`month-body-${key}`);
  const item = document.querySelector(`.accordion-item[data-mkey="${key}"]`);
  if (!body || !item) return;
  const isOpen = !body.hidden;
  if (isOpen) {
    body.hidden = true;
    item.classList.remove("open");
    return;
  }
  item.classList.add("open");
  body.hidden = false;
  if (body.dataset.loaded) return;

  const data = await api(`/api/analytics/monthly/${key}`);
  const fmt = (v) => (v === null || v === undefined ? "—" : Number(v).toFixed(2));

  body.innerHTML = `
    <table>
      <thead><tr><th>Продукт</th><th>Нач.</th><th>Приход</th>
        <th>Спис.</th><th>Конец</th><th>Расход</th></tr></thead>
      <tbody>
        ${data.items.map((i) => `
          <tr>
            <td>${escapeHtml(i.name)} <small>${escapeHtml(i.unit)}</small></td>
            <td>${fmt(i.beginning)}</td>
            <td class="pos">${i.intake ? "+" + i.intake.toFixed(2) : "0"}</td>
            <td class="err">${i.writeoff ? "−" + i.writeoff.toFixed(2) : "0"}</td>
            <td>${fmt(i.ending)}</td>
            <td><b>${fmt(i.consumption)}</b></td>
          </tr>`).join("") || "<tr><td colspan='6' class='hint'>Нет данных.</td></tr>"}
      </tbody>
    </table>
  `;
  body.dataset.loaded = "1";
};

async function loadLowAlert() {
  const products = await api("/api/inventory/balance");
  const low = products.filter((p) => (p.last_qty ?? 0) < 1);
  const box = document.getElementById("low-alert");
  if (!low.length) {
    box.innerHTML = "<p class='hint'>Всё в норме.</p>";
    return;
  }
  box.innerHTML = low.map((p) => `
    <div class="history-row">
      <div><b>${escapeHtml(p.name)}</b></div>
      <b class="err">${p.last_qty ?? 0} ${escapeHtml(p.unit)}</b>
    </div>`).join("");
}

window.toggleAccordion = (key) => {
  const item = document.querySelector(`.accordion-item[data-key="${key}"]`);
  if (!item) return;
  const body = item.querySelector(".accordion-body");
  const isOpen = !body.hidden;
  if (isOpen) {
    body.hidden = true;
    item.classList.remove("open");
  } else {
    body.hidden = false;
    item.classList.add("open");
  }
};

// ============================================================
// ТЕХКАРТЫ (мини-таблицы в списке)
// ============================================================
async function loadCards() {
  document.getElementById("cards-search").value = "";
  renderCardsEmpty();
}

function renderCardsEmpty() {
  document.getElementById("cards-list").innerHTML = "";
  document.getElementById("cards-empty").hidden = false;
  document.getElementById("cards-empty").textContent = "Введи название для поиска";
}

async function refreshCardsList() {
  const q = document.getElementById("cards-search").value.trim();
  const box = document.getElementById("cards-list");
  const empty = document.getElementById("cards-empty");

  if (!q) {
    renderCardsEmpty();
    return;
  }

  const cards = await api(`/api/techcards?q=${encodeURIComponent(q)}`);
  empty.hidden = cards.length > 0;
  empty.textContent = "Ничего не найдено";

  const renderTable = (items, title) => {
    if (!items.length) return "";
    return `
      <div class="tc-mini-block">
        ${title ? `<div class="tc-mini-title">${title}</div>` : ""}
        <table class="tc-mini-table">
          <thead>
            <tr><th>Ингредиент</th><th>Кол-во</th></tr>
          </thead>
          <tbody>
            ${items.map((i) => `
              <tr>
                <td>${escapeHtml(i.product_name)}</td>
                <td>${Number(i.qty_per_portion).toFixed(4)} <small>${escapeHtml(i.unit || "")}</small></td>
              </tr>`).join("")}
          </tbody>
        </table>
      </div>`;
  };

  box.innerHTML = cards.map((c) => {
    const small = c.items.filter((i) => i.variant === "small" || !i.variant);
    const large = c.items.filter((i) => i.variant === "large");
    const hasBoth = large.length > 0;

    return `
      <div class="tc-block" data-id="${c.id}">
        <div class="tc-block-head">
          <b>${escapeHtml(c.name)}</b>
          ${c.note ? `<small>${escapeHtml(c.note)}</small>` : ""}
        </div>
        <div class="tc-block-body">
          ${renderTable(small, hasBoth ? "Малый объём" : "")}
          ${renderTable(large, hasBoth ? "Большой объём" : "")}
        </div>
        ${c.method ? `
          <details class="tc-method">
            <summary>Метод приготовления</summary>
            <div class="tc-method-body">${escapeHtml(c.method)}</div>
          </details>` : ""}
      </div>`;
  }).join("");
}

let cardsSearchTimer;
document.getElementById("cards-search").addEventListener("input", () => {
  clearTimeout(cardsSearchTimer);
  cardsSearchTimer = setTimeout(refreshCardsList, 180);
});

// ============================================================
// КАЛЬКУЛЯТОР
// ============================================================
let CALC = { card: null };

async function loadCalc() {
  document.getElementById("calc-list-view").hidden = false;
  document.getElementById("calc-detail-view").hidden = true;
  document.getElementById("calc-search").value = "";
  await refreshCalcList();

  const newBtn = document.getElementById("calc-new-btn");
  newBtn.hidden = CURRENT_USER?.role !== "admin";
  newBtn.onclick = () => editTechcard(null);
}

async function refreshCalcList() {
  const q = document.getElementById("calc-search").value.trim();
  const url = q ? `/api/techcards?q=${encodeURIComponent(q)}` : "/api/techcards";
  const cards = await api(url);
  const box = document.getElementById("calc-cards");
  box.innerHTML = cards.length
    ? cards.map((c) => `
        <div class="card techcard-card" onclick="openCard(${c.id})">
          <div>
            <b>${escapeHtml(c.name)}</b>
            ${c.note ? `<small>${escapeHtml(c.note)}</small>` : ""}
          </div>
          <span class="chev">›</span>
        </div>`).join("")
    : `<p class="hint">${q ? "Ничего не найдено." : "Начни вводить название."}</p>`;
}

let calcSearchTimer;
document.getElementById("calc-search").addEventListener("input", () => {
  clearTimeout(calcSearchTimer);
  calcSearchTimer = setTimeout(refreshCalcList, 200);
});

window.openCard = async (cid) => {
  const card = await api(`/api/techcards/${cid}`);
  CALC.card = card;

  document.getElementById("calc-list-view").hidden = true;
  document.getElementById("calc-detail-view").hidden = false;
  document.getElementById("calc-name").textContent = card.name;
  document.getElementById("calc-note").textContent = card.note || "";
  document.getElementById("calc-needed").value = 1;

  const editBtn = document.getElementById("calc-edit-btn");
  editBtn.hidden = CURRENT_USER?.role !== "admin";
  editBtn.onclick = () => editTechcard(card.id);

  recomputeCalc();
};

document.getElementById("calc-back").onclick = () => loadCalc();
document.getElementById("calc-needed").addEventListener("input", recomputeCalc);

function calcIngredientMl(needed, sumPerPortion, ingrPerPortion) {
  if (!sumPerPortion || sumPerPortion <= 0) return 0;
  const raw = (needed / sumPerPortion) * ingrPerPortion * 1000;
  return Math.floor(raw / 5) * 5;
}

function recomputeCalc() {
  const card = CALC.card;
  if (!card) return;
  const needed = Number(document.getElementById("calc-needed").value) || 0;
  const sum = card.items.reduce((s, i) => s + Number(i.qty_per_portion), 0);
  const rows = card.items.map((i) => {
    const ml = calcIngredientMl(needed, sum, Number(i.qty_per_portion));
    return `<tr>
      <td>${escapeHtml(i.product_name)}</td>
      <td>${Number(i.qty_per_portion).toFixed(4)} ${escapeHtml(i.unit || "")}</td>
      <td><b>${ml}</b> мл</td>
    </tr>`;
  }).join("");
  document.querySelector("#calc-table tbody").innerHTML =
    rows || "<tr><td colspan='3' class='hint'>Ингредиентов нет.</td></tr>";
}

// ============================================================
// РЕДАКТОР ТЕХКАРТЫ
// ============================================================
window.editTechcard = async (cid) => {
  const card = cid ? await api(`/api/techcards/${cid}`) : null;
  const products = await api("/api/admin/products");
  if (!products.length) {
    alert("Сначала заведи продукты в админке.");
    return;
  }

  const items = card ? card.items.map((i) => ({
    product_id: i.product_id,
    qty_per_portion: i.qty_per_portion,
    unit: i.unit || (products.find((p) => p.id === i.product_id)?.unit || ""),
    variant: i.variant || "small",
  })) : [];

  const hasLarge = items.some((i) => i.variant === "large");

  openModal(`
    <h3>${card ? "Техкарта: " + escapeHtml(card.name) : "Новая техкарта"}</h3>
    <form id="tc-form">
      <input name="name" placeholder="Название ПФ" value="${card ? escapeHtml(card.name) : ""}" required>
      <input name="note" placeholder="Заметка (опц.)" value="${card?.note ? escapeHtml(card.note) : ""}">
      <textarea name="method" placeholder="Метод приготовления (можно длинно)"
        rows="4" style="width:100%;background:#0f1115;color:var(--fg);border:1px solid #2a3140;border-radius:8px;padding:10px;font-family:inherit;margin:6px 0;resize:vertical"
      >${card?.method ? escapeHtml(card.method) : ""}</textarea>

      <label class="toggle-row" style="margin-top:8px">
        <span>Есть большой объём?</span>
        <span class="toggle">
          <input type="checkbox" id="tc-has-large" ${hasLarge ? "checked" : ""}>
          <span class="slider"></span>
        </span>
      </label>

      <div id="tc-variant-small">
        <h4 style="margin:10px 0 4px">Малый рецепт</h4>
        <div id="tc-items-small"></div>
        <button type="button" class="secondary" data-add="small">+ Добавить (малый)</button>
      </div>

      <div id="tc-variant-large" ${hasLarge ? "" : "hidden"}>
        <h4 style="margin:10px 0 4px">Большой рецепт</h4>
        <div id="tc-items-large"></div>
        <button type="button" class="secondary" data-add="large">+ Добавить (большой)</button>
      </div>

      <div class="modal-actions">
        ${card ? `<button type="button" id="tc-del" class="danger">Удалить</button>` : ""}
        <button type="button" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary">Сохранить</button>
      </div>
    </form>
  `);

  const smallBox = document.getElementById("tc-items-small");
  const largeBox = document.getElementById("tc-items-large");
  const hasLargeChk = document.getElementById("tc-has-large");

  hasLargeChk.onchange = () => {
    document.getElementById("tc-variant-large").hidden = !hasLargeChk.checked;
    if (hasLargeChk.checked && !items.some((i) => i.variant === "large")) {
      items.push({
        product_id: products[0].id, qty_per_portion: 0,
        unit: products[0].unit || "", variant: "large",
      });
      refresh();
    }
  };

  function renderRow(it, idx) {
    return `
      <div class="tc-item-row" data-idx="${idx}">
        <select data-f="product_id">
          ${products.map((p) =>
            `<option value="${p.id}" ${p.id === it.product_id ? "selected" : ""}>${escapeHtml(p.name)}</option>`
          ).join("")}
        </select>
        <input type="number" step="0.0001" data-f="qty_per_portion"
               value="${it.qty_per_portion}" placeholder="кол-во">
        <input data-f="unit" value="${escapeHtml(it.unit || "")}" placeholder="ед.">
        <button type="button" class="remove-item" data-idx="${idx}">✕</button>
      </div>`;
  }

  function refresh() {
    smallBox.innerHTML = items
      .map((it, i) => ({ it, i }))
      .filter(({ it }) => it.variant !== "large")
      .map(({ it, i }) => renderRow(it, i)).join("");

    largeBox.innerHTML = items
      .map((it, i) => ({ it, i }))
      .filter(({ it }) => it.variant === "large")
      .map(({ it, i }) => renderRow(it, i)).join("");

    [...smallBox.querySelectorAll(".tc-item-row"), ...largeBox.querySelectorAll(".tc-item-row")]
      .forEach((row) => bindRow(row));
  }

  function bindRow(row) {
    const idx = Number(row.dataset.idx);
    row.querySelector('[data-f="product_id"]').onchange = (e) => {
      const pid = Number(e.target.value);
      const p = products.find((x) => x.id === pid);
      items[idx].product_id = pid;
      if (p) { items[idx].unit = p.unit; row.querySelector('[data-f="unit"]').value = p.unit; }
    };
    row.querySelector('[data-f="qty_per_portion"]').oninput = (e) => {
      items[idx].qty_per_portion = Number(e.target.value);
    };
    row.querySelector('[data-f="unit"]').oninput = (e) => {
      items[idx].unit = e.target.value;
    };
    row.querySelector(".remove-item").onclick = () => {
      items.splice(idx, 1); refresh();
    };
  }

  if (!items.length && products.length) {
    items.push({
      product_id: products[0].id, qty_per_portion: 0,
      unit: products[0].unit || "", variant: "small",
    });
  }
  refresh();

  document.querySelectorAll("[data-add]").forEach((btn) => {
    btn.onclick = () => {
      const variant = btn.dataset.add;
      items.push({
        product_id: products[0].id, qty_per_portion: 0,
        unit: products[0].unit || "", variant,
      });
      refresh();
    };
  });

  if (card) {
    document.getElementById("tc-del").onclick = async () => {
      if (!confirm("Деактивировать техкарту?")) return;
      await api(`/api/techcards/${card.id}`, { method: "DELETE" });
      closeModal();
      loadAdminTechcards();
    };
  }

  document.getElementById("tc-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    const cleanItems = items
      .filter((i) => i.product_id && Number(i.qty_per_portion) > 0)
      .map((i) => ({
        product_id: i.product_id,
        qty_per_portion: Number(i.qty_per_portion),
        unit: i.unit || null,
        variant: i.variant,
      }));
    if (!cleanItems.length) {
      alert("Добавь хотя бы один ингредиент с количеством > 0");
      return;
    }
    const payload = {
      name: f.name.value.trim(),
      note: f.note.value.trim() || null,
      method: f.method.value.trim() || null,
      items: cleanItems,
    };
    try {
      if (card) {
        await api(`/api/techcards/${card.id}`, {
          method: "PATCH",
          body: { name: payload.name, note: payload.note, method: payload.method },
        });
        await api(`/api/techcards/${card.id}/items`, {
          method: "PUT", body: cleanItems,
        });
      } else {
        await api("/api/techcards", { method: "POST", body: payload });
      }
      closeModal();
      loadAdminTechcards();
    } catch (err) {
      alert("Ошибка: " + err.message);
    }
  };
};

// ============================================================
// АДМИН
// ============================================================
async function loadAdmin() {
  await Promise.all([
    loadAdminProducts(),
    loadAdminTechcards(),
    loadSettings(),
    loadUsers(),
  ]);
}

async function loadAdminProducts() {
  const products = await api("/api/admin/products");
  const box = document.getElementById("admin-products");
  box.innerHTML = products.map((p) => `
    <div class="admin-row" data-id="${p.id}">
      <input value="${escapeHtml(p.name)}" data-field="name">
      <input value="${escapeHtml(p.unit)}" data-field="unit">
      <input type="number" step="0.01" value="${p.ref_qty}" data-field="ref_qty">
      <button onclick="saveProduct(${p.id})" title="Сохранить">💾</button>
      <button onclick="refModal(${p.id}, '${escapeHtml(p.name)}', ${p.ref_qty}, '${escapeHtml(p.unit)}')" title="Норма">Σ</button>
      <button onclick="deleteProduct(${p.id})" title="Деактивировать">🗑</button>
    </div>`).join("") || "<p class='hint'>Продуктов пока нет.</p>";
}

window.saveProduct = async (id) => {
  const row = document.querySelector(`.admin-row[data-id="${id}"]`);
  const body = {};
  row.querySelectorAll("input[data-field]").forEach((i) => {
    if (i.dataset.field === "ref_qty") return;
    body[i.dataset.field] = i.value;
  });
  await api(`/api/admin/products/${id}`, { method: "PATCH", body });
  loadAdminProducts();
};

window.deleteProduct = async (id) => {
  if (!confirm("Деактивировать продукт?")) return;
  try {
    const r = await fetch(`/api/admin/products/${id}`, { method: "DELETE" });
    if (!r.ok) throw new Error(await r.text());
    await loadAdminProducts();
  } catch (e) {
    alert("Ошибка удаления: " + e.message);
  }
};

window.refModal = async (id, name, currentRef, unit) => {
  const history = await api(`/api/admin/products/${id}/ref-history`).catch(() => []);
  openModal(`
    <h3>Норма: ${escapeHtml(name)}</h3>
    <p class="hint">Текущая: <b>${currentRef} ${escapeHtml(unit)}</b></p>
    <form id="ref-form">
      <input type="number" step="0.01" name="ref_qty" value="${currentRef}" required>
      <input name="note" placeholder="Причина изменения (опц.)">
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary">Сохранить</button>
      </div>
    </form>
    ${history.length ? `<h4 style="margin-top:14px">История</h4>
      <div class="hint" style="max-height:140px;overflow:auto">
        ${history.map((h) => `<div>${h.changed_at.slice(0,10)}: ${h.old_qty} → ${h.new_qty} ${h.note ? "· " + escapeHtml(h.note) : ""}</div>`).join("")}
      </div>` : ""}
  `);
  document.getElementById("ref-form").onsubmit = async (e) => {
    e.preventDefault();
    const f = e.target;
    await api(`/api/admin/products/${id}/ref`, {
      method: "PUT",
      body: { ref_qty: Number(f.ref_qty.value), note: f.note.value || null },
    });
    closeModal();
    loadAdminProducts();
  };
};

document.getElementById("add-product").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api("/api/admin/products", {
      method: "POST",
      body: {
        name: f.name.value,
        unit: f.unit.value,
        ref_qty: Number(f.ref_qty.value),
        track_stock: f.track_stock.checked,
      },
    });
    f.reset();
    f.unit.value = "шт";
    f.ref_qty.value = "0";
    f.track_stock.checked = true;
    loadAdminProducts();
  } catch (err) {
    alert("Ошибка: " + err.message);
  }
};

async function loadAdminTechcards() {
  const cards = await api("/api/techcards");
  const box = document.getElementById("admin-techcards");
  box.innerHTML = cards.length
    ? cards.map((c) => `
        <div class="card" style="cursor:default">
          <div><b>${escapeHtml(c.name)}</b>
            ${c.note ? `<small>${escapeHtml(c.note)}</small>` : ""}
          </div>
          <button class="icon-btn" onclick="editTechcard(${c.id})">✎</button>
        </div>`).join("")
    : "<p class='hint'>Техкарт пока нет.</p>";
}

document.getElementById("add-techcard-btn").onclick = () => editTechcard(null);

async function loadSettings() {
  const s = await api("/api/admin/settings");
  document.getElementById("disp-weekday").textContent = s.alert_time_weekday;
  document.getElementById("disp-weekend").textContent = s.alert_time_weekend;
}

window.openTimeModal = (which) => {
  const key = which === "weekday" ? "alert_time_weekday" : "alert_time_weekend";
  const elId = which === "weekday" ? "disp-weekday" : "disp-weekend";
  const current = document.getElementById(elId).textContent;
  openModal(`
    <h3>Время отчёта: ${which === "weekday" ? "Пн–Пт" : "Сб–Вс"}</h3>
    <p class="hint">Сейчас: <b>${current}</b> (Екб, UTC+5)</p>
    <form id="time-form">
      <input type="time" name="t" value="${current}" required>
      <div class="modal-actions">
        <button type="button" onclick="closeModal()">Отмена</button>
        <button type="submit" class="primary">Сохранить</button>
      </div>
    </form>
  `);
  document.getElementById("time-form").onsubmit = async (e) => {
    e.preventDefault();
    await api("/api/admin/settings", {
      method: "PATCH",
      body: { [key]: e.target.t.value },
    });
    closeModal();
    loadSettings();
  };
};

async function loadUsers() {
  const users = await api("/api/auth/users");
  document.getElementById("users-list").innerHTML = users.map((u) => `
    <div class="admin-row" data-id="${u.id}">
      <span style="flex:1">${escapeHtml(u.username)}</span>
      <span class="badge">${u.role === "admin" ? "админ" : "линейный"}</span>
      <span class="badge ${u.active ? "" : "new"}">${u.active ? "активен" : "отключён"}</span>
      <button onclick="resetPassword(${u.id})" title="Сменить пароль">🔑</button>
      ${u.active ? `<button onclick="disableUser(${u.id})" title="Отключить">🗑</button>` : ""}
    </div>`).join("");
}

window.resetPassword = async (uid) => {
  const pwd = prompt("Новый пароль (мин. 4 символа):");
  if (!pwd) return;
  try {
    await api(`/api/auth/users/${uid}/password`, { method: "PUT", body: { password: pwd } });
    alert("Пароль изменён");
  } catch (e) {
    alert("Ошибка: " + e.message);
  }
};

window.disableUser = async (uid) => {
  if (!confirm("Отключить пользователя?")) return;
  await api(`/api/auth/users/${uid}`, { method: "DELETE" });
  loadUsers();
};

document.getElementById("add-user").onsubmit = async (e) => {
  e.preventDefault();
  const f = e.target;
  try {
    await api("/api/auth/users", {
      method: "POST",
      body: { username: f.username.value, password: f.password.value, role: f.role.value },
    });
    f.reset();
    loadUsers();
  } catch (err) {
    alert("Ошибка: " + err.message);
  }
};

// ============================================================
// PWA
// ============================================================
if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}