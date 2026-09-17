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
function extractTile(tile, position) {
  const watch = tile.querySelector(SEL.watchLink);
  const href = watch?.getAttribute("href") || "";
  const videoId = new URLSearchParams(href.split("?")[1]).get("v");
  const channel = tile.querySelector(SEL.channel);

  return {
    videoId,
    title: tile.querySelector(SEL.title)?.textContent.trim() || null,
    channel: channel?.textContent.trim() || null,
    channelHandle: channel?.getAttribute("href") || null,
    duration: watch?.textContent.trim() || null,
    isAd: !!tile.querySelector(SEL.ad),
    position,
  };
}

// Wait for YouTube to build the feed, then log the first 5 tiles
// (temporary, MutationObserver replaces this later)
setTimeout(() => {
  const tiles = getTiles();
  console.log("[mirror] tiles found:", tiles.length);
  [...tiles].slice(0, 5).forEach((t, i) => console.log(extractTile(t, i)));
}, 3000);