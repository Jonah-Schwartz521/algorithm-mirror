// Extension popup: join the study with a code, then quick links to your dashboard.

const $ = (id) => document.getElementById(id);
const PHASES = {
  "not started": "Study hasn't started yet",
  baseline: "Baseline: just use your apps normally",
  treatment: "Treatment week: follow your assigned topic on your phone",
  washout: "Washout: back to normal use",
  finished: "Study finished. Thank you!",
};

// Same token logic as sync.js: one random id per install, created on first use.
async function getUserToken() {
  const { userToken } = await chrome.storage.local.get("userToken");
  if (userToken) return userToken;
  const token = crypto.randomUUID();
  await chrome.storage.local.set({ userToken: token });
  return token;
}

async function showEnrolled(code, token) {
  $("loading").hidden = true;
  $("join").hidden = true;
  $("enrolled").hidden = false;
  $("my-code").textContent = code;
  $("dash").href = `${SERVER}/?token=${encodeURIComponent(token)}`;
  $("upload").href = `${SERVER}/upload?token=${encodeURIComponent(token)}`;
  try {
    const p = await (await fetch(`${SERVER}/users/${encodeURIComponent(token)}/participant`)).json();
    $("my-phase").textContent = PHASES[p.phase] || "Enrolled";
  } catch {
    $("my-phase").textContent = "Can't reach the study server right now";
  }
}

function showJoin() {
  $("loading").hidden = true;
  $("join").hidden = false;
  $("code").focus();
}

$("join").addEventListener("submit", async (e) => {
  e.preventDefault();
  const code = $("code").value.trim().toUpperCase();
  if (!code) return;
  $("join-btn").disabled = true;
  $("err").textContent = "";
  try {
    const userToken = await getUserToken();
    const res = await fetch(`${SERVER}/enroll`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ code, userToken }),
    });
    const d = await res.json();
    if (!res.ok) throw new Error(d.error || `HTTP ${res.status}`);
    // On a reinstall the server hands back the participant's existing token; adopt it so data stays together.
    await chrome.storage.local.set({ userToken: d.userToken, studyCode: d.studyCode });
    chrome.action.setBadgeText({ text: "" });
    showEnrolled(d.studyCode, d.userToken);
  } catch (err) {
    $("err").textContent = err.message === "Failed to fetch" ? "Can't reach the study server. Try again in a minute." : err.message;
    $("join-btn").disabled = false;
  }
});

(async () => {
  const { studyCode, userToken } = await chrome.storage.local.get(["studyCode", "userToken"]);
  if (studyCode && userToken) showEnrolled(studyCode, userToken);
  else showJoin();
})();