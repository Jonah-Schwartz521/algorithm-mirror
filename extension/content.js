// Confirm the script ran on this page
console.log("[mirror] loaded", location.href);

// All selectors in one place. If YouTube changes its layout, fix them here.
const SEL = {
  tile: "ytd-rich-item-renderer",
  watchLink: 'a[href*="/watch?v="]',
  title: "a.ytLockupMetadataViewModelTitle",
  channel: 'a[href^="/@"]',
  ad: "ytd-ad-slot-renderer, [aria-label='Sponsored']",
 shortTitle: "h3.shortsLockupViewModelHostMetadataTitle",
};

function getTiles() {
  return document.querySelectorAll(SEL.tile);
}

// Pull the fields we care about out of one tile
// Returns null for tiles we don't track (games, empty, placeholders).
function extractTile(tile, position) {
    const link = tile.querySelector("a[href]");
    const href = link?.getAttribute("href") || "";

    // ID and type come from the URL shape, which is more stable than class names 
    let itemId = null, mediaType = null;
    const watch = href.match(/\/watch\?v=([\w-]+)/);
    const short = href.match(/\/shorts\/([\w-]+)/);
    if (watch) { itemId = watch[1]; mediaType = "video"; }
    else if (short) { itemId = short[1]; mediaType = "short"; }
    else return null;    

    const channel = tile.querySelector(SEL.channel);
    const durationEl = tile.querySelector(SEL.watchLink);
    const titleEl = tile.querySelector(mediaType === "short" ? SEL.shortTitle : SEL.title) || tile.querySelector("h3");
    

    return {
        itemId,
        mediaType,
        title: titleEl?.textContent.trim() || null,
        channel: channel?.textContent.trim() || null,
        channelHandle: channel?.getAttribute("href") || null,
        duration: mediaType === "video" ? durationEl?.textContent.trim() || null : null,
        isAd: !!tile.querySelector(SEL.ad),
        position,
    };
    }


// Tiles we've already attached an observer to
const tracked = new WeakSet();
// For tiles currently on screen: when they entered
const onScreenSince = new WeakMap();

// Fires when a tile crosses 50% visible, in either direction
const viewObserver = new IntersectionObserver((entries) => {
  const now = Date.now();
  for (const entry of entries) {
    const tile = entry.target;
    if (entry.isIntersecting) {
      onScreenSince.set(tile, now);
    } else if (onScreenSince.has(tile)) {
      const enteredAt = onScreenSince.get(tile);
      onScreenSince.delete(tile);
      const item = extractTile(tile, [...getTiles()].indexOf(tile));
      if (!item) continue;
      console.log("[mirror] impression", { ...item, enteredAt, dwellMs: now - enteredAt });
    }
  }
}, { threshold: 0.5 });

// Attach the observer to any tile we haven't seen yet
function scanTiles() {
  getTiles().forEach((tile) => {
    if (tracked.has(tile)) return;
    tracked.add(tile);
    viewObserver.observe(tile);
  });
}

// YouTube adds tiles as you scroll. Re-scan whenever the page changes,
// debounced so we don't scan 100 times a second.
let scanTimer = null;
const observer = new MutationObserver(() => {
  clearTimeout(scanTimer);
  scanTimer = setTimeout(scanTiles, 500);
});
observer.observe(document.body, { childList: true, subtree: true });

scanTiles();