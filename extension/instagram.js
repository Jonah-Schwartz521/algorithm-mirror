// Instagram adapter: history sync only (likes + saved). No live feed capture here.
const PLATFORM = {
  name: "instagram",
  tile: null,
  // Your own likes / saved pages.
  historyPage: /^\/(your_activity\/interactions\/likes|[^/]+\/saved)(\/|$)/,
  extract() { return null; },
};
