const elements = Object.fromEntries(
  [...document.querySelectorAll("[id]")].map(element => [element.id, element])
);
const comparison = document.querySelector(".comparison");
const money = new Intl.NumberFormat("en-US", { style: "currency", currency: "USD" });
let products = [];
let selectedId = null;
let offers = [];
let activeRequest;
let account = null;

async function api(path, { method = "GET", data, signal } = {}) {
  const response = await fetch(path, {
    method,
    headers: data === undefined ? {} : { "Content-Type": "application/json" },
    body: data === undefined ? undefined : JSON.stringify(data),
    signal,
  });
  if (response.status === 204) return;
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    if (response.status === 401 && account) showLogin("Your session has ended. Sign in again.");
    const detail = Array.isArray(payload.detail)
      ? payload.detail.map(error => `${error.loc.at(-1)}: ${error.msg}`).join(" ")
      : payload.detail;
    throw new Error(detail || `Request failed (HTTP ${response.status}).`);
  }
  return payload;
}

function canEdit() {
  return ["admin", "editor"].includes(account?.role);
}

function renderProducts() {
  const query = elements.search.value.trim().toLowerCase();
  const visible = products.filter(product =>
    [product.part_number, product.product_name].some(value => value.toLowerCase().includes(query))
  );
  elements.products.replaceChildren();
  for (const product of visible) {
    const item = document.createElement("li");
    const button = document.createElement("button");
    const code = document.createElement("span");
    code.textContent = product.part_number;
    button.type = "button";
    button.dataset.productId = product.product_id;
    button.setAttribute("aria-pressed", String(product.product_id === selectedId));
    button.append(code, product.product_name);
    button.addEventListener("click", () => {
      selectProduct(product);
    });
    item.append(button);
    elements.products.append(item);
  }

  const message = elements["catalog-message"];
  message.hidden = visible.length > 0;
  message.textContent = products.length ? "No products match your search." : "No products yet.";
}

function renderOffers() {
  const field = elements.sort.value;
  const valueForSort = offer => offer[field] === null ? Infinity : Number(offer[field]);
  const sorted = [...offers].sort((first, second) =>
    (valueForSort(first) - valueForSort(second)) ||
    first.vendor.vendor_code.localeCompare(second.vendor.vendor_code)
  );
  elements.suppliers.replaceChildren();
  for (const offer of sorted) {
    const row = elements.suppliers.insertRow();
    const supplier = row.insertCell();
    const code = document.createElement("span");
    code.textContent = offer.vendor.vendor_code;
    supplier.append(offer.vendor.vendor_name, code);
    row.insertCell().textContent = offer.unit_price === null ? "—" : money.format(offer.unit_price);
    row.insertCell().textContent = offer.lead_time_days === null ? "—" : days(offer.lead_time_days);
    if (canEdit()) {
      const cell = row.insertCell();
      cell.append(action("Edit terms", () => editOffer(offer)), action("Unlink", () => removeOffer(offer)));
    }
  }

  elements["supplier-count"].textContent = offers.length;
  const prices = offers.flatMap(offer => offer.unit_price === null ? [] : [Number(offer.unit_price)]);
  const leadTimes = offers.flatMap(offer => offer.lead_time_days === null ? [] : [offer.lead_time_days]);
  elements["lowest-price"].textContent = prices.length ? money.format(Math.min(...prices)) : "—";
  elements["shortest-lead"].textContent = leadTimes.length ? days(Math.min(...leadTimes)) : "—";
}

function days(value) {
  return `${value} ${value === 1 ? "day" : "days"}`;
}

async function selectProduct(product) {
  selectedId = product.product_id;
  for (const button of elements.products.querySelectorAll("button")) {
    button.setAttribute("aria-pressed", String(button.dataset.productId === String(selectedId)));
  }

  activeRequest?.abort();
  const request = new AbortController();
  activeRequest = request;
  const message = elements["comparison-message"];
  const status = elements["product-status"];

  elements["product-name"].textContent = product.product_name;
  elements["part-number"].textContent = product.part_number;
  elements["part-number"].hidden = false;
  elements["product-meta"].textContent = [product.material, product.unit].filter(Boolean).join(" · ");
  elements["product-meta"].hidden = !elements["product-meta"].textContent;
  status.textContent = product.is_active ? "Active" : "Inactive";
  status.classList.toggle("inactive", !product.is_active);
  status.hidden = false;
  elements["product-actions"].hidden = !canEdit();
  elements["deactivate-product"].hidden = !product.is_active;
  elements.results.hidden = true;
  message.hidden = false;
  message.textContent = "Loading supplier offers…";
  comparison.setAttribute("aria-busy", "true");

  try {
    const data = await api(`/products/${selectedId}/suppliers`, { signal: request.signal });
    if (activeRequest !== request) return;
    offers = data.suppliers;
    if (offers.length) {
      renderOffers();
      elements.results.hidden = false;
      message.hidden = true;
    } else {
      message.textContent = "No suppliers are linked to this product.";
    }
  } catch (error) {
    if (activeRequest !== request) return;
    message.textContent = `Could not load supplier offers. Select the product to retry. ${error.message}`;
  } finally {
    if (activeRequest === request) comparison.setAttribute("aria-busy", "false");
  }
}

async function loadProducts(preferredId = selectedId) {
  try {
    products = await api("/products/");
    products.sort((first, second) => first.part_number.localeCompare(second.part_number));
    elements.search.disabled = false;
    renderProducts();
    const initial = products.find(product => product.product_id === preferredId)
      ?? products.find(product => product.part_number === "DEMO-BRK-100")
      ?? products[0];
    if (initial) {
      await selectProduct(initial);
    } else {
      elements["comparison-message"].textContent = "Add a product to start comparing suppliers.";
      comparison.setAttribute("aria-busy", "false");
    }
  } catch (error) {
    elements["catalog-message"].textContent = `Could not load products. ${error.message}`;
    elements["comparison-message"].textContent = "Refresh the page to try again.";
    comparison.setAttribute("aria-busy", "false");
  }
}

elements.search.addEventListener("input", renderProducts);
elements.sort.addEventListener("change", renderOffers);
