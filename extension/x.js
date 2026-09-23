// X adapter: tweets are <article data-testid="tweet">, with stable data-testid hooks inside
const PLATFORM = {
  name: "x",
  tile: 'article[data-testid="tweet"]',
  // Pages that list YOUR activity, not the feed. Live capture skips these.
  historyPage: /^\/(i\/bookmarks|i\/history\/likes|[^/]+\/likes)(\/|$)/,
  extract(tile) {
    const link = tile.querySelector('a[href*="/status/"]');
    const m = link?.getAttribute("href").match(/^\/([^/]+)\/status\/(\d+)/);
    if (!m) return null;
    const [, author, statusId] = m;
    const text = tile.querySelector('[data-testid="tweetText"]')?.innerText.trim() || null;
    return {
      itemId: statusId,
      mediaType: tile.querySelector("video") ? "video" : tile.querySelector('[data-testid="tweetPhoto"]') ? "image" : "post",
      title: text ? text.slice(0, 300) : null,
      channel: author,
      channelHandle: `/@${author}`,
      duration: null,
      isAd: !!tile.querySelector('[data-testid="placementTracking"]') || /^Ad$/m.test(tile.innerText),
    };
  },
};