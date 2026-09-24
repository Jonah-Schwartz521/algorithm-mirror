// LinkedIn adapter. Feed posts carry an id like "urn:li:activity:123" on the card
// (data-urn / data-id), so we key on that instead of LinkedIn's class names.
const LI_URN = /urn:li:(activity|ugcPost|share):(\d+)/;
const LI_TILE = 'div[data-id*="urn:li:"], div[data-urn*="urn:li:"], div.feed-shared-update-v2';

function liFindUrn(tile) {
  for (const el of [tile, ...tile.querySelectorAll("[data-urn], [data-id]")]) {
    const m = `${el.getAttribute("data-urn") || ""} ${el.getAttribute("data-id") || ""}`.match(LI_URN);
    if (m) return m;
  }
  const a = tile.querySelector('a[href*="urn:li:activity:"], a[href*="urn:li:ugcPost:"], a[href*="urn:li:share:"]');
  return a ? decodeURIComponent(a.getAttribute("href")).match(LI_URN) : null;
}

const firstText = (root, sels) => {
  for (const s of sels) {
    const t = root.querySelector(s)?.innerText?.trim();
    if (t) return t;
  }
  return null;
};

const PLATFORM = {
  name: "linkedin",
  tile: LI_TILE,
  // Your own reactions / saved-posts pages. Live capture skips these.
  historyPage: /^\/(in\/[^/]+\/recent-activity\/reactions|my-items\/saved-posts)(\/|$)/,
  extract(tile) {
    if (tile.parentElement?.closest(LI_TILE)) return null;  // nested card (reshare): count the outer one
    const m = liFindUrn(tile);
    if (!m) return null;
    const actorLink = tile.querySelector(
      '.update-components-actor__meta-link, .update-components-actor a[href*="/in/"], .update-components-actor a[href*="/company/"], a[href*="/in/"], a[href*="/company/"]');
    const author = firstText(tile, [
      '.update-components-actor__title span[aria-hidden="true"]',
      '.update-components-actor__name span[aria-hidden="true"]',
      ".update-components-actor__title", ".update-components-actor__name", ".feed-shared-actor__name",
    ]) || actorLink?.innerText?.trim().split("\n")[0] || null;
    const text = firstText(tile, [
      ".update-components-text", ".feed-shared-update-v2__description", ".feed-shared-inline-show-more-text",
      ".feed-shared-text",
    ]);
    let handle = null;
    try { handle = actorLink ? new URL(actorLink.href, location.origin).pathname.replace(/\/$/, "") : null; } catch {}
    const head = (tile.innerText || "").slice(0, 400);
    return {
      itemId: `li:${m[1]}:${m[2]}`,
      mediaType: tile.querySelector("video") ? "video"
        : tile.querySelector(".update-components-article, .feed-shared-article") ? "article"
        : tile.querySelector(".update-components-image, .feed-shared-image") ? "image" : "post",
      title: (text || (author ? `LinkedIn post from ${author}` : "")).replace(/\s+/g, " ").slice(0, 300) || null,
      channel: author,
      channelHandle: handle,
      duration: null,
      isAd: /\bPromoted\b/.test(head) || /sponsored/i.test(tile.getAttribute("data-id") || ""),
    };
  },
};
