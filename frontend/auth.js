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
      access_token:   token,
      expiration:     null,   // sender doesn't send exp; server 401 will bounce
      displayName:    p.empThaiName || p.empEngName || p.nickName || '',
      empThaiName:    p.empThaiName || '',
      empEngName:     p.empEngName || '',
      nickName:       p.nickName || '',
      email:          p.email || '',
      positionName:   p.positionName || '',
      departmentName: p.departmentName || '',
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

  // user chip in the nav — an avatar button that opens a Facebook-style
  // popup with the full name + logout button (nothing else is shown next to
  // the avatar itself, to keep the nav tidy).
  function mountChip() {
    const nav = document.querySelector('nav.nav');
    if (!nav) return;
    const name = s.displayName || s.empThaiName || s.empEngName || s.nickName || s.email || '';
    const meta = s.email || (s.displayName && s.displayName !== s.empEngName ? s.empEngName : '') || '';
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

    // build one avatar element at the given size, with initials fallback and
    // (if available) the photo layered on top; if the photo 404s the img
    // removes itself and the initials show through
    function buildAvatar(size, fontSize) {
      const el = document.createElement('div');
      el.style.cssText = 'position:relative;width:' + size + 'px;height:' + size + 'px;flex:none';
      const fb = document.createElement('div');
      fb.textContent = initials;
      fb.style.cssText = 'position:absolute;inset:0;border-radius:50%;background:' + bgColor
        + ';color:#fff;display:flex;align-items:center;justify-content:center;'
        + 'font-weight:700;font-size:' + fontSize + ';letter-spacing:.02em;border:1px solid #e5e7eb;'
        + 'font-family:system-ui,\'Segoe UI\',Arial,sans-serif';
      el.appendChild(fb);
      if (s.photo) {
        const img = document.createElement('img');
        img.src = s.photo;
        img.alt = name;
        img.referrerPolicy = 'no-referrer';
        img.style.cssText = 'position:absolute;inset:0;width:100%;height:100%;'
          + 'border-radius:50%;object-fit:cover;border:1px solid #e5e7eb;background:#e2e8f0';
        img.onerror = function () { this.remove(); };
        el.appendChild(img);
      }
      return el;
    }

    // wrapper anchors the absolutely-positioned popup. margin-left:auto so the
    // chip parks itself at the far right of the nav; the navtabs sit
    // naturally next to the logo (only nav-brand's fixed margin-right between
    // them, not a free-space push).
    const wrap = document.createElement('div');
    wrap.style.cssText = 'position:relative;margin-left:auto';

    // avatar trigger (36px, ~30% larger than before). A real <button> so it
    // is keyboard-focusable and screen readers announce it as clickable.
    const trigger = document.createElement('button');
    trigger.type = 'button';
    trigger.setAttribute('aria-label', 'บัญชี ' + name);
    trigger.setAttribute('aria-haspopup', 'true');
    trigger.setAttribute('aria-expanded', 'false');
    trigger.style.cssText = 'padding:0;border:none;background:none;cursor:pointer;line-height:0;'
      + 'border-radius:50%;transition:box-shadow .12s;overflow:visible;position:relative';
    const triggerAvatar = buildAvatar(36, '.85rem');
    // small chevron badge at bottom-right — signals "this opens a menu"
    // (mirrors Facebook's account-switcher / GitHub's avatar-menu affordance)
    const caret = document.createElement('span');
    caret.textContent = '▾';
    caret.setAttribute('aria-hidden', 'true');
    caret.style.cssText = 'position:absolute;right:-2px;bottom:-2px;'
      + 'width:14px;height:14px;border-radius:50%;background:#94a3b8;color:#fff;'
      + 'font-size:.55rem;line-height:1;display:flex;align-items:center;justify-content:center;'
      + 'border:2px solid #fff;font-family:system-ui,sans-serif;'
      + 'box-shadow:0 1px 2px rgba(0,0,0,.15);pointer-events:none';
    triggerAvatar.appendChild(caret);
    trigger.appendChild(triggerAvatar);
    trigger.onmouseenter = function () { this.style.boxShadow = '0 0 0 3px #eef2f7'; };
    trigger.onmouseleave = function () { this.style.boxShadow = 'none'; };

    // popup (menu) — hidden until the avatar is clicked. Header row: avatar
    // on the left, empThaiName + positionName stacked on the right.
    const popup = document.createElement('div');
    popup.setAttribute('role', 'menu');
    popup.style.cssText = 'position:absolute;top:calc(100% + 10px);right:0;z-index:60;'
      + 'width:280px;background:#fff;border:1px solid #e5e7eb;border-radius:12px;'
      + 'box-shadow:0 12px 32px rgba(15,23,42,.14);padding:1rem;display:none;'
      + 'font-family:\'Noto Sans Thai\',system-ui,sans-serif';

    const header = document.createElement('div');
    header.style.cssText = 'display:flex;align-items:center;gap:.75rem;min-width:0';

    const bigAvatar = buildAvatar(56, '1.3rem');
    header.appendChild(bigAvatar);

    const info = document.createElement('div');
    info.style.cssText = 'flex:1;min-width:0';

    const nameEl = document.createElement('div');
    nameEl.textContent = (s.empThaiName || name || '(ไม่มีชื่อ)');
    nameEl.style.cssText = 'font-weight:700;color:#0f172a;font-size:.95rem;line-height:1.25;word-break:break-word';
    info.appendChild(nameEl);

    const position = s.positionName || '';
    if (position) {
      const posEl = document.createElement('div');
      posEl.textContent = position;
      posEl.style.cssText = 'color:#64748b;font-size:.78rem;margin-top:.15rem;line-height:1.3;word-break:break-word';
      info.appendChild(posEl);
    }

    header.appendChild(info);
    popup.appendChild(header);

    const divider = document.createElement('div');
    divider.style.cssText = 'height:1px;background:#e5e7eb;margin:.85rem 0';
    popup.appendChild(divider);

    const btn = document.createElement('button');
    btn.type = 'button';
    btn.setAttribute('role', 'menuitem');
    // inline SVG (Feather-style log-out icon) + label, so the icon inherits
    // currentColor and animates with the hover color change
    btn.innerHTML = '<svg viewBox="0 0 24 24" width="15" height="15" fill="none" '
      + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" '
      + 'aria-hidden="true" style="flex:none">'
      + '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/>'
      + '<polyline points="16 17 21 12 16 7"/>'
      + '<line x1="21" y1="12" x2="9" y2="12"/>'
      + '</svg><span>ออกจากระบบ</span>';
    btn.style.cssText = 'width:100%;border:1px solid #e5e7eb;background:#fff;'
      + 'border-radius:8px;padding:.55rem;cursor:pointer;font-size:.85rem;'
      + 'font-family:inherit;color:#475569;font-weight:600;transition:.12s;'
      + 'display:flex;align-items:center;justify-content:center;gap:.5rem';
    btn.onmouseenter = function () {
      this.style.background = '#fef2f2'; this.style.color = '#dc2626'; this.style.borderColor = '#fecaca';
    };
    btn.onmouseleave = function () {
      this.style.background = '#fff'; this.style.color = '#475569'; this.style.borderColor = '#e5e7eb';
    };
    btn.onclick = function () { localStorage.removeItem('wz_session'); location.href = '/login'; };
    popup.appendChild(btn);

    wrap.appendChild(trigger);
    wrap.appendChild(popup);
    nav.appendChild(wrap);

    function setOpen(open) {
      popup.style.display = open ? 'block' : 'none';
      trigger.setAttribute('aria-expanded', open ? 'true' : 'false');
    }
    trigger.onclick = function (e) {
      e.stopPropagation();
      setOpen(popup.style.display !== 'block');
    };
    // click anywhere else on the page closes it
    document.addEventListener('click', function (e) {
      if (!wrap.contains(e.target)) setOpen(false);
    });
    document.addEventListener('keydown', function (e) {
      if (e.key === 'Escape') setOpen(false);
    });
  }
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', mountChip);
  } else { mountChip(); }
})();
