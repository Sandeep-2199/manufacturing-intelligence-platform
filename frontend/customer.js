const loginForm = document.querySelector("#customer-login");
const inviteForm = document.querySelector("#customer-invite");
const jobsPanel = document.querySelector("#my-jobs");
const jobRows = document.querySelector("#job-rows");
const message = document.querySelector("#customer-message");
const signOut = document.querySelector("#sign-out");
let jobLoad = 0;
let customerJobs = [];
let portalUser = null;
const jobSearch = document.querySelector("#job-search");
const jobFilter = document.querySelector("#job-filter");
let invitation = new URLSearchParams(window.location.hash.slice(1)).get("invite");
if (invitation) history.replaceState(null, "", window.location.pathname);

async function request(path, method = "GET", data) {
  const response = await fetch(path, {
    method,
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
  });
  if (response.status === 204) return;
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(Array.isArray(payload.detail)
      ? payload.detail.map(item => item.msg).join(" ")
      : payload.detail);
    error.status = response.status;
    throw error;
  }
  return payload;
}

function showForm(form, notice = "") {
  loginForm.hidden = form !== loginForm;
  inviteForm.hidden = form !== inviteForm;
  jobsPanel.hidden = true;
  jobRows.replaceChildren();
  message.textContent = notice;
  if (form) form.querySelector("input").focus();
}

async function loadJobs(user) {
  const load = ++jobLoad;
  signOut.hidden = false;
  if (user.role !== "customer") {
    showForm(null, "You are signed in to the team workspace. Sign out to use a customer account.");
    return;
  }
  showForm(null, "Loading jobs…");
  const [company, jobs] = await Promise.all([request("/portal/company"), request("/portal/jobs")]);
  if (load !== jobLoad) return;
  document.querySelector("#company-name").textContent = company.name;
  portalUser = user;
  customerJobs = jobs;
  const summary = document.querySelector("#job-summary");
  summary.replaceChildren();
  for (const [label, count] of [
    ["Total jobs", jobs.length],
    ["In progress", jobs.filter(job => job.status === "in_progress").length],
    ["Ready", jobs.filter(job => job.status === "ready").length],
    ["Delivered", jobs.filter(job => job.status === "delivered").length],
  ]) {
    const item = document.createElement("div");
    const title = document.createElement("span");
    title.textContent = label;
    const value = document.createElement("strong");
    value.textContent = count;
    item.append(title, value);
    summary.append(item);
  }
  renderJobs();
  jobsPanel.hidden = false;
  message.textContent = "";
}

function renderJobs() {
  const query = jobSearch.value.trim().toLowerCase();
  const visible = customerJobs.filter(job => (!jobFilter.value || job.status === jobFilter.value)
    && (job.reference + " " + job.title).toLowerCase().includes(query));
  jobRows.replaceChildren();
  for (const job of visible) {
    const row = jobRows.insertRow();
    row.insertCell().textContent = job.reference;
    row.insertCell().textContent = job.title;
    const status = document.createElement("span");
    status.className = "customer-status " + job.status;
    status.textContent = job.status.replaceAll("_", " ");
    row.insertCell().append(status);
    row.insertCell().textContent = job.expected_delivery ?? "Pending";
  }
  const empty = document.querySelector("#no-jobs");
  empty.hidden = visible.length > 0;
  empty.textContent = customerJobs.length ? "No jobs match these filters." : "No jobs have been assigned to your company yet.";
}

jobSearch.addEventListener("input", renderJobs);
jobFilter.addEventListener("change", renderJobs);
document.querySelector("#refresh-jobs").addEventListener("click", () => {
  if (portalUser) loadJobs(portalUser).catch(error => {
    if (error.status === 401) {
      signOut.hidden = true;
      showForm(loginForm, "Sign in to refresh your jobs.");
    } else {
      jobsPanel.hidden = false;
      message.textContent = error.message;
    }
  });
});

function handleForm(form, onSubmit) {
  form.addEventListener("submit", async event => {
    event.preventDefault();
    const button = form.querySelector("button");
    button.disabled = true;
    message.textContent = "";
    try {
      await onSubmit(Object.fromEntries(new FormData(form)));
    } catch (error) {
      message.textContent = error.message || "The request failed. Try again.";
    } finally {
      button.disabled = false;
    }
  });
}

handleForm(inviteForm, async ({ password, confirmation }) => {
  if (password !== confirmation) throw new Error("The passwords must match.");
  const user = await request("/portal/invitations/accept", "POST", { token: invitation, password });
  invitation = null;
  inviteForm.reset();
  showForm(loginForm, "Account activated. Sign in with the password you chose.");
  loginForm.elements.username.value = user.username;
  loginForm.elements.password.focus();
});

handleForm(loginForm, async data => {
  const user = await request("/auth/login", "POST", data);
  loginForm.reset();
  await loadJobs(user);
});

signOut.addEventListener("click", async () => {
  signOut.disabled = true;
  try {
    await request("/auth/logout", "POST");
    jobLoad++;
    portalUser = null;
    customerJobs = [];
    jobSearch.value = "";
    jobFilter.value = "";
    signOut.hidden = true;
    showForm(loginForm);
  } catch (error) {
    message.textContent = error.message;
  } finally {
    signOut.disabled = false;
  }
});

if (invitation) {
  showForm(inviteForm);
} else {
  request("/auth/me").then(loadJobs).catch(error => {
    showForm(loginForm, error.status === 401 ? "" : error.message);
  });
}
