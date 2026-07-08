// Client-side auth guard (Wazzup session). Included by every protected page.
// - Redirects to /login when there is no live session (expiration checked)
// - Attaches Authorization: Bearer <token> to every same-origin /api/ fetch
// - On any 401 from the API, clears the session and returns to /login
// - Adds a user chip + logout button to the nav
// View-only client pages (/v/<key> or ?view=1) are NOT guarded.
(function () {
  if (/^\/v\//i.test(location.pathname) ||
      new URLSearchParams(location.search).get('view') === '1') return;

  function readSession() {
    try {
      const s = JSON.parse(localStorage.getItem('wz_session') || 'null');
      if (!s || !s.access_token) return null;
      if (s.expiration && new Date(s.expiration) <= new Date()) {  // expired
        localStorage.removeItem('wz_session');
        return null;
      }
      return s;
    } catch (e) { return null; }
  }
  function toLogin() {
    localStorage.removeItem('wz_session');
    location.replace('/login?next=' + encodeURIComponent(location.pathname + location.search));
  }

  const s = readSession();
  if (!s) { toLogin(); return; }

  // attach the bearer token to same-origin API calls; bounce to login on 401
  const origFetch = window.fetch.bind(window);
  window.fetch = function (input, init) {
    let url = '';
    try { url = (typeof input === 'string') ? input : (input && input.url) || ''; } catch (e) {}
    const isApi = url.startsWith('/api/') || url.startsWith(location.origin + '/api/');
    if (isApi) {
      init = init || {};
      const h = new Headers(init.headers || {});
      h.set('Authorization', 'Bearer ' + s.access_token);
      init.headers = h;
    }
    return origFetch(input, init).then(function (r) {
      if (isApi && r.status === 401 && !url.includes('/api/auth/')) toLogin();
      return r;
    });
  };

  // user chip + logout in the nav
  function mountChip() {
    const nav = document.querySelector('nav.nav');
    if (!nav) return;
    const name = s.nickName || s.empThaiName || s.empEngName || s.email || '';
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:.45rem;font-size:.78rem;color:#475569;margin-left:.4rem';
    const who = document.createElement('span');
    who.textContent = '👤 ' + name;
    const btn = document.createElement('button');
    btn.textContent = 'ออกจากระบบ';
    btn.style.cssText = 'border:1px solid #e5e7eb;background:#fff;border-radius:999px;padding:.25rem .7rem;cursor:pointer;font-size:.72rem;font-family:inherit;color:#475569';
    btn.onclick = function () { localStorage.removeItem('wz_session'); location.href = '/login'; };
    wrap.appendChild(who); wrap.appendChild(btn);
    nav.appendChild(wrap);
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountChip);
  } else { mountChip(); }
})();
