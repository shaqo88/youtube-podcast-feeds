(function (root) {
  "use strict";
  function escapeMarkup(value) {
    const entities = { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" };
    return String(value ?? "").replace(/[&<>"']/g, (character) => entities[character]);
  }
  function recentEpisodes(episodes, followedSlugs = null, limit = 20) {
    const followed = followedSlugs === null ? null : new Set(followedSlugs);
    const seen = new Set();
    return episodes.filter((episode) => {
      if (!episode?.id || seen.has(episode.id) || (followed && !followed.has(episode.show_slug))) return false;
      seen.add(episode.id);
      return true;
    }).sort((a, b) => String(b.published || "").localeCompare(String(a.published || "")) || a.id.localeCompare(b.id)).slice(0, limit);
  }
  function pageEpisodes(episodes, page = 0, size = 20) {
    const start = Math.max(0, page) * size;
    return { episodes: episodes.slice(start, start + size), hasMore: start + size < episodes.length };
  }
  function retryDecoderOnce(audio, active, retry) {
    if (!active || audio.error?.code !== 3 || audio.dataset.decodeRetried === "true") return false;
    audio.dataset.decodeRetried = "true";
    audio.dataset.playbackFailed = "true";
    retry();
    return true;
  }
  const api = { escapeMarkup, recentEpisodes, pageEpisodes, retryDecoderOnce };
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  else root.TorahPodListening = api;
})(typeof window === "undefined" ? globalThis : window);
