const params = new URLSearchParams(location.search);
const DEV_ID = params.get("dev");

const tgApi = () => (window.Telegram && window.Telegram.WebApp) || null;

function getInitData() {
  const tg = tgApi();
  if (tg && tg.initData) return tg.initData;
  try {
    const hash = new URLSearchParams(location.hash.slice(1));
    const fromHash = hash.get("tgWebAppData");
    if (fromHash) return fromHash;
    return new URLSearchParams(location.search).get("tgWebAppData") || "";
  } catch (e) {
    return "";
  }
}

function applyTelegramTheme() {
  const tg = tgApi();
  if (!tg) return;
  try {
    tg.ready();
    tg.expand();
    tg.setHeaderColor("#07091a");
    tg.setBackgroundColor("#07091a");
  } catch (e) {}
}

(function loadTelegramSdk() {
  const script = document.createElement("script");
  script.src = "https://telegram.org/js/telegram-web-app.js";
  script.async = true;
  script.onload = () => {
    applyTelegramTheme();
    const tg = tgApi();
    try {
      tg.onEvent("activated", () => {
        if (state.user) refreshState().catch(() => {});
      });
    } catch (e) {}
  };
  document.head.appendChild(script);
})();

const state = {
  user: null,
  botUsername: "",
  categories: [],
  products: [],
  cart: [],
  orders: [],
  ordersCount: 0,
  spent: 0,
  promo: null,
  promoDiscount: 0,
  starsRate: 1,
  activeCategory: "all",
  sheetProductId: null,
};

let paying = false;
let cartBusy = false;
let backdropTimer;

const $ = (id) => document.getElementById(id);

const esc = (value) =>
  String(value ?? "").replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c])
  );

const fmt = (value) => Number(value).toLocaleString("ru-RU") + " ₽";
const fmtShort = (value) =>
  value >= 1000 ? (value / 1000).toFixed(1).replace(".0", "") + "к ₽" : value + " ₽";

const STATUS = {
  pending: ["ожидает оплаты", "pending"],
  paid: ["оплачен", "paid"],
  delivered: ["выполнен", "delivered"],
  cancelled: ["отменён", "cancelled"],
};

function haptic(style = "light") {
  const tg = tgApi();
  try { if (tg && tg.HapticFeedback) tg.HapticFeedback.impactOccurred(style); } catch (e) {}
}

function notify(type) {
  const tg = tgApi();
  try {
    if (tg && tg.HapticFeedback) {
      tg.HapticFeedback.notificationOccurred(type === "error" ? "error" : "success");
    }
  } catch (e) {}
}

let toastTimer;
function toast(text, isError = false) {
  const el = $("toast");
  el.textContent = text;
  el.classList.toggle("error", isError);
  el.classList.add("show");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 2600);
}

async function api(path, options = {}) {
  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
  const initData = getInitData();
  if (initData) headers["X-Init-Data"] = initData;
  else if (DEV_ID) headers["X-Dev-Id"] = DEV_ID;

  const response = await fetch(path, Object.assign({}, options, { headers }));
  let data = {};
  try { data = await response.json(); } catch (e) {}
  if (!response.ok) {
    const fallback =
      response.status === 401
        ? "Не удалось войти через Telegram. Открой приложение заново"
        : `Ошибка сервера (${response.status})`;
    throw new Error(data.error || fallback);
  }
  return data;
}


function renderSkeletons() {
  $("productGrid").innerHTML = Array.from({ length: 6 })
    .map(
      () => `
      <div class="sk-card">
        <div class="sk-thumb skeleton"></div>
        <div class="sk-line skeleton"></div>
        <div class="sk-line short skeleton"></div>
      </div>`
    )
    .join("");
}

function renderChips() {
  const chips = [`
    <button class="chip is-active" data-cat="all">Все</button>`];
  for (const category of state.categories) {
    chips.push(
      `<button class="chip" data-cat="${category.id}">${esc(category.emoji)} ${esc(category.title)}</button>`
    );
  }
  $("categoryChips").innerHTML = chips.join("");
}

function visibleProducts() {
  if (state.activeCategory === "all") return state.products;
  return state.products.filter((p) => String(p.category_id) === String(state.activeCategory));
}

function renderCatalog() {
  const products = visibleProducts();
  if (!products.length) {
    $("productGrid").innerHTML =
      `<div class="empty" style="grid-column:1/-1"><div class="big">🌌</div><p>Пока пусто</p></div>`;
    return;
  }
  $("productGrid").innerHTML = products
    .map(
      (p) => `
      <article class="product" data-id="${p.id}">
        <div class="thumb">
          ${p.photo ? `<img src="${esc(p.photo)}" alt="" loading="lazy">` : `<div class="thumb-placeholder">🎁</div>`}
        </div>
        <div class="p-title">${esc(p.title)}</div>
        <div class="p-foot">
          <span class="p-price">${fmt(p.price)}</span>
          <button class="add-btn" data-add="${p.id}" aria-label="В корзину">+</button>
        </div>
      </article>`
    )
    .join("");
}

const cartSubtotal = () => state.cart.reduce((sum, item) => sum + item.price * item.qty, 0);
const cartCount = () => state.cart.reduce((sum, item) => sum + item.qty, 0);

function cartDiscount() {
  return Math.floor((cartSubtotal() * state.promoDiscount) / 100);
}

function cartTotal() {
  return cartSubtotal() - cartDiscount();
}

function renderCart() {
  const list = $("cartList");
  if (!state.cart.length) {
    list.innerHTML =
      `<div class="empty"><div class="big">🛒</div><p>Корзина пуста</p></div>`;
    $("cartTotals").hidden = true;
    $("promoRow").hidden = true;
    $("clearCart").hidden = true;
    $("checkoutBtn").disabled = true;
    return;
  }

  $("promoRow").hidden = false;
  $("clearCart").hidden = false;
  list.innerHTML = state.cart
    .map(
      (item) => `
      <div class="cart-item">
        <div class="ci-thumb">${item.photo ? `<img src="${esc(item.photo)}" alt="">` : ""}</div>
        <div class="ci-info">
          <div class="ci-title">${esc(item.title)}</div>
          <div class="ci-price">${fmt(item.price)}</div>
        </div>
        <div class="stepper">
          <button data-step="-1" data-item="${item.item_id}" aria-label="Меньше">−</button>
          <span class="qty">${item.qty}</span>
          <button data-step="1" data-item="${item.item_id}" aria-label="Больше">+</button>
        </div>
      </div>`
    )
    .join("");

  $("checkoutBtn").disabled = false;
  renderTotals();
}

function renderTotals() {
  const subtotal = cartSubtotal();
  const discount = cartDiscount();
  const total = cartTotal();
  const el = $("cartTotals");
  el.hidden = false;
  el.innerHTML = `
    <div class="row"><span>Товары</span><b>${fmt(subtotal)}</b></div>
    ${discount ? `<div class="row discount"><span>Промокод ${esc(state.promo)}</span><b>−${fmt(discount)}</b></div>` : ""}
    <div class="row total"><span>Итого</span><b>${fmt(total)}</b></div>`;
}

function updateBadge() {
  const badge = $("cartBadge");
  const count = cartCount();
  badge.hidden = count === 0;
  badge.textContent = count;
}

function renderProfile() {
  const user = state.user || {};

  $("bonusBig").textContent = Number(user.bonus || 0).toLocaleString("ru-RU");
  $("statOrders").textContent = state.ordersCount;
  $("statInvited").textContent = user.invited || 0;
  $("statSpent").textContent = fmtShort(state.spent || 0);

  const list = $("ordersList");
  if (!state.orders.length) {
    list.innerHTML = `<div class="empty"><div class="big">📦</div><p>Заказов пока нет</p></div>`;
  } else {
    list.innerHTML = state.orders
      .map((order) => {
        const [label, cls] = STATUS[order.status] || [order.status, "pending"];
        return `
        <div class="order-row">
          <div>
            <div class="o-id">Заказ #${order.id}</div>
            <div class="o-date">${esc(order.date)}</div>
          </div>
          <div style="text-align:right">
            <div class="o-total">${fmt(order.total)}</div>
            <div class="pill ${cls}" style="margin-top:4px">${label}</div>
          </div>
        </div>`;
      })
      .join("");
  }

  const link = state.botUsername
    ? `https://t.me/${state.botUsername}?start=ref_${user.id}`
    : "—";
  $("refLink").textContent = link;
  $("copyRef").dataset.link = link;
}

function applyState(data) {
  state.user = data.user;
  state.botUsername = data.bot_username || "";
  state.starsRate = data.stars_rate || 1;
  state.cart = data.cart;
  state.orders = data.orders;
  state.ordersCount = data.orders_count ?? data.orders.length;
  state.spent = data.spent || 0;

  if (data.cashback_percent != null) {
    $("cashbackHint").textContent = `Кешбэк ${data.cashback_percent}% с каждой покупки`;
  }
  if (data.referral_bonus_inviter != null) {
    $("refBonusInviter").textContent = `+${data.referral_bonus_inviter} бонусов`;
  }
  if (data.referral_bonus_newbie != null) {
    $("refBonusNewbie").textContent = `+${data.referral_bonus_newbie}`;
  }

  $("userName").textContent = state.user.first_name || "друг";
  $("bonusValue").textContent = Number(state.user.bonus || 0).toLocaleString("ru-RU");

  renderCart();
  renderProfile();
  updateBadge();
}


async function refreshState() {
  const data = await api("/api/state");
  applyState(data);
}

async function addToCart(productId, buttonEl, fromSheet = false) {
  haptic();
  try {
    const data = await api("/api/cart", {
      method: "POST",
      body: JSON.stringify({ action: "add", product_id: productId }),
    });
    state.cart = data.items;
    renderCart();
    updateBadge();
    if (buttonEl && fromSheet) {
      buttonEl.classList.add("added");
      buttonEl.textContent = "✓ Добавлено";
      setTimeout(() => {
        buttonEl.classList.remove("added");
        buttonEl.textContent = "В корзину";
      }, 1200);
    } else {
      toast("Добавлено в корзину 🛒");
    }
  } catch (error) {
    notify("error");
    toast(error.message, true);
  }
}

async function setQty(itemId, qty) {
  if (cartBusy) return;
  cartBusy = true;
  try {
    const data = await api("/api/cart", {
      method: "POST",
      body: JSON.stringify({ action: "set", item_id: itemId, qty }),
    });
    state.cart = data.items;
    renderCart();
    updateBadge();
  } catch (error) {
    notify("error");
    toast(error.message, true);
  } finally {
    cartBusy = false;
  }
}

async function clearCart() {
  if (cartBusy || !state.cart.length) return;
  cartBusy = true;
  try {
    const data = await api("/api/cart", {
      method: "POST",
      body: JSON.stringify({ action: "clear" }),
    });
    state.cart = data.items;
    state.promo = null;
    state.promoDiscount = 0;
    $("promoInput").value = "";
    renderCart();
    updateBadge();
    toast("Корзина очищена 🧹");
  } catch (error) {
    notify("error");
    toast(error.message, true);
  } finally {
    cartBusy = false;
  }
}

async function applyPromo() {
  const input = $("promoInput");
  const code = input.value.trim();
  if (!code) return toast("Введи промокод", true);
  try {
    const data = await api("/api/promo", {
      method: "POST",
      body: JSON.stringify({ code }),
    });
    if (data.valid) {
      state.promo = code.toUpperCase();
      state.promoDiscount = data.discount;
      input.value = "";
      renderTotals();
      notify("success");
      toast(`Промокод ${state.promo} применён · −${data.discount}%`);
    } else {
      notify("error");
      toast("Такого промокода нет 😔", true);
    }
  } catch (error) {
    notify("error");
    toast(error.message, true);
  }
}


function openSheet(id) {
  clearTimeout(backdropTimer);
  $("backdrop").hidden = false;
  requestAnimationFrame(() => {
    $("backdrop").classList.add("show");
    $(id).classList.add("show");
  });
}

function closeSheets() {
  $("backdrop").classList.remove("show");
  document.querySelectorAll(".sheet").forEach((sheet) => sheet.classList.remove("show"));
  backdropTimer = setTimeout(() => { $("backdrop").hidden = true; }, 260);
}

function openProduct(productId) {
  const product = state.products.find((p) => p.id === productId);
  if (!product) return;
  state.sheetProductId = productId;

  const photo = $("sheetPhoto");
  const wrap = $("sheetPhotoWrap");
  if (product.photo) {
    photo.src = product.photo;
    wrap.style.display = "";
  } else {
    photo.removeAttribute("src");
    wrap.style.display = "none";
  }
  $("sheetTitle").textContent = product.title;
  $("sheetDesc").textContent = product.description;
  $("sheetPrice").textContent = fmt(product.price);
  openSheet("productSheet");
}

function openPaySheet() {
  if (!state.cart.length) return;
  const total = cartTotal();
  const bonus = state.user ? state.user.bonus : 0;
  const stars = Math.max(1, Math.round(total * state.starsRate));
  const rateNote = state.starsRate === 1 ? "1:1" : `курс ${state.starsRate}`;

  $("payStars").textContent = `Спишется ${stars} ⭐ (${rateNote})`;
  const bonusBtn = document.querySelector('[data-method="bonus"]');
  if (bonus >= total) {
    $("payBonus").textContent = `Доступно ${bonus.toLocaleString("ru-RU")} 💠`;
    bonusBtn.disabled = false;
  } else {
    $("payBonus").textContent = `Не хватает ${fmt(total - bonus)}`;
    bonusBtn.disabled = true;
  }
  openSheet("paySheet");
}

async function pay(method) {
  if (paying || !state.cart.length) return;
  paying = true;
  const buttons = Array.from(document.querySelectorAll(".pay-option"));
  buttons.forEach((button) => (button.disabled = true));
  try {
    const data = await api("/api/checkout", {
      method: "POST",
      body: JSON.stringify({ method, promo: state.promo || "" }),
    });
    closeSheets();
    notify("success");
    toast(data.message);
    if (method === "bonus") {
      state.promo = null;
      state.promoDiscount = 0;
      await refreshState();
    }
  } catch (error) {
    notify("error");
    toast(error.message, true);
  } finally {
    paying = false;
    buttons.forEach((button) => (button.disabled = false));
    const bonusButton = document.querySelector('[data-method="bonus"]');
    if (bonusButton && state.user) {
      bonusButton.disabled = state.user.bonus < cartTotal();
    }
  }
}


function setTab(tab) {
  if (!["catalog", "cart", "profile"].includes(tab)) tab = "catalog";
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.classList.toggle("is-active", btn.dataset.tab === tab);
  });
  ["catalog", "cart", "profile"].forEach((name) => {
    $("screen-" + name).hidden = name !== tab;
  });
  document.querySelector(".screens").scrollTop = 0;
}

async function copyRef() {
  const link = $("copyRef").dataset.link || "";
  if (!link || link === "—") return;
  try {
    await navigator.clipboard.writeText(link);
    haptic();
    toast("Скопировано");
  } catch (error) {
    toast("Не удалось скопировать", true);
  }
}


function bindEvents() {
  document.querySelectorAll(".tab").forEach((btn) => {
    btn.addEventListener("click", () => {
      haptic();
      setTab(btn.dataset.tab);
    });
  });

  $("categoryChips").addEventListener("click", (event) => {
    const chip = event.target.closest("[data-cat]");
    if (!chip) return;
    haptic();
    state.activeCategory = chip.dataset.cat;
    document.querySelectorAll("#categoryChips .chip").forEach((c) => {
      c.classList.toggle("is-active", c === chip);
    });
    renderCatalog();
  });

  $("productGrid").addEventListener("click", (event) => {
    const addBtn = event.target.closest("[data-add]");
    if (addBtn) {
      addToCart(Number(addBtn.dataset.add), addBtn);
      return;
    }
    const card = event.target.closest("[data-id]");
    if (card) openProduct(Number(card.dataset.id));
  });

  $("cartList").addEventListener("click", (event) => {
    const btn = event.target.closest("[data-step]");
    if (!btn) return;
    const item = state.cart.find((i) => i.item_id === Number(btn.dataset.item));
    if (!item) return;
    haptic();
    setQty(item.item_id, item.qty + Number(btn.dataset.step));
  });

  $("promoBtn").addEventListener("click", applyPromo);
  $("promoInput").addEventListener("keydown", (event) => {
    if (event.key === "Enter") applyPromo();
  });

  $("checkoutBtn").addEventListener("click", () => {
    haptic("medium");
    openPaySheet();
  });

  $("sheetAdd").addEventListener("click", () => {
    if (state.sheetProductId) addToCart(state.sheetProductId, $("sheetAdd"), true);
  });

  $("backdrop").addEventListener("click", closeSheets);

  document.querySelectorAll(".pay-option").forEach((btn) => {
    btn.addEventListener("click", () => {
      haptic("medium");
      pay(btn.dataset.method);
    });
  });

  $("copyRef").addEventListener("click", copyRef);
  $("clearCart").addEventListener("click", clearCart);

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && state.user) refreshState().catch(() => {});
  });
}

async function boot() {
  applyTelegramTheme();
  bindEvents();
  renderSkeletons();

  try {
    const [catalog, stateData] = await Promise.all([api("/api/catalog"), api("/api/state")]);
    state.categories = catalog.categories;
    state.products = catalog.products;
    applyState(stateData);
    renderChips();
    renderCatalog();
  } catch (error) {
    renderCatalog();
    toast(error.message || "Не удалось загрузить данные", true);
  }

  const promoParam = params.get("promo");
  if (promoParam) {
    try {
      const data = await api("/api/promo", {
        method: "POST",
        body: JSON.stringify({ code: promoParam }),
      });
      if (data.valid) {
        state.promo = promoParam.toUpperCase();
        state.promoDiscount = data.discount;
        renderCart();
      }
    } catch (e) {}
  }

  const tab = params.get("tab");
  if (tab) setTab(tab);

  const productIndex = params.get("p");
  if (productIndex !== null && state.products[Number(productIndex)]) {
    openProduct(state.products[Number(productIndex)].id);
  }

  if (params.get("pay")) {
    openPaySheet();
  }
}

boot();
