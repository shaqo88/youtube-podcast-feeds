(() => {
  const labels = window.TORAH_POD_LABELS || {};
  const html = document.documentElement;
  const basePath = window.TORAH_POD_BASE || "";
  const progressPrefix = "torahpod-progress:";
  const lastKey = "torahpod-last-episode";
  const followsKey = "torahpod:v1:follows";
  const queueKey = "torahpod:v1:queue";
  const episodeStateKey = "torahpod:v1:episode-state";
  const speedKey = "torahpod:v1:playback-rate";
  const playbackRates = [1, 1.25, 1.5, 1.75, 2];
  const player = document.querySelector("[data-player]");
  const playerToggle = document.querySelector("[data-player-toggle]");
  const playerTitle = document.querySelector("[data-player-title]");
  const playerShow = document.querySelector("[data-player-show]");
  const playerTime = document.querySelector("[data-player-time]");
  const playerSeek = document.querySelector("[data-player-seek]");
  const playerPrev = document.querySelector("[data-player-prev]");
  const playerNext = document.querySelector("[data-player-next]");
  const playerSpeed = document.querySelector("[data-player-speed]");
  const playerClose = document.querySelector("[data-player-close]");
  const resume = document.querySelector("[data-resume]");
  const resumeTitle = document.querySelector("[data-resume-title]");
  const resumeShow = document.querySelector("[data-resume-show]");
  const resumeButton = document.querySelector("[data-resume-play]");
  const resumeClose = document.querySelector("[data-resume-close]");
  const parser = new DOMParser();
  const audioDock = document.createElement("div");
  let activeAudio = null;
  let activeEpisode = null;
  let activeState = null;
  let renderedActiveQueueId = "";
  let closingAudio = null;
  let playerClosed = false;
  let seeking = false;
  let resumeDismissedAt = Number(safeGet("torahpod-resume-dismissed-at") || 0);
  let resumeDismissedId = String(safeGet("torahpod-resume-dismissed-id") || "");
  let resumeShownId = "";
  let resumeVisibleForId = "";

  try {
    resumeShownId = sessionStorage.getItem("torahpod-resume-shown-id") || "";
  } catch {
    resumeShownId = "";
  }

  audioDock.hidden = true;
  audioDock.dataset.audioDock = "";
  document.body.append(audioDock);

  function t(key) {
    const lang = html.lang === "en" ? "en" : "he";
    return (labels[lang] && labels[lang][key]) || (labels.he && labels.he[key]) || key;
  }

  function formatTime(value) {
    const total = Math.max(0, Math.floor(Number(value) || 0));
    const hours = Math.floor(total / 3600);
    const minutes = Math.floor((total % 3600) / 60);
    const seconds = total % 60;
    if (hours) return `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
    return `${minutes}:${String(seconds).padStart(2, "0")}`;
  }

  function playbackRate() {
    const saved = Number(safeGet(speedKey) || 1);
    return playbackRates.includes(saved) ? saved : 1;
  }

  function formatRate(rate) {
    return `${Number(rate).toString()}x`;
  }

  function applyPlaybackRate(audio = activeAudio) {
    const rate = playbackRate();
    if (audio) audio.playbackRate = rate;
    if (playerSpeed) {
      const label = `${t("playback_speed")} ${formatRate(rate)}`;
      playerSpeed.textContent = formatRate(rate);
      playerSpeed.setAttribute("aria-label", label);
      playerSpeed.setAttribute("title", label);
    }
  }

  function cyclePlaybackRate() {
    const current = playbackRate();
    const index = playbackRates.indexOf(current);
    const next = playbackRates[(index + 1) % playbackRates.length];
    safeSet(speedKey, next);
    applyPlaybackRate();
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value || "");
    return node.innerHTML;
  }

  function progressKey(id) {
    return `${progressPrefix}${id}`;
  }

  function safeGet(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "null");
    } catch {
      return null;
    }
  }

  function safeSet(key, value) {
    try {
      localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Storage can be unavailable in private modes.
    }
  }

  function safeRemove(key) {
    try {
      localStorage.removeItem(key);
    } catch {
      // Storage can be unavailable in private modes.
    }
  }

  function safeArray(key) {
    const value = safeGet(key);
    return Array.isArray(value) ? value : [];
  }

  function safeObject(key) {
    const value = safeGet(key);
    return value && typeof value === "object" && !Array.isArray(value) ? value : {};
  }

  function showState(card) {
    if (!card) return null;
    const slug = card.dataset.showSlug || "";
    if (!slug) return null;
    return {
      slug,
      title: card.dataset.showTitle || slug,
      author: card.dataset.showAuthor || "",
      artwork: card.dataset.showArtwork ? new URL(card.dataset.showArtwork, location.href).href : "",
      url: card.dataset.showUrl ? new URL(card.dataset.showUrl, location.href).href : `${basePath}${slug}/index.html`,
    };
  }

  function episodeState(article) {
    if (!article) return null;
    const artwork = article.dataset.episodeArtwork || "";
    return {
      id: article.dataset.episodeId || "",
      title: article.dataset.episodeTitle || "",
      show: article.dataset.episodeShow || "",
      showSlug: article.dataset.episodeShowSlug || "",
      artwork: artwork ? new URL(artwork, location.href).href : "",
      src: article.dataset.episodeSrc || "",
      duration: Number(article.dataset.episodeDuration || 0),
      href: `${location.href.split("#")[0]}#${article.id}`,
    };
  }

  function followedShows() {
    return safeArray(followsKey).filter((item) => item && item.slug);
  }

  function saveFollowedShows(items) {
    const unique = [];
    const seen = new Set();
    items.forEach((item) => {
      if (!item?.slug || seen.has(item.slug)) return;
      seen.add(item.slug);
      unique.push(item);
    });
    safeSet(followsKey, unique);
    updateFollowButtons();
    renderLibrary();
    document.dispatchEvent(new CustomEvent("torahpod:librarychange"));
  }

  function isFollowing(slug) {
    return followedShows().some((item) => item.slug === slug);
  }

  function toggleFollow(card) {
    const state = showState(card);
    if (!state) return;
    const items = followedShows();
    if (items.some((item) => item.slug === state.slug)) {
      saveFollowedShows(items.filter((item) => item.slug !== state.slug));
    } else {
      saveFollowedShows([...items, state]);
    }
  }

  function updateFollowButtons() {
    document.querySelectorAll("[data-show-card]").forEach((card) => {
      const state = showState(card);
      const button = card.querySelector("[data-follow-show]");
      if (!state || !button) return;
      const following = isFollowing(state.slug);
      button.dataset.following = String(following);
      button.setAttribute("aria-pressed", String(following));
      button.textContent = following ? t("following") : t("follow");
    });
  }

  function queueEntries() {
    return safeArray(queueKey).filter((item) => item && item.id);
  }

  function saveQueue(entries) {
    const unique = [];
    const seen = new Set();
    entries.forEach((item) => {
      if (!item?.id || seen.has(item.id)) return;
      seen.add(item.id);
      unique.push(item);
    });
    safeSet(queueKey, unique);
    updateQueueUi();
  }

  function isQueued(id) {
    return queueEntries().some((item) => item.id === id);
  }

  function toggleQueued(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const entries = queueEntries();
    if (entries.some((item) => item.id === state.id)) {
      saveQueue(entries.filter((item) => item.id !== state.id));
    } else {
      saveQueue([...entries, state]);
    }
  }

  function promoteQueueEntry(state) {
    if (!state?.id) return;
    const entries = queueEntries().filter((item) => item.id !== state.id);
    saveQueue([state, ...entries]);
  }

  function queueNext(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const entries = queueEntries().filter((item) => item.id !== state.id);
    const activeId = activeState?.id || "";
    if (activeId && activeId !== state.id) {
      const activeIndex = entries.findIndex((item) => item.id === activeId);
      if (activeIndex >= 0) {
        entries.splice(activeIndex + 1, 0, state);
        saveQueue(entries);
        return;
      }
    }
    saveQueue([state, ...entries]);
  }

  function episodeStateMap() {
    return safeObject(episodeStateKey);
  }

  function isPlayed(article) {
    const state = episodeState(article);
    if (!state?.id) return false;
    const saved = safeGet(progressKey(state.id));
    if (saved?.completed) return true;
    return Boolean(episodeStateMap()[state.id]?.played);
  }

  function setPlayed(article, played) {
    const state = episodeState(article);
    if (!state?.id) return;
    const states = episodeStateMap();
    states[state.id] = { played, updatedAt: Date.now() };
    safeSet(episodeStateKey, states);
    updateEpisodeActions(article);
  }

  function updateEpisodeActions(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const queueButton = article.querySelector("[data-queue-add]");
    const playedButton = article.querySelector("[data-toggle-played]");
    const queued = isQueued(state.id);
    const played = isPlayed(article);
    article.dataset.played = String(played);
    if (queueButton) {
      queueButton.textContent = queued ? t("remove_from_queue") : t("add_to_queue");
      queueButton.setAttribute("aria-pressed", String(queued));
    }
    if (playedButton) {
      playedButton.textContent = played ? t("mark_unplayed") : t("mark_played");
      playedButton.setAttribute("aria-pressed", String(played));
    }
  }

  function updateAllEpisodeActions() {
    document.querySelectorAll("[data-episode-id]").forEach(updateEpisodeActions);
  }

  function drawerItemImage(src, alt) {
    if (!src) return "";
    return `<img src="${escapeHtml(src)}" alt="${escapeHtml(alt)}">`;
  }

  function renderLibrary() {
    const list = document.querySelector("[data-library-list]");
    const empty = document.querySelector("[data-library-empty]");
    if (!list) return;
    const items = followedShows();
    list.innerHTML = items.map((item) => `
      <article class="drawer-item">
        ${drawerItemImage(item.artwork || "", "")}
        <div>
          <h3><a href="${escapeHtml(item.url)}">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(item.author || "")}</p>
        </div>
        <button class="button secondary" type="button" data-library-remove="${escapeHtml(item.slug)}">${t("remove_from_library")}</button>
      </article>
    `).join("");
    if (empty) empty.hidden = items.length > 0;
  }

  function renderQueue() {
    const list = document.querySelector("[data-queue-list]");
    const empty = document.querySelector("[data-queue-empty]");
    if (!list) return;
    const clear = document.querySelector("[data-queue-clear]");
    const activeId = activeState?.id || "";
    const items = queueEntries();
    list.innerHTML = items.map((item, index) => `
      <article class="drawer-item${item.id === activeId ? " is-current" : ""}">
        ${drawerItemImage(item.artwork || "", "")}
        <div>
          <h3>${escapeHtml(item.title)}${item.id === activeId ? ` <span class="queue-current">${t("now_playing")}</span>` : ""}</h3>
          <p>${escapeHtml(item.show || "")}</p>
        </div>
        <div class="drawer-actions">
          <button class="button primary" type="button" data-queue-play="${escapeHtml(item.id)}">${t("listen")}</button>
          <button class="button secondary" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="-1" ${index === 0 ? "disabled" : ""}>${t("move_up")}</button>
          <button class="button secondary" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="1" ${index === items.length - 1 ? "disabled" : ""}>${t("move_down")}</button>
          <button class="button secondary" type="button" data-queue-remove="${escapeHtml(item.id)}">${t("remove_from_queue")}</button>
        </div>
      </article>
    `).join("");
    if (empty) empty.hidden = items.length > 0;
    if (clear) clear.hidden = items.length === 0;
    document.querySelectorAll("[data-queue-count]").forEach((node) => {
      node.textContent = String(items.length);
      node.hidden = items.length === 0;
    });
  }

  function updateQueueUi() {
    renderQueue();
    updateAllEpisodeActions();
    updateQueueNavButtons();
  }

  function updateLibraryAndQueueUi() {
    updateFollowButtons();
    renderLibrary();
    updateQueueUi();
  }

  async function playQueuedEntry(entry) {
    if (!entry?.id) return;
    let article = Array.from(document.querySelectorAll("[data-episode-id]"))
      .find((candidate) => candidate.dataset.episodeId === entry.id);
    if (!article && entry.href) {
      await navigateTo(entry.href);
      article = Array.from(document.querySelectorAll("[data-episode-id]"))
        .find((candidate) => candidate.dataset.episodeId === entry.id);
    }
    if (article) playEpisode(article);
  }

  function removeFromQueue(id) {
    saveQueue(queueEntries().filter((item) => item.id !== id));
  }

  function clearQueue() {
    saveQueue([]);
  }

  function moveQueueItem(id, delta) {
    const entries = queueEntries();
    const index = entries.findIndex((item) => item.id === id);
    const nextIndex = index + delta;
    if (index < 0 || nextIndex < 0 || nextIndex >= entries.length) return;
    const [item] = entries.splice(index, 1);
    entries.splice(nextIndex, 0, item);
    saveQueue(entries);
  }

  function playNextQueuedAfter(currentId) {
    const remaining = queueEntries().filter((item) => item.id !== currentId);
    saveQueue(remaining);
    if (remaining[0]) playQueuedEntry(remaining[0]);
  }

  function updateQueueNavButtons() {
    const entries = queueEntries();
    const activeId = activeState?.id || "";
    const index = entries.findIndex((item) => item.id === activeId);
    if (playerPrev) playerPrev.disabled = index <= 0;
    if (playerNext) playerNext.disabled = index < 0 || index >= entries.length - 1;
  }

  function playAdjacentQueued(delta) {
    const entries = queueEntries();
    const activeId = activeState?.id || "";
    const index = entries.findIndex((item) => item.id === activeId);
    const next = entries[index + delta];
    if (!next) return;
    playQueuedEntry(next);
  }

  function openDrawer(drawer) {
    if (!drawer) return;
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = node !== drawer;
    });
    drawer.hidden = false;
  }

  function closeDrawers() {
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = true;
    });
  }

  function loadAudio(audio) {
    if (!audio.src && audio.dataset.audioSrc) {
      audio.src = audio.dataset.audioSrc;
      audio.preload = "metadata";
    }
    applyPlaybackRate(audio);
  }

  function savedProgress(article) {
    const state = episodeState(article);
    return state?.id ? safeGet(progressKey(state.id)) : null;
  }

  function updateEpisodeProgress(article) {
    const marker = article?.querySelector("[data-episode-progress]");
    const saved = savedProgress(article);
    if (!marker || !saved || saved.position < 10 || (saved.duration && saved.duration - saved.position < 20)) {
      if (marker) marker.hidden = true;
      return;
    }
    marker.textContent = `${t("saved_progress")}: ${formatTime(saved.position)}`;
    marker.hidden = false;
  }

  function updateAllEpisodeProgress() {
    document.querySelectorAll("[data-episode-id]").forEach(updateEpisodeProgress);
  }

  function saveCurrentProgress(audio, article) {
    const state = episodeState(article);
    if (!state?.id || !audio || !Number.isFinite(audio.currentTime)) return null;
    const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : state.duration;
    const payload = {
      ...state,
      position: audio.currentTime,
      duration,
      updatedAt: Date.now(),
    };
    if (duration && duration - payload.position < 20) {
      payload.position = 0;
      payload.completed = true;
    }
    safeSet(progressKey(state.id), payload);
    safeSet(lastKey, payload);
    updateEpisodeProgress(article);
    updateEpisodeActions(article);
    updateResume();
    return payload;
  }

  function rememberCurrentEpisode(audio, article) {
    const state = episodeState(article);
    if (!state?.id) return null;
    const saved = safeGet(progressKey(state.id));
    const duration = Number.isFinite(audio?.duration) && audio.duration > 0
      ? audio.duration
      : Number(article?.dataset.episodeDuration || saved?.duration || 0);
    const position = Number.isFinite(audio?.currentTime)
      ? audio.currentTime
      : Number(saved?.position || 0);
    const payload = {
      ...state,
      position,
      duration,
      completed: false,
      updatedAt: Date.now(),
    };
    safeSet(lastKey, payload);
    resumeDismissedId = "";
    resumeShownId = "";
    resumeVisibleForId = "";
    safeRemove("torahpod-resume-dismissed-id");
    safeRemove("torahpod-resume-dismissed-at");
    try {
      sessionStorage.removeItem("torahpod-resume-shown-id");
    } catch {
      // Ignore unavailable storage.
    }
    updateResume();
    return payload;
  }

  function dismissResumeFor(saved) {
    const id = saved?.id || resumeVisibleForId || resumeShownId;
    if (!id) {
      resumeVisibleForId = "";
      if (resume) resume.hidden = true;
      return;
    }
    resumeDismissedId = id;
    resumeDismissedAt = Number(saved?.updatedAt || Date.now());
    resumeVisibleForId = "";
    resumeShownId = id;
    safeSet("torahpod-resume-dismissed-id", resumeDismissedId);
    safeSet("torahpod-resume-dismissed-at", resumeDismissedAt);
    safeRemove(lastKey);
    try {
      sessionStorage.setItem("torahpod-resume-shown-id", resumeShownId);
    } catch {
      // Ignore unavailable storage.
    }
    if (resume) resume.hidden = true;
  }

  function updateMediaSession(audio, state) {
    if (!("mediaSession" in navigator) || !state) return;
    const artwork = state.artwork
      ? [{ src: state.artwork, sizes: "512x512", type: "image/png" }]
      : [];
    navigator.mediaSession.metadata = new MediaMetadata({
      title: state.title,
      artist: state.show || "Torah Pod",
      album: "Torah Pod",
      artwork,
    });
    navigator.mediaSession.playbackState = audio.paused ? "paused" : "playing";
    const handlers = {
      play: () => audio.play(),
      pause: () => audio.pause(),
      seekbackward: () => {
        audio.currentTime = Math.max(0, audio.currentTime - 15);
      },
      seekforward: () => {
        audio.currentTime = Math.min(audio.duration || audio.currentTime + 30, audio.currentTime + 30);
      },
    };
    Object.entries(handlers).forEach(([name, handler]) => {
      try {
        navigator.mediaSession.setActionHandler(name, handler);
      } catch {
        // Some browsers expose Media Session partially.
      }
    });
    if (navigator.mediaSession.setPositionState && Number.isFinite(audio.duration) && audio.duration > 0) {
      try {
        navigator.mediaSession.setPositionState({
          duration: audio.duration,
          playbackRate: audio.playbackRate || 1,
          position: Math.min(audio.currentTime, audio.duration),
        });
      } catch {
        // Position state is best-effort.
      }
    }
  }

  function setPlayerState(audio, article) {
    if (playerClosed) return;
    if (audio === closingAudio) return;
    activeAudio = audio;
    activeEpisode = article;
    activeState = episodeState(article);
    if (!player || !activeState) return;
    document.body.classList.add("has-player");
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    player.hidden = false;
    playerToggle.textContent = audio.paused ? "▶" : "Ⅱ";
    playerToggle.setAttribute("aria-label", audio.paused ? t("listen") : t("pause"));
    applyPlaybackRate(audio);
    updatePlayerProgress();
    updateMediaSession(audio, activeState);
    updateQueueNavButtons();
    if (renderedActiveQueueId !== activeState.id) {
      renderedActiveQueueId = activeState.id;
      updateQueueUi();
    }
    updateResume();
  }

  function updatePlayerProgress() {
    if (!player || !activeAudio) return;
    const duration = Number.isFinite(activeAudio.duration) && activeAudio.duration > 0
      ? activeAudio.duration
      : Number(activeEpisode?.dataset.episodeDuration || 0);
    const position = activeAudio.currentTime || 0;
    playerTime.textContent = `${formatTime(position)} / ${formatTime(duration)}`;
    if (playerSeek && !seeking) {
      playerSeek.max = String(Math.max(1, Math.floor(duration || 1)));
      playerSeek.value = String(Math.floor(position));
    }
    if (activeState) updateMediaSession(activeAudio, activeState);
  }

  function dockActiveAudio() {
    if (activeAudio && activeAudio.parentElement !== audioDock) {
      audioDock.append(activeAudio);
    }
  }

  function stopOtherAudio(nextAudio) {
    document.querySelectorAll("audio").forEach((candidate) => {
      if (candidate === nextAudio || candidate.paused) return;
      candidate.pause();
    });
    if (activeAudio && activeAudio !== nextAudio) {
      activeAudio.pause();
      saveCurrentProgress(activeAudio, activeEpisode);
    }
  }

  function restoreProgress(audio, article) {
    if (audio.dataset.progressRestored === "true") return;
    const saved = savedProgress(article);
    const duration = Number.isFinite(audio.duration) && audio.duration > 0 ? audio.duration : Number(article.dataset.episodeDuration || 0);
    if (saved && saved.position > 10 && (!duration || duration - saved.position > 20)) {
      try {
        audio.currentTime = saved.position;
      } catch {
        // Some streams only become seekable after more metadata arrives.
      }
    }
    audio.dataset.progressRestored = "true";
  }

  function playEpisode(article) {
    const audio = article?.querySelector("audio[data-audio-src]");
    if (!audio) return;
    closingAudio = null;
    playerClosed = false;
    loadAudio(audio);
    stopOtherAudio(audio);
    restoreProgress(audio, article);
    rememberCurrentEpisode(audio, article);
    promoteQueueEntry(episodeState(article));
    audio.play().then(() => setPlayerState(audio, article)).catch(() => {});
  }

  function updateResume() {
    if (!resume) return;
    const saved = safeGet(lastKey);
    const valid = saved && saved.position > 10 && (!saved.duration || saved.duration - saved.position > 20);
    const dismissed = saved && resumeDismissedId === saved.id;
    const alreadyShown = saved && resumeShownId === saved.id && resumeVisibleForId !== saved.id;
    const playerActive = Boolean(activeState) || (player && !player.hidden);
    if (!valid || dismissed || alreadyShown || playerActive) {
      resumeVisibleForId = "";
      resume.hidden = true;
      return;
    }
    resumeTitle.textContent = saved.title || "";
    resumeShow.textContent = `${saved.show || ""} · ${formatTime(saved.position)}`;
    resumeVisibleForId = saved.id;
    resumeShownId = saved.id;
    try {
      sessionStorage.setItem("torahpod-resume-shown-id", resumeShownId);
    } catch {
      // Ignore unavailable storage.
    }
    resume.hidden = false;
  }

  function resumeLast() {
    const saved = safeGet(lastKey);
    if (!saved?.id) return;
    const article = Array.from(document.querySelectorAll("[data-episode-id]"))
      .find((candidate) => candidate.dataset.episodeId === saved.id);
    if (article) {
      article.scrollIntoView({ behavior: "smooth", block: "center" });
      playEpisode(article);
    } else if (saved.href) {
      navigateTo(saved.href).then(() => {
        const nextArticle = Array.from(document.querySelectorAll("[data-episode-id]"))
          .find((candidate) => candidate.dataset.episodeId === saved.id);
        if (nextArticle) playEpisode(nextArticle);
      });
    }
  }

  function setupEpisodes() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      const audio = article.querySelector("audio[data-audio-src]");
      const play = article.querySelector("[data-episode-play]");
      const queue = article.querySelector("[data-queue-add]");
      const queueNextButton = article.querySelector("[data-queue-next]");
      const played = article.querySelector("[data-toggle-played]");
      updateEpisodeProgress(article);
      updateEpisodeActions(article);
      play?.addEventListener("click", () => playEpisode(article));
      queue?.addEventListener("click", () => toggleQueued(article));
      queueNextButton?.addEventListener("click", () => queueNext(article));
      played?.addEventListener("click", () => setPlayed(article, !isPlayed(article)));
      audio?.addEventListener("loadedmetadata", () => restoreProgress(audio, article));
      audio?.addEventListener("play", () => {
        closingAudio = null;
        playerClosed = false;
        stopOtherAudio(audio);
        restoreProgress(audio, article);
        rememberCurrentEpisode(audio, article);
        setPlayerState(audio, article);
      });
      audio?.addEventListener("pause", () => {
        if (playerClosed && closingAudio === audio) return;
        saveCurrentProgress(audio, article);
        if (closingAudio === audio) return;
        setPlayerState(audio, article);
      });
      audio?.addEventListener("timeupdate", () => {
        if (playerClosed) return;
        if (closingAudio === audio) return;
        setPlayerState(audio, article);
        if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
          audio.dataset.lastSavedAt = String(Date.now());
          saveCurrentProgress(audio, article);
        }
      });
      audio?.addEventListener("ended", () => {
        if (playerClosed) return;
        if (closingAudio === audio) return;
        saveCurrentProgress(audio, article);
        setPlayed(article, true);
        updatePlayerProgress();
        playNextQueuedAfter(article.dataset.episodeId || "");
      });
    });
  }

  function setupPlayerControls() {
    const closePlayer = () => {
      let saved = activeState;
      const audio = activeAudio;
      const article = activeEpisode;
      if (player) player.hidden = true;
      playerClosed = true;
      activeAudio = null;
      activeState = null;
      activeEpisode = null;
      renderedActiveQueueId = "";
      document.body.classList.remove("has-player");
      updateQueueUi();
      updateQueueNavButtons();
      if (audio) {
        closingAudio = audio;
        audio.pause();
        saved = saveCurrentProgress(audio, article) || saved;
      }
      dismissResumeFor(saved);
    };

    const closeResume = () => {
      if (resume) resume.hidden = true;
      const saved = safeGet(lastKey);
      dismissResumeFor(saved);
    };

    const bindClosePress = (button, handler) => {
      if (!button) return;
      let lastPressAt = 0;
      const run = (event) => {
        const now = Date.now();
        event.preventDefault();
        event.stopPropagation();
        if (now - lastPressAt < 700) return;
        lastPressAt = now;
        handler();
      };
      ["touchstart", "pointerdown", "mousedown", "click"].forEach((type) => {
        button.addEventListener(type, run, { capture: true, passive: false });
      });
    };

    playerToggle?.addEventListener("click", () => {
      if (!activeAudio) return;
      if (activeAudio.paused) activeAudio.play().catch(() => {});
      else activeAudio.pause();
    });
    playerPrev?.addEventListener("click", () => playAdjacentQueued(-1));
    playerNext?.addEventListener("click", () => playAdjacentQueued(1));
    playerSpeed?.addEventListener("click", cyclePlaybackRate);
    document.querySelectorAll("[data-player-skip]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!activeAudio) return;
        const delta = Number(button.dataset.playerSkip || 0);
        activeAudio.currentTime = Math.max(0, Math.min(activeAudio.duration || activeAudio.currentTime + delta, activeAudio.currentTime + delta));
      });
    });
    playerSeek?.addEventListener("input", () => {
      seeking = true;
      if (activeAudio) activeAudio.currentTime = Number(playerSeek.value || 0);
      seeking = false;
    });
    bindClosePress(playerClose, closePlayer);
    resumeButton?.addEventListener("click", resumeLast);
    bindClosePress(resumeClose, closeResume);
  }

  function setupLists() {
    document.querySelectorAll("[data-list]").forEach((list) => {
      const pageSize = Number(list.dataset.pageSize || "24");
      let visibleLimit = pageSize;
      const controls = document.querySelector(`[data-list-controls="${list.id}"]`);
      const search = document.querySelector(`[data-search-target="${list.id}"]`);
      const filterToggle = document.querySelector(`[data-filter-toggle="${list.id}"]`);
      const libraryToggle = document.querySelector(`[data-library-filter-toggle="${list.id}"]`);
      const more = document.querySelector(`[data-load-more="${list.id}"]`);
      const items = Array.from(list.querySelectorAll("[data-list-item]"));
      if (!items.length) {
        controls?.setAttribute("hidden", "");
        if (more) more.hidden = true;
        return;
      }
      function matches(item) {
        const term = search?.value.trim().toLowerCase() || "";
        const hostedOnly = filterToggle?.getAttribute("aria-pressed") === "true";
        const libraryOnly = libraryToggle?.getAttribute("aria-pressed") === "true";
        const itemFilter = item.dataset.filterValue || "";
        const showSlug = item.dataset.showSlug || item.dataset.episodeShowSlug || "";
        const matchesTerm = !term || item.dataset.searchItem.toLowerCase().includes(term);
        const matchesFilter = !hostedOnly || itemFilter === "hosted_by_torahpod" || itemFilter === "mixed_sources";
        const matchesLibrary = !libraryOnly || isFollowing(showSlug);
        return matchesTerm && matchesFilter && matchesLibrary;
      }
      function render() {
        const matched = items.filter(matches);
        items.forEach((item) => {
          item.hidden = true;
        });
        matched.slice(0, visibleLimit).forEach((item) => {
          item.hidden = false;
          item.querySelectorAll("audio[data-audio-src]").forEach(loadAudio);
        });
        if (more) more.hidden = matched.length <= visibleLimit;
        updateAllEpisodeProgress();
      }
      search?.addEventListener("input", () => {
        visibleLimit = pageSize;
        render();
      });
      filterToggle?.addEventListener("click", () => {
        const nextPressed = filterToggle.getAttribute("aria-pressed") !== "true";
        filterToggle.setAttribute("aria-pressed", String(nextPressed));
        visibleLimit = pageSize;
        render();
      });
      libraryToggle?.addEventListener("click", () => {
        const nextPressed = libraryToggle.getAttribute("aria-pressed") !== "true";
        libraryToggle.setAttribute("aria-pressed", String(nextPressed));
        visibleLimit = pageSize;
        render();
      });
      document.addEventListener("torahpod:librarychange", () => {
        visibleLimit = pageSize;
        render();
      });
      more?.addEventListener("click", () => {
        visibleLimit += pageSize;
        render();
      });
      render();
    });
  }

  function setupLibraryQueueControls() {
    document.addEventListener("click", (event) => {
      const follow = event.target.closest?.("[data-follow-show]");
      if (follow) {
        event.preventDefault();
        toggleFollow(follow.closest("[data-show-card]"));
        return;
      }

      const libraryOpen = event.target.closest?.("[data-library-open]");
      if (libraryOpen) {
        event.preventDefault();
        renderLibrary();
        openDrawer(document.querySelector("[data-library-drawer]"));
        return;
      }

      const browsePodcasts = event.target.closest?.("[data-browse-podcasts]");
      if (browsePodcasts) {
        closeDrawers();
        return;
      }

      const queueOpen = event.target.closest?.("[data-queue-open]");
      if (queueOpen) {
        event.preventDefault();
        renderQueue();
        openDrawer(document.querySelector("[data-queue-drawer]"));
        return;
      }

      const close = event.target.closest?.("[data-drawer-close]");
      if (close) {
        event.preventDefault();
        closeDrawers();
        return;
      }

      const removeLibrary = event.target.closest?.("[data-library-remove]");
      if (removeLibrary) {
        event.preventDefault();
        const slug = removeLibrary.dataset.libraryRemove;
        saveFollowedShows(followedShows().filter((item) => item.slug !== slug));
        return;
      }

      const removeQueue = event.target.closest?.("[data-queue-remove]");
      if (removeQueue) {
        event.preventDefault();
        removeFromQueue(removeQueue.dataset.queueRemove);
        return;
      }

      const moveQueue = event.target.closest?.("[data-queue-move]");
      if (moveQueue) {
        event.preventDefault();
        moveQueueItem(moveQueue.dataset.queueMove, Number(moveQueue.dataset.queueDelta || 0));
        return;
      }

      const clearQueueButton = event.target.closest?.("[data-queue-clear]");
      if (clearQueueButton) {
        event.preventDefault();
        clearQueue();
        return;
      }

      const playQueue = event.target.closest?.("[data-queue-play]");
      if (playQueue) {
        event.preventDefault();
        const entry = queueEntries().find((item) => item.id === playQueue.dataset.queuePlay);
        if (entry) {
          closeDrawers();
          playQueuedEntry(entry);
        }
      }
    });
  }

  function setupLanguage() {
    const toggle = document.querySelector("[data-language-toggle]");
    function setLanguage(lang) {
      const next = labels[lang] || labels.he;
      html.lang = next.lang;
      html.dir = next.dir;
      document.querySelectorAll("[data-i18n]").forEach((node) => {
        const value = next[node.dataset.i18n];
        if (value) node.innerHTML = value;
      });
      document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
        const value = next[node.dataset.i18nPlaceholder];
        if (value) node.setAttribute("placeholder", value);
      });
      document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
        const value = next[node.dataset.i18nAria];
        if (value) node.setAttribute("aria-label", value);
      });
      applyPlaybackRate();
      try {
        localStorage.setItem("torahpod-language", lang);
      } catch {
        // Ignore unavailable storage.
      }
      updateAllEpisodeProgress();
      updateLibraryAndQueueUi();
      updateResume();
    }
    toggle?.addEventListener("click", () => {
      setLanguage(html.lang === "he" ? "en" : "he");
    });
    let stored = "he";
    try {
      stored = localStorage.getItem("torahpod-language") || "he";
    } catch {
      stored = "he";
    }
    setLanguage(stored);
  }

  function setupContactForms() {
    document.querySelectorAll("[data-contact-form]").forEach((form) => {
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        const data = new FormData(form);
        const email = form.dataset.contactEmail;
        const subject = html.lang === "en" ? "Torah Pod contact" : "פנייה ל-Torah Pod";
        const lines = [
          `Name: ${data.get("name") || ""}`,
          `Email: ${data.get("email") || ""}`,
          "",
          `${data.get("message") || ""}`,
        ];
        window.location.href = `mailto:${email}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(lines.join("\n"))}`;
      });
    });
  }

  function normalizePagePath(pathname) {
    let path = pathname.replace(/\/+$/, "");
    path = path.replace(/\/index\.html$/i, "");
    return path || "/";
  }

  function isSamePageUrl(url) {
    return (
      url.origin === location.origin &&
      url.search === location.search &&
      normalizePagePath(url.pathname) === normalizePagePath(location.pathname)
    );
  }

  function shouldHandleNavigation(event, link) {
    if (
      event.defaultPrevented ||
      event.button !== 0 ||
      event.metaKey ||
      event.ctrlKey ||
      event.shiftKey ||
      event.altKey ||
      link.target ||
      link.hasAttribute("download")
    ) {
      return false;
    }
    const url = new URL(link.href, location.href);
    if (url.origin !== location.origin) return false;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return false;
    if (url.pathname.endsWith(".xml") || url.pathname.endsWith(".json") || url.pathname.endsWith(".png")) return false;
    const lastSegment = url.pathname.split("/").filter(Boolean).pop() || "";
    return url.pathname.endsWith("/") || url.pathname.endsWith(".html") || !lastSegment.includes(".");
  }

  async function navigateTo(target, { push = true } = {}) {
    const url = new URL(target, location.href);
    document.body.classList.add("app-loading");
    try {
      const response = await fetch(url.href, { headers: { "X-Torah-Pod-Navigation": "1" } });
      if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);
      const nextDocument = parser.parseFromString(await response.text(), "text/html");
      const nextHeader = nextDocument.querySelector(".site-header");
      const nextMain = nextDocument.querySelector("main");
      const nextFooter = nextDocument.querySelector(".footer");
      if (!nextMain) throw new Error("Navigation response had no main content");

      dockActiveAudio();
      closeDrawers();
      document.title = nextDocument.title || document.title;
      if (nextHeader) document.querySelector(".site-header")?.replaceWith(nextHeader);
      document.querySelector("main")?.replaceWith(nextMain);
      if (nextFooter) document.querySelector(".footer")?.replaceWith(nextFooter);
      if (push) history.pushState({}, "", url.href);
      setupLanguage();
      setupLists();
      setupEpisodes();
      setupContactForms();
      updateLibraryAndQueueUi();
      updateResume();
      const hashTarget = url.hash ? document.querySelector(url.hash) : null;
      if (hashTarget) hashTarget.scrollIntoView({ block: "center" });
      else window.scrollTo(0, 0);
      return true;
    } catch {
      location.href = url.href;
      return false;
    } finally {
      document.body.classList.remove("app-loading");
    }
  }

  function setupAppNavigation() {
    document.addEventListener("click", (event) => {
      const link = event.target.closest?.("a[href]");
      if (!link) return;
      const url = new URL(link.href, location.href);
      if (isSamePageUrl(url) && !url.hash) {
        event.preventDefault();
        window.scrollTo({ top: 0, behavior: "smooth" });
        return;
      }
      if (!shouldHandleNavigation(event, link)) return;
      event.preventDefault();
      navigateTo(link.href);
    });
    window.addEventListener("popstate", () => {
      navigateTo(location.href, { push: false });
    });
  }

  function setupServiceWorker() {
    if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(`${basePath}sw.js`).catch(() => {});
    });
  }

  setupLanguage();
  setupLists();
  setupEpisodes();
  setupPlayerControls();
  setupLibraryQueueControls();
  setupContactForms();
  setupAppNavigation();
  setupServiceWorker();
  updateLibraryAndQueueUi();
  updateResume();
})();
