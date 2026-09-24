// LinkedIn adapter (feed only). LinkedIn's current site has no post ids or stable
// class names, so we find each post by the hidden "Feed post" heading it carries,
// and build a stable id from the author + the post's main text.
const LI_MARK = "Feed post";
const LI_NOISE = new RegExp([
  "^(Feed post|Promoted|Suggested|Follow|\\+ Follow|Following|Like|Comment|Repost|Send|Edited|…more|more|…see more)$",
  "^•? ?\\d(st|nd|rd|th)\\+?$",                       // • 1st
  "^[\\d,.]+K? followers$",                           // 278,018 followers
  "^\\d+(s|m|h|d|w|mo|y|yr)s? •.*$",                  // 1w •
  "^[\\d,.]+K?( (reactions?|comments?|reposts?))?$",  // 45 / 12 comments
  "^[\\d,.]+ (comments?|reposts?) ?(•.*)?$",
  " and [\\d,]+ others?$",
  " (likes|loves|celebrates|supports|commented on|reposted) this$",
  "^Visible to anyone",
].join("|"), "i");

function liMarkers(root) {
  return [...root.querySelectorAll("h2, h3, span")].filter(
    (e) => e.childElementCount === 0 && e.textContent.trim() === LI_MARK);
}

function liHash(s) {  // FNV-1a: same input, same id, every session
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193); }
  return (h >>> 0).toString(36);
}

const PLATFORM = {
  name: "linkedin",
  tile: "div[componentkey]",
  historyPage: null,   // no account sync for LinkedIn (it aggressively detects automation)
  extract(tile) {
    if (liMarkers(tile).length !== 1) return null;             // must hold exactly one post
    const outer = tile.parentElement?.closest("[componentkey]");
    if (outer && liMarkers(outer).length === 1) return null;   // a bigger box holds this same post
    const who = [...tile.querySelectorAll('a[href*="/in/"], a[href*="/company/"]')]
      .find((a) => (a.innerText || "").trim());
    const author = who ? who.innerText.trim().split("\n")[0].trim() : null;
    let handle = null;
    try { handle = who ? new URL(who.href, location.origin).pathname.replace(/\/$/, "") : null; } catch {}
    const raw = tile.innerText || "";
    const lines = raw.split("\n").map((l) => l.trim())
      .filter((l) => l && l !== author && !LI_NOISE.test(l));
    if (!lines.length && !author) return null;
    const main = lines.reduce((a, b) => (b.length > a.length ? b : a), "");  // longest line = the post itself
    return {
      itemId: `li:${liHash(`${handle || author}|${main.slice(0, 200)}`)}`,
      mediaType: tile.querySelector("video") ? "video" : "post",
      title: (lines.join(" ").replace(/\s+/g, " ").trim() || `LinkedIn post from ${author}`).slice(0, 300),
      channel: author,
      channelHandle: handle,
      duration: null,
      isAd: /(^|\n)\s*Promoted\s*(\n|$)/.test(raw),
    };
  },
};

// ---- Reactions, recorded as they happen (no background tabs, no extra requests) ----
// When you click Like (or pick Celebrate/Support/... from the reaction menu) on a post,
// log that post as engagement. Clicking again to un-react is ignored.
const LI_REACT = /^(Like|Celebrate|Support|Love|Insightful|Funny|Curious)$/i;
const LI_REACT_LABEL = /^(React\b|Like\b|Celebrate\b|Support\b|Love\b|Insightful\b|Funny\b|Curious\b)/i;
let liLastPost = null;            // post under the Like button you last hovered (the reaction menu floats outside it)
const liReacted = new Set();      // one engagement per post per page load

function liPostFor(el) {
  for (let t = el.closest("[componentkey]"); t; t = t.parentElement?.closest("[componentkey]")) {
    const it = PLATFORM.extract(t);
    if (it) return it;
  }
  return null;
}
const liIsReactButton = (b) =>
  !!b && (LI_REACT.test((b.innerText || "").trim()) || LI_REACT_LABEL.test(b.getAttribute("aria-label") || ""));

document.addEventListener("mouseover", (e) => {
  const b = e.target.closest?.("button");
  if (liIsReactButton(b)) { const p = liPostFor(b); if (p) liLastPost = p; }
}, true);

function liReactClicks(e) {
  const b = e.target.closest?.("button");
  if (!liIsReactButton(b)) return;
  if (b.getAttribute("aria-pressed") === "true") return;          // un-reacting
  const post = liPostFor(b) || liLastPost;
  if (!post || liReacted.has(post.itemId)) return;
  liReacted.add(post.itemId);
  saveImpression(
    { ...post, platform: PLATFORM.name },
    { itemId: post.itemId, position: 0, enteredAt: Date.now(), dwellMs: 0, source: "live", evidence: "engagement" }
  ).then(() => console.log("[mirror] reacted", post.itemId));
}
document.addEventListener("click", liReactClicks, true);
