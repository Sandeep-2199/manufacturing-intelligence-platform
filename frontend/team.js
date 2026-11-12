const editor = elements.editor;
const fields = elements["editor-fields"];
const editorMessage = elements["editor-message"];
const saveButton = elements["save-editor"];
let saveAction;
let saving = false;
let editorVersion = 0;

function action(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.addEventListener("click", handler);
  return button;
}

function field(name, label, value = "", options = {}) {
  const wrapper = document.createElement("label");
  const input = document.createElement(options.choices ? "select" : "input");
  if (options.choices) {
    for (const [id, text] of options.choices) input.add(new Option(text, id));
  } else {
    input.type = options.type ?? "text";
    if (options.limit) input.maxLength = options.limit;
    if (options.min !== undefined) input.min = options.min;
    if (options.step !== undefined) input.step = options.step;
    if (options.autocomplete) input.autocomplete = options.autocomplete;
  }
  input.name = name;
  input.required = options.required ?? false;
  if (value !== "" || !options.choices) input.value = value ?? "";
  wrapper.append(label, input);
  return wrapper;
}

function openEditor(title, controls, submit, label = "Save") {
  elements["editor-title"].textContent = title;
  editorMessage.textContent = "";
  fields.replaceChildren(...controls);
  saveAction = submit;
  saveButton.textContent = label;
  saveButton.hidden = !submit;
  if (!editor.open) editor.showModal();
  return ++editorVersion;
}

function showLogin(message = "") {
  account = null;
  activeRequest?.abort();
  if (editor.open) editor.close();
  fields.replaceChildren();
  elements["login-form"].reset();
  elements["login-message"].textContent = message;
  elements.dashboard.hidden = true;
  elements["sign-out"].hidden = true;
  elements["sign-in"].hidden = false;
  elements["login-form"].elements.username.focus();
}

async function showDashboard(user) {
  if (user.role === "customer") {
    window.location.replace("/customer/sign-in");
    return;
  }
  account = user;
  elements["sign-in"].hidden = true;
  elements["sign-out"].hidden = false;
  elements.dashboard.hidden = false;
  elements.identity.textContent = `${user.username} · ${user.role}`;
  elements["dashboard-message"].textContent = "";
  elements["add-product"].hidden = !canEdit();
  elements["manage-vendors"].hidden = !canEdit();
  elements["manage-team"].hidden = user.role !== "admin";
  elements["offer-actions"].hidden = !canEdit();
  elements["product-actions"].hidden = true;
  elements.results.hidden = true;
  elements.products.replaceChildren();
  elements.search.value = "";
  elements.search.disabled = true;
  selectedId = null;
  await Promise.all([loadProducts(), showOperations("overview")]);
}

function editProduct(product) {
  openEditor(product ? "Edit product" : "Add product", [
    field("part_number", "Part number", product?.part_number, { required: true, limit: 50 }),
    field("product_name", "Name", product?.product_name, { required: true, limit: 150 }),
    field("description", "Description", product?.description),
    field("material", "Material", product?.material, { limit: 100 }),
    field("unit", "Unit", product?.unit ?? "piece", { required: true, limit: 30 }),
  ], async data => {
    data.description ||= null;
    data.material ||= null;
    const saved = await api(product ? `/products/${product.product_id}` : "/products/", {
      method: product ? "PUT" : "POST", data,
    });
    await loadProducts(saved.product_id);
  });
}

function selectedProduct() {
  return products.find(product => product.product_id === selectedId);
}

async function manageVendors() {
  const version = openEditor("Manage vendors", ["Loading vendors…"]);
  try {
    const vendors = await api("/vendors/");
    if (!editor.open || editorVersion !== version) return;
    const list = document.createElement("ul");
    list.id = "vendor-list";
    for (const vendor of vendors) {
      const item = document.createElement("li");
      item.append(`${vendor.vendor_name} · ${vendor.vendor_code}`, action("Edit", () => editVendor(vendor)));
      list.append(item);
    }
    fields.replaceChildren(action("Add vendor", () => editVendor()), list);
  } catch (error) {
    if (editor.open && editorVersion === version) editorMessage.textContent = error.message;
  }
}

function editVendor(vendor) {
  openEditor(vendor ? "Edit vendor" : "Add vendor", [
    field("vendor_code", "Vendor code", vendor?.vendor_code, { required: true, limit: 50 }),
    field("vendor_name", "Vendor name", vendor?.vendor_name, { required: true, limit: 150 }),
  ], async data => {
    await api(vendor ? `/vendors/${vendor.vendor_id}` : "/vendors/", {
      method: vendor ? "PUT" : "POST", data,
    });
    if (selectedProduct()) await selectProduct(selectedProduct());
  });
}

function termFields(offer) {
  return [
    field("unit_price", "Unit price (USD)", offer?.unit_price, { type: "number", min: 0, step: "0.01" }),
    field("lead_time_days", "Lead time (days)", offer?.lead_time_days, { type: "number", min: 0, step: "1" }),
  ];
}

function readTerms(data) {
  return {
    unit_price: data.unit_price || null,
    lead_time_days: data.lead_time_days === "" ? null : Number(data.lead_time_days),
  };
}

async function linkVendor() {
  const product = selectedProduct();
  const version = openEditor("Link vendor", ["Loading vendors…"]);
  try {
    const vendors = await api("/vendors/");
    if (!editor.open || editorVersion !== version) return;
    if (!vendors.length) {
      fields.replaceChildren("Add a vendor first.", action("Add vendor", () => editVendor()));
      return;
    }
    const choices = vendors.map(vendor => [vendor.vendor_id, `${vendor.vendor_name} · ${vendor.vendor_code}`]);
    openEditor("Link vendor", [field("vendor_id", "Vendor", "", { choices, required: true }), ...termFields()], async data => {
      await api(`/vendors/${data.vendor_id}/products/${product.product_id}`, {
        method: "POST", data: readTerms(data),
      });
      await selectProduct(product);
    }, "Link vendor");
  } catch (error) {
    if (editor.open && editorVersion === version) editorMessage.textContent = error.message;
  }
}

function editOffer(offer) {
  const product = selectedProduct();
  openEditor(`Edit terms for ${offer.vendor.vendor_name}`, termFields(offer), async data => {
    await api(`/vendors/${offer.vendor.vendor_id}/products/${product.product_id}`, {
      method: "PUT", data: readTerms(data),
    });
    await selectProduct(product);
  });
}

function removeOffer(offer) {
  const product = selectedProduct();
  openEditor("Unlink vendor", [`Remove ${offer.vendor.vendor_name} and its terms from ${product.product_name}?`], async () => {
    await api(`/vendors/${offer.vendor.vendor_id}/products/${product.product_id}`, { method: "DELETE" });
    await selectProduct(product);
  }, "Unlink vendor");
}

async function manageTeam() {
  const version = openEditor("Team accounts", ["Loading accounts…"]);
  try {
    const users = await api("/team/users");
    if (!editor.open || editorVersion !== version) return;
    const list = document.createElement("ul");
    list.id = "team-list";
    for (const user of users) {
      const item = document.createElement("li");
      item.textContent = `${user.username} · ${user.role}${user.is_active ? "" : " · disabled"}`;
      list.append(item);
    }
    fields.replaceChildren(action("Add account", addAccount), list);
  } catch (error) {
    if (editor.open && editorVersion === version) editorMessage.textContent = error.message;
  }
}

function addAccount() {
  openEditor("Add team account", [
    field("username", "Username", "", { required: true, limit: 64 }),
    field("password", "Password (8–128 characters)", "", {
      type: "password", autocomplete: "new-password", required: true, limit: 128,
    }),
    field("role", "Role", "viewer", { choices: [["viewer", "Viewer"], ["editor", "Editor"], ["admin", "Administrator"]] }),
  ], data => api("/team/users", { method: "POST", data }), "Create account");
}

elements["login-form"].addEventListener("submit", async event => {
  event.preventDefault();
  const button = event.target.querySelector("button");
  button.disabled = true;
  elements["login-message"].textContent = "";
  try {
    const user = await api("/auth/login", { method: "POST", data: Object.fromEntries(new FormData(event.target)) });
    event.target.reset();
    await showDashboard(user);
  } catch (error) {
    elements["login-message"].textContent = error.message;
  } finally {
    button.disabled = false;
  }
});

elements["forgot-password"].addEventListener("click", () => {
  openEditor("Request a password reset", [
    field("username", "Username", elements["login-form"].elements.username.value, {
      required: true, limit: 64, autocomplete: "username",
    }),
  ], async data => {
    const result = await api("/auth/password-reset/request", { method: "POST", data });
    editor.close();
    elements["login-message"].textContent = result.message;
  }, "Send reset link");
});

function openPasswordReset(token) {
  openEditor("Choose a new password", [
    field("password", "New password (8–128 characters)", "", {
      type: "password", required: true, limit: 128, autocomplete: "new-password",
    }),
    field("confirm", "Confirm new password", "", {
      type: "password", required: true, limit: 128, autocomplete: "new-password",
    }),
  ], async ({ password, confirm }) => {
    if (password.length < 8) throw new Error("Enter at least 8 characters.");
    if (password !== confirm) throw new Error("Passwords differ.");
    await api("/auth/password-reset/confirm", { method: "POST", data: { token, password } });
    showLogin("Password reset. Sign in with your new password.");
  }, "Reset password");
}

elements["sign-out"].addEventListener("click", async () => {
  try {
    await api("/auth/logout", { method: "POST" });
    showLogin();
  } catch (error) {
    elements["dashboard-message"].textContent = error.message;
  }
});

elements["editor-form"].addEventListener("submit", async event => {
  event.preventDefault();
  if (!saveAction || saving) return;
  saving = true;
  saveButton.disabled = true;
  elements["close-editor"].disabled = true;
  editorMessage.textContent = "";
  try {
    const close = await saveAction(Object.fromEntries(new FormData(event.target)));
    if (close === false) return;
    editor.close();
    if (account) elements["dashboard-message"].textContent = "Changes saved.";
  } catch (error) {
    editorMessage.textContent = error.message;
  } finally {
    saving = false;
    saveButton.disabled = false;
    elements["close-editor"].disabled = false;
  }
});

editor.addEventListener("cancel", event => {
  if (saving) event.preventDefault();
});
editor.addEventListener("close", () => {
  if (!editor.open) fields.replaceChildren();
});
elements["close-editor"].addEventListener("click", () => editor.close());
elements["add-product"].addEventListener("click", () => editProduct());
elements["edit-product"].addEventListener("click", () => editProduct(selectedProduct()));
elements["manage-vendors"].addEventListener("click", manageVendors);
elements["manage-team"].addEventListener("click", manageTeam);
elements["link-vendor"].addEventListener("click", linkVendor);
elements["deactivate-product"].addEventListener("click", () => {
  const product = selectedProduct();
  openEditor("Deactivate product", [`Mark ${product.product_name} inactive?`], async () => {
    await api(`/products/${product.product_id}`, { method: "DELETE" });
    await loadProducts(product.product_id);
  }, "Deactivate");
});

const resetLink = window.location.hash.match(/^#reset=([A-Za-z0-9_-]{43})$/);
if (resetLink) history.replaceState(null, "", window.location.pathname + window.location.search);

api("/auth/me").then(showDashboard).catch(error => {
  showLogin(error.message === "Sign in to continue" ? "" : error.message);
}).finally(() => {
  if (resetLink) openPasswordReset(resetLink[1]);
});
