// YouTube adapter: how to find tiles and what to pull out of them
const PLATFORM = {
  name: "youtube",
  tile: "ytd-rich-item-renderer",
  // Your watch history (includes phone viewing). Live capture skips it; history.js reads it.
  historyPage: /^\/feed\/history/,
  extract(tile) {
    // Target the video link directly; the first link in a new-layout card can be the channel avatar
    const link = tile.querySelector('a[href*="/watch?v="], a[href*="/shorts/"]');
    const href = link?.getAttribute("href") || "";
    let itemId = null, mediaType = null;
    const watch = href.match(/[?&]v=([\w-]{11})/);
    const short = href.match(/\/shorts\/([\w-]{11})/);
    if (watch) { itemId = watch[1]; mediaType = "video"; }
    else if (short) { itemId = short[1]; mediaType = "short"; }
    else return null; // playables, shelves, etc.

    // Skip the avatar link (no text); take the first channel link that has a name
    const channel = [...tile.querySelectorAll('a[href^="/@"], a[href^="/channel/"], ytd-channel-name a')]
      .find(a => a.textContent.trim());

    const h3 = tile.querySelector("h3");
    const title =
      h3?.getAttribute("title") ||
      tile.querySelector("#video-title")?.textContent.trim() ||
      h3?.textContent.trim() ||
      null;

    const duration = mediaType === "video"
      ? tile.querySelector("badge-shape, ytd-thumbnail-overlay-time-status-renderer #text")?.textContent.trim() || null
      : null;

    return {
      itemId, mediaType,
      title,
      channel: channel?.textContent.trim() || null,
      channelHandle: channel?.getAttribute("href") || null,
      duration,
      isAd: !!tile.querySelector("ytd-ad-slot-renderer, ytd-in-feed-ad-layout-renderer, [aria-label='Sponsored']"),
    };
  },
};