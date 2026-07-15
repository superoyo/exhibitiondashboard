// Client-side auth guard (Wazzup session). Included by every protected page.
// - Redirects to /login when there is no live session (expiration checked)
// - SSO handoff: accepts #token=<access_token> (or ?token=...) from another
//   app that already has a Wazzup session, validates it against
//   /api/auth/profile, stores the session, and cleans the token off the URL.
// - Attaches Authorization: Bearer <token> to every same-origin /api/ fetch
// - On any 401 from the API, clears the session and returns to /login
// - Adds a user chip + logout button to the nav
// View-only client pages (/v/<key> or ?view=1) are NOT guarded.
(async function () {
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

  // SSO handoff — if the URL carries a token (fragment or query), validate it
  // against Wazzup via /api/auth/profile, promote it to a real session, and
  // scrub the token from the URL so it doesn't linger in history / copy-paste.
  // No `exp` is required from the sender: if the token is stale, the next
  // /api/ call gets 401 and the guard bounces the user to /login as usual.
  async function tryUrlToken() {
    const hashParams = new URLSearchParams((location.hash || '').replace(/^#/, ''));
    const qsParams   = new URLSearchParams(location.search);
    const token = hashParams.get('token') || qsParams.get('token');
    if (!token) return null;

    let profile = null;
    try {
      const r = await fetch('/api/auth/profile',
        { headers: { 'Authorization': 'Bearer ' + token } });
      if (r.ok) profile = await r.json();
    } catch (e) {}

    // always scrub the token from the URL — whether validation succeeded or
    // not — so a bad/stale token doesn't sit in the address bar being retried
    hashParams.delete('token');
    qsParams.delete('token');
    const newSearch = qsParams.toString();
    const newHash   = hashParams.toString();
    history.replaceState(null, '', location.pathname
      + (newSearch ? '?' + newSearch : '')
      + (newHash ? '#' + newHash : ''));

    if (!profile) return null;

    const p = profile.profile || {};
    const sess = {
      access_token: token,
      expiration:   null,   // sender doesn't send exp; server 401 will bounce
      displayName:  p.empThaiName || p.empEngName || p.nickName || '',
      empThaiName:  p.empThaiName || '',
      empEngName:   p.empEngName || '',
      nickName:     p.nickName || '',
      email:        p.email || '',
    };
    if (p.wazzupPhotoBase64) {
      let t = (p.wazzupPhotoFileType || 'jpeg').replace(/^\./, '').toLowerCase();
      if (!t.includes('/')) t = 'image/' + (t === 'jpg' ? 'jpeg' : t);
      const uri = 'data:' + t + ';base64,' + p.wazzupPhotoBase64;
      if (uri.length < 400000) sess.photo = uri;
    }
    if (!sess.photo && p.profileURL && /^https?:/i.test(p.profileURL)) {
      sess.photo = p.profileURL;
    }
    localStorage.setItem('wz_session', JSON.stringify(sess));
    return sess;
  }

  // Kick off session determination (async). Wrap fetch IMMEDIATELY — before
  // any await — so /api/ calls fired by the page during the SSO handoff
  // (e.g. home.html's inline `loadGrid()` right after this script tag) hang
  // on `sessionReady` and pick up the Authorization header, instead of
  // firing un-authed and coming back 401 → empty UI.
  const sessionReady = (async () => (await tryUrlToken()) || readSession())();

  const origFetch = window.fetch.bind(window);
  window.fetch = async function (input, init) {
    let url = '';
    try { url = (typeof input === 'string') ? input : (input && input.url) || ''; } catch (e) {}
    const isApi = url.startsWith('/api/') || url.startsWith(location.origin + '/api/');
    const isAuthCall = url.includes('/api/auth/');
    if (isApi && !isAuthCall) {
      const sess = await sessionReady;
      if (sess && sess.access_token) {
        init = init || {};
        const h = new Headers(init.headers || {});
        h.set('Authorization', 'Bearer ' + sess.access_token);
        init.headers = h;
      }
    }
    const r = await origFetch(input, init);
    if (isApi && !isAuthCall && r.status === 401) toLogin();
    return r;
  };

  const s = await sessionReady;
  if (!s) { toLogin(); return; }

  // user chip (photo + real full name) + logout in the nav
  function mountChip() {
    const nav = document.querySelector('nav.nav');
    if (!nav) return;
    const name = s.displayName || s.empThaiName || s.empEngName || s.nickName || s.email || '';
    const wrap = document.createElement('div');
    wrap.style.cssText = 'display:flex;align-items:center;gap:.45rem;font-size:.78rem;color:#475569;margin-left:.4rem';
    // Avatar: initials fallback baked in underneath; photo layered on top if
    // available. If the photo URL 404s (Wazzup CDN expires, etc.) the img
    // removes itself and the initials show through — instead of leaving a
    // blank hole in the nav like before.
    const initials = (function () {
      const parts = String(name).trim().split(/\s+/).filter(Boolean);
      if (parts.length >= 2) return (parts[0][0] + parts[parts.length - 1][0]).toUpperCase();
      return (parts[0] || '?').slice(0, 1).toUpperCase();
    })();
    const bgColor = (function () {
      let h = 0;
      for (let i = 0; i < name.length; i++) h = (h * 31 + name.charCodeAt(i)) & 0xffff;
      return 'hsl(' + (h % 360) + ',55%,42%)';
    })();
    const avatar = document.createElement('div');
    avatar.style.cssText = 'position:relative;width:28px;height:28px;flex:none';
    const fallback = document.createElement('div');
    fallback.textContent = initials;
    fallback.style.cssText = 'position:absolute;inset:0;border-radius:50%;background:' + bgColor
      + ';color:#fff;display:flex;align-items:center;justify-content:center;'
      + 'font-weight:700;font-size:.7rem;letter-spacing:.02em;border:1px solid #e5e7eb;'
      + 'font-family:system-ui,\'Segoe UI\',Arial,sans-serif';
    avatar.appendChild(fallback);
    if (s.photo) {
      const img = document.createElement('img');
      img.src = s.photo;
      img.alt = name;
      img.referrerPolicy = 'no-referrer';
      img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;'
        + 'border-radius:50%;object-fit:cover;border:1px solid #e5e7eb;background:#e2e8f0';
      img.onerror = function () { this.remove(); };
      avatar.appendChild(img);
    }
    wrap.appendChild(avatar);
    const who = document.createElement('span');
    who.textContent = name;
    who.style.cssText = 'font-weight:600;color:#334155;white-space:nowrap';
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
