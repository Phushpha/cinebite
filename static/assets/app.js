/* CineBite shared frontend helper: API, auth, cart, toasts */
const API = "";

/* ---------------- storage ---------------- */
const store = {
  get(k, d) { try { return JSON.parse(localStorage.getItem(k)) ?? d; } catch { return d; } },
  set(k, v) { localStorage.setItem(k, JSON.stringify(v)); },
  del(k) { localStorage.removeItem(k); },
};

const auth = {
  token: () => store.get("cb_token", ""),
  user: () => store.get("cb_user", null),
  set(token, user) { store.set("cb_token", token); store.set("cb_user", user); },
  clear() { store.del("cb_token"); store.del("cb_user"); },
  loggedIn() { return !!auth.token(); },
};

const cart = {
  read() { return store.get("cb_cart", { show_id: null, seats: [], items: [] }); },
  write(c) { store.set("cb_cart", c); cart.paint(); },
  add(item) {
    const c = cart.read();
    const found = c.items.find(i => i.id === item.id);
    if (found) found.qty = Math.min(found.qty + 1, 20);
    else c.items.push({ id: item.id, qty: 1, name: item.name, price: item.price, size: item.size || "" });
    cart.write(c);
  },
  setQty(id, qty) {
    const c = cart.read();
    c.items = c.items.filter(i => { if (i.id === id) i.qty = qty; return i.qty > 0; });
    cart.write(c);
  },
  clear() { cart.write({ show_id: null, seats: [], items: [] }); },
  count() { const c = cart.read(); return c.items.reduce((s, i) => s + i.qty, 0); },
  total() { const c = cart.read(); return c.items.reduce((s, i) => s + i.qty * i.price, 0); },
  paint() {
    document.querySelectorAll("[data-cart-badge]").forEach(el => {
      const n = cart.count();
      el.textContent = n;
      el.classList.toggle("hidden", n === 0);
    });
  },
};

/* ---------------- api ---------------- */
async function api(path, opts = {}) {
  const headers = { "Content-Type": "application/json", ...(opts.headers || {}) };
  if (auth.token()) headers["Authorization"] = "Bearer " + auth.token();
  const res = await fetch(API + path, { ...opts, headers });
  let data = {};
  try { data = await res.json(); } catch { /* empty body */ }
  if (!res.ok) {
    if (res.status === 401 && auth.loggedIn()) {
      auth.clear();
      toast("Session expired - please login again", "err");
    }
    const detail = data && typeof data.detail === "string" ? data.detail : null;
    throw new Error(detail || `Request failed (${res.status})`);
  }
  return data;
}

/* ---------------- ui ---------------- */
let toastTimer;
function toast(msg, type = "") {
  let el = document.getElementById("toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "toast";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.className = type;
  requestAnimationFrame(() => el.classList.add("show"));
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.classList.remove("show"), 3200);
}

function money(n) { return "₹" + Number(n).toLocaleString("en-IN"); }

function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, c =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

/* requires login, remembers where the user was heading */
function requireLogin() {
  if (auth.loggedIn()) return true;
  store.set("cb_next", location.pathname + location.search);
  location.href = "login.html";
  return false;
}

function afterLogin() {
  const next = store.get("cb_next", null);
  store.del("cb_next");
  location.href = next || "index.html";
}

function logout() {
  auth.clear();
  cart.clear();
  location.href = "index.html";
  toast("Logged out", "ok");
}

/* paint nav login state + cart badge on every page */
function paintNav() {
  document.querySelectorAll("[data-auth-link]").forEach(el => {
    const u = auth.user();
    if (auth.loggedIn() && u) {
      el.textContent = "Hi " + (u.phone || u.email || "").split("@")[0];
      el.href = "orders.html";
    } else {
      el.textContent = "Login";
      el.href = "login.html";
    }
  });
  cart.paint();
}

/* ---------------- location (city) ---------------- */
const city = {
  get: () => store.get("cb_city", ""),
  set: c => store.set("cb_city", c),
};

/**
 * Paint the city selector into #slotId and return the active city.
 * onChange(city) fires whenever the user switches city.
 */
async function mountCity(slotId, onChange) {
  const host = document.getElementById(slotId);
  let cities = [];
  try {
    ({ cities } = await api("/api/cities"));
  } catch (e) {
    console.error(e);
    return city.get();
  }
  if (!cities.length) return city.get();
  let cur = city.get();
  if (!cities.some(c => c.city === cur)) {
    cur = cities[0].city;
    city.set(cur);
  }
  if (host) {
    host.innerHTML =
      `<span class="citybox">📍<select aria-label="Choose your city">${cities
        .map(c => `<option value="${esc(c.city)}"${c.city === cur ? " selected" : ""}>` +
                 `${esc(c.city)}</option>`)
        .join("")}</select><button type="button" id="locBtn" class="locbtn" title="Detect my location">📍 Auto</button></span>`;
    host.querySelector("select").addEventListener("change", e => {
      city.set(e.target.value);
      onChange && onChange(e.target.value);
    });
    const locBtn = document.getElementById("locBtn");
    if (locBtn) {
      locBtn.addEventListener("click", () => {
        if (!navigator.geolocation) { toast("Geolocation not supported","err"); return; }
        locBtn.disabled = true; locBtn.textContent = "Detecting...";
        navigator.geolocation.getCurrentPosition((pos) => {
          const c = nearestCity(pos.coords.latitude, pos.coords.longitude);
          if (c && cities.some(x=>x.city===c)) {
            city.set(c);
            onChange && onChange(c);
            locBtn.textContent = "📍 Auto"; locBtn.disabled=false;
          } else {
            locBtn.textContent="📍 Auto"; locBtn.disabled=false; toast("Could not map location","warn");
          }
        }, (err) => { locBtn.textContent="📍 Auto"; locBtn.disabled=false; toast(err.message||"Location denied","warn"); },
        {enableHighAccuracy:true, timeout:10000, maximumAge:600000});
      });
    }
  }
  return cur;
}

const CITY_COORDS = {
  "Mumbai": {lat:19.076, lon:72.8777},
  "Delhi NCR": {lat:28.7041, lon:77.1025},
  "Bengaluru": {lat:12.9716, lon:77.5946},
  "Pune": {lat:18.5204, lon:73.8567},
  "Hyderabad": {lat:17.385, lon:78.4867},
  "Chennai": {lat:13.0827, lon:80.2707},
  "Kolkata": {lat:22.5726, lon:88.3639},
  "Jaipur": {lat:26.9124, lon:75.7873},
  "Bokaro": {lat:23.6693, lon:86.1511},
  "Ranchi": {lat:23.3441, lon:85.3096},
  "Dhanbad": {lat:23.7957, lon:86.4304}
};

function haversine(lat1,lon1,lat2,lon2){
  const R=6371; const dLat=(lat2-lat1)*Math.PI/180; const dLon=(lon2-lon1)*Math.PI/180;
  const a=Math.sin(dLat/2)**2 + Math.cos(lat1*Math.PI/180)*Math.cos(lat2*Math.PI/180)*Math.sin(dLon/2)**2;
  return 2*Math.atan2(Math.sqrt(a), Math.sqrt(1-a))*R;
}
function nearestCity(lat,lon){
  let best=null, min=Infinity;
  for (const [name,c] of Object.entries(CITY_COORDS)){ const d=haversine(lat,lon,c.lat,c.lon); if (d<min){ min=d; best=name; } }
  return best;
}

/* ---------------- posters ----------------
   Some titles have licensed key art, some do not. When the artwork is missing
   (or fails to load) we draw a designed title card instead of a broken image. */
function posterHTML(m) {
  const accent = m.accent || "#e11d48";
  const year = (m.release_date || "").slice(0, 4);
  const badge = `<span class="rate">★ ${m.rating}</span>` +
                `<span class="cert">${esc(m.certificate)}</span>`;
  const soon = m.releasing === false
    ? `<span class="relbadge">📅 ${esc(relLabel(m) || "Coming soon")}</span>`
    : "";
  if (!m.poster_url) {
    return `<div class="poster nopost" style="--acc2:${esc(accent)}">` +
           `<span class="ptitle">${esc(m.title)}</span>` +
           (year ? `<span class="pyear">${esc(year)}</span>` : "") + badge + soon + `</div>`;
  }
  return `<div class="poster" data-title="${esc(m.title)}" data-year="${esc(year)}" ` +
         `data-accent="${esc(accent)}">` +
         `<img src="${esc(m.poster_url)}" alt="${esc(m.title)}" loading="lazy" ` +
         `onerror="posterFail(this)">${badge}${soon}</div>`;
}

function posterFail(img) {
  const box = img.parentNode;
  if (!box) return;
  box.classList.add("nopost");
  box.style.setProperty("--acc2", box.dataset.accent || "#ff8500");
  box.insertAdjacentHTML(
    "afterbegin",
    `<span class="ptitle">${esc(box.dataset.title || "")}</span>` +
      (box.dataset.year ? `<span class="pyear">${esc(box.dataset.year)}</span>` : "")
  );
  img.remove();
}

/* ---------------- dates ---------------- */
function fmtDate(iso, opts) {
  if (!iso) return "";
  const d = new Date(iso + "T00:00:00");
  return d.toLocaleDateString("en-IN", opts || { weekday: "short", day: "numeric", month: "short" });
}

function relLabel(m) {
  if (m.releasing || !m.release_date) return "";
  if (m.days_until === 1) return "Releasing tomorrow";
  if (m.days_until > 1)
    return `Releasing ${fmtDate(m.release_date, { day: "numeric", month: "short" })}`;
  return "";
}

document.addEventListener("DOMContentLoaded", paintNav);
