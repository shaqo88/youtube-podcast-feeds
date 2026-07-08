(() => {
  const labels = window.TORAH_POD_LABELS || {};
  const html = document.documentElement;
  const basePath = window.TORAH_POD_BASE || "";
  const progressPrefix = "torahpod-progress:";
  const lastKey = "torahpod-last-episode";
  const player = document.querySelector("[data-player]");
  const playerToggle = document.querySelector("[data-player-toggle]");
  const playerTitle = document.querySelector("[data-player-title]");
  const playerShow = document.querySelector("[data-player-show]");
  const playerTime = document.querySelector("[data-player-time]");
  const playerSeek = document.querySelector("[data-player-seek]");
  const playerClose = document.querySelector("[data-player-close]");
  const resume = document.querySelector("[data-resume]");
  const resumeTitle = document.querySelector("[data-resume-title]");
  const resumeShow = document.querySelector("[data-resume-show]");
  const resumeButton = document.querySelector("[data-resume-play]");
  let activeAudio = null;
  let activeEpisode = null;
  let activeState = null;
  let seeking = false;

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

  function episodeState(article) {
    if (!article) return null;
    return {
      id: article.dataset.episodeId || "",
      title: article.dataset.episodeTitle || "",
      show: article.dataset.episodeShow || "",
      artwork: article.dataset.episodeArtwork || "",
      src: article.dataset.episodeSrc || "",
      duration: Number(article.dataset.episodeDuration || 0),
      href: `${location.href.split("#")[0]}#${article.id}`,
    };
  }

  function loadAudio(audio) {
    if (!audio.src && audio.dataset.audioSrc) {
      audio.src = audio.dataset.audioSrc;
      audio.preload = "metadata";
    }
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
    if (!state?.id || !audio || !Number.isFinite(audio.currentTime)) return;
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
    updateResume();
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
    activeAudio = audio;
    activeEpisode = article;
    activeState = episodeState(article);
    if (!player || !activeState) return;
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    player.hidden = false;
    playerToggle.textContent = audio.paused ? "▶" : "Ⅱ";
    playerToggle.setAttribute("aria-label", audio.paused ? t("listen") : t("pause"));
    updatePlayerProgress();
    updateMediaSession(audio, activeState);
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
    loadAudio(audio);
    if (activeAudio && activeAudio !== audio) {
      activeAudio.pause();
      saveCurrentProgress(activeAudio, activeEpisode);
    }
    restoreProgress(audio, article);
    audio.play().catch(() => {});
  }

  function updateResume() {
    if (!resume) return;
    const saved = safeGet(lastKey);
    const valid = saved && saved.position > 10 && (!saved.duration || saved.duration - saved.position > 20);
    if (!valid) {
      resume.hidden = true;
      return;
    }
    resumeTitle.textContent = saved.title || "";
    resumeShow.textContent = `${saved.show || ""} · ${formatTime(saved.position)}`;
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
      location.href = saved.href;
    }
  }

  function setupEpisodes() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      const audio = article.querySelector("audio[data-audio-src]");
      const play = article.querySelector("[data-episode-play]");
      updateEpisodeProgress(article);
      play?.addEventListener("click", () => playEpisode(article));
      audio?.addEventListener("loadedmetadata", () => restoreProgress(audio, article));
      audio?.addEventListener("play", () => {
        if (activeAudio && activeAudio !== audio) {
          activeAudio.pause();
          saveCurrentProgress(activeAudio, activeEpisode);
        }
        restoreProgress(audio, article);
        setPlayerState(audio, article);
      });
      audio?.addEventListener("pause", () => {
        saveCurrentProgress(audio, article);
        setPlayerState(audio, article);
      });
      audio?.addEventListener("timeupdate", () => {
        setPlayerState(audio, article);
        if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
          audio.dataset.lastSavedAt = String(Date.now());
          saveCurrentProgress(audio, article);
        }
      });
      audio?.addEventListener("ended", () => {
        saveCurrentProgress(audio, article);
        updatePlayerProgress();
      });
    });
  }

  function setupPlayerControls() {
    playerToggle?.addEventListener("click", () => {
      if (!activeAudio) return;
      if (activeAudio.paused) activeAudio.play().catch(() => {});
      else activeAudio.pause();
    });
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
    playerClose?.addEventListener("click", () => {
      if (activeAudio) {
        activeAudio.pause();
        saveCurrentProgress(activeAudio, activeEpisode);
      }
      if (player) player.hidden = true;
    });
    resumeButton?.addEventListener("click", resumeLast);
  }

  function setupLists() {
    document.querySelectorAll("[data-list]").forEach((list) => {
      const pageSize = Number(list.dataset.pageSize || "24");
      let visibleLimit = pageSize;
      const controls = document.querySelector(`[data-list-controls="${list.id}"]`);
      const search = document.querySelector(`[data-search-target="${list.id}"]`);
      const filterToggle = document.querySelector(`[data-filter-toggle="${list.id}"]`);
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
        const itemFilter = item.dataset.filterValue || "";
        const matchesTerm = !term || item.dataset.searchItem.toLowerCase().includes(term);
        const matchesFilter = !hostedOnly || itemFilter === "hosted_by_torahpod" || itemFilter === "mixed_sources";
        return matchesTerm && matchesFilter;
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
      more?.addEventListener("click", () => {
        visibleLimit += pageSize;
        render();
      });
      render();
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
      try {
        localStorage.setItem("torahpod-language", lang);
      } catch {
        // Ignore unavailable storage.
      }
      updateAllEpisodeProgress();
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
  setupContactForms();
  setupServiceWorker();
  updateResume();
})();
