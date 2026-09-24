// Account-history capture for Reddit and X.
// Reads YOUR upvotes/saves (Reddit) and likes/bookmarks (X). These are account-level,
// so they include phone activity. Stored as source="account_history",
// evidence="engagement": what you acted on, NOT what the feed showed you.
// Loaded after db.js, the platform adapter, core.js and sync.js.

const HISTORY_SEEN_CAP = 3000;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const seenKey = () => `historySeen_${PLATFORM.name}`;

// Remember which items were already sent, so each run only adds new ones.
async function loadSeen() {
  const r = await chrome.storage.local.get(seenKey());
  return new Set(r[seenKey()] || []);
}
async function saveSeen(seen) {
  await chrome.storage.local.set({ [seenKey()]: [...seen].slice(-HISTORY_SEEN_CAP) });
}

async function storeHistory(items) {
  const seen = await loadSeen();
  const now = Date.now();  // when we found it; the platforms don't expose when you liked it
  let added = 0;
  for (const [i, item] of items.entries()) {
    if (!item || seen.has(item.itemId)) continue;
    await saveImpression(
      { ...item, platform: PLATFORM.name },
      { itemId: item.itemId, position: i, enteredAt: now, dwellMs: 0, source: "account_history", evidence: "engagement" }
    );
    seen.add(item.itemId);
    added++;
  }
  await saveSeen(seen);
  // Push now instead of waiting 30s, since this tab closes right after.
  for (let i = 0; i < Math.ceil(added / 50); i++) await syncOnce();
  return added;
}

// ---- Reddit: logged-in JSON endpoints, no page scraping needed ----
async function redditJson(path) {
  const r = await fetch(path, { credentials: "include" });
  if (!r.ok) throw new Error(`${path} HTTP ${r.status}`);
  return r.json();
}

async function harvestReddit() {
  const me = await redditJson("/api/me.json");
  const name = me?.data?.name;
  if (!name) return { error: "not logged in to Reddit" };
  const items = [];
  for (const list of ["upvoted", "saved"]) {
    const res = await redditJson(`/user/${name}/${list}.json?limit=100&raw_json=1`);
    for (const c of res?.data?.children || []) {
      if (c.kind !== "t3") continue;  // posts only; saved comments are skipped
      const d = c.data;
      items.push({
        itemId: d.name,  // "t3_xxxx", same id format as live capture
        mediaType: d.is_video ? "video" : d.post_hint || "post",
        title: d.title || null,
        channel: d.subreddit_name_prefixed,
        channelHandle: `/${d.subreddit_name_prefixed}`,
        duration: null,
        isAd: !!d.promoted,
      });
    }
  }
  return { found: items.length, added: await storeHistory(items) };
}

// ---- X: no public JSON, so read the likes/bookmarks page itself ----
async function harvestX() {
  for (let i = 0; i < 20 && !document.querySelector(PLATFORM.tile); i++) await sleep(500);
  const byId = new Map();
  const grab = () => document.querySelectorAll(PLATFORM.tile).forEach((t) => {
    const it = PLATFORM.extract(t);
    if (it && !byId.has(it.itemId)) byId.set(it.itemId, it);
  });
  // A few scrolls is plenty when this runs every few hours.
  for (let i = 0; i < 4; i++) { grab(); window.scrollBy(0, innerHeight * 2); await sleep(1500); }
  grab();
  const items = [...byId.values()];
  return { found: items.length, added: await storeHistory(items) };
}

// ---- YouTube: read the watch-history page. Finds videos by their link pattern
// (/watch?v=ID, /shorts/ID) so it survives YouTube layout changes. ----
async function harvestYouTube() {
  const LINKS = 'a[href*="/watch?v="], a[href*="/shorts/"]';
  const BOXES = "ytd-video-renderer, yt-lockup-view-model, ytd-reel-item-renderer, " +
                "ytm-shorts-lockup-view-model, ytm-shorts-lockup-view-model-v2";
  for (let i = 0; i < 20 && !document.querySelector(LINKS); i++) await sleep(500);

  const byId = new Map();
  const grab = () => {
    const root = document.querySelector("#primary") || document;  // skip the sidebar
    root.querySelectorAll(LINKS).forEach((a) => {
      const href = a.getAttribute("href") || "";
      const watch = href.match(/[?&]v=([\w-]{11})/);
      const short = href.match(/\/shorts\/([\w-]{11})/);
      const itemId = watch?.[1] || short?.[1];
      if (!itemId || byId.has(itemId)) return;
      const box = a.closest(BOXES) || a.parentElement;
      const titleEl = box.querySelector("#video-title, a.ytLockupMetadataViewModelTitle, h3");
      const title = (titleEl?.getAttribute("title") || titleEl?.textContent ||
                     a.getAttribute("title") || a.getAttribute("aria-label") || "").trim();
      if (!title) return;  // thumbnail link seen first; the title link comes next
      const ch = box.querySelector('a[href^="/@"]');
      byId.set(itemId, {
        itemId,
        mediaType: short ? "short" : "video",
        title: title.slice(0, 300),
        channel: ch?.textContent.trim() || null,
        channelHandle: ch?.getAttribute("href") || null,
        duration: null,
        isAd: false,
      });
    });
  };
  for (let i = 0; i < 4; i++) { grab(); window.scrollBy(0, innerHeight * 2); await sleep(1500); }
  grab();
  const items = [...byId.values()];
  return { found: items.length, added: await storeHistory(items) };
}

// ---- Instagram: the same JSON endpoints instagram.com itself calls ----
const IG_APP_ID = "936619743392459";  // Instagram's public web-app id, sent by instagram.com on every call
async function igJson(path) {
  const csrf = document.cookie.match(/(?:^|; )csrftoken=([^;]+)/)?.[1] || "";
  const r = await fetch(path, {
    credentials: "include",
    headers: { "X-IG-App-ID": IG_APP_ID, "X-CSRFToken": csrf, "X-Requested-With": "XMLHttpRequest" },
  });
  if (!r.ok) throw new Error(`${path} HTTP ${r.status}`);
  return r.json();
}

function igItem(m) {
  if (!m?.code) return null;
  const author = m.user?.username || null;
  const caption = (m.caption?.text || "").trim();
  return {
    itemId: `ig:${m.code}`,  // same id the export upload uses, so a post isn't counted twice
    mediaType: m.product_type === "clips" ? "reel" : m.media_type === 2 ? "video" : "post",
    title: (caption || (author ? `Instagram post from @${author}` : "")).slice(0, 300) || null,
    channel: author,
    channelHandle: author ? `/@${author}` : null,
    duration: null,
    isAd: false,
  };
}

async function harvestInstagram() {
  // Liked and saved are tried separately so one failing doesn't block the other.
  const items = [], errors = {};
  const lists = {
    saved: ["/api/v1/feed/saved/posts/", (d) => (d?.items || []).map((x) => x.media || x)],
  };
  for (const [name, [path, pick]] of Object.entries(lists)) {
    try { for (const m of pick(await igJson(path))) items.push(igItem(m)); }
    catch (e) { errors[name] = e.message; }
  }
  const out = { found: items.filter(Boolean).length, added: await storeHistory(items) };
  if (Object.keys(errors).length) out.errors = errors;
  return out;
}

function rememberXUsername() {
  const href = document.querySelector('a[data-testid="AppTabBar_Profile_Link"]')?.getAttribute("href");
  if (href) chrome.storage.local.set({ xUsername: href.slice(1) });
}

(async () => {
  if (PLATFORM.name === "x") setTimeout(rememberXUsername, 3000);

  // Run if the background just started a sync (flag in storage, set < 2 min ago),
  // or if you opened your own likes/upvotes/saves page yourself.
  // Reddit and Instagram read JSON from any page, so each has its own "sync running" flag
  // (set by background.js, valid for 2 minutes). X and YouTube only run on their history pages.
  const JSON_PLATFORMS = ["reddit", "instagram"];
  const flag = `historyPending_${PLATFORM.name}`;
  const { [flag]: pendingSince = 0 } = await chrome.storage.local.get(flag);
  const syncRunning = Date.now() - pendingSince < 2 * 60 * 1000;
  const isHistoryPage = PLATFORM.historyPage?.test(location.pathname);
  const isJson = JSON_PLATFORMS.includes(PLATFORM.name);
  if (!isHistoryPage && !(syncRunning && isJson)) return;
  if (isJson && !isHistoryPage) await chrome.storage.local.set({ [flag]: 0 });  // one run per sync

  let result;
  try {
    const harvest = { reddit: harvestReddit, x: harvestX, youtube: harvestYouTube, instagram: harvestInstagram }[PLATFORM.name];
    result = await harvest();
  } catch (e) {
    result = { error: e.message };
  }
  console.log("[mirror] history", PLATFORM.name, location.pathname, result);
  try { chrome.runtime?.sendMessage?.({ type: "historyDone", result })?.catch?.(() => {}); } catch {}
})();