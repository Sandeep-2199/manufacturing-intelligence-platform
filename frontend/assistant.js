function showManufacturingAssistant() {
  ops.replaceChildren();
  const buttons = account.role === "admin" ? [action("Manage procedures", manageProcedures)] : [];
  heading("Ask Manufacturing", "Search approved work instructions, such as inspection checklists, or ask about recorded production and current inventory.", buttons);
  const form = node("form", undefined, "assistant-form");
  const question = node("textarea");
  question.name = "question";
  question.required = true;
  question.minLength = 3;
  question.maxLength = 1200;
  question.rows = 4;
  const label = node("label", "Question");
  label.append(question);
  const scope = field("scope", "Search", "auto", {choices: [
    ["auto", "Auto-select"], ["inventory", "Current inventory"], ["procedures", "Work instructions"], ["production", "Production records"], ["both", "Work instructions and production"],
  ]});
  const dates = node("div", undefined, "toolbar");
  const start = new Date();
  start.setDate(start.getDate() - 6);
  dates.append(field("start", "From", dateKey(start), {type: "date", required: true}),
    field("end", "Through", dateKey(), {type: "date", required: true}));
  dates.hidden = false;
  scope.querySelector("select").addEventListener("change", event => {
    dates.hidden = ["procedures", "inventory"].includes(event.target.value);
  });
  const submit = node("button", "Ask", "primary");
  const status = node("p", undefined, "ops-muted");
  status.setAttribute("role", "status");
  const output = node("div");
  form.append(label, scope, dates, submit, status);
  ops.append(panel("Question and sources", form, output));

  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    output.replaceChildren();
    status.textContent = "Retrieving evidence…";
    try {
      const result = await api("/assistant/ask", {method: "POST", data: Object.fromEntries(new FormData(form))});
      status.textContent = result.message ?? "";
      if (result.answer) output.append(node("p", result.answer, "assistant-answer"));
      if (result.inventory?.length) {
        output.append(table(["SKU", "Item", "On hand", "Reorder point"],
          result.inventory.map(item => [item.sku, item.name, `${item.quantity} ${item.unit}`, item.reorder_point])));
        if (result.inventory_truncated) output.append(node("p", "Showing the first 50 items by SKU. Open Inventory for the full list.", "ops-muted"));
      } else if (result.scope === "inventory" && !result.answer) {
        output.append(node("p", "No inventory items are recorded.", "assistant-answer"));
      }
      for (const source of result.sources) {
        const details = node("details", undefined, "assistant-source");
        details.append(node("summary", `[${source.id}] ${source.title}`), node("pre", source.content));
        output.append(details);
      }
    } catch (error) {
      status.textContent = error.message;
    } finally {
      submit.disabled = false;
    }
  });
}

async function manageProcedures() {
  const version = openEditor("Manage procedures", ["Loading procedures…"]);
  try {
    const documents = await api("/assistant/documents");
    if (!editor.open || version !== editorVersion) return;
    fields.replaceChildren(action("Add procedure", addProcedure), dialogList(documents.map(doc => [
      doc.title, " ", action("Remove", () => openEditor("Remove procedure", [`Remove ${doc.title} from search?`],
        () => api(`/assistant/documents/${doc.document_id}`, {method: "DELETE"}), "Remove"),
      ),
    ])));
  } catch (error) {
    if (editor.open && version === editorVersion) editorMessage.textContent = error.message;
  }
}

function addProcedure() {
  const content = node("textarea");
  content.name = "content";
  content.required = true;
  content.minLength = 10;
  content.maxLength = 60000;
  content.rows = 9;
  const label = node("label", "Procedure text");
  label.append(content);
  openEditor("Add procedure", [field("title", "Title", "", {required: true, limit: 150}), label],
    data => api("/assistant/documents", {method: "POST", data}), "Add procedure");
}

async function investigateRejects(run) {
  const version = openEditor(`Reject investigation · Run #${run.run_id}`, ["Gathering run history and work instructions…"]);
  try {
    const result = await api(`/assistant/runs/${run.run_id}/investigate`, {method: "POST"});
    if (!editor.open || version !== editorVersion) return;
    const { findings } = result;
    const current = findings.reject_rate_pct === null ? "unavailable" : `${findings.reject_rate_pct}%`;
    const baseline = findings.prior_reject_rate_pct === null
      ? "No comparable prior runs with output."
      : `${findings.prior_reject_rate_pct}% across ${findings.prior_runs} prior runs for this machine and part.`;
    const content = [
      node("p", `${findings.rejected} rejected of ${findings.produced} produced · Reject rate ${current}`, "assistant-answer"),
      node("p", baseline, "ops-muted"),
    ];
    if (!findings.procedure_matches) content.push(node("p", "No matching work instructions found.", "ops-muted"));
    if (result.draft) {
      content.push(node("h3", "Supervisor handoff draft"), node("p", result.draft, "assistant-answer"));
    }
    if (result.message) content.push(node("p", result.message, "ops-muted"));
    for (const source of result.sources) {
      const details = node("details", undefined, "assistant-source");
      details.append(node("summary", `[${source.id}] ${source.title}`), node("pre", source.content));
      content.push(details);
    }
    fields.replaceChildren(...content);
  } catch (error) {
    if (editor.open && version === editorVersion) editorMessage.textContent = error.message;
  }
}
