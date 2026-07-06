// Shared roster-import helpers (used by the Edit KOL page and the report page's
// auto-sync-on-refresh). Requires SheetJS (XLSX) to be loaded on the page.
window.ImportSync = (function () {
  const _n = s => (s == null ? '' : s).toString().trim();
  const _low = s => _n(s).toLowerCase();
  function pickCol(headers, keys) {
    for (let i = 0; i < headers.length; i++) { const h = headers[i]; if (h && keys.some(k => h.includes(k))) return i; }
    return -1;
  }
  function looksUrl(s) { return /https?:\/\/|www\.|tiktok\.com|facebook\.com|fb\.watch|instagram\.com|youtu/i.test(_n(s)); }
  function platformOf(u) {
    u = (u || '').toLowerCase();
    if (u.includes('tiktok.com')) return 'tiktok';
    if (u.includes('facebook.com') || u.includes('fb.watch') || u.includes('fb.com')) return 'facebook';
    if (u.includes('instagram.com')) return 'instagram';
    if (u.includes('youtube.com') || u.includes('youtu.be')) return 'youtube';
    if (u.includes('x.com') || u.includes('twitter.com')) return 'x';
    if (u.includes('line.me')) return 'line';
    return 'website';
  }
  const _FB_SKIP = ['story.php', 'permalink.php', 'profile.php', 'watch', 'reel', 'share', 'photo', 'video', 'groups', 'events', 'media', 'pages', 'p', 'login', 'login.php', 'l.php', 'sharer', 'sharer.php', 'home.php', 'hashtag', 'help', 'privacy', 'policies', 'people', 'public', 'stories'];
  const _IG_SKIP = ['p', 'reel', 'reels', 'tv', 'stories', 'explore', 'accounts'];
  const _X_SKIP = ['i', 'status', 'home', 'search', 'hashtag', 'intent', 'login'];
  function handleFromUrl(u) {
    u = _n(u);
    let m = u.match(/tiktok\.com\/@([^\/\?#\s]+)/i); if (m) return m[1].toLowerCase();
    m = u.match(/(?:facebook\.com|fb\.com)\/([^\/\?#\s]+)/i); if (m) { const h = m[1].toLowerCase(); if (!_FB_SKIP.includes(h)) return h; }
    m = u.match(/instagram\.com\/([^\/\?#\s]+)/i); if (m) { const h = m[1].toLowerCase(); if (!_IG_SKIP.includes(h)) return h; }
    m = u.match(/(?:x\.com|twitter\.com)\/([^\/\?#\s]+)/i); if (m) { const h = m[1].toLowerCase(); if (!_X_SKIP.includes(h)) return h; }
    m = u.match(/youtube\.com\/@([^\/\?#\s]+)/i); if (m) return m[1].toLowerCase();
    return '';
  }
  const NONWORK_URL = /google\.[a-z.]+\/maps|maps\.app\.goo\.gl|goo\.gl\/maps|maps\.google|waze\.com|forms\.gle|docs\.google\.com\/forms/i;
  function normalizeUrl(u) {
    const m = u.match(/facebook\.com\/(?:login[^?]*|l\.php)\?(?:[^#]*&)?(?:next|u)=([^&#]+)/i);
    if (m) { try { return decodeURIComponent(m[1]); } catch (e) { } }
    return u;
  }
  function isProfileUrl(u) {
    const plat = platformOf(u);
    if (plat === 'tiktok') return /tiktok\.com\/@[^\/\?#\s]+\/?([?#]|$)/i.test(u);
    if (plat === 'facebook') { return !!handleFromUrl(u) && !/(\/posts\/|\/videos\/|\/reel\/|\/watch|story_fbid=|\/permalink\/|\/share\/|fb\.watch)/i.test(u); }
    if (plat === 'instagram') { return !!handleFromUrl(u) && !/\/(p|reel|reels|tv)\//i.test(u); }
    if (plat === 'youtube') return /youtube\.com\/(@[^\/\?#\s]+\/?([?#]|$)|channel\/|c\/|user\/)/i.test(u);
    if (plat === 'x') { return !!handleFromUrl(u) && !/\/status\//i.test(u); }
    return false;
  }
  const HEADER_WORDS = ['name', 'ชื่อ', 'username', 'user', 'kol', 'influencer', 'influ', 'link', 'ลิงก์', 'no', 'ลำดับ', 'account', 'ช่อง', 'channel', 'handle', 'id'];
  function postIdOf(plat, u) {
    let m;
    if (plat === 'tiktok') m = u.match(/\/video\/(\d+)/);
    else if (plat === 'instagram') m = u.match(/\/(?:p|reel|reels|tv)\/([A-Za-z0-9_-]+)/);
    else if (plat === 'youtube') m = u.match(/(?:shorts\/|v=|youtu\.be\/)([A-Za-z0-9_-]{6,})/);
    else if (plat === 'x') m = u.match(/\/status\/(\d+)/);
    else if (plat === 'facebook') m = u.match(/(?:\/posts\/|\/videos\/|\/reel\/|story_fbid=|\/permalink\/)([\w.-]+)/);
    return m ? m[1] : '';
  }
  function dedupeLinks(urls) {
    const seen = new Set(), out = [];
    for (const u of urls) {
      const plat = platformOf(u);
      const key = plat + ':' + (postIdOf(plat, u) || u.split('?')[0].replace(/\/$/, '').toLowerCase());
      if (seen.has(key)) continue;
      seen.add(key);
      out.push({ platform: plat, url: u, handle: handleFromUrl(u) });
    }
    return out;
  }
  function urlsIn(text) { return (text.match(/https?:\/\/[^\s)]+/gi) || []).map(u => normalizeUrl(u.replace(/[.,;]+$/, ''))).filter(u => !NONWORK_URL.test(u)); }

  const SOCIAL = /(tiktok\.com|facebook\.com|fb\.watch|instagram\.com|youtu|x\.com|twitter\.com)/i;
  const ADDR = ['address', 'addr', 'ที่อยู่', 'จัดส่ง', 'ส่งของ', 'shipping', 'delivery', 'ไปรษณีย์', 'พัสดุ', 'tracking', 'ผู้รับ', 'เบอร์', 'โทร', 'ของรางวัล', 'เลขที่บ้าน'];
  function parseWorkbook(wb) {
    const out = []; const multi = wb.SheetNames.length > 1;
    wb.SheetNames.forEach(sheetName => {
      const ws = wb.Sheets[sheetName]; if (!ws) return;
      const rows = XLSX.utils.sheet_to_json(ws, { header: 1, blankrows: false, defval: '' });
      if (!rows.length) return;
      let hi = 0; for (let i = 0; i < rows.length; i++) { if (rows[i].filter(c => _n(c)).length >= 1) { hi = i; break; } }
      const headers = rows[hi].map(_low);
      // Skip non-work sheets (shipping-address etc.): no social link + address-ish
      const hasUrl = rows.some(r => r.some(c => SOCIAL.test(_n(c))));
      const nmeta = _low(sheetName) + ' ' + headers.join(' ');
      if (!hasUrl && ADDR.some(k => nmeta.includes(k))) return;
      let cU = pickCol(headers, ['username', 'handle', 'ผู้ใช้', 'บัญชี', 'user', 'ไอดี', 'ชื่อบัญชี', 'account', 'ช่อง', 'channel', 'kol', 'ชื่อ', 'name']);
      const cGrp = pickCol(headers, ['หมวด', 'ประเภท', 'group', 'category', 'type', 'tier', 'กลุ่ม']);
      const cSub = pickCol(headers, ['ย่อย', 'subgroup', 'sub']);
      const cFol = pickCol(headers, ['follow', 'ติดตาม', 'fan']);
      const headerIsData = rows[hi].some(c => looksUrl(c) || /^@[\w.]+$/.test(_n(c)));
      let section = '';
      for (let i = (headerIsData ? hi : hi + 1); i < rows.length; i++) {
        const row = rows[i]; const filled = row.filter(c => _n(c)); if (!filled.length) continue;
        const urls = [...new Set(urlsIn(row.map(_n).join('  ')))];
        if (!urls.length && !multi && cGrp < 0 && filled.length <= 2) {
          const t = filled.map(_n).find(v => v && !/^\d+$/.test(v) && !/^#/.test(v));
          if (t) section = t;
          continue;
        }
        const profUrls = urls.filter(isProfileUrl);
        const workUrls = urls.filter(u => !isProfileUrl(u));
        let username = cU >= 0 ? _n(row[cU]).replace(/^@/, '') : '';
        if (/https?:|\//.test(username)) username = handleFromUrl(username);
        if (!username) { const at = filled.map(_n).find(v => /^@[\w.]+$/.test(v)); if (at) username = at.slice(1); }
        if (!username && profUrls.length) username = handleFromUrl(profUrls[0]);
        if (!username && workUrls.length) username = handleFromUrl(workUrls.find(u => platformOf(u) === 'tiktok') || workUrls[0]);
        if (!username && !workUrls.length) continue;
        if (!workUrls.length && HEADER_WORDS.includes((username || '').toLowerCase())) continue;
        const links = dedupeLinks(workUrls);
        const colGrp = cGrp >= 0 ? _n(row[cGrp]) : '';
        let group, subgroup = cSub >= 0 ? _n(row[cSub]) : '';
        if (colGrp) group = colGrp; else if (multi) group = _n(sheetName) || 'KOL'; else group = section || 'KOL';
        let followers = 0; if (cFol >= 0) { const fv = parseInt(_n(row[cFol]).replace(/[^0-9]/g, '')); if (!isNaN(fv)) followers = fv; }
        out.push({ username: (username || '').toLowerCase(), display: (cU >= 0 ? _n(row[cU]) : '') || username, group, subgroup, links, followers });
      }
    });
    return out;
  }

  // Fetch the online file, parse it, resolve missing handles, and REPLACE the
  // campaign roster. Returns the number of KOLs imported.
  async function syncRosterFromUrl(campaign, url, onStatus) {
    onStatus && onStatus('กำลังดึงไฟล์ต้นทาง…');
    const resp = await fetch('/api/sheet/fetch?url=' + encodeURIComponent(url));
    if (!resp.ok) { const d = await resp.json().catch(() => ({})); throw new Error(d.detail || 'ดึงไฟล์ไม่สำเร็จ'); }
    const wb = XLSX.read(await resp.arrayBuffer(), { type: 'array' });
    let kols = parseWorkbook(wb);
    const need = [...new Set(kols.flatMap(k => (k.links || []).filter(l => !l.handle || !postIdOf(l.platform, l.url)).map(l => l.url)))];
    if (need.length) {
      onStatus && onStatus('กำลังตรวจลิงก์ ' + need.length + ' รายการ (แยกลิงก์ช่อง/ลิงก์โพสต์)…');
      try {
        const d = await (await fetch('/api/resolve-handles', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls: need }) })).json();
        const map = d.handles || {}; const res = d.resolved || {};
        kols.forEach(k => (k.links || []).forEach(l => {
          if (!l.handle && map[l.url]) l.handle = map[l.url];
          const fin = res[l.url];
          if (fin && fin !== l.url) { l.url = normalizeUrl(fin); l.platform = platformOf(l.url); if (!l.handle) l.handle = handleFromUrl(l.url); }
        }));
      } catch (e) { /* leave unresolved */ }
    }
    // post-resolution: profile/non-work links only name the KOL; then dedupe by post id
    kols.forEach(k => {
      const prof = (k.links || []).filter(l => isProfileUrl(l.url) || NONWORK_URL.test(l.url));
      k.links = (k.links || []).filter(l => !isProfileUrl(l.url) && !NONWORK_URL.test(l.url));
      if (!k.username) { const pl = prof.find(x => x.handle || handleFromUrl(x.url)); if (pl) k.username = pl.handle || handleFromUrl(pl.url); }
      const seen = new Set();
      k.links = k.links.filter(l => {
        const key = l.platform + ':' + (postIdOf(l.platform, l.url) || l.url.split('?')[0].replace(/\/$/, '').toLowerCase());
        if (seen.has(key)) return false; seen.add(key); return true;
      });
    });
    kols.forEach(k => { if (!k.username) { const l = (k.links || []).find(x => x.handle); if (l) k.username = l.handle; } if (!k.display) k.display = k.username; });
    kols = kols.filter(k => k.username);
    if (!kols.length) throw new Error('ไม่พบรายชื่อในไฟล์');
    onStatus && onStatus('กำลังอัปเดตรายชื่อ…');
    const r = await fetch('/api/roster/report/bulk?campaign=' + encodeURIComponent(campaign), { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ kols, sheet_url: url }) });
    const d = await r.json(); if (!r.ok) throw new Error(d.detail || ('HTTP ' + r.status));
    return d.count;
  }

  return { syncRosterFromUrl, parseWorkbook, platformOf, handleFromUrl };
})();
