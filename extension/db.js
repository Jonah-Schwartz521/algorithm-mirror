// Local storage for captured feed data. Raw content never leaves this machine
// until the sync step explicitly sends it.

const DB_NAME = "algorithm-mirror";
const DB_VERSION = 1;

let dbPromise = null;

// Open (or create) the database. Called once, reused after.
function openDB() {
  if (dbPromise) return dbPromise;
  dbPromise = new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      // One row per video/short, keyed by YouTube's own ID
      db.createObjectStore("items", { keyPath: "itemId" });
      // One row per impression, auto-numbered, indexed for sync later
      const events = db.createObjectStore("events", { keyPath: "id", autoIncrement: true });
      events.createIndex("synced", "synced");
      events.createIndex("enteredAt", "enteredAt");
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
  return dbPromise;
}

// Save an item (upsert) and its impression event in one transaction
async function saveImpression(item, event) {
  const db = await openDB();
  const tx = db.transaction(["items", "events"], "readwrite");
  tx.objectStore("items").put(item);
  tx.objectStore("events").add({ ...event, synced: 0 });
  return new Promise((resolve, reject) => {
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}

// Pull up to `limit` events that haven't been synced yet
async function getUnsyncedEvents(limit = 50) {
  const db = await openDB();
  return new Promise((resolve, reject) => {
    const req = db.transaction("events").objectStore("events").index("synced").getAll(0, limit);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// Fetch the item rows for a set of itemIds
async function getItems(itemIds) {
  const db = await openDB();
  const store = db.transaction("items").objectStore("items");
  return Promise.all([...new Set(itemIds)].map((id) => new Promise((resolve) => {
    const req = store.get(id);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => resolve(null);
  }))).then((rows) => rows.filter(Boolean));
}

// Flip synced=1 on the events the server accepted
async function markSynced(eventIds) {
  const db = await openDB();
  const tx = db.transaction("events", "readwrite");
  const store = tx.objectStore("events");
  for (const id of eventIds) {
    const req = store.get(id);
    req.onsuccess = () => { if (req.result) store.put({ ...req.result, synced: 1 }); };
  }
  return new Promise((resolve, reject) => {
    tx.oncomplete = resolve;
    tx.onerror = () => reject(tx.error);
  });
}