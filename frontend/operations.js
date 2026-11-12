const ops = elements["ops-view"];
const navButtons = [...document.querySelectorAll("[data-view]")];
let currentView;
let viewVersion = 0;

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function dateKey(date = new Date()) {
  const parts = [date.getFullYear(), date.getMonth() + 1, date.getDate()];
  return parts.map(value => String(value).padStart(2, "0")).join("-");
}

function displayStatus(value) {
  return value.replaceAll("_", " ");
}

function panel(title, ...content) {
  const box = node("section", undefined, "ops-panel");
  box.append(node("h2", title), ...content);
  return box;
}

function table(headers, records, empty = "No records yet.") {
  if (!records.length) return node("p", empty, "ops-muted");
  const scroll = node("div", undefined, "table-scroll ops-table");
  scroll.tabIndex = 0;
  const grid = node("table");
  const header = grid.createTHead().insertRow();
  for (const label of headers) {
    const cell = node("th", label);
    cell.scope = "col";
    header.append(cell);
  }
  const body = grid.createTBody();
  for (const record of records) {
    const row = body.insertRow();
    for (const value of record) {
      const cell = row.insertCell();
      if (value instanceof Node) cell.append(value);
      else cell.textContent = value ?? "—";
    }
  }
  scroll.append(grid);
  return scroll;
}

function heading(title, detail, buttons = []) {
  const line = node("div", undefined, "ops-title");
  const text = node("div");
  text.append(node("h1", title), node("p", detail, "ops-muted"));
  line.append(text, ...buttons);
  ops.append(line);
}

function badge(text, variant = "") {
  return node("span", text, `ops-badge ${variant}`);
}

function metrics(label, value, detail) {
  const box = node("div", undefined, "ops-stat");
  box.append(node("span", label), node("strong", value), node("small", detail));
  return box;
}

function jobTable(jobs, today, editable = false) {
  const headers = ["Work order", "Customer", "Status", "Expected delivery"];
  if (editable) headers.push("Action");
  return table(headers, jobs.map(job => {
    const overdue = job.expected_delivery < today && job.expected_delivery && !["delivered", "cancelled"].includes(job.status);
    const row = [job.reference + " · " + job.title, job.company,
      badge(overdue ? "overdue" : displayStatus(job.status), overdue ? "warn" : ""),
      job.expected_delivery];
    if (editable) row.push(action("Edit", () => editJob({company_id: job.company_id, name: job.company}, job)));
    return row;
  }), "No work orders to show.");
}

function productionChart(trend, today) {
  const chart = node("div", undefined, "ops-chart");
  const maximum = Math.max(1, ...trend.map(row => row.output));
  const byDate = new Map(trend.map(row => [row.production_date, row]));
  const day = new Date(today + "T12:00:00");
  day.setDate(day.getDate() - 6);
  for (let index = 0; index < 7; index++, day.setDate(day.getDate() + 1)) {
    const value = byDate.get(dateKey(day))?.output ?? 0;
    const group = node("div", undefined, "ops-bar-group");
    const bar = node("div", undefined, "ops-bar");
    bar.style.setProperty("--height", `${value / maximum * 108}px`);
    const label = day.toLocaleDateString(undefined, { weekday: "short" });
    group.title = `${dateKey(day)} · ${value} units`;
    group.append(node("span", value, "ops-bar-value"), bar, node("span", label, "ops-bar-label"));
    chart.append(group);
  }
  return chart;
}

function overview(data, today) {
  heading("Production overview", new Date(today + "T12:00:00").toLocaleDateString(undefined, { dateStyle: "full" }), [
    action("Refresh", () => showOperations("overview")),
  ]);
  const daily = data.trend.find(row => row.production_date === today);
  const open = data.jobs.filter(job => !["delivered", "cancelled"].includes(job.status));
  const low = data.stock.filter(item => item.quantity <= item.reorder_point);
  const attention = data.machines.filter(machine => ["maintenance", "offline"].includes(machine.status));
  const counts = node("div", undefined, "ops-stats");
  counts.append(metrics("Units produced", daily?.output ?? 0, daily ? `${daily.rejected} rejected today` : "Today"),
    metrics("Machines running", `${data.machines.filter(m => m.status === "running").length} / ${data.machines.length}`, "Current status"),
    metrics("Open work orders", open.length, "Awaiting delivery"),
    metrics("Low stock items", low.length, "At or below reorder point"));
  ops.append(counts);

  const first = node("div", undefined, "ops-grid");
  const oee = daily ? Math.round(100 * Number(daily.good_ideal_seconds) / (daily.planned * 60)) : null;
  const gauge = node("div", oee === null ? "—" : `${oee}%`, "ops-gauge");
  gauge.style.setProperty("--score", `${oee ?? 0}%`);
  const factors = node("div", undefined, "ops-factors");
  const percent = (numerator, denominator) => denominator ? `${Math.round(numerator * 100 / denominator)}%` : "—";
  for (const [label, value] of [
    ["Availability", percent(daily?.runtime, daily?.planned)],
    ["Performance", percent(daily?.ideal_seconds, (daily?.runtime ?? 0) * 60)],
    ["Quality", percent(daily?.good_ideal_seconds, Number(daily?.ideal_seconds))],
  ]) {
    const line = node("p");
    line.append(node("span", label), node("strong", value));
    factors.append(line);
  }
  const effectiveness = node("div", undefined, "ops-effectiveness");
  effectiveness.append(gauge, factors);
  first.append(panel("Production trend · 7 days", productionChart(data.trend, today)),
    panel("Equipment effectiveness · Today", effectiveness));
  ops.append(first);

  const second = node("div", undefined, "ops-grid");
  const signals = [...low.map(item => `Low stock · ${item.name} (${item.quantity} ${item.unit})`),
    ...attention.map(machine => `${displayStatus(machine.status)} · ${machine.name}`),
    ...open.filter(job => job.expected_delivery && job.expected_delivery < today).map(job => `Overdue · ${job.reference} (${job.company})`)];
  const signalList = node("ul", undefined, "ops-alerts");
  for (const signal of signals) signalList.append(node("li", signal));
  second.append(panel("Work orders", jobTable(open.slice(0, 6), today)),
    panel("Alerts", signals.length ? signalList : node("p", "No alerts to show.", "ops-muted")));
  ops.append(second);
}

function saveOperation(title, controls, path, method = "POST", transform = data => data) {
  openEditor(title, controls, async data => {
    await api(path, { method, data: transform(data) });
    await showOperations(currentView);
  });
}

function machineForm(machine) {
  const choices = ["running", "idle", "maintenance", "offline"].map(value => [value, displayStatus(value)]);
  saveOperation(machine ? "Edit machine" : "Add machine", [
    field("code", "Machine code", machine?.code, {required: true, limit: 50}),
    field("name", "Machine name", machine?.name, {required: true, limit: 150}),
    field("status", "Status", machine?.status ?? "idle", {choices}),
  ], machine ? `/operations/machines/${machine.machine_id}` : "/operations/machines", machine ? "PUT" : "POST");
}

function numberField(name, label, value, min = 0) {
  return field(name, label, value, {type: "number", min, step: 1, required: true});
}

function stockForm(item) {
  saveOperation(item ? "Edit stock item" : "Add stock item", [
    field("sku", "SKU", item?.sku, {required: true, limit: 50}),
    field("name", "Item name", item?.name, {required: true, limit: 150}),
    field("unit", "Unit", item?.unit, {required: true, limit: 30}),
    numberField("reorder_point", "Reorder point", item?.reorder_point ?? 0),
  ], item ? `/operations/stock/${item.item_id}` : "/operations/stock", item ? "PUT" : "POST");
}

function adjustStock(item) {
  saveOperation(`Adjust stock · ${item.sku}`, [
    numberField("delta", "Quantity change (positive or negative)", "", -2147483647),
    field("reason", "Reason", "", {required: true, limit: 150}),
  ], `/operations/stock/${item.item_id}/movements`);
}

async function stockHistory(item) {
  const version = openEditor(`Stock history · ${item.sku}`, ["Loading movements…"]);
  try {
    const history = await api(`/operations/stock/${item.item_id}/movements`);
    if (!editor.open || editorVersion !== version) return;
    fields.replaceChildren(table(["Change", "Reason", "Recorded by", "Recorded"], history.map(entry =>
      [entry.delta, entry.reason, entry.username, new Date(entry.recorded_at).toLocaleString()]), "No movements recorded."));
  } catch (error) {
    if (editor.open && editorVersion === version) editorMessage.textContent = error.message;
  }
}

function recordRun(data) {
  const available = products.filter(product => product.is_active);
  if (!data.machines.length || !available.length) {
    openEditor("Record production run", ["Add a machine and an active product first."]);
    return;
  }
  saveOperation("Record production run", [
    field("machine_id", "Machine", "", {choices: data.machines.map(m => [m.machine_id, `${m.code} · ${m.name}`])}),
    field("product_id", "Product", "", {choices: available.map(p => [p.product_id, `${p.part_number} · ${p.product_name}`])}),
    field("job_id", "Work order", "", {choices: [["", "No work order"], ...data.jobs.map(j => [j.job_id, `${j.reference} · ${j.company}`])]}),
    field("production_date", "Production date", dateKey(), {type: "date", required: true}),
    numberField("planned_minutes", "Planned minutes", 480, 1),
    numberField("run_minutes", "Run minutes", 420),
    numberField("ideal_cycle_seconds", "Ideal cycle (seconds per unit)", 60, 1),
    numberField("units_produced", "Units produced", 0),
    numberField("units_rejected", "Units rejected", 0),
  ], "/operations/runs", "POST", data => ({...data, job_id: data.job_id || null}));
}

function recordInspection(runs) {
  const available = runs.filter(run => run.units_produced > 0);
  if (!available.length) {
    openEditor("Record inspection", ["Record a production run with output first."]);
    return;
  }
  saveOperation("Record inspection", [
    field("run_id", "Production run", "", {choices: available.map(r => [r.run_id, `#${r.run_id} · ${r.production_date} · ${r.part_number}`])}),
    numberField("inspected", "Units inspected", 1, 1),
    numberField("rejected", "Units rejected", 0),
    field("notes", "Notes", "", {limit: 500}),
  ], "/operations/quality");
}

function exportRuns(runs) {
  const keys = ["run_id", "production_date", "machine", "part_number", "job_reference", "planned_minutes", "run_minutes", "units_produced", "units_rejected"];
  const quote = value => {
    const text = String(value ?? "");
    const safe = /^[\t\r\n=+@-]/.test(text) ? "'" + text : text;
    return '"' + safe.replaceAll('"', '""') + '"';
  };
  const csv = [keys.join(","), ...runs.map(run => keys.map(key => quote(run[key])).join(","))].join("\r\n");
  const url = URL.createObjectURL(new Blob([csv], {type: "text/csv;charset=utf-8"}));
  const link = node("a");
  link.href = url;
  link.download = "production-runs.csv";
  link.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

async function showOperations(view) {
  currentView = view;
  const version = ++viewVersion;
  for (const button of navButtons) {
    if (button.dataset.view === view) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  }
  elements["sourcing-view"].hidden = view !== "sourcing";
  ops.hidden = view === "sourcing";
  if (ops.hidden) return;
  if (view === "assistant") {
    showManufacturingAssistant();
    return;
  }
  ops.replaceChildren(node("p", "Loading workspace…", "ops-muted"));
  const today = dateKey();
  try {
    const [data, runs, checks] = await Promise.all([
      api(`/operations/snapshot?as_of=${today}`),
      ["production", "quality"].includes(view) ? api("/operations/runs") : [],
      view === "quality" ? api("/operations/quality") : [],
    ]);
    if (version !== viewVersion || !account) return;
    ops.replaceChildren();
    const editButtons = (label, handler) => canEdit() ? [action(label, handler)] : [];
    if (view === "overview") overview(data, today);
    if (view === "orders") {
      heading("Work orders", "Manage customer companies, jobs, and invitations.", [action("Customer jobs", manageWork)]);
      ops.append(panel("All work orders", jobTable(data.jobs, today, canEdit())));
    }
    if (view === "machines") {
      heading("Machines", "Track the current state of shop-floor equipment.", editButtons("Add machine", () => machineForm()));
      const headers = ["Code", "Machine", "Status"];
      if (canEdit()) headers.push("Action");
      ops.append(panel("Equipment", table(headers, data.machines.map(machine => {
        const row = [machine.code, machine.name, badge(displayStatus(machine.status), machine.status === "running" ? "good" : "")];
        if (canEdit()) row.push(action("Edit", () => machineForm(machine)));
        return row;
      }))));
    }
    if (view === "inventory") {
      heading("Inventory", "Review balances and record receipts or usage.", editButtons("Add stock item", () => stockForm()));
      ops.append(panel("Stock items", table(["SKU", "Item", "On hand", "Reorder point", "Actions"], data.stock.map(item => {
        const buttons = node("div", undefined, "ops-actions");
        buttons.append(action("History", () => stockHistory(item)));
        if (canEdit()) buttons.append(action("Adjust", () => adjustStock(item)), action("Edit", () => stockForm(item)));
        const balance = `${item.quantity} ${item.unit}`;
        return [item.sku, item.name, item.quantity <= item.reorder_point ? badge(balance, "warn") : balance, item.reorder_point, buttons];
      }))));
    }
    if (view === "production") {
      heading("Production", "Record output, rejects, and planned versus actual run time.", [
        ...editButtons("Record run", () => recordRun(data)),
        ...(runs.length ? [action("Export CSV", () => exportRuns(runs))] : []),
      ]);
      ops.append(panel("Run history", table(["Date", "Machine", "Part", "Work order", "Output", "Rejected", "Run time", "Review"],
        runs.map(run => [run.production_date, run.machine, run.part_number, run.job_reference,
          run.units_produced, run.units_rejected, `${run.run_minutes} / ${run.planned_minutes} min`,
          run.units_rejected ? action("Investigate rejects", () => investigateRejects(run)) : "—"]))));
    }
    if (view === "quality") {
      heading("Quality control", "Record inspection results against production runs.", editButtons("Record inspection", () => recordInspection(runs)));
      ops.append(panel("Inspection history", table(["Run", "Part", "Inspected", "Rejected", "Notes", "Recorded by"],
        checks.map(check => [check.run_id, check.part_number, check.inspected, check.rejected, check.notes, check.username]))));
    }
  } catch (error) {
    if (version === viewVersion) ops.replaceChildren(node("p", error.message), action("Retry", () => showOperations(view)));
  }
}

for (const button of navButtons) button.addEventListener("click", () => showOperations(button.dataset.view));
