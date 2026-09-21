// Reddit adapter: posts expose everything as attributes on <shreddit-post>
const PLATFORM = {
  name: "reddit",
  tile: "shreddit-post, shreddit-ad-post",
  extract(tile) {
    const itemId = tile.getAttribute("id");
    if (!itemId) return null;
    const sub = tile.getAttribute("subreddit-prefixed-name");
    return {
      itemId,
      mediaType: tile.getAttribute("post-type") || "post",
      title: tile.getAttribute("post-title") || null,
      channel: sub,
      channelHandle: sub ? `/${sub}` : null,
      duration: null,
      isAd: tile.tagName === "SHREDDIT-AD-POST" || tile.hasAttribute("promoted"),
    };
  },
};