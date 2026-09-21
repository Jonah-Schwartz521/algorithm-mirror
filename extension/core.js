// Shared capture logic. Expects a PLATFORM adapter to be loaded first.
console.log("[mirror] loaded", PLATFORM.name, location.href);

const tracked = new WeakSet();
const onScreenSince = new WeakMap();

function getTiles() {
  return document.querySelectorAll(PLATFORM.tile);
}

const viewObserver = new IntersectionObserver((entries) => {
  const now = Date.now();
  for (const entry of entries) {
    const tile = entry.target;
    if (entry.isIntersecting) {
      onScreenSince.set(tile, now);
    } else if (onScreenSince.has(tile)) {
      const enteredAt = onScreenSince.get(tile);
      onScreenSince.delete(tile);
      const item = PLATFORM.extract(tile);
      if (!item) continue;
      const position = [...getTiles()].indexOf(tile);
      saveImpression(
        { ...item, platform: PLATFORM.name },
        { itemId: item.itemId, position, enteredAt, dwellMs: now - enteredAt, source: "live", evidence: "impression" }
      ).then(() => console.log("[mirror] saved", item.itemId, now - enteredAt));
    }
  }
}, { threshold: 0.5 });

function scanTiles() {
  getTiles().forEach((tile) => {
    if (tracked.has(tile)) return;
    tracked.add(tile);
    viewObserver.observe(tile);
  });
}

let scanTimer = null;
new MutationObserver(() => {
  clearTimeout(scanTimer);
  scanTimer = setTimeout(scanTiles, 500);
}).observe(document.body, { childList: true, subtree: true });

scanTiles();