// YouTube adapter: how to find tiles and what to pull out of them
const PLATFORM = {
  name: "youtube",
  tile: "ytd-rich-item-renderer",
  // Your watch history (includes phone viewing). Live capture skips it; history.js reads it.
  historyPage: /^\/feed\/history/,
  extract(tile) {
    const link = tile.querySelector("a[href]");
    const href = link?.getAttribute("href") || "";
    let itemId = null, mediaType = null;
    const watch = href.match(/\/watch\?v=([\w-]+)/);
    const short = href.match(/\/shorts\/([\w-]+)/);
    if (watch) { itemId = watch[1]; mediaType = "video"; }
    else if (short) { itemId = short[1]; mediaType = "short"; }
    else return null;

    const channel = tile.querySelector('a[href^="/@"]');
    const titleEl =
      tile.querySelector(mediaType === "short" ? "h3.shortsLockupViewModelHostMetadataTitle" : "a.ytLockupMetadataViewModelTitle") ||
      tile.querySelector("h3");
    return {
      itemId, mediaType,
      title: titleEl?.textContent.trim() || null,
      channel: channel?.textContent.trim() || null,
      channelHandle: channel?.getAttribute("href") || null,
      duration: mediaType === "video" ? tile.querySelector('a[href*="/watch?v="]')?.textContent.trim() || null : null,
      isAd: !!tile.querySelector("ytd-ad-slot-renderer, [aria-label='Sponsored']"),
    };
  },
};