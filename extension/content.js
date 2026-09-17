// Confirm the script ran on this page
console.log("[mirror] loaded", location.href);

// All selectors in one place. If YouTube changes its layout, fix them here.
const SEL = {
  tile: "ytd-rich-item-renderer",
  watchLink: 'a[href*="/watch?v="]',
  title: "a.ytLockupMetadataViewModelTitle",
  channel: 'a[href^="/@"]',
  ad: "ytd-ad-slot-renderer, [aria-label='Sponsored']",
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


    return {
        itemId,
        mediaType,
        title: tile.querySelector(SEL.title)?.textContent.trim() || null,
        channel: channel?.textContent.trim() || null,
        channelHandle: channel?.getAttribute("href") || null,
        duration: mediaType === "video" ? durationEl?.textContent.trim() || null : null,
        isAd: !!tile.querySelector(SEL.ad),
        position,
    };
    }

// Wait for YouTube to build the feed, then log the first 10 tiles
// (temporary, MutationObserver replaces this later)
setTimeout(() => {
  const tiles = getTiles();
  console.log("[mirror] tiles found:", tiles.length);
  [...tiles].slice(0, 10).forEach((t, i) => {
    const item = extractTile(t, i);
    if (item) console.log("[mirror] tile", item);
  });
}, 3000);