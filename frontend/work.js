const jobStatuses = [
  ["received", "Received"],
  ["in_progress", "In progress"],
  ["ready", "Ready"],
  ["delivered", "Delivered"],
  ["cancelled", "Cancelled"],
];

function dialogList(rows) {
  const list = document.createElement("ul");
  list.className = "work-list";
  for (const row of rows) {
    const item = document.createElement("li");
    item.append(...row);
    list.append(item);
  }
  return list;
}

async function manageWork() {
  const version = openEditor("Customer companies", ["Loading companies…"]);
  try {
    const companies = await api("/work/companies");
    if (!editor.open || editorVersion !== version) return;
    const rows = companies.map(company => [action(company.name, () => companyWork(company))]);
    const controls = canEdit() ? [action("Add company", addCompany)] : [];
    controls.push(rows.length ? dialogList(rows) : " No customer companies yet.");
    fields.replaceChildren(...controls);
  } catch (error) {
    if (editor.open && editorVersion === version) editorMessage.textContent = error.message;
  }
}

function addCompany() {
  openEditor("Add customer company", [
    field("name", "Company name", "", { required: true, limit: 150 }),
  ], async data => {
    const company = await api("/work/companies", { method: "POST", data });
    await companyWork(company);
    return false;
  });
}

async function companyWork(company) {
  const version = openEditor(company.name, ["Loading jobs…"]);
  try {
    const jobs = await api(`/work/companies/${company.company_id}/jobs`);
    if (!editor.open || editorVersion !== version) return;
    const toolbar = document.createElement("div");
    toolbar.className = "toolbar";
    toolbar.append(action("All companies", manageWork));
    if (canEdit()) toolbar.append(action("Add job", () => editJob(company)));
    if (account.role === "admin") toolbar.append(action("Create invitation", () => inviteCustomer(company)));
    const rows = jobs.map(job => {
      const status = jobStatuses.find(([value]) => value === job.status)[1];
      const info = document.createElement("span");
      info.textContent = `${job.reference} · ${job.title} · ${status}`;
      if (job.expected_delivery) info.textContent += ` · Due ${job.expected_delivery}`;
      return canEdit() ? [info, action("Edit", () => editJob(company, job))] : [info];
    });
    fields.replaceChildren(toolbar, rows.length ? dialogList(rows) : "No jobs yet.");
  } catch (error) {
    if (editor.open && editorVersion === version) editorMessage.textContent = error.message;
  }
}

function editJob(company, job) {
  openEditor(job ? "Edit customer job" : "Add customer job", [
    field("reference", "Job reference", job?.reference, { required: true, limit: 64 }),
    field("title", "Job title", job?.title, { required: true, limit: 150 }),
    field("status", "Status", job?.status ?? "received", { choices: jobStatuses }),
    field("expected_delivery", "Expected delivery", job?.expected_delivery, { type: "date" }),
  ], async data => {
    data.expected_delivery ||= null;
    const path = `/work/companies/${company.company_id}/jobs`;
    await api(job ? `${path}/${job.job_id}` : path, { method: job ? "PUT" : "POST", data });
    if (currentView === "orders") await showOperations("orders");
    await companyWork(company);
    return false;
  });
}

function inviteCustomer(company) {
  openEditor(`Invite a contact at ${company.name}`, [
    field("username", "Choose a username", "", { required: true, limit: 64, autocomplete: "off" }),
  ], async data => {
    const invite = await api(`/work/companies/${company.company_id}/invitations`, { method: "POST", data });
    const url = new URL("/customer/sign-in", window.location.origin);
    url.hash = new URLSearchParams({ invite: invite.token }).toString();
    const linkField = field("invitation", "Invitation link", url.href);
    const input = linkField.querySelector("input");
    input.readOnly = true;
    const copy = action("Copy invitation", async () => {
      try {
        await navigator.clipboard.writeText(input.value);
        copy.textContent = "Copied";
      } catch {
        input.select();
        editorMessage.textContent = "Copy the selected link.";
      }
    });
    const note = document.createElement("p");
    note.textContent = "Send this link to the intended contact. It expires in 24 hours and can be used once.";
    openEditor("Share the customer invitation", [note, linkField, copy]);
    input.focus();
    input.select();
    return false;
  }, "Create invitation");
}
