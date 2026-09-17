// Sends unsynced events to the server every 30s while a YouTube tab is open.

const SYNC_URL = "http://localhost:8000/sync";
const SYNC_INTERVAL_MS = 30000;

// Random per-install token. Never the user's name or email.
async function getUserToken() {
  const { userToken } = await chrome.storage.local.get("userToken");
  if (userToken) return userToken;
  const token = crypto.randomUUID();
  await chrome.storage.local.set({ userToken: token });
  return token;
}

async function syncOnce() {
  const events = await getUnsyncedEvents(50);
  if (events.length === 0) return;
  const items = await getItems(events.map((e) => e.itemId));
  const userToken = await getUserToken();

  try {
    const res = await fetch(SYNC_URL, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ userToken, items, events }),
    });
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const { accepted } = await res.json();
    await markSynced(accepted);
    console.log("[mirror] synced", accepted.length, "events");
  } catch (err) {
    console.log("[mirror] sync failed, will retry:", err.message);
  }
}

setInterval(syncOnce, SYNC_INTERVAL_MS);
setTimeout(syncOnce, 5000); // first attempt shortly after load