// Account-history sync scheduler.
// Every few hours, opens Reddit and X in quiet background tabs so history.js can read
// YOUR upvotes/saves/likes/bookmarks. Those lists are account-level, so they include
// what you did on your phone. history.js tags everything evidence="engagement".

const HISTORY_EVERY_MIN = 180;   // how often to run
const CLEANUP_AFTER_MIN = 4;     // force-close any history tab still open after this

function ensureAlarm() {
  chrome.alarms.get("history-sync", (a) => {
    if (!a) chrome.alarms.create("history-sync", { delayInMinutes: 1, periodInMinutes: HISTORY_EVERY_MIN });
  });
}
// Show a "!" on the toolbar icon until the person joins with a study code.
async function updateBadge() {
  const { studyCode } = await chrome.storage.local.get("studyCode");
  chrome.action.setBadgeText({ text: studyCode ? "" : "!" });
  chrome.action.setBadgeBackgroundColor({ color: "#d93025" });
}

chrome.runtime.onInstalled.addListener(() => { ensureAlarm(); updateBadge(); });
chrome.runtime.onStartup.addListener(() => { ensureAlarm(); updateBadge(); });

chrome.alarms.onAlarm.addListener(async (alarm) => {
  if (alarm.name === "history-sync") await openHistoryTabs();
  if (alarm.name === "history-cleanup") await closeHistoryTabs();
});

async function openHistoryTabs() {
  await closeHistoryTabs();  // leftovers from a previous run
  const { xUsername, liUsername } = await chrome.storage.local.get(["xUsername", "liUsername"]);
  const urls = [
    "https://www.reddit.com/settings/",  // any Reddit page works; history.js fetches upvoted/saved JSON
    "https://x.com/i/bookmarks",
    "https://www.youtube.com/feed/history",  // everything you watched, any device
    "https://www.instagram.com/",  // any page works; history.js fetches liked/saved JSON
  ];
  // X likes need your handle; history.js learns it the first time you open x.com normally.
  if (xUsername) urls.push(`https://x.com/${xUsername}/likes`);
  urls.push("https://www.linkedin.com/my-items/saved-posts/");
  // LinkedIn reactions need your handle; history.js learns it the first time you open linkedin.com.
  if (liUsername) urls.push(`https://www.linkedin.com/in/${liUsername}/recent-activity/reactions/`);

  // Tell history.js "a sync is running" through storage (Reddit strips URL #markers).
  const now = Date.now();
  await chrome.storage.local.set({ historyPendingSince: now, historyPending_reddit: now, historyPending_instagram: now });

  const ids = [];
  for (const url of urls) {
    const tab = await chrome.tabs.create({ url, active: false });
    ids.push(tab.id);
  }
  await chrome.storage.local.set({ historyTabs: ids });
  chrome.alarms.create("history-cleanup", { delayInMinutes: CLEANUP_AFTER_MIN });
  console.log("[mirror] history sync opened", urls);
}

async function closeHistoryTabs() {
  const { historyTabs = [] } = await chrome.storage.local.get("historyTabs");
  for (const id of historyTabs) { try { await chrome.tabs.remove(id); } catch {} }
  await chrome.storage.local.set({ historyTabs: [] });
}

// history.js reports back when it's done; close the tab only if WE opened it.
chrome.runtime.onMessage.addListener((msg, sender) => {
  if (msg?.type !== "historyDone" || !sender.tab) return;
  console.log("[mirror] history done", sender.tab.url, msg.result);
  chrome.storage.local.get("historyTabs").then(({ historyTabs = [] }) => {
    if (!historyTabs.includes(sender.tab.id)) return;
    chrome.tabs.remove(sender.tab.id).catch(() => {});
    chrome.storage.local.set({ historyTabs: historyTabs.filter((id) => id !== sender.tab.id) });
  });
});