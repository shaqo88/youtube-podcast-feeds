(() => {
  const appScript = document.currentScript || document.querySelector("script[data-torah-pod-labels]");
  const labels = JSON.parse(appScript?.dataset.torahPodLabels || "{}");
  const runtimeLabels = {
    he: {
      skip_to_content: "דילוג לתוכן הראשי",
      player_details: "פתיחת פרטי הניגון",
      network_offline: "אין חיבור. דפים שמורים עשויים לעבוד; השמע דורש חיבור לרשת.",
      network_online: "החיבור חזר",
      navigation_loading: "העמוד נטען",
      navigation_failed: "לא ניתן לפתוח את העמוד. בדקו את החיבור ונסו שוב.",
      navigation_retry: "נסו שוב",
      playback_failed: "לא ניתן לנגן את הפרק. בדקו את החיבור ונסו שוב.",
      playback_offline: "אין חיבור לרשת. הפרק וההתקדמות נשמרו; נסו שוב כשהחיבור יחזור.",
      playback_stalled: "טעינת הפרק נמשכת זמן רב מהרגיל. אפשר לנסות שוב בלי לאבד את ההתקדמות.",
      playback_retry: "ניסיון נוסף",
      player_stop: "עצירת הניגון",
      diagnostics_title: "פתרון תקלות",
      diagnostics_text: "אם ההאזנה לא עובדת כמצופה, העתיקו פרטי אבחון בטוחים ושלחו אותם אלינו.",
      copy_diagnostics: "העתקת פרטי אבחון",
      diagnostics_copied: "פרטי האבחון הועתקו.",
      diagnostics_failed: "לא ניתן להעתיק את פרטי האבחון כרגע.",
      search_start: "הקלידו לפחות שני תווים כדי לחפש בכל הפרקים.",
      search_loading: "טוען את מאגר החיפוש…",
      search_failed: "לא ניתן לטעון את החיפוש כרגע. בדקו את החיבור ונסו שוב.",
      new_episodes: "פרקים חדשים",
      no_queue_preview: "התור שלכם ריק. הוסיפו פרק כדי להמשיך להאזין ברצף.",
      update_ready: "גרסה חדשה מוכנה.",
      update_now: "רענון עכשיו",
      reorder_queue: "גרירה לשינוי סדר",
      copy_feed: "העתקת קישור RSS",
      feed_copied: "קישור ה-RSS הועתק.",
      copy_feed_failed: "לא ניתן להעתיק את הקישור. אפשר לפתוח את RSS ולהעתיק משם.",
    },
    en: {
      skip_to_content: "Skip to main content",
      player_details: "Open playback details",
      network_offline: "You are offline. Saved pages may still work; audio needs a connection.",
      network_online: "Back online",
      navigation_loading: "Loading page",
      navigation_failed: "Could not open the page. Check your connection and try again.",
      navigation_retry: "Try again",
      playback_failed: "Could not play this episode. Check your connection and try again.",
      playback_offline: "You are offline. The episode and progress are preserved; try again when your connection returns.",
      playback_stalled: "This episode is taking longer than usual to start. You can retry without losing progress.",
      playback_retry: "Retry playback",
      player_stop: "Stop playback",
      diagnostics_title: "Troubleshooting",
      diagnostics_text: "If playback is not working as expected, copy safe diagnostics and send them to us.",
      copy_diagnostics: "Copy diagnostics",
      diagnostics_copied: "Diagnostics copied.",
      diagnostics_failed: "Could not copy diagnostics right now.",
      search_start: "Enter at least two characters to search every episode.",
      search_loading: "Loading the search catalog…",
      search_failed: "Search could not be loaded. Check your connection and try again.",
      new_episodes: "new episodes",
      no_queue_preview: "Your queue is empty. Add an episode to keep listening continuously.",
      update_ready: "A new version is ready.",
      update_now: "Refresh now",
      reorder_queue: "Drag to reorder",
      copy_feed: "Copy RSS Link",
      feed_copied: "RSS link copied.",
      copy_feed_failed: "Could not copy the link. Open RSS to copy it instead.",
    },
  };
  const html = document.documentElement;
  const basePath = appScript?.dataset.torahPodBase || "";
  function updateVersionBadges() {
    const match = navigator.userAgent.match(/TorahPodVersion\/([0-9][0-9A-Za-z._-]*)/);
    document.querySelectorAll("[data-app-version]").forEach((badge) => {
      const siteBuild = badge.dataset.siteBuild || "unknown";
      badge.textContent = match ? `Site ${siteBuild} · App ${match[1]}` : `Site ${siteBuild} · Web`;
    });
  }
  function nativePrompt(command, payload = {}) {
    if (!navigator.userAgent.includes("TorahPodAndroid/1") || typeof window.prompt !== "function") return false;
    try {
      window.prompt("torahpod-native", JSON.stringify({ version: 1, command, payload }));
      return true;
    } catch {
      return false;
    }
  }
  // Older released Android builds expose a native object directly. Keep using it
  // until the prompt-protocol build is installed; otherwise Android would show
  // the JSON prompt as a browser dialog.
  if (navigator.userAgent.includes("TorahPodAndroid/1") && !window.TorahPodNative) {
    window.TorahPodNative = {
      play: (json) => nativePrompt("play", JSON.parse(json || "{}")),
      toggle: () => nativePrompt("toggle"),
      stop: () => nativePrompt("stop"),
      seekBy: (seconds) => nativePrompt("seekBy", { seconds }),
      seekTo: (seconds) => nativePrompt("seekTo", { seconds }),
      htmlPlayback: (json) => nativePrompt("htmlPlayback", JSON.parse(json || "{}")),
      htmlStop: () => nativePrompt("htmlStop"),
    };
  }
  const progressPrefix = "torahpod-progress:";
  const lastKey = "torahpod-last-episode";
  const followsKey = "torahpod:v1:follows";
  const queueKey = "torahpod:v1:queue";
  const episodeStateKey = "torahpod:v1:episode-state";
  const speedKey = "torahpod:v1:playback-rate";
  const playbackDebugKey = "torahpod:v1:playback-debug";
  const showVisitsKey = "torahpod:v1:show-visits";
  const uxMigrationKey = "torahpod:v1:ux-0.4.0-migrated";
  const playbackRates = [1, 1.25, 1.5, 1.75, 2];
  const player = document.querySelector("[data-player]");
  const playerToggle = document.querySelector("[data-player-toggle]");
  const playerTitle = document.querySelector("[data-player-title]");
  const playerShow = document.querySelector("[data-player-show]");
  const playerEpisodeLink = document.querySelector("[data-player-episode-link]");
  const playerShowLink = document.querySelector("[data-player-show-link]");
  const playerArtwork = document.querySelector("[data-player-artwork]");
  const playerDescription = document.querySelector("[data-player-description]");
  const playerTime = document.querySelector("[data-player-time]");
  let playerElapsed = document.querySelector("[data-player-elapsed]");
  let playerRemaining = document.querySelector("[data-player-remaining]");
  const playerSeek = document.querySelector("[data-player-seek]");
  const playerMiniProgress = document.querySelector("[data-player-mini-progress]");
  const playerPrev = document.querySelector("[data-player-prev]");
  const playerNext = document.querySelector("[data-player-next]");
  const playerSpeed = document.querySelector("[data-player-speed]");
  let playerVolume = null;
  const playerMinimize = document.querySelector("[data-player-minimize]");
  const playerClose = document.querySelector("[data-player-close]");
  let playerDetails = document.querySelector("[data-player-details]");
  let appStatus = document.querySelector("[data-app-status]");
  const resume = document.querySelector("[data-resume]");
  const resumeTitle = document.querySelector("[data-resume-title]");
  const resumeShow = document.querySelector("[data-resume-show]");
  const resumeButton = document.querySelector("[data-resume-play]");
  const resumeClose = document.querySelector("[data-resume-close]");
  const parser = new DOMParser();
  const navigationTimeoutMs = 30000;
  const playbackStartupTimeoutMs = 30000;
  let navigationController = null;
  let navigationRequestId = 0;
  const audioDock = document.createElement("div");
  let activeAudio = null;
  let activeEpisode = null;
  let activeState = null;
  let activeNativeState = null;
  let activeNativePlaying = false;
  let nativeFallbackTimer = 0;
  let nativePlaybackRequestId = 0;
  let nativeNotificationLastSentAt = 0;
  let renderedActiveQueueId = "";
  let closingAudio = null;
  let playerClosed = false;
  let seeking = false;
  let resumeDismissedAt = Number(safeGet("torahpod-resume-dismissed-at") || 0);
  let resumeDismissedId = String(safeGet("torahpod-resume-dismissed-id") || "");
  let resumeShownId = "";
  let resumeVisibleForId = "";
  let appStatusTimer = 0;
  let playbackAttemptId = 0;
  let playbackStartupTimer = 0;

  const playerIconPaths = {
    play: '<path d="m9 7 9 5-9 5Z" fill="currentColor" stroke="none"/>',
    pause: '<path d="M9 7v10M15 7v10"/>',
    loading: '<circle class="player-spinner" cx="12" cy="12" r="7"/>',
    stop: '<rect x="8" y="8" width="8" height="8" rx="1" fill="currentColor" stroke="none"/>',
  };

  function playerIcon(name) {
    return `<svg class="ui-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">${playerIconPaths[name]}</svg>`;
  }

  function setPlayerToggle(playing = false, buffering = false) {
    if (!playerToggle) return;
    playerToggle.innerHTML = playerIcon(buffering ? "loading" : playing ? "pause" : "play");
    playerToggle.setAttribute("aria-label", playing ? t("pause") : t("listen"));
    playerToggle.setAttribute("aria-busy", String(buffering));
  }

  function updateMiniProgress(position = 0, duration = 0) {
    if (!playerMiniProgress) return;
    playerMiniProgress.max = Math.max(1, Number(duration) || 1);
    playerMiniProgress.value = Math.max(0, Math.min(Number(position) || 0, Number(duration) || 0));
  }

  function updatePlayerTime(position = 0, duration = 0) {
    const elapsed = formatTime(Math.max(0, Number(position) || 0));
    const remaining = Number(duration) > 0
      ? `-${formatTime(Math.max(0, Number(duration) - Number(position || 0)))}`
      : "--";
    if (playerElapsed && playerRemaining) {
      playerElapsed.textContent = elapsed;
      playerRemaining.textContent = remaining;
    } else if (playerTime) {
      playerTime.textContent = `${elapsed} / ${remaining}`;
    }
  }

  function setupPolishedPlayerShell() {
    if (!player) return;
    const topbar = player.querySelector(".player-topbar");
    const secondary = player.querySelector(".player-secondary-controls");
    if (topbar && playerClose?.parentElement === topbar && secondary) {
      const spacer = document.createElement("span");
      spacer.className = "player-topbar-spacer";
      spacer.setAttribute("aria-hidden", "true");
      topbar.replaceChild(spacer, playerClose);
      secondary.appendChild(playerClose);
    }
    if (playerClose) {
      playerClose.dataset.i18nAria = "player_stop";
      playerClose.setAttribute("aria-label", t("player_stop"));
      playerClose.innerHTML = `${playerIcon("stop")}<span data-i18n="player_stop">${t("player_stop")}</span>`;
    }
    if (playerTime && (!playerElapsed || !playerRemaining)) {
      playerTime.replaceChildren();
      playerElapsed = document.createElement("span");
      playerElapsed.dataset.playerElapsed = "";
      playerRemaining = document.createElement("span");
      playerRemaining.dataset.playerRemaining = "";
      playerTime.append(playerElapsed, playerRemaining);
      updatePlayerTime(0, 0);
    }
  }
  let searchIndexPromise = null;
  let lastDrawerTrigger = null;
  let listBindingsAbortController = null;
  let playerExpandedTrigger = null;

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
    return (labels[lang] && labels[lang][key]) || runtimeLabels[lang]?.[key] ||
      (labels.he && labels.he[key]) || runtimeLabels.he[key] || key;
  }

  function setupAccessibility() {
    [
      [document.querySelector(".nav"), "primary_navigation"],
      [document.querySelector(".app-bottom-nav"), "app_navigation"],
      [player, "audio_player"],
    ].forEach(([landmark, label]) => {
      if (!landmark) return;
      landmark.dataset.i18nAria = label;
      landmark.setAttribute("aria-label", t(label));
    });
    if (!document.querySelector(".skip-link")) {
      const skip = document.createElement("a");
      skip.className = "skip-link";
      skip.href = "#main-content";
      skip.dataset.i18n = "skip_to_content";
      skip.textContent = t("skip_to_content");
      document.body.prepend(skip);
    }
    const main = document.querySelector("main");
    if (main) {
      main.id = "main-content";
      main.tabIndex = -1;
    }
    const libraryDrawer = document.querySelector("[data-library-drawer]");
    const queueDrawer = document.querySelector("[data-queue-drawer]");
    [
      [libraryDrawer, "library-drawer", "[data-library-open]"],
      [queueDrawer, "queue-drawer", "[data-queue-open]"],
    ].forEach(([drawer, id, triggerSelector]) => {
      if (!drawer) return;
      drawer.id = id;
      drawer.setAttribute("role", "dialog");
      drawer.setAttribute("aria-modal", "true");
      drawer.tabIndex = -1;
      document.querySelectorAll(triggerSelector).forEach((trigger) => {
        trigger.setAttribute("aria-controls", id);
        trigger.setAttribute("aria-expanded", "false");
      });
    });
    if (playerDetails?.classList.contains("player-main")) {
      const legacyMain = playerDetails;
      const detailsButton = document.createElement("button");
      detailsButton.className = "player-details";
      detailsButton.type = "button";
      detailsButton.dataset.playerDetails = "";
      detailsButton.dataset.i18nAria = "player_details";
      detailsButton.setAttribute("aria-label", t("player_details"));
      detailsButton.setAttribute("aria-expanded", legacyMain.getAttribute("aria-expanded") || "false");
      [playerArtwork, playerTitle, playerShow].forEach((node) => {
        if (node) detailsButton.appendChild(node);
      });
      legacyMain.removeAttribute("role");
      legacyMain.removeAttribute("tabindex");
      legacyMain.removeAttribute("data-player-details");
      legacyMain.insertBefore(detailsButton, playerSeek || legacyMain.firstChild);
      playerDetails = detailsButton;
    }
    if (!appStatus) {
      appStatus = document.createElement("div");
      appStatus.className = "app-status";
      appStatus.dataset.appStatus = "";
      appStatus.setAttribute("role", "status");
      appStatus.setAttribute("aria-live", "polite");
      appStatus.setAttribute("aria-atomic", "true");
      appStatus.hidden = true;
      document.body.appendChild(appStatus);
    }
    setupFeedCopyButtons();
    setupHomeNavButton();
    setupDiagnostics();
  }

  function setupHomeNavButton() {
    const actions = document.querySelector(".nav-actions");
    if (!actions || actions.querySelector("[data-nav-home]")) return;
    const link = document.createElement("a");
    link.className = "nav-home-button";
    link.href = `${basePath}index.html`;
    link.dataset.appRoute = "/";
    link.dataset.navHome = "";
    link.dataset.i18n = "home";
    link.textContent = t("home");
    actions.prepend(link);
  }

  function setupFeedCopyButtons() {
    document.querySelectorAll(".show-actions a[data-i18n='feed']").forEach((feedLink) => {
      if (feedLink.parentElement?.querySelector("[data-copy-feed]")) return;
      const copyButton = document.createElement("button");
      copyButton.className = "button secondary copy-feed-button";
      copyButton.type = "button";
      copyButton.dataset.copyFeed = "";
      copyButton.dataset.i18n = "copy_feed";
      copyButton.textContent = t("copy_feed");
      copyButton.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(new URL(feedLink.href, location.href).href);
          announceAppStatus(t("feed_copied"));
        } catch {
          announceAppStatus(t("copy_feed_failed"), 4200);
        }
      });
      feedLink.insertAdjacentElement("afterend", copyButton);
    });
  }

  function announceAppStatus(message, timeout = 2600) {
    if (!appStatus) return;
    window.clearTimeout(appStatusTimer);
    delete appStatus.dataset.statusKind;
    appStatus.textContent = message;
    appStatus.hidden = false;
    if (timeout > 0) {
      appStatusTimer = window.setTimeout(() => { appStatus.hidden = true; }, timeout);
    }
  }

  function clearPlaybackStatus() {
    if (!appStatus || appStatus.dataset.statusKind !== "playback") return;
    window.clearTimeout(appStatusTimer);
    appStatus.replaceChildren();
    appStatus.hidden = true;
    delete appStatus.dataset.statusKind;
  }

  function showPlaybackStatus(messageKey, retry) {
    if (!appStatus) return;
    window.clearTimeout(appStatusTimer);
    appStatus.replaceChildren();
    appStatus.dataset.statusKind = "playback";
    const text = document.createElement("span");
    text.dataset.i18n = messageKey;
    text.textContent = t(messageKey);
    const button = document.createElement("button");
    button.className = "button secondary";
    button.type = "button";
    button.dataset.i18n = "playback_retry";
    button.textContent = t("playback_retry");
    button.addEventListener("click", () => {
      clearPlaybackStatus();
      retry();
    }, { once: true });
    appStatus.append(text, button);
    appStatus.hidden = false;
  }

  function showUpdateNotice() {
    if (!appStatus) return;
    window.clearTimeout(appStatusTimer);
    appStatus.replaceChildren();
    appStatus.hidden = true;
  }

  function showNavigationFailure(url, push) {
    if (!appStatus) return;
    window.clearTimeout(appStatusTimer);
    appStatus.replaceChildren();
    const message = document.createElement("span");
    message.textContent = t("navigation_failed");
    const retry = document.createElement("button");
    retry.className = "button secondary";
    retry.type = "button";
    retry.textContent = t("navigation_retry");
    retry.addEventListener("click", () => navigateTo(url, { push }));
    appStatus.append(message, retry);
    appStatus.hidden = false;
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

  function playbackVolume() {
    const saved = Number(safeGet("torahpod-volume"));
    return Number.isFinite(saved) ? Math.min(1, Math.max(0, saved)) : 1;
  }

  function updateVolumeControl(volume = playbackVolume()) {
    if (!playerVolume) return;
    const normalized = Math.min(1, Math.max(0, Number(volume) || 0));
    playerVolume.value = String(normalized);
    playerVolume.setAttribute("aria-valuetext", `${Math.round(normalized * 100)}%`);
  }

  function applyPlaybackVolume(audio) {
    const volume = playbackVolume();
    if (audio) audio.volume = volume;
    updateVolumeControl(volume);
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

  // Search should not depend on whether a Hebrew title was entered with ניקוד,
  // a maqaf, or typographic punctuation. Keep the same normalization for both
  // the query and the generated search text.
  function normalizeSearchText(value) {
    return String(value || "")
      .normalize("NFKD")
      .replace(/[\u0591-\u05C7]/g, "")
      .replace(/[\u05BE\u2010-\u2015'\"׳״.,:;!?()[\]{}\\/\\|_]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .toLowerCase();
  }

  function recordPlaybackEvent(name, details = {}) {
    const event = {
      at: new Date().toISOString(),
      name,
      page: location.pathname,
      id: details.id || activeState?.id || "",
      title: details.title || activeState?.title || "",
      position: Math.max(0, Math.floor(Number(details.position || activeAudio?.currentTime || 0))),
      native: Boolean(window.TorahPodNative),
    };
    try {
      const events = safeArray(playbackDebugKey);
      events.push(event);
      safeSet(playbackDebugKey, events.slice(-80));
    } catch {
      // Diagnostics must never affect playback.
    }
  }

  window.TorahPodPlaybackDebug = () => safeArray(playbackDebugKey);

  function diagnosticsReport() {
    const appMatch = navigator.userAgent.match(/TorahPodVersion\/([0-9][0-9A-Za-z._-]*)/);
    const siteVersion = document.querySelector("[data-site-build]")?.dataset.siteBuild || "unknown";
    const events = safeArray(playbackDebugKey).slice(-20).map((event) => {
      const parsedAt = Date.parse(String(event?.at || ""));
      const rawName = String(event?.name || "unknown");
      const rawPosition = Number(event?.position || 0);
      return {
        at: Number.isFinite(parsedAt) ? new Date(parsedAt).toISOString() : "unknown",
        type: /^[a-z0-9-]{1,64}$/.test(rawName) ? rawName : "unknown",
        position: Number.isFinite(rawPosition) ? Math.max(0, Math.floor(rawPosition)) : 0,
        native: event?.native === true,
      };
    });
    return JSON.stringify({
      appVersion: appMatch ? appMatch[1] : "web",
      siteVersion,
      online: navigator.onLine !== false,
      page: location.pathname,
      language: html.lang === "en" ? "en" : "he",
      events,
    }, null, 2);
  }

  async function copyDiagnostics() {
    const report = diagnosticsReport();
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      await navigator.clipboard.writeText(report);
      return;
    }
    const field = document.createElement("textarea");
    field.value = report;
    field.readOnly = true;
    field.className = "diagnostics-copy-field";
    document.body.appendChild(field);
    field.select();
    const copied = document.execCommand("copy");
    field.remove();
    if (!copied) throw new Error("Copy unavailable");
  }

  function setupDiagnostics() {
    document.querySelectorAll("[data-copy-diagnostics]").forEach((button) => {
      if (button.dataset.bound === "true") return;
      button.dataset.bound = "true";
      button.addEventListener("click", async () => {
        try {
          await copyDiagnostics();
          announceAppStatus(t("diagnostics_copied"));
        } catch {
          announceAppStatus(t("diagnostics_failed"), 4000);
        }
      });
    });
  }

  window.TorahPodDiagnostics = diagnosticsReport;

  function clearPlaybackStartupTimer() {
    if (!playbackStartupTimer) return;
    window.clearTimeout(playbackStartupTimer);
    playbackStartupTimer = 0;
  }

  function isCurrentPlaybackAttempt(audio, attemptId) {
    return Boolean(
      audio &&
      activeAudio === audio &&
      !playerClosed &&
      Number(audio.dataset.playbackAttempt || 0) === attemptId &&
      playbackAttemptId === attemptId
    );
  }

  function beginPlaybackAttempt(audio, state, article, retry) {
    clearPlaybackStartupTimer();
    clearPlaybackStatus();
    playbackAttemptId += 1;
    const attemptId = playbackAttemptId;
    audio.dataset.playbackAttempt = String(attemptId);
    delete audio.dataset.playbackFailed;
    playbackStartupTimer = window.setTimeout(() => {
      failPlaybackAttempt(audio, state, article, retry, "stalled", attemptId);
    }, playbackStartupTimeoutMs);
    return attemptId;
  }

  function completePlaybackAttempt(audio) {
    const attemptId = Number(audio?.dataset.playbackAttempt || 0);
    if (!isCurrentPlaybackAttempt(audio, attemptId)) return false;
    clearPlaybackStartupTimer();
    clearPlaybackStatus();
    return true;
  }

  function failPlaybackAttempt(audio, state, article, retry, reason, attemptId = Number(audio?.dataset.playbackAttempt || 0)) {
    if (!isCurrentPlaybackAttempt(audio, attemptId)) return;
    clearPlaybackStartupTimer();
    playbackAttemptId += 1;
    recordPlaybackEvent(`audio-${reason}`, {
      id: state?.id,
      title: state?.title,
      position: audio.currentTime,
    });
    if (article) saveCurrentProgress(audio, article);
    else if (state) saveCurrentStateProgress(audio, state);
    audio.dataset.playbackFailed = "true";
    closingAudio = audio;
    try { audio.pause(); } catch { /* Playback failure cleanup is best-effort. */ }
    if (!article && audio.parentElement === audioDock) audio.remove();
    if (activeAudio === audio) activeAudio = null;
    activeEpisode = article || null;
    activeState = state || activeState;
    player?.classList.remove("is-buffering");
    setPlayerToggle(false);
    stopNativeNotification();
    const messageKey = navigator.onLine === false
      ? "playback_offline"
      : reason === "stalled" ? "playback_stalled" : "playback_failed";
    showPlaybackStatus(messageKey, () => {
      recordPlaybackEvent("audio-retry", { id: state?.id, title: state?.title });
      retry();
    });
  }

  function invalidatePlaybackAttempt() {
    clearPlaybackStartupTimer();
    playbackAttemptId += 1;
  }

  function resumeHtmlPlayback() {
    const audio = activeAudio;
    const state = activeState;
    const article = activeEpisode;
    if (!audio || !state) return;
    const retry = article ? () => playEpisode(article) : () => playHtmlState(state);
    player?.classList.add("is-buffering");
    const attemptId = beginPlaybackAttempt(audio, state, article, retry);
    audio.play().then(() => {
      if (!isCurrentPlaybackAttempt(audio, attemptId)) return;
      completePlaybackAttempt(audio);
    }).catch(() => failPlaybackAttempt(audio, state, article, retry, "play-failed", attemptId));
  }

  function nativeAudioBridge() {
    let nativeAudioEnabled = false;
    try {
      nativeAudioEnabled = localStorage.getItem("torahpod-native-audio-enabled") === "true";
    } catch {
      nativeAudioEnabled = false;
    }
    if (!nativeAudioEnabled) return null;
    return window.TorahPodNative && typeof window.TorahPodNative.play === "function"
      ? window.TorahPodNative
      : null;
  }

  function nativeNotificationBridge() {
    return window.TorahPodNative && typeof window.TorahPodNative.htmlPlayback === "function"
      ? window.TorahPodNative
      : null;
  }

  function syncNativeNotification(audio, state, playing, options = {}) {
    const bridge = nativeNotificationBridge();
    if (!bridge || !state?.src || !audio) return;
    const now = Date.now();
    if (!options.force && now - nativeNotificationLastSentAt < 2000) return;
    nativeNotificationLastSentAt = now;
    const duration = Number.isFinite(audio.duration) && audio.duration > 0
      ? audio.duration
      : Number(state.duration || 0);
    const payload = {
      ...state,
      position: Math.max(0, Math.floor(audio.currentTime || 0)),
      duration: Math.max(0, Math.floor(duration || 0)),
      playing: playing === true,
    };
    try {
      bridge.htmlPlayback(JSON.stringify(payload));
      if (options.force) recordPlaybackEvent("notification-sync", { id: state.id, title: state.title, position: payload.position });
    } catch {
      // Native notification mirroring is best-effort.
    }
  }

  function stopNativeNotification() {
    nativeNotificationLastSentAt = 0;
    try {
      nativeNotificationBridge()?.htmlStop();
    } catch {
      // Native notification mirroring is best-effort.
    }
  }

  window.TorahPodNativeControl = (payload = {}) => {
    const command = payload?.command || "";
    if (command === "toggle") {
      if (activeAudio) {
        if (activeAudio.paused) resumeHtmlPlayback();
        else activeAudio.pause();
      } else if (activeState?.src) {
        playHtmlState(activeState);
      }
    } else if (command === "play") {
      if (activeAudio) resumeHtmlPlayback();
      else if (activeState?.src) playHtmlState(activeState);
    } else if (command === "pause") {
      if (activeAudio) activeAudio.pause();
    } else if (command === "seekBy") {
      const seconds = Math.floor(Number(payload?.seconds) || 0);
      if (activeAudio && seconds) {
        const duration = Number.isFinite(activeAudio.duration) ? activeAudio.duration : 0;
        activeAudio.currentTime = Math.max(0, duration > 0
          ? Math.min(duration, activeAudio.currentTime + seconds)
          : activeAudio.currentTime + seconds);
      }
    } else if (command === "stop") {
      if (activeAudio) activeAudio.pause();
      stopNativeNotification();
    } else if (command === "ended") {
      if (activeState?.id) playNextQueuedAfter(activeState.id);
    }
  };

  function nativeSeekBy(seconds) {
    const bridge = nativeAudioBridge();
    if (!bridge || typeof bridge.seekBy !== "function") return;
    try {
      bridge.seekBy(Math.floor(Number(seconds) || 0));
    } catch {
      // Native seek is best-effort.
    }
  }

  function nativeSeekTo(seconds) {
    const bridge = nativeAudioBridge();
    if (!bridge || typeof bridge.seekTo !== "function") return;
    try {
      bridge.seekTo(Math.max(0, Math.floor(Number(seconds) || 0)));
    } catch {
      // Native seek is best-effort.
    }
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

  function episodeDates(card) {
    try {
      const dates = JSON.parse(card?.dataset.showEpisodeDates || "[]");
      return Array.isArray(dates) ? dates.filter((value) => /^\d{8}$/.test(value)) : [];
    } catch {
      return [];
    }
  }

  function migrateShowVisits() {
    if (safeGet(uxMigrationKey)) return;
    const now = Date.now();
    const visits = safeObject(showVisitsKey);
    followedShows().forEach((show) => {
      if (!visits[show.slug]) visits[show.slug] = now;
    });
    safeSet(showVisitsKey, visits);
    safeSet(uxMigrationKey, { migratedAt: now });
  }

  function publicationTime(value) {
    if (!/^\d{8}$/.test(String(value || ""))) return 0;
    const text = String(value);
    return Date.UTC(Number(text.slice(0, 4)), Number(text.slice(4, 6)) - 1, Number(text.slice(6, 8)));
  }

  function newEpisodeCount(card) {
    const slug = card?.dataset.showSlug || "";
    const visitedAt = Number(safeObject(showVisitsKey)[slug] || Date.now());
    return episodeDates(card).filter((value) => publicationTime(value) > visitedAt).length;
  }

  function markCurrentShowVisited() {
    const show = document.querySelector("[data-show-page]");
    const slug = show?.dataset.showSlug || "";
    if (!slug) return;
    const visits = safeObject(showVisitsKey);
    visits[slug] = Date.now();
    safeSet(showVisitsKey, visits);
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
      description: article.dataset.episodeDescription || "",
      duration: Number(article.dataset.episodeDuration || 0),
      href: article.dataset.episodeHref || `${location.href.split("#")[0]}#${article.id}`,
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
    renderSubscriptions();
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
      const visits = safeObject(showVisitsKey);
      visits[state.slug] = Date.now();
      safeSet(showVisitsKey, visits);
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

  function includePlaybackEntry(state) {
    if (!state?.id) return;
    const entries = queueEntries();
    if (entries.some((item) => item.id === state.id)) return;
    const activeId = activeState?.id || "";
    const activeIndex = entries.findIndex((item) => item.id === activeId);
    if (activeIndex >= 0) {
      entries.splice(activeIndex + 1, 0, state);
    } else {
      entries.unshift(state);
    }
    saveQueue(entries);
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
    if (!played) {
      const progress = safeGet(progressKey(state.id));
      if (progress?.completed) safeRemove(progressKey(state.id));
      const last = safeGet(lastKey);
      if (last?.id === state.id && last.completed) safeRemove(lastKey);
    }
    const states = episodeStateMap();
    states[state.id] = { played, updatedAt: Date.now() };
    safeSet(episodeStateKey, states);
    updateEpisodeActions(article);
    updateEpisodeProgress(article);
    updateResume();
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

  function ensureEpisodeShareButtons() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      const actions = article.querySelector(".episode-actions");
      if (!actions || actions.querySelector("[data-share-episode]")) return;
      const button = document.createElement("button");
      button.className = "button secondary episode-share";
      button.type = "button";
      button.dataset.shareEpisode = "";
      button.dataset.i18n = "share";
      button.textContent = t("share");
      actions.insertBefore(button, actions.querySelector("[data-toggle-played]") || null);
    });
  }

  function hashTarget(hash = location.hash) {
    let fragment = "";
    try {
      fragment = decodeURIComponent(hash.slice(1));
    } catch {
      return null;
    }
    return fragment ? document.getElementById(fragment) : null;
  }

  function highlightSharedEpisode() {
    const article = hashTarget();
    if (!article?.matches("[data-episode-id]")) return;
    article.classList.add("is-deep-linked");
    window.setTimeout(() => article.classList.remove("is-deep-linked"), 5000);
  }

  function episodeShareUrl(article) {
    const slug = article?.dataset.episodeShowSlug || "";
    const anchor = (article?.id || "").replace(/-library-recent$/, "");
    const fragment = anchor ? `#${anchor}` : "";
    if (!slug) return new URL(fragment || location.href, location.href).href;
    return new URL(`${siteRootPath()}${slug}/${fragment}`, location.origin).href;
  }

  async function shareEpisode(article) {
    const state = episodeState(article);
    if (!state) return;
    const url = episodeShareUrl(article);
    const payload = { title: state.title, text: state.show || BRAND, url };
    if (typeof navigator.share === "function") {
      try {
        await navigator.share(payload);
        return;
      } catch (error) {
        if (error?.name === "AbortError") return;
      }
    }
    try {
      await navigator.clipboard.writeText(url);
      announceAppStatus(t("share_copied"));
    } catch {
      announceAppStatus(t("share_failed"), 4200);
    }
  }

  function isVisibleEpisode(article) {
    return Boolean(article && !article.hidden && !article.closest("[hidden]"));
  }

  function updateVisibleEpisodeActions() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      if (isVisibleEpisode(article)) updateEpisodeActions(article);
    });
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
      <article class="drawer-item library-tile">
        <a class="library-tile-art" href="${escapeHtml(item.url)}">${drawerItemImage(item.artwork || "", item.title || "")}</a>
        <div class="library-tile-copy">
          <h3><a href="${escapeHtml(item.url)}">${escapeHtml(item.title)}</a></h3>
          <p>${escapeHtml(item.author || "")}</p>
        </div>
        <button class="button secondary" type="button" data-library-remove="${escapeHtml(item.slug)}">${t("remove_from_library")}</button>
      </article>
    `).join("");
    if (empty) empty.hidden = items.length > 0;
  }

  function renderSubscriptionPage() {
    const page = document.querySelector("[data-subscriptions-page]");
    if (!page) return;
    const followed = new Set(followedShows().map((item) => item.slug));
    const term = normalizeSearchText(page.querySelector("[data-subscription-filter]")?.value || "");
    const sort = page.querySelector("[data-subscription-sort][aria-pressed=true]")?.dataset.subscriptionSort || "recent";
    const grid = page.querySelector("[data-subscriptions-grid]");
    const cards = Array.from(grid?.querySelectorAll("[data-show-card]") || []);
    cards.sort((left, right) => {
      if (sort === "alpha") return (left.dataset.showTitle || "").localeCompare(right.dataset.showTitle || "", html.lang);
      return (right.dataset.showLatest || "").localeCompare(left.dataset.showLatest || "");
    }).forEach((card) => {
      const matches = followed.has(card.dataset.showSlug || "") && (!term || normalizeSearchText(card.dataset.searchItem).includes(term));
      card.hidden = !matches;
      if (matches) grid?.appendChild(card);
      let badge = card.querySelector("[data-new-count]");
      const count = newEpisodeCount(card);
      if (!badge && count > 0) {
        badge = document.createElement("span");
        badge.className = "new-count";
        badge.dataset.newCount = "";
        card.querySelector(".show-card-topline")?.appendChild(badge);
      }
      if (badge) {
        badge.textContent = count > 99 ? "99+" : String(count);
        badge.setAttribute("aria-label", `${count} ${t("new_episodes")}`);
        badge.hidden = count === 0;
      }
    });
    const visible = cards.filter((card) => !card.hidden).length;
    page.querySelector("[data-subscriptions-page-empty]")?.toggleAttribute("hidden", followed.size > 0);
    page.querySelector("[data-subscriptions-page-none]")?.toggleAttribute("hidden", visible > 0 || !followed.size);
    updateFollowButtons();
  }

  function renderSubscriptions() {
    const section = document.querySelector("[data-subscriptions-section]");
    if (!section) return;
    const empty = section.querySelector("[data-subscriptions-empty]");
    const active = section.querySelector("[data-subscriptions-active]");
    const none = section.querySelector("[data-subscriptions-none]");
    const followedItems = followedShows();
    const followed = new Set(followedItems.map((item) => item.slug));
    const hasSubscriptions = followedItems.length > 0;
    const term = normalizeSearchText(document.querySelector("[data-global-search]")?.value);
    if (empty) empty.hidden = hasSubscriptions;
    if (active) active.hidden = !hasSubscriptions;
    if (!hasSubscriptions) {
      const emptyCard = empty?.querySelector(".empty-library-card");
      if (emptyCard) emptyCard.hidden = Boolean(term);
      const suggestionGroup = empty?.querySelector(".subscription-suggestions")?.parentElement;
      let suggestionVisible = 0;
      empty?.querySelectorAll("[data-show-card]").forEach((card) => {
        const matches = !term || normalizeSearchText(card.dataset.searchItem).includes(term);
        card.hidden = !matches;
        if (matches) suggestionVisible += 1;
      });
      if (suggestionGroup) suggestionGroup.hidden = suggestionVisible === 0;
      return;
    }

    let visible = 0;
    let recentVisible = 0;
    section.querySelectorAll("[data-library-recent-episode]").forEach((item) => {
      const matches = followed.has(item.dataset.episodeShowSlug || "")
        && (!term || normalizeSearchText(item.dataset.searchItem).includes(term));
      item.hidden = !matches;
      if (matches) {
        recentVisible += 1;
        updateEpisodeProgress(item);
        updateEpisodeActions(item);
      }
    });
    section.querySelectorAll("[data-subscription-show]").forEach((block) => {
      const card = block.querySelector("[data-show-card]");
      const matches = followed.has(block.dataset.showSlug || "")
        && (!term || normalizeSearchText(card?.dataset.searchItem).includes(term));
      block.hidden = !matches;
      if (matches) visible += 1;
    });
    if (none) none.hidden = visible > 0;
    section.querySelector("[data-library-recent-block]")?.toggleAttribute("hidden", recentVisible === 0);
    updateFollowButtons();
    updateVisibleEpisodeActions();
    updateVisibleEpisodeProgress();
  }

  function renderQueue() {
    const list = document.querySelector("[data-queue-list]");
    const empty = document.querySelector("[data-queue-empty]");
    if (!list) return;
    const clear = document.querySelector("[data-queue-clear]");
    const activeId = activeState?.id || "";
    const items = queueEntries();
    list.innerHTML = items.map((item, index) => {
      const duration = item.duration ? formatTime(item.duration) : "";
      return `
      <article class="drawer-item queue-item${item.id === activeId ? " is-current" : ""}" data-queue-id="${escapeHtml(item.id)}">
        ${drawerItemImage(item.artwork || "", "")}
        <div>
          <h3><a href="${escapeHtml(item.href || "#")}">${escapeHtml(item.title)}</a>${item.id === activeId ? ` <span class="queue-current">${t("now_playing")}</span>` : ""}</h3>
          <p class="queue-meta">${escapeHtml(item.show || "")}${duration ? ` · ${escapeHtml(duration)}` : ""}</p>
        </div>
        <div class="drawer-actions">
          <span class="queue-drag-handle" data-queue-drag-handle role="button" tabindex="0" aria-label="${t("reorder_queue")}" title="${t("reorder_queue")}">⋮⋮</span>
          <button class="button primary icon-button queue-play-button" type="button" data-queue-play="${escapeHtml(item.id)}" aria-label="${t("listen")}" title="${t("listen")}"><span aria-hidden="true">▶</span><span class="sr-only">${t("listen")}</span></button>
          <button class="button secondary icon-button" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="-1" aria-label="${t("move_up")}" title="${t("move_up")}" ${index === 0 ? "disabled" : ""}><span aria-hidden="true">↑</span><span class="sr-only">${t("move_up")}</span></button>
          <button class="button secondary icon-button" type="button" data-queue-move="${escapeHtml(item.id)}" data-queue-delta="1" aria-label="${t("move_down")}" title="${t("move_down")}" ${index === items.length - 1 ? "disabled" : ""}><span aria-hidden="true">↓</span><span class="sr-only">${t("move_down")}</span></button>
          <button class="button secondary icon-button" type="button" data-queue-remove="${escapeHtml(item.id)}" aria-label="${t("remove_from_queue")}" title="${t("remove_from_queue")}"><span aria-hidden="true">×</span><span class="sr-only">${t("remove_from_queue")}</span></button>
        </div>
      </article>
    `;
    }).join("");
    bindQueueDrag(list);
    if (empty) empty.hidden = items.length > 0;
    if (clear) clear.hidden = items.length === 0;
    document.querySelectorAll("[data-queue-count]").forEach((node) => {
      node.textContent = String(items.length);
      node.hidden = items.length === 0;
    });
    document.querySelectorAll("[data-queue-preview]").forEach((preview) => {
      preview.innerHTML = items.slice(0, 3).map((item) => `
        <article class="queue-preview-item">
          ${drawerItemImage(item.artwork || "", "")}
          <div><strong>${escapeHtml(item.title)}</strong><span>${escapeHtml(item.show || "")}</span></div>
          <button class="button primary icon-button" type="button" data-queue-play="${escapeHtml(item.id)}" aria-label="${t("listen")}">▶</button>
        </article>
      `).join("");
    });
    document.querySelectorAll("[data-queue-preview-empty]").forEach((node) => {
      node.hidden = items.length > 0;
    });
  }

  function updateQueueUi() {
    renderQueue();
    updateVisibleEpisodeActions();
    updateQueueNavButtons();
  }

  function updateLibraryAndQueueUi() {
    updateFollowButtons();
    renderLibrary();
    renderSubscriptions();
    renderSubscriptionPage();
    updateQueueUi();
  }

  async function playQueuedEntry(entry) {
    if (!entry?.id) return;
    if (nativeAudioBridge() && entry.src) {
      playNativeState(entry);
      return;
    }
    let article = Array.from(document.querySelectorAll("[data-episode-id]"))
      .find((candidate) => candidate.dataset.episodeId === entry.id);
    if (!article && entry.href) {
      await navigateTo(entry.href);
      article = Array.from(document.querySelectorAll("[data-episode-id]"))
        .find((candidate) => candidate.dataset.episodeId === entry.id);
    }
    if (article) playEpisode(article);
    else if (entry.src) playHtmlState(entry);
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

  function bindQueueDrag(list) {
    if (!list || list.dataset.queueDragBound) return;
    list.dataset.queueDragBound = "true";
    let drag = null;
    const finish = (event, save) => {
      if (!drag || (event && event.pointerId !== drag.pointerId)) return;
      drag.source.classList.remove("is-dragging");
      try { drag.source.releasePointerCapture(drag.pointerId); } catch {}
      const moved = drag.moved;
      drag = null;
      if (save && moved) {
        const entries = queueEntries();
        const ordered = Array.from(list.querySelectorAll("[data-queue-id]"))
          .map((node) => entries.find((item) => item.id === node.dataset.queueId))
          .filter(Boolean);
        saveQueue(ordered);
      }
    };
    list.addEventListener("pointerdown", (event) => {
      const handle = event.target.closest?.("[data-queue-drag-handle]");
      const source = handle?.closest("[data-queue-id]");
      if (!source || event.button > 0) return;
      drag = { pointerId: event.pointerId, source, moved: false };
      source.classList.add("is-dragging");
      source.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });
    list.addEventListener("pointermove", (event) => {
      if (!drag || event.pointerId !== drag.pointerId) return;
      const target = document.elementFromPoint(event.clientX, event.clientY)?.closest?.("[data-queue-id]");
      if (!target || target === drag.source || !list.contains(target)) return;
      const rect = target.getBoundingClientRect();
      if (event.clientY < rect.top + rect.height / 2) list.insertBefore(drag.source, target);
      else list.insertBefore(drag.source, target.nextSibling);
      drag.moved = true;
      event.preventDefault();
    });
    list.addEventListener("pointerup", (event) => finish(event, true));
    list.addEventListener("pointercancel", (event) => finish(event, false));
  }

  function playNextQueuedAfter(currentId) {
    const entries = queueEntries();
    const currentIndex = entries.findIndex((item) => item.id === currentId);
    if (currentIndex < 0) return;
    const remaining = entries.filter((item) => item.id !== currentId);
    saveQueue(remaining);
    const next = remaining[currentIndex] || remaining[0];
    if (next) playQueuedEntry(next);
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

  function setPlayerExpanded(expanded) {
    if (!player) return;
    if (expanded) playerExpandedTrigger = document.activeElement;
    player.classList.toggle("is-expanded", expanded);
    document.body.classList.toggle("has-expanded-player", expanded);
    playerDetails?.setAttribute("aria-expanded", String(expanded));
    if (expanded) {
      player.setAttribute("role", "dialog");
      player.setAttribute("aria-modal", "true");
      player.setAttribute("aria-label", t("full_player"));
      playerMinimize?.focus();
    } else {
      player.removeAttribute("role");
      player.removeAttribute("aria-modal");
      player.setAttribute("aria-label", t("audio_player"));
      if (playerExpandedTrigger?.isConnected) playerExpandedTrigger.focus();
      playerExpandedTrigger = null;
    }
  }

  function updatePlayerLinks(state) {
    if (playerEpisodeLink) {
      playerEpisodeLink.textContent = state?.title || "";
      playerEpisodeLink.href = state?.href || "#";
    }
    if (playerShowLink) {
      playerShowLink.textContent = state?.show || "";
      playerShowLink.href = state?.showSlug ? `${siteRootPath()}${state.showSlug}/` : "#";
      playerShowLink.hidden = !state?.showSlug;
    }
  }

  function setDrawerActiveState(drawer) {
    const libraryActive = Boolean(drawer?.matches("[data-library-drawer]"));
    const queueActive = Boolean(drawer?.matches("[data-queue-drawer]"));
    document.body.classList.toggle("app-drawer-open", libraryActive || queueActive);
    document.querySelectorAll("[data-library-open]").forEach((node) => {
      node.setAttribute("aria-pressed", String(libraryActive));
      node.setAttribute("aria-expanded", String(libraryActive));
    });
    document.querySelectorAll("[data-queue-open]").forEach((node) => {
      node.setAttribute("aria-pressed", String(queueActive));
      node.setAttribute("aria-expanded", String(queueActive));
    });
  }

  function openDrawer(drawer, trigger = null) {
    if (!drawer) return;
    lastDrawerTrigger = trigger || document.activeElement;
    setPlayerExpanded(false);
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = node !== drawer;
    });
    drawer.hidden = false;
    setDrawerActiveState(drawer);
    drawer.querySelector("[data-drawer-close]")?.focus();
  }

  function closeDrawers({ restoreFocus = true } = {}) {
    document.querySelectorAll("[data-library-drawer], [data-queue-drawer]").forEach((node) => {
      node.hidden = true;
    });
    setDrawerActiveState(null);
    if (restoreFocus && lastDrawerTrigger?.isConnected) lastDrawerTrigger.focus();
    lastDrawerTrigger = null;
  }

  function handleAppBack() {
    const openDrawer = document.querySelector("[data-library-drawer]:not([hidden]), [data-queue-drawer]:not([hidden])");
    if (openDrawer) {
      closeDrawers();
      return true;
    }
    if (player?.classList.contains("is-expanded")) {
      setPlayerExpanded(false);
      return true;
    }
    if (history.length > 1) {
      history.back();
      return true;
    }
    return false;
  }

  window.TorahPodHandleBack = handleAppBack;

  function loadAudio(audio) {
    if (!audio.src && audio.dataset.audioSrc) {
      audio.src = audio.dataset.audioSrc;
      audio.preload = "none";
    }
    applyPlaybackRate(audio);
  }

  function audioForEpisode(article) {
    if (!article) return null;
    let audio = article.querySelector("audio[data-audio-src]");
    if (audio) return audio;
    const state = episodeState(article);
    if (!state?.src) return null;
    audio = document.createElement("audio");
    audio.hidden = true;
    audio.setAttribute("aria-hidden", "true");
    audio.preload = "none";
    audio.dataset.audioSrc = state.src;
    article.append(audio);
    return audio;
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

  function updateVisibleEpisodeProgress() {
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      if (isVisibleEpisode(article)) updateEpisodeProgress(article);
    });
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

  function saveCurrentStateProgress(audio, state) {
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
      previoustrack: () => playAdjacentQueued(-1),
      nexttrack: () => playAdjacentQueued(1),
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
    activeNativeState = null;
    activeNativePlaying = false;
    activeAudio = audio;
    activeEpisode = article;
    activeState = episodeState(article);
    if (!player || !activeState) return;
    document.body.classList.add("has-player");
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    updatePlayerLinks(activeState);
    if (playerArtwork) {
      playerArtwork.src = activeState.artwork || "";
      playerArtwork.hidden = !activeState.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = activeState.description || "";
      playerDescription.hidden = !activeState.description;
    }
    player.hidden = false;
    player.classList.remove("is-buffering");
    playerDetails?.setAttribute("aria-expanded", player.classList.contains("is-expanded") ? "true" : "false");
    setPlayerToggle(!audio.paused);
    if (playerSeek) playerSeek.disabled = false;
    if (playerVolume) playerVolume.disabled = false;
    applyPlaybackVolume(audio);
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

  function setPlayerStateForState(audio, state) {
    if (playerClosed) return;
    if (audio === closingAudio) return;
    activeNativeState = null;
    activeNativePlaying = false;
    activeAudio = audio;
    activeEpisode = null;
    activeState = state;
    if (!player || !activeState) return;
    document.body.classList.add("has-player");
    playerTitle.textContent = activeState.title;
    playerShow.textContent = activeState.show;
    updatePlayerLinks(activeState);
    if (playerArtwork) {
      playerArtwork.src = activeState.artwork || "";
      playerArtwork.hidden = !activeState.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = activeState.description || "";
      playerDescription.hidden = !activeState.description;
    }
    player.hidden = false;
    player.classList.remove("is-buffering");
    playerDetails?.setAttribute("aria-expanded", player.classList.contains("is-expanded") ? "true" : "false");
    setPlayerToggle(!audio.paused);
    if (playerSeek) playerSeek.disabled = false;
    if (playerVolume) playerVolume.disabled = false;
    applyPlaybackVolume(audio);
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

  function setNativePlayerState(state) {
    if (!player || !state?.src) return;
    activeNativeState = state;
    activeNativePlaying = false;
    activeAudio = null;
    activeEpisode = null;
    activeState = state;
    document.body.classList.add("has-player");
    playerTitle.textContent = state.title || "";
    playerShow.textContent = state.show || "";
    updatePlayerLinks(state);
    if (playerArtwork) {
      playerArtwork.src = state.artwork || "";
      playerArtwork.hidden = !state.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = state.description || "";
      playerDescription.hidden = !state.description;
    }
    player.hidden = false;
    player.classList.add("is-buffering");
    setPlayerToggle(false, true);
    updatePlayerTime(0, 0);
    updateMiniProgress(0, 0);
    if (playerSeek) {
      playerSeek.max = "1";
      playerSeek.value = "0";
      playerSeek.disabled = true;
    }
    if (playerVolume) playerVolume.disabled = true;
    updateQueueNavButtons();
    if (renderedActiveQueueId !== state.id) {
      renderedActiveQueueId = state.id;
      updateQueueUi();
    }
    updateResume();
  }

  function setPendingHtmlPlayerState(audio, state, article = null) {
    if (playerClosed || !player || !state?.src) return;
    activeNativeState = null;
    activeNativePlaying = false;
    activeAudio = audio;
    activeEpisode = article;
    activeState = state;
    document.body.classList.add("has-player");
    playerTitle.textContent = state.title || "";
    playerShow.textContent = state.show || "";
    updatePlayerLinks(state);
    if (playerArtwork) {
      playerArtwork.src = state.artwork || "";
      playerArtwork.hidden = !state.artwork;
    }
    if (playerDescription) {
      playerDescription.textContent = state.description || "";
      playerDescription.hidden = !state.description;
    }
    player.hidden = false;
    player.classList.add("is-buffering");
    playerDetails?.setAttribute("aria-expanded", player.classList.contains("is-expanded") ? "true" : "false");
    setPlayerToggle(false, true);
    updatePlayerTime(0, state.duration || 0);
    updateMiniProgress(0, state.duration || 0);
    if (playerSeek) {
      playerSeek.max = String(Math.max(1, Math.floor(state.duration || 1)));
      playerSeek.value = "0";
      playerSeek.disabled = true;
    }
    updateQueueNavButtons();
    if (renderedActiveQueueId !== state.id) {
      renderedActiveQueueId = state.id;
      updateQueueUi();
    }
    updateResume();
  }

  function saveNativeProgress(position, duration) {
    if (!activeNativeState?.id) return;
    const now = Date.now();
    if (activeNativeState.lastSavedAt && now - activeNativeState.lastSavedAt < 4000) return;
    activeNativeState.lastSavedAt = now;
    const payload = {
      ...activeNativeState,
      position,
      duration,
      completed: false,
      updatedAt: now,
    };
    if (duration && duration - position < 20) {
      payload.position = 0;
      payload.completed = true;
    }
    safeSet(progressKey(activeNativeState.id), payload);
    safeSet(lastKey, payload);
    updateResume();
  }

  function updateNativeProgress(payload = {}) {
    if (!activeNativeState || !player) return;
    const duration = Math.max(0, Number(payload.duration || activeNativeState.duration || 0));
    const position = Math.max(0, Number(payload.position || 0));
    activeNativeState.duration = duration || activeNativeState.duration || 0;
    activeNativePlaying = payload.playing === true;
    if (activeNativePlaying || position > 0 || duration > 0) clearNativeFallback();
    player.classList.toggle("is-buffering", !activeNativePlaying && position === 0 && duration === 0);
    setPlayerToggle(activeNativePlaying);
    updatePlayerTime(position, duration);
    updateMiniProgress(position, duration);
    if (playerSeek) {
      playerSeek.disabled = duration <= 0;
      playerSeek.max = String(Math.max(1, Math.floor(duration || 1)));
      if (!seeking) playerSeek.value = String(Math.floor(Math.min(position, duration || position)));
      playerSeek.setAttribute("aria-valuetext", `${formatTime(position)} / ${duration ? formatTime(duration) : "--"}`);
    }
    saveNativeProgress(position, duration);
  }

  window.TorahPodNativeProgress = updateNativeProgress;

  function clearNativeFallback() {
    if (!nativeFallbackTimer) return;
    clearTimeout(nativeFallbackTimer);
    nativeFallbackTimer = 0;
  }

  function scheduleNativeFallback(state, requestId) {
    clearNativeFallback();
    nativeFallbackTimer = window.setTimeout(() => {
      nativeFallbackTimer = 0;
      if (requestId !== nativePlaybackRequestId) return;
      if (!activeNativeState || activeNativeState.id !== state.id) return;
      try {
        nativeAudioBridge()?.stop();
      } catch {
        // Native stop is best-effort before falling back to HTML audio.
      }
      activeNativeState = null;
      activeNativePlaying = false;
      player?.classList.remove("is-buffering");
      playHtmlState(state);
    }, 3200);
  }

  function updatePlayerProgress() {
    if (!player || !activeAudio) return;
    const duration = Number.isFinite(activeAudio.duration) && activeAudio.duration > 0
      ? activeAudio.duration
      : Number(activeEpisode?.dataset.episodeDuration || activeState?.duration || 0);
    const position = activeAudio.currentTime || 0;
    updatePlayerTime(position, duration);
    updateMiniProgress(position, duration);
    if (playerSeek && !seeking) {
      playerSeek.max = String(Math.max(1, Math.floor(duration || 1)));
      playerSeek.value = String(Math.floor(position));
      playerSeek.setAttribute("aria-valuetext", `${formatTime(position)} / ${formatTime(duration)}`);
    }
    if (activeState) updateMediaSession(activeAudio, activeState);
  }

  function rememberCurrentState(state) {
    if (!state?.id) return null;
    const saved = safeGet(progressKey(state.id));
    const payload = {
      ...state,
      position: Number(saved?.position || 0),
      duration: Number(state.duration || saved?.duration || 0),
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

  function playNativeState(state) {
    const bridge = nativeAudioBridge();
    if (!bridge || !state?.src) return false;
    recordPlaybackEvent("native-play-request", { id: state.id, title: state.title });
    const requestId = ++nativePlaybackRequestId;
    invalidatePlaybackAttempt();
    clearPlaybackStatus();
    closingAudio = null;
    playerClosed = false;
    stopOtherAudio(null);
    rememberCurrentState(state);
    setNativePlayerState(state);
    try {
      bridge.play(JSON.stringify(state));
      scheduleNativeFallback(state, requestId);
      return true;
    } catch {
      clearNativeFallback();
      activeNativeState = null;
      activeNativePlaying = false;
      return false;
    }
  }

  function playNativeEpisode(article) {
    const state = episodeState(article);
    if (!state?.src) return false;
    includePlaybackEntry(state);
    return playNativeState(state);
  }

  function playHtmlState(state) {
    if (!state?.src) return false;
    recordPlaybackEvent("html-state-play-request", { id: state.id, title: state.title });
    clearNativeFallback();
    nativePlaybackRequestId += 1;
    if (activeNativeState) {
      try {
        nativeAudioBridge()?.stop();
      } catch {
        // Native stop is best-effort before falling back to HTML audio.
      }
      activeNativeState = null;
      activeNativePlaying = false;
    }
    closingAudio = null;
    playerClosed = false;
    const audio = document.createElement("audio");
    audio.hidden = true;
    audio.setAttribute("aria-hidden", "true");
    audio.preload = "none";
    audio.dataset.audioSrc = state.src;
    audioDock.append(audio);
    loadAudio(audio);
    rememberCurrentState(state);
    includePlaybackEntry(state);
    setPendingHtmlPlayerState(audio, state);
    recordPlaybackEvent("pending-player-shown", { id: state.id, title: state.title });
    const retry = () => playHtmlState(state);
    const attemptId = beginPlaybackAttempt(audio, state, null, retry);
    audio.addEventListener("playing", () => {
      if (!completePlaybackAttempt(audio)) return;
      recordPlaybackEvent("audio-play", { id: state.id, title: state.title });
      stopOtherAudio(audio);
      setPlayerStateForState(audio, state);
      syncNativeNotification(audio, state, true, { force: true });
    });
    audio.addEventListener("pause", () => {
      if (audio !== activeAudio || closingAudio === audio) return;
      recordPlaybackEvent("audio-pause", { id: state.id, title: state.title, position: audio.currentTime });
      saveCurrentStateProgress(audio, state);
      if (audio === activeAudio) {
        setPlayerStateForState(audio, state);
        if (closingAudio !== audio) syncNativeNotification(audio, state, false, { force: true });
      }
    });
    audio.addEventListener("timeupdate", () => {
      if (audio !== activeAudio) return;
      setPlayerStateForState(audio, state);
      syncNativeNotification(audio, state, !audio.paused);
      if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
        audio.dataset.lastSavedAt = String(Date.now());
        saveCurrentStateProgress(audio, state);
      }
    });
    audio.addEventListener("ended", () => {
      if (audio !== activeAudio || closingAudio === audio) return;
      recordPlaybackEvent("audio-ended", { id: state.id, title: state.title });
      saveCurrentStateProgress(audio, state);
      stopNativeNotification();
      playNextQueuedAfter(state.id || "");
    });
    audio.addEventListener("error", () => {
      failPlaybackAttempt(audio, state, null, retry, "media-error");
    });
    audio.play().then(() => {
      if (!isCurrentPlaybackAttempt(audio, attemptId)) return;
      completePlaybackAttempt(audio);
      setPlayerStateForState(audio, state);
    }).catch(() => failPlaybackAttempt(audio, state, null, retry, "play-failed", attemptId));
    return true;
  }

  function dockActiveAudio() {
    if (activeAudio && activeAudio.parentElement !== audioDock) {
      audioDock.append(activeAudio);
    }
  }

  function stopOtherAudio(nextAudio) {
    document.querySelectorAll("audio").forEach((candidate) => {
      if (candidate === nextAudio || candidate.paused) return;
      if (candidate === activeAudio) closingAudio = candidate;
      candidate.pause();
    });
    if (activeAudio && activeAudio !== nextAudio) {
      closingAudio = activeAudio;
      activeAudio.pause();
      if (activeEpisode) {
        saveCurrentProgress(activeAudio, activeEpisode);
      } else if (activeState) {
        saveCurrentStateProgress(activeAudio, activeState);
      }
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
    const requestedState = episodeState(article);
    if (requestedState) recordPlaybackEvent("episode-play-tap", { id: requestedState.id, title: requestedState.title });
    if (playNativeEpisode(article)) return;
    const audio = audioForEpisode(article);
    if (!audio) return;
    closingAudio = null;
    playerClosed = false;
    if (activeNativeState) {
      try {
        nativeAudioBridge()?.stop();
      } catch {
        // Native stop is best-effort before falling back to HTML audio.
      }
      activeNativeState = null;
      activeNativePlaying = false;
    }
    bindEpisodeAudio(audio, article);
    if (audio.dataset.playbackFailed === "true") {
      delete audio.dataset.progressRestored;
      try { audio.load(); } catch { /* Retry can continue through play(). */ }
    }
    loadAudio(audio);
    restoreProgress(audio, article);
    rememberCurrentEpisode(audio, article);
    const state = requestedState || episodeState(article);
    includePlaybackEntry(state);
    setPendingHtmlPlayerState(audio, state, article);
    recordPlaybackEvent("pending-player-shown", { id: state.id, title: state.title });
    const retry = () => playEpisode(article);
    const attemptId = beginPlaybackAttempt(audio, state, article, retry);
    audio.play().then(() => {
      if (!isCurrentPlaybackAttempt(audio, attemptId)) return;
      completePlaybackAttempt(audio);
      setPlayerState(audio, article);
    }).catch(() => failPlaybackAttempt(audio, state, article, retry, "play-failed", attemptId));
  }

  function updateResume() {
    const saved = safeGet(lastKey);
    const valid = saved && saved.position > 10 && (!saved.duration || saved.duration - saved.position > 20);
    const dismissed = saved && resumeDismissedId === saved.id;
    const alreadyShown = saved && resumeShownId === saved.id && resumeVisibleForId !== saved.id;
    const playerActive = Boolean(activeState) || (player && !player.hidden);
    const homeResume = document.querySelector("[data-home-resume]");
    if (homeResume) {
      const showHomeResume = Boolean(valid && !dismissed && !playerActive);
      homeResume.hidden = !showHomeResume;
      if (showHomeResume) {
        const title = homeResume.querySelector("[data-home-resume-title]");
        const show = homeResume.querySelector("[data-home-resume-show]");
        if (title) title.textContent = saved.title || "";
        if (show) show.textContent = `${saved.show || ""} · ${formatTime(saved.position)}`;
      }
    }
    if (!resume) return;
    if (homeResume) {
      resume.hidden = true;
      return;
    }
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
    ensureEpisodeShareButtons();
    highlightSharedEpisode();
    document.querySelectorAll("[data-episode-id]").forEach((article) => {
      if (!isVisibleEpisode(article)) return;
      updateEpisodeProgress(article);
      updateEpisodeActions(article);
    });
  }

  function bindEpisodeAudio(audio, article) {
    if (!audio || audio.dataset.bound === "true") return;
    audio.dataset.bound = "true";
    audio.addEventListener("loadedmetadata", () => restoreProgress(audio, article));
    audio.addEventListener("playing", () => {
      if (!completePlaybackAttempt(audio)) return;
      const state = episodeState(article);
      recordPlaybackEvent("audio-play", { id: state?.id, title: state?.title });
      closingAudio = null;
      playerClosed = false;
      stopOtherAudio(audio);
      restoreProgress(audio, article);
      rememberCurrentEpisode(audio, article);
      setPlayerState(audio, article);
      syncNativeNotification(audio, episodeState(article), true, { force: true });
    });
    audio.addEventListener("error", () => {
      const state = episodeState(article);
      failPlaybackAttempt(
        audio,
        state,
        article,
        () => playEpisode(article),
        "media-error"
      );
    });
    audio.addEventListener("pause", () => {
      const state = episodeState(article);
      recordPlaybackEvent("audio-pause", { id: state?.id, title: state?.title, position: audio.currentTime });
      if (playerClosed && closingAudio === audio) return;
      saveCurrentProgress(audio, article);
      if (closingAudio === audio) return;
      if (audio === activeAudio) {
        setPlayerState(audio, article);
        syncNativeNotification(audio, episodeState(article), false, { force: true });
      }
    });
    audio.addEventListener("timeupdate", () => {
      if (playerClosed) return;
      if (closingAudio === audio) return;
      if (audio !== activeAudio) return;
      setPlayerState(audio, article);
      syncNativeNotification(audio, episodeState(article), !audio.paused);
      if (!audio.dataset.lastSavedAt || Date.now() - Number(audio.dataset.lastSavedAt) > 4000) {
        audio.dataset.lastSavedAt = String(Date.now());
        saveCurrentProgress(audio, article);
      }
    });
    audio.addEventListener("ended", () => {
      const state = episodeState(article);
      recordPlaybackEvent("audio-ended", { id: state?.id, title: state?.title });
      if (playerClosed) return;
      if (closingAudio === audio) return;
      saveCurrentProgress(audio, article);
      setPlayed(article, true);
      updatePlayerProgress();
      stopNativeNotification();
      playNextQueuedAfter(article.dataset.episodeId || "");
    });
  }

  function setupPlayerControls() {
    if (player && !playerVolume) {
      playerVolume = document.createElement("input");
      playerVolume.className = "player-volume";
      playerVolume.type = "range";
      playerVolume.min = "0";
      playerVolume.max = "1";
      playerVolume.step = "0.05";
      playerVolume.value = String(playbackVolume());
      playerVolume.setAttribute("aria-label", t("volume"));
      updateVolumeControl();
      playerVolume.addEventListener("input", () => {
        const volume = Math.min(1, Math.max(0, Number(playerVolume.value || 1)));
        safeSet("torahpod-volume", volume);
        if (activeAudio) activeAudio.volume = volume;
        updateVolumeControl(volume);
      });
      (player.querySelector(".player-secondary-controls") || player).appendChild(playerVolume);
    }
    const closePlayer = () => {
      const audio = activeAudio;
      const article = activeEpisode;
      const nativeState = activeNativeState;
      if (player) player.hidden = true;
      setPlayerExpanded(false);
      invalidatePlaybackAttempt();
      clearPlaybackStatus();
      playerClosed = true;
      activeAudio = null;
      activeState = null;
      activeEpisode = null;
      activeNativeState = null;
      activeNativePlaying = false;
      renderedActiveQueueId = "";
      document.body.classList.remove("has-player");
      updateQueueUi();
      updateQueueNavButtons();
      if (audio) {
        closingAudio = audio;
        audio.pause();
        saveCurrentProgress(audio, article);
        stopNativeNotification();
      }
      if (nativeState) {
        try {
          nativeAudioBridge()?.stop();
        } catch {
          // Native stop is best-effort.
        }
      }
      player?.classList.remove("is-buffering");
      updateResume();
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
      if (activeNativeState) {
        try {
          nativeAudioBridge()?.toggle();
          activeNativePlaying = !activeNativePlaying;
          setPlayerToggle(activeNativePlaying);
        } catch {
          // Native toggle is best-effort.
        }
        return;
      }
      if (!activeAudio) return;
      if (activeAudio.paused) resumeHtmlPlayback();
      else activeAudio.pause();
    });
    playerPrev?.addEventListener("click", () => playAdjacentQueued(-1));
    playerNext?.addEventListener("click", () => playAdjacentQueued(1));
    playerSpeed?.addEventListener("click", cyclePlaybackRate);
    playerMinimize?.addEventListener("click", () => setPlayerExpanded(false));
    document.querySelectorAll("[data-player-skip]").forEach((button) => {
      button.addEventListener("click", () => {
        const delta = Number(button.dataset.playerSkip || 0);
        if (activeNativeState) {
          nativeSeekBy(delta);
          return;
        }
        if (!activeAudio) return;
        activeAudio.currentTime = Math.max(0, Math.min(activeAudio.duration || activeAudio.currentTime + delta, activeAudio.currentTime + delta));
      });
    });
    playerSeek?.addEventListener("input", () => {
      seeking = true;
      if (activeNativeState) {
        nativeSeekTo(Number(playerSeek.value || 0));
        seeking = false;
        return;
      }
      if (activeAudio) activeAudio.currentTime = Number(playerSeek.value || 0);
      seeking = false;
    });
    bindClosePress(playerClose, closePlayer);
    playerDetails?.addEventListener("click", () => {
      if (!player) return;
      if (player.classList.contains("is-expanded")) return;
      setPlayerExpanded(true);
    });
    let playerTouchStartY = 0;
    player?.addEventListener("touchstart", (event) => {
      playerTouchStartY = event.touches[0]?.clientY || 0;
    }, { passive: true });
    player?.addEventListener("touchend", (event) => {
      const endY = event.changedTouches[0]?.clientY || playerTouchStartY;
      const delta = endY - playerTouchStartY;
      if (!player.classList.contains("is-expanded") && delta < -60) setPlayerExpanded(true);
      if (player.classList.contains("is-expanded") && delta > 80) setPlayerExpanded(false);
    }, { passive: true });
    resumeButton?.addEventListener("click", resumeLast);
    bindClosePress(resumeClose, closeResume);
  }

  function setupLists() {
    listBindingsAbortController?.abort();
    listBindingsAbortController = new AbortController();
    const listBindingSignal = listBindingsAbortController.signal;
    document.querySelector("[data-global-search]")?.addEventListener("input", () => renderSubscriptions());
    document.querySelectorAll("[data-list]").forEach((list) => {
      const pageSize = Number(list.dataset.pageSize || "24");
      let visibleLimit = pageSize;
      const controls = document.querySelector(`[data-list-controls="${list.id}"]`);
      const search = document.querySelector(`[data-search-target="${list.id}"]`) || document.querySelector("[data-global-search]");
      const filterToggle = document.querySelector(`[data-filter-toggle="${list.id}"]`);
      const libraryToggle = document.querySelector(`[data-library-filter-toggle="${list.id}"]`);
      const more = document.querySelector(`[data-load-more="${list.id}"]`);
      const items = Array.from(list.querySelectorAll("[data-list-item]"));
      const resultStatus = document.createElement("p");
      resultStatus.className = "list-result-status";
      resultStatus.setAttribute("role", "status");
      resultStatus.setAttribute("aria-live", "polite");
      controls?.appendChild(resultStatus);
      const emptyState = document.createElement("p");
      emptyState.className = "list-empty-state";
      emptyState.setAttribute("role", "status");
      emptyState.hidden = true;
      list.appendChild(emptyState);
      if (!items.length) {
        controls?.setAttribute("hidden", "");
        if (more) more.hidden = true;
        return;
      }
      function matches(item) {
        const term = normalizeSearchText(search?.value);
        const hostedOnly = filterToggle?.getAttribute("aria-pressed") === "true";
        const libraryOnly = libraryToggle?.getAttribute("aria-pressed") === "true";
        const itemFilter = item.dataset.filterValue || "";
        const showSlug = item.dataset.showSlug || item.dataset.episodeShowSlug || "";
        const matchesTerm = !term || normalizeSearchText(item.dataset.searchItem).includes(term);
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
          if (item.matches("[data-episode-id]")) {
            updateEpisodeProgress(item);
            updateEpisodeActions(item);
          }
        });
        if (more) more.hidden = matched.length <= visibleLimit;
        emptyState.hidden = matched.length > 0;
        emptyState.textContent = t("no_search_results");
        if (html.lang === "he") {
          resultStatus.textContent = matched.length === items.length
            ? `${matched.length} פריטים`
            : `${matched.length} תוצאות`;
        } else {
          resultStatus.textContent = matched.length === items.length
            ? `${matched.length} items`
            : `${matched.length} matching items`;
        }
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
      }, { signal: listBindingSignal });
      document.addEventListener("torahpod:languagechange", render, { signal: listBindingSignal });
      more?.addEventListener("click", () => {
        visibleLimit += pageSize;
        render();
      });
      render();
    });
  }

  function searchScore(query, title, show, author) {
    const normalizedTitle = normalizeSearchText(title);
    const normalizedShow = normalizeSearchText(show);
    const normalizedAuthor = normalizeSearchText(author);
    const tokens = query.split(" ").filter(Boolean);
    if (!tokens.every((token) => `${normalizedTitle} ${normalizedShow} ${normalizedAuthor}`.includes(token))) return 0;
    if (normalizedTitle === query) return 500;
    if (normalizedTitle.startsWith(query)) return 400;
    if (tokens.every((token) => normalizedTitle.includes(token))) return 300;
    if (normalizedShow.includes(query)) return 200;
    if (normalizedAuthor.includes(query)) return 150;
    return 100;
  }

  function loadSearchIndex() {
    if (searchIndexPromise) return searchIndexPromise;
    const url = new URL(`${basePath}search-index.json`, location.href);
    searchIndexPromise = fetch(url.href)
      .then((response) => {
        if (!response.ok) throw new Error(`Search index failed: ${response.status}`);
        return response.json();
      })
      .then((payload) => {
        if (payload?.schema_version !== 1 || !Array.isArray(payload.episodes)) throw new Error("Invalid search index");
        return payload.episodes;
      })
      .catch((error) => {
        searchIndexPromise = null;
        throw error;
      });
    return searchIndexPromise;
  }

  function searchEpisodeMarkup(item, show) {
    const pageUrl = new URL(`${basePath}${item.page_url}`, location.href).href;
    const showUrl = new URL(`${basePath}${item.show_slug}/`, location.href).href;
    const artwork = show?.dataset.showArtwork ? new URL(show.dataset.showArtwork, location.href).href : "";
    const stateId = escapeHtml(item.id || "");
    return `
      <article id="search-${stateId.replace(/[^a-zA-Z0-9_-]/g, "-")}" class="episode search-episode" data-episode-id="${stateId}" data-episode-title="${escapeHtml(item.title || "")}" data-episode-show="${escapeHtml(show?.dataset.showTitle || "")}" data-episode-show-slug="${escapeHtml(item.show_slug || "")}" data-episode-artwork="${escapeHtml(artwork)}" data-episode-duration="${Number(item.duration || 0)}" data-episode-src="${escapeHtml(item.audio_url || "")}" data-episode-href="${escapeHtml(pageUrl)}" data-episode-description="" data-search-item="${escapeHtml(item.title || "")}">
        ${artwork ? `<img class="episode-artwork" src="${escapeHtml(artwork)}" alt="">` : ""}
        <div class="episode-head"><div><h3><a href="${escapeHtml(pageUrl)}">${escapeHtml(item.title || "")}</a></h3><p class="muted episode-show-link"><a href="${escapeHtml(showUrl)}">${escapeHtml(show?.dataset.showTitle || "")}</a></p></div><p class="episode-meta">${escapeHtml(item.published || "")}${item.duration ? ` · ${formatTime(item.duration)}` : ""}</p></div>
        <audio preload="none" data-audio-src="${escapeHtml(item.audio_url || "")}" hidden aria-hidden="true"></audio>
        <p class="episode-progress" data-episode-progress hidden></p>
        <div class="episode-actions"><button class="button episode-play" type="button" data-episode-play data-i18n="listen">${t("listen")}</button><button class="button secondary episode-queue" type="button" data-queue-add data-i18n="add_to_queue">${t("add_to_queue")}</button><button class="button secondary episode-queue-next" type="button" data-queue-next data-i18n="play_next">${t("play_next")}</button></div>
      </article>`;
  }

  function setupCatalogSearch() {
    const page = document.querySelector("[data-search-page]");
    if (!page || page.dataset.bound === "true") return;
    page.dataset.bound = "true";
    const input = page.querySelector("[data-catalog-search]");
    const podcastGrid = page.querySelector("[data-search-podcast-catalog]");
    const episodeList = page.querySelector("[data-search-episode-results]");
    const status = page.querySelector("[data-search-status]");
    const more = page.querySelector("[data-search-more]");
    let episodeLimit = 30;
    let resultToken = 0;
    let currentMatches = [];

    const podcastCards = Array.from(podcastGrid?.querySelectorAll("[data-show-card]") || []);
    const showMap = new Map(podcastCards.map((card) => [card.dataset.showSlug, card]));
    const renderEpisodes = () => {
      if (episodeList) episodeList.innerHTML = currentMatches.slice(0, episodeLimit).map((item) => searchEpisodeMarkup(item, showMap.get(item.show_slug))).join("");
      if (more) more.hidden = currentMatches.length <= episodeLimit;
      setupEpisodes();
      updateVisibleEpisodeActions();
      updateVisibleEpisodeProgress();
    };
    const render = async () => {
      const token = ++resultToken;
      const query = normalizeSearchText(input?.value || "");
      episodeLimit = 30;
      podcastCards
        .map((card) => ({ card, score: query ? searchScore(query, card.dataset.showTitle, "", card.dataset.showAuthor) : 1 }))
        .sort((left, right) => right.score - left.score || (right.card.dataset.showLatest || "").localeCompare(left.card.dataset.showLatest || ""))
        .forEach(({ card, score }, index) => {
          card.hidden = score === 0 || index >= (query ? 30 : 12);
          if (!card.hidden) podcastGrid?.appendChild(card);
        });
      if (query.length < 2) {
        currentMatches = [];
        if (episodeList) episodeList.replaceChildren();
        if (more) more.hidden = true;
        if (status) status.textContent = query ? t("search_start") : "";
        return;
      }
      if (status) status.textContent = t("search_loading");
      try {
        const episodes = await loadSearchIndex();
        if (token !== resultToken) return;
        currentMatches = episodes.map((item) => {
          const show = showMap.get(item.show_slug);
          return { ...item, score: searchScore(query, item.title, show?.dataset.showTitle, show?.dataset.showAuthor) };
        }).filter((item) => item.score > 0).sort((left, right) => right.score - left.score || String(right.published).localeCompare(String(left.published)));
        if (status) status.textContent = currentMatches.length ? "" : t("no_search_results");
        renderEpisodes();
      } catch {
        if (token === resultToken && status) status.textContent = t("search_failed");
      }
    };
    input?.addEventListener("input", render);
    more?.addEventListener("click", () => {
      episodeLimit += 30;
      renderEpisodes();
    });
    render();
  }

  function setupSubscriptionPage() {
    const page = document.querySelector("[data-subscriptions-page]");
    if (!page || page.dataset.bound === "true") return;
    page.dataset.bound = "true";
    page.querySelector("[data-subscription-filter]")?.addEventListener("input", renderSubscriptionPage);
    page.querySelectorAll("[data-subscription-sort]").forEach((button) => {
      button.addEventListener("click", () => {
        page.querySelectorAll("[data-subscription-sort]").forEach((candidate) => candidate.setAttribute("aria-pressed", String(candidate === button)));
        renderSubscriptionPage();
      });
    });
    renderSubscriptionPage();
  }

  function setupLibraryQueueControls() {
    document.addEventListener("click", (event) => {
      const episodeAction = event.target.closest?.("[data-episode-play], [data-queue-add], [data-queue-next], [data-share-episode], [data-toggle-played]");
      if (episodeAction) {
        const article = episodeAction.closest("[data-episode-id]");
        if (!article) return;
        event.preventDefault();
        if (episodeAction.matches("[data-episode-play]")) {
          playEpisode(article);
        } else if (episodeAction.matches("[data-queue-add]")) {
          toggleQueued(article);
        } else if (episodeAction.matches("[data-queue-next]")) {
          queueNext(article);
        } else if (episodeAction.matches("[data-share-episode]")) {
          void shareEpisode(article);
        } else if (episodeAction.matches("[data-toggle-played]")) {
          setPlayed(article, !isPlayed(article));
        }
        return;
      }

      const follow = event.target.closest?.("[data-follow-show]");
      if (follow) {
        event.preventDefault();
        toggleFollow(follow.closest("[data-show-card]"));
        return;
      }

      const homeResumePlay = event.target.closest?.("[data-home-resume-play]");
      if (homeResumePlay) {
        event.preventDefault();
        resumeLast();
        return;
      }

      const libraryOpen = event.target.closest?.("[data-library-open]");
      if (libraryOpen) {
        event.preventDefault();
        renderLibrary();
        openDrawer(document.querySelector("[data-library-drawer]"), libraryOpen);
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
        openDrawer(document.querySelector("[data-queue-drawer]"), queueOpen);
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
        if (!window.confirm(t("confirm_clear_queue"))) return;
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
    document.addEventListener("keydown", (event) => {
      const openDrawer = document.querySelector("[data-library-drawer]:not([hidden]), [data-queue-drawer]:not([hidden])");
      const focusRoot = player?.classList.contains("is-expanded") ? player : openDrawer;
      if (event.key === "Tab" && focusRoot) {
        const focusable = Array.from(focusRoot.querySelectorAll(
          'a[href], button:not([disabled]), input:not([disabled]), select:not([disabled]), textarea:not([disabled]), [tabindex]:not([tabindex="-1"])'
        )).filter((node) => !node.hidden && node.getClientRects().length > 0);
        if (focusable.length) {
          const first = focusable[0];
          const last = focusable[focusable.length - 1];
          if (event.shiftKey && document.activeElement === first) {
            event.preventDefault();
            last.focus();
          } else if (!event.shiftKey && document.activeElement === last) {
            event.preventDefault();
            first.focus();
          }
        }
        return;
      }
      if (event.key !== "Escape") return;
      if (handleAppBack()) event.preventDefault();
    });
  }

  function setupLanguage(options = {}) {
    const refreshUi = options.refreshUi !== false;
    const toggle = document.querySelector("[data-language-toggle]");
    function setLanguage(lang) {
      const next = labels[lang] || labels.he;
      html.lang = next.lang;
      html.dir = next.dir;
      document.querySelectorAll("[data-i18n]").forEach((node) => {
        const value = next[node.dataset.i18n] || runtimeLabels[lang]?.[node.dataset.i18n];
        if (value) node.innerHTML = value;
      });
      document.querySelectorAll("[data-i18n-placeholder]").forEach((node) => {
        const value = next[node.dataset.i18nPlaceholder] || runtimeLabels[lang]?.[node.dataset.i18nPlaceholder];
        if (value) node.setAttribute("placeholder", value);
      });
      document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
        const value = next[node.dataset.i18nAria] || runtimeLabels[lang]?.[node.dataset.i18nAria];
        if (value) node.setAttribute("aria-label", value);
      });
      playerSeek?.setAttribute("aria-label", t("player_progress"));
      if (playerVolume) playerVolume.setAttribute("aria-label", t("volume"));
      updateVolumeControl();
      applyPlaybackRate();
      try {
        localStorage.setItem("torahpod-language", lang);
      } catch {
        // Ignore unavailable storage.
      }
      document.dispatchEvent(new CustomEvent("torahpod:languagechange"));
      if (refreshUi) {
        updateVisibleEpisodeProgress();
        updateLibraryAndQueueUi();
      }
      setupOnboardingForms(lang);
      if (refreshUi) updateResume();
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

  function setupOnboardingForms(language = html.lang === "en" ? "en" : "he") {
    const form = document.querySelector("#onboarding-form");
    if (!form) return;

    const status = form.querySelector("#status");
    const submitButton = form.querySelector("#submit-button");
    const successPanel = document.querySelector("#onboarding-success");
    const anotherRequestButton = document.querySelector("[data-onboarding-another]");
    const languageToggle = document.querySelector("[data-language-toggle]");
    const sourceInputs = Array.from(form.querySelectorAll('input[name="source"]'));
    const sourceYoutube = form.querySelector("#source-youtube");
    const youtubeUrl = form.querySelector("#youtube-url");
    const driveUrl = form.querySelector("#drive-url");
    const feedUrl = form.querySelector("#feed-url");
    const approvalInput = form.querySelector("#approval");
    const fields = {
      title: form.querySelector("#title"),
      slug: form.querySelector("#slug"),
      speaker: form.querySelector("#speaker"),
      startDate: form.querySelector("#start-date"),
      description: form.querySelector("#description"),
      artwork: form.querySelector("#artwork"),
      contact: form.querySelector("#contact"),
      notes: form.querySelector("#notes"),
      companyWebsite: form.querySelector("#company-website"),
    };
    const groups = {
      youtube: form.querySelector("#youtube-fields"),
      drive: form.querySelector("#drive-fields"),
      feed: form.querySelector("#feed-fields"),
      title: form.querySelector("#title-fields"),
      speaker: form.querySelector("#speaker-fields"),
      slug: form.querySelector("#slug-fields"),
      startDate: form.querySelector("#start-date-fields"),
      description: form.querySelector("#description-fields"),
      artwork: form.querySelector("#artwork-fields"),
      contact: form.querySelector("#contact-fields"),
      notes: form.querySelector("#notes-fields"),
      approval: form.querySelector("#approval-fields"),
    };
    const text = {
      he: {
        toggle: "English",
        heading: "צירוף פודקאסט",
        intro: "מלאו פרטים בסיסיים. Torah Pod יבדוק ויאשר לפני פרסום.",
        stepOne: "בחרו מאיפה השיעורים מגיעים.",
        stepTwo: "מלאו פרטי רב, קישור ותאריך התחלה.",
        stepThree: "אחרי אישור, Torah Pod יוצר RSS פתוח להאזנה.",
        sourceLegend: "איפה נמצאים השיעורים?",
        youtubeChoice: "יוטיוב",
        driveChoice: "תיקיית Google Drive",
        feedChoice: "פיד פודקאסט קיים",
        sourceHint: "בחרו מקור אחד כדי להמשיך. אחר כך יוצגו רק השדות הרלוונטיים.",
        sourceRequired: "בחרו מקור אחד.",
        titleLabel: "שם הפודקאסט (לא חובה)",
        titleHint: "אם נשאר ריק, נשתמש בשם הרב.",
        speakerLabel: "שם הרב / מוסר השיעור",
        slugLabel: "שם קצר לקישור באנגלית",
        slugHint: "אותיות באנגלית, מספרים ומקפים בלבד. זה יהיה חלק מקישור הפיד.",
        startDateLabel: "תאריך התחלה",
        startDateHint: "רק שיעורים מהתאריך הזה והלאה ייכנסו לפודקאסט.",
        youtubeUrlLabel: "קישור ליוטיוב",
        youtubeUrlHint: "אפשר להדביק ערוץ או פלייליסט.",
        driveUrlLabel: "קישור לתיקיית Google Drive",
        feedUrlLabel: "קישור לפיד פודקאסט קיים",
        feedUrlHint: "אפשר להדביק RSS או Atom. Torah Pod ייקח מהפיד את שם הפודקאסט, הקישור, התיאור, הרב/מחבר, התמונה והפרקים.",
        shareFolder: "שתפו את התיקייה עם החשבון הזה כ-Viewer:",
        fileNameHint: "קובץ מוכן לפרסום: YYYY-MM-DD - Episode Title.ext",
        descriptionLabel: "תיאור (לא חובה)",
        descriptionHint: "ביוטיוב אפשר להשאיר ריק, ו-Torah Pod יוכל להשתמש בתיאור הערוץ.",
        artworkLabel: "קישור לתמונת הפודקאסט (לא חובה)",
        contactLabel: "כתובת אימייל שלכם (לא חובה)",
        notesLabel: "הערות נוספות (לא חובה)",
        approvalLabel: "אני מאשר/ת שאני בעל/ת הזכויות בתוכן או מוסמך/ת לאשר ל-Torah Pod לאחסן ולהפיץ אותו, ומבין/ה שנדרש אישור לפני פרסום.",
        terms: "תנאים וזכויות",
        submitButton: "שלחו בקשה",
        sending: "שולח בקשה...",
        success: "הבקשה נשלחה ל-Torah Pod.",
        successTitle: "הבקשה נשלחה",
        successDetail: "קיבלנו את פרטי הפודקאסט. נבדוק אותם לפני כל פרסום, וניצור קשר אם נצטרך פרטים נוספים.",
        anotherRequest: "שליחת בקשה נוספת",
        verificationRequired: "יש להשלים את אימות האבטחה לפני השליחה.",
        notConfigured: "הטופס עדיין לא חובר לשירות השליחה. פנו ל-Torah Pod.",
        failure: "לא הצלחנו לשלוח את הבקשה. נסו שוב מאוחר יותר.",
      },
      en: {
        toggle: "עברית",
        heading: "Podcast Onboarding",
        intro: "Send the basic details. Torah Pod reviews and approves before anything is published.",
        stepOne: "Choose where the lessons come from.",
        stepTwo: "Add the speaker, source link, and start date.",
        stepThree: "After approval, Torah Pod creates an open RSS feed.",
        sourceLegend: "Where are the lessons?",
        youtubeChoice: "YouTube",
        driveChoice: "Google Drive folder",
        feedChoice: "Existing podcast feed",
        sourceHint: "Choose one source to continue. Only relevant fields will appear.",
        sourceRequired: "Choose one source.",
        titleLabel: "Podcast name (optional)",
        titleHint: "If this is blank, the rabbi/speaker name will be used.",
        speakerLabel: "Rabbi / speaker name",
        slugLabel: "Short English URL name",
        slugHint: "Use lowercase English letters, numbers, and hyphens. This becomes part of the feed URL.",
        startDateLabel: "Start date",
        startDateHint: "Only lessons from this date and later will be included.",
        youtubeUrlLabel: "YouTube URL",
        youtubeUrlHint: "Paste a channel or playlist URL.",
        driveUrlLabel: "Google Drive folder URL",
        feedUrlLabel: "Existing podcast feed URL",
        feedUrlHint: "Paste an RSS or Atom feed. Torah Pod will use the feed title, link, description, author, artwork, and episodes.",
        shareFolder: "Share the folder with this account as Viewer:",
        fileNameHint: "Published files should be named: YYYY-MM-DD - Episode Title.ext",
        descriptionLabel: "Description (optional)",
        descriptionHint: "For YouTube, this can be blank and Torah Pod can use the channel description.",
        artworkLabel: "Artwork image URL (optional)",
        contactLabel: "Your email (optional)",
        notesLabel: "Additional notes (optional)",
        approvalLabel: "I confirm that I own the content or am authorized to let Torah Pod host and distribute it, and understand that approval is required before publication.",
        terms: "Terms & Rights",
        submitButton: "Submit Request",
        sending: "Submitting request...",
        success: "The request was sent to Torah Pod.",
        successTitle: "Request sent",
        successDetail: "We received the podcast details. We will review them before publishing and contact you if we need anything else.",
        anotherRequest: "Submit another request",
        verificationRequired: "Complete the security verification before submitting.",
        notConfigured: "This form is not connected to the submission service yet. Contact Torah Pod.",
        failure: "Could not submit the request. Try again later.",
      },
    };
    let currentLanguage = language === "en" ? "en" : "he";
    let turnstileWidgetId = null;
    let turnstileLoaded = null;

    function setupTurnstile() {
      const key = (form.dataset.turnstileSiteKey || "").trim();
      const container = form.querySelector("[data-turnstile-container]");
      if (!key || !container || turnstileWidgetId !== null) return;
      container.hidden = false;
      turnstileLoaded ||= new Promise((resolve, reject) => {
        if (window.turnstile) return resolve(window.turnstile);
        const script = document.createElement("script");
        script.src = "https://challenges.cloudflare.com/turnstile/v0/api.js?render=explicit";
        script.async = true;
        script.onload = () => resolve(window.turnstile);
        script.onerror = reject;
        document.head.append(script);
      });
      turnstileLoaded.then((turnstile) => {
        if (!turnstile || !document.contains(container)) return;
        turnstileWidgetId = turnstile.render(container, {
          sitekey: key,
          action: "onboarding",
          callback: (token) => { form.dataset.turnstileToken = token; },
          "expired-callback": () => { delete form.dataset.turnstileToken; },
          "error-callback": () => { delete form.dataset.turnstileToken; },
        });
      }).catch(() => { delete form.dataset.turnstileToken; });
    }

    function selectedSource() {
      return form.querySelector('input[name="source"]:checked')?.value || "";
    }
    function value(field) {
      return field?.value.trim() || "";
    }
    function sourceUrl() {
      const source = selectedSource();
      if (source === "drive") return value(driveUrl);
      if (source === "feed") return value(feedUrl);
      if (source === "youtube") return value(youtubeUrl);
      return "";
    }
    function updateSourceFields() {
      const source = selectedSource();
      const needsDrive = source === "drive";
      const needsYouTube = source === "youtube";
      const needsFeed = source === "feed";
      const sourceSelected = needsDrive || needsYouTube || needsFeed;
      groups.drive?.classList.toggle("hidden", !needsDrive);
      groups.youtube?.classList.toggle("hidden", !needsYouTube);
      groups.feed?.classList.toggle("hidden", !needsFeed);
      ["title", "speaker", "slug", "startDate", "description", "artwork", "contact", "notes"].forEach((key) => {
        groups[key]?.classList.toggle("hidden", !sourceSelected || needsFeed);
      });
      groups.approval?.classList.toggle("hidden", !sourceSelected);
      submitButton?.classList.toggle("hidden", !sourceSelected);
      if (driveUrl) driveUrl.required = needsDrive;
      if (youtubeUrl) youtubeUrl.required = needsYouTube;
      if (feedUrl) feedUrl.required = needsFeed;
      if (fields.speaker) fields.speaker.required = sourceSelected && !needsFeed;
      if (fields.slug) fields.slug.required = sourceSelected && !needsFeed;
      if (fields.startDate) fields.startDate.required = sourceSelected && !needsFeed;
      if (approvalInput) approvalInput.required = sourceSelected;
      sourceYoutube?.setCustomValidity(sourceSelected ? "" : text[currentLanguage].sourceRequired);
    }
    function applyOnboardingLanguage(language) {
      currentLanguage = language === "en" ? "en" : "he";
      const labels = text[currentLanguage];
      if (languageToggle) languageToggle.textContent = labels.toggle;
      form.closest("main")?.querySelectorAll("[data-i18n]").forEach((element) => {
        const nextText = labels[element.dataset.i18n];
        if (nextText) element.textContent = nextText;
      });
      if (status) {
        status.textContent = "";
        status.classList.remove("error", "success");
      }
      updateSourceFields();
    }
    function endpoint() {
      const value = (form.dataset.workerEndpoint || "").trim();
      return !value || value.startsWith("__") ? "" : value.replace(/\/$/, "");
    }
    function payload() {
      const source = selectedSource();
      const useFeedMetadata = source === "feed";
      return {
        source,
        sourceUrl: sourceUrl(),
        youtubeUrl: value(youtubeUrl),
        driveUrl: value(driveUrl),
        feedUrl: value(feedUrl),
        title: useFeedMetadata ? "" : value(fields.title),
        slug: useFeedMetadata ? "" : value(fields.slug).toLowerCase(),
        speaker: useFeedMetadata ? "" : value(fields.speaker),
        startDate: useFeedMetadata ? "" : value(fields.startDate),
        description: useFeedMetadata ? "" : value(fields.description),
        artwork: useFeedMetadata ? "" : value(fields.artwork),
        contact: useFeedMetadata ? "" : value(fields.contact),
        notes: useFeedMetadata ? "" : value(fields.notes),
        authorizationConfirmed: Boolean(approvalInput?.checked),
        companyWebsite: value(fields.companyWebsite),
        turnstileToken: form.dataset.turnstileToken || "",
      };
    }
    function showStatus(message, kind) {
      if (!status) return;
      status.textContent = message;
      status.classList.toggle("error", kind === "error");
      status.classList.toggle("success", kind === "success");
    }

    if (form.dataset.onboardingBound !== "true") {
      form.dataset.onboardingBound = "true";
      form.addEventListener("change", updateSourceFields);
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        updateSourceFields();
        if (!form.reportValidity()) return;
        if (!form.dataset.turnstileToken) {
          showStatus(text[currentLanguage].verificationRequired, "error");
          return;
        }
        const target = endpoint();
        if (!target) {
          showStatus(text[currentLanguage].notConfigured, "error");
          return;
        }
        if (submitButton) submitButton.disabled = true;
        showStatus(text[currentLanguage].sending, "");
        try {
          const response = await fetch(`${target}/submit`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload()),
          });
          const body = await response.json().catch(() => ({}));
          if (!response.ok || !body.ok) {
            showStatus(body.error || text[currentLanguage].failure, "error");
            return;
          }
          showStatus(text[currentLanguage].success, "success");
          form.reset();
          delete form.dataset.turnstileToken;
          if (turnstileWidgetId !== null && window.turnstile) window.turnstile.reset(turnstileWidgetId);
          updateSourceFields();
          form.hidden = true;
          if (successPanel) {
            successPanel.hidden = false;
            successPanel.focus();
          }
        } catch {
          showStatus(text[currentLanguage].failure, "error");
        } finally {
          if (submitButton) submitButton.disabled = false;
        }
      });
    }

    anotherRequestButton?.addEventListener("click", () => {
      if (successPanel) successPanel.hidden = true;
      form.hidden = false;
      showStatus("", "");
      updateSourceFields();
      sourceInputs[0]?.focus();
    });

    applyOnboardingLanguage(currentLanguage);
    setupTurnstile();
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

  function updateDestinationNavigation() {
    const current = normalizePagePath(location.pathname);
    document.querySelectorAll("[data-nav-route]").forEach((link) => {
      const target = normalizePagePath(new URL(link.href, location.href).pathname);
      const active = current === target;
      link.classList.toggle("is-active", active);
      if (active) link.setAttribute("aria-current", "page");
      else link.removeAttribute("aria-current");
    });
  }

  function siteRootPath() {
    const first = location.pathname.split("/").filter(Boolean)[0] || "";
    return first === "youtube-podcast-feeds" ? "/youtube-podcast-feeds/" : "/";
  }

  function routeFromLink(link) {
    if (link.dataset.appRoute) return link.dataset.appRoute;
    if (link.hasAttribute("data-browse-podcasts")) return "/#podcasts";
    if (!link.closest(".site-header, .footer")) return "";
    const routes = {
      home: "/",
      onboard: "/onboard/",
      about: "/about/",
      contact: "/about/#contact",
      donate: "/donate/",
      terms: "/terms/",
    };
    return routes[link.dataset.i18n] || "";
  }

  function appLinkUrl(link) {
    const route = routeFromLink(link);
    if (!route) return new URL(link.href, location.href);
    const root = siteRootPath();
    const path = route.replace(/^\/+/, "");
    return new URL(`${root}${path}`, location.origin);
  }

  function isSamePageUrl(url) {
    return (
      url.origin === location.origin &&
      url.search === location.search &&
      normalizePagePath(url.pathname) === normalizePagePath(location.pathname)
    );
  }

  function shouldHandleNavigation(event, link, url) {
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
    if (url.origin !== location.origin) return false;
    if (url.pathname === location.pathname && url.search === location.search && url.hash) return false;
    if (url.pathname.endsWith(".xml") || url.pathname.endsWith(".json") || url.pathname.endsWith(".png")) return false;
    const lastSegment = url.pathname.split("/").filter(Boolean).pop() || "";
    return url.pathname.endsWith("/") || url.pathname.endsWith(".html") || !lastSegment.includes(".");
  }

  async function navigateTo(target, { push = true } = {}) {
    const url = new URL(target, location.href);
    const requestId = ++navigationRequestId;
    navigationController?.abort();
    const controller = new AbortController();
    let navigationTimedOut = false;
    const navigationTimeout = window.setTimeout(() => {
      navigationTimedOut = true;
      controller.abort();
    }, navigationTimeoutMs);
    navigationController = controller;
    document.body.classList.add("app-loading");
    document.body.setAttribute("aria-busy", "true");
    announceAppStatus(t("navigation_loading"), 0);
    if (player?.classList.contains("is-expanded")) setPlayerExpanded(false);
    try {
      const response = await fetch(url.href, {
        headers: { "X-Torah-Pod-Navigation": "1" },
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`Navigation failed: ${response.status}`);
      const contentType = (response.headers.get("content-type") || "").toLowerCase();
      if (!contentType.includes("text/html")) throw new Error(`Unexpected navigation content type: ${contentType || "missing"}`);
      const responseText = await response.text();
      if (controller.signal.aborted || requestId !== navigationRequestId) return false;
      const nextDocument = parser.parseFromString(responseText, "text/html");
      const nextHeader = nextDocument.querySelector(".site-header");
      const nextMain = nextDocument.querySelector("main");
      const nextFooter = nextDocument.querySelector(".footer");
      const nextBottomNav = nextDocument.querySelector(".app-bottom-nav");
      if (!nextMain) throw new Error("Navigation response had no main content");

      dockActiveAudio();
      closeDrawers({ restoreFocus: false });
      document.title = nextDocument.title || document.title;
      if (nextHeader) document.querySelector(".site-header")?.replaceWith(nextHeader);
      document.querySelector("main")?.replaceWith(nextMain);
      if (nextFooter) document.querySelector(".footer")?.replaceWith(nextFooter);
      if (nextBottomNav) document.querySelector(".app-bottom-nav")?.replaceWith(nextBottomNav);
      if (push) history.pushState({}, "", url.href);
      setupAccessibility();
      setupLanguage({ refreshUi: false });
      updateVersionBadges();
      setupLists();
      setupEpisodes();
      setupContactForms();
      setupOnboardingForms();
      setupCatalogSearch();
      setupSubscriptionPage();
      markCurrentShowVisited();
      updateDestinationNavigation();
      updateLibraryAndQueueUi();
      updateResume();
      const hashElement = hashTarget(url.hash);
      const focusTarget = hashElement || document.querySelector("main");
      if (focusTarget) {
        if (!focusTarget.hasAttribute("tabindex")) focusTarget.setAttribute("tabindex", "-1");
        focusTarget.focus({ preventScroll: true });
      }
      if (hashElement) hashElement.scrollIntoView({ block: "center" });
      else window.scrollTo(0, 0);
      if (appStatus) appStatus.hidden = true;
      return true;
    } catch (error) {
      if (requestId !== navigationRequestId) return false;
      if (error?.name === "AbortError" && !navigationTimedOut) return false;
      showNavigationFailure(url.href, push);
      return false;
    } finally {
      window.clearTimeout(navigationTimeout);
      if (requestId === navigationRequestId) {
        navigationController = null;
        document.body.classList.remove("app-loading");
        document.body.removeAttribute("aria-busy");
      }
    }
  }

  function setupAppNavigation() {
    document.addEventListener("click", (event) => {
      const link = event.target.closest?.("a[href]");
      if (!link) return;
      const url = appLinkUrl(link);
      if (isSamePageUrl(url) && !url.hash) {
        event.preventDefault();
        closeDrawers();
        setPlayerExpanded(false);
        window.scrollTo({ top: 0, behavior: "smooth" });
        document.querySelector("main")?.focus({ preventScroll: true });
        return;
      }
      if (!shouldHandleNavigation(event, link, url)) return;
      event.preventDefault();
      navigateTo(url.href);
    });
    window.addEventListener("popstate", () => {
      navigateTo(location.href, { push: false });
    });
  }

  function setupServiceWorker() {
    if (!("serviceWorker" in navigator) || location.protocol === "file:") return;
    const hadController = Boolean(navigator.serviceWorker.controller);
    navigator.serviceWorker.addEventListener("controllerchange", () => {
      if (hadController) showUpdateNotice();
    });
    window.addEventListener("load", () => {
      navigator.serviceWorker.register(`${basePath}sw.js`).catch(() => {});
    });
  }

  function setupNetworkStatus() {
    const notice = document.createElement("div");
    notice.className = "network-status";
    notice.setAttribute("role", "status");
    notice.hidden = true;
    document.body.appendChild(notice);
    const update = () => {
      if (navigator.onLine) {
        if (!notice.hidden) {
          notice.textContent = t("network_online");
          window.setTimeout(() => { notice.hidden = true; }, 1800);
        }
      } else {
        notice.textContent = t("network_offline");
        notice.hidden = false;
      }
    };
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    update();
  }

  setupPolishedPlayerShell();
  setupAccessibility();
  migrateShowVisits();
  markCurrentShowVisited();
  setupLanguage({ refreshUi: false });
  setupEpisodes();
  setupPlayerControls();
  setupAppNavigation();
  setupNetworkStatus();
  updateVersionBadges();
  updateDestinationNavigation();
  nativePrompt("ready");
  window.setTimeout(() => {
    setupLists();
    setupLibraryQueueControls();
    setupContactForms();
    setupOnboardingForms();
    setupCatalogSearch();
    setupSubscriptionPage();
    setupServiceWorker();
    updateLibraryAndQueueUi();
    updateResume();
  }, 0);
})();
