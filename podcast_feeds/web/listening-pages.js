  // These functions are assembled inside the player closure by the Python build.
  let latestPromise = null;
  let latestMetadata = null;
  let homeGeneration = 0;
  let homeLimit = 20;
  const homeExtraEpisodes = new Map();
  const homePages = new Map();

  async function episodeMetadata(path) {
    const response = await fetch(new URL(`metadata/v1/${path}`, basePath));
    if (!response.ok) throw new Error("Episode metadata unavailable");
    const payload = await response.json();
    if (payload?.schema_version !== 1) throw new Error("Unsupported episode metadata");
    return payload;
  }

  function loadLatestMetadata() {
    if (!latestPromise) latestPromise = episodeMetadata("latest.json").then((payload) => {
      if (!Array.isArray(payload.shows)) throw new Error("Invalid latest episodes");
      latestMetadata = payload;
      return payload;
    }).catch((error) => { latestPromise = null; throw error; });
    return latestPromise;
  }

  function showForMetadata(show) {
    return { dataset: { showTitle: show.title, showAuthor: show.author,
      showArtwork: new URL(`${show.slug}/assets/podcast-cover.png`, basePath).href } };
  }

  function replaceEpisodeList(list, markup) {
    // Keep the audio element connected before replacing an episode's DOM row.
    if (activeAudio && list.contains(activeAudio)) dockActiveAudio();
    list.innerHTML = markup;
    setupEpisodes();
    updateVisibleEpisodeActions();
    updateVisibleEpisodeProgress();
  }

  async function renderHomeEpisodes() {
    const list = document.querySelector("[data-home-recent-list]");
    if (!list) return;
    const generation = ++homeGeneration;
    const status = document.querySelector("[data-home-recent-status]");
    try {
      const payload = await loadLatestMetadata();
      if (generation !== homeGeneration || !list.isConnected) return;
      const followed = followedShows().map((show) => show.slug);
      const selection = followed.length ? followed : null;
      const selectedShows = payload.shows.filter((show) => !selection || selection.includes(show.slug));
      const episodes = selectedShows.flatMap((show) => [...show.latest, ...(homeExtraEpisodes.get(show.slug) || [])]);
      const recent = window.TorahPodListening.recentEpisodes(episodes, selection, homeLimit);
      const map = new Map(selectedShows.map((show) => [show.slug, showForMetadata(show)]));
      replaceEpisodeList(list, recent.map((episode) => searchEpisodeMarkup(episode, map.get(episode.show_slug))).join(""));
      const title = document.querySelector("[data-home-recent-title]");
      if (title) { title.dataset.i18n = followed.length ? "new_from_subscriptions" : "recent_catalog"; title.textContent = t(title.dataset.i18n); }
      if (status) status.textContent = recent.length ? "" : t("no_subscription_episodes");
      const more = document.querySelector("[data-home-more]");
      if (more) more.hidden = selectedShows.reduce((sum, show) => sum + show.total, 0) <= recent.length;
    } catch {
      // Existing server-rendered playable episodes remain visible on failure.
      if (list.isConnected && generation === homeGeneration && status) status.textContent = t("episodes_failed");
    }
  }

  async function moreHomeEpisodes(button) {
    const list = document.querySelector("[data-home-recent-list]");
    const status = document.querySelector("[data-home-recent-status]");
    const generation = homeGeneration;
    button.disabled = true;
    try {
      const payload = await loadLatestMetadata();
      const followed = followedShows().map((show) => show.slug);
      const selected = payload.shows.filter((show) => !followed.length || followed.includes(show.slug));
      // Fetch each selected show's next page before merging and applying a limit.
      const pages = await Promise.all(selected.map(async (show) => {
        const page = homePages.get(show.slug) || 2;
        if (page > show.pages) return null;
        const result = await episodeMetadata(`shows/${encodeURIComponent(show.slug)}/${page}.json`);
        if (result.show_slug !== show.slug || !Array.isArray(result.episodes)) throw new Error("Invalid episode page");
        return { slug: show.slug, page, episodes: result.episodes };
      }));
      // Commit pages together so a failed show cannot advance the other cursors.
      if (!list?.isConnected || generation !== homeGeneration) return;
      pages.filter(Boolean).forEach(({ slug, page, episodes }) => {
        homeExtraEpisodes.set(slug, [...(homeExtraEpisodes.get(slug) || []), ...episodes]);
        homePages.set(slug, page + 1);
      });
      homeLimit += 20;
      await renderHomeEpisodes();
    } catch { if (status?.isConnected && generation === homeGeneration) status.textContent = t("episodes_failed"); }
    finally { button.disabled = false; }
  }

  function toggleSavedEpisode(article) {
    const state = episodeState(article);
    if (!state?.id) return;
    const items = safeArray(savedKey);
    const exists = items.some((item) => item.id === state.id);
    safeSet(savedKey, exists ? items.filter((item) => item.id !== state.id) : [...items, { ...state, savedAt: Date.now() }]);
    updateVisibleEpisodeActions();
    renderListeningLibrary();
  }

  function listeningHistory() {
    const entries = [];
    try {
      for (let index = 0; index < localStorage.length; index++) {
        const key = localStorage.key(index);
        if (!key?.startsWith(progressPrefix)) continue;
        const entry = safeGet(key);
        if (entry?.id && entry?.src && entry.position > 0) entries.push(entry);
      }
    } catch { /* Storage may be unavailable; anonymous playback continues. */ }
    return entries.sort((left, right) => Number(right.updatedAt || 0) - Number(left.updatedAt || 0));
  }

  function renderListeningLibrary() {
    const list = document.querySelector("[data-library-episode-list]");
    if (!list) return;
    const tab = document.querySelector("[data-library-tab][aria-pressed=true]")?.dataset.libraryTab || "followed";
    const section = document.querySelector("[data-library-episodes]");
    const followedSection = document.querySelector("[data-subscriptions-page]");
    if (section) section.hidden = tab === "followed";
    if (followedSection) followedSection.hidden = tab !== "followed";
    if (tab === "followed") return;
    const items = tab === "saved" ? safeArray(savedKey).slice().reverse() : listeningHistory();
    replaceEpisodeList(list, items.map((state) => searchEpisodeMarkup({ id: state.id, title: state.title,
      show_slug: state.showSlug || "", page_url: state.href, audio_url: state.src, duration: state.duration || 0, published: "" },
    { dataset: { showTitle: state.show, showArtwork: state.artwork } })).join(""));
    document.querySelector("[data-library-episodes-empty]")?.toggleAttribute("hidden", items.length > 0);
  }

  function setupListeningPages() {
    setupExplorePage();
    const homeMore = document.querySelector("[data-home-more]");
    if (homeMore && !homeMore.dataset.bound) {
      homeMore.dataset.bound = "true";
      homeMore.addEventListener("click", () => { void moreHomeEpisodes(homeMore); });
    }
    document.querySelectorAll("[data-library-tab]").forEach((button) => {
      if (button.dataset.bound) return;
      button.dataset.bound = "true";
      button.addEventListener("click", () => {
        document.querySelectorAll("[data-library-tab]").forEach((tab) => tab.setAttribute("aria-pressed", String(tab === button)));
        renderListeningLibrary();
      });
    });
    const latest = document.querySelector("[data-play-latest]");
    if (latest && !latest.dataset.bound) {
      latest.dataset.bound = "true";
      latest.addEventListener("click", () => {
        const article = Array.from(document.querySelectorAll("[data-episode-id]")).find((row) => row.dataset.episodeId === latest.dataset.playLatest);
        if (article) playEpisode(article);
      });
    }
    const list = document.querySelector("[data-paginated-show]");
    if (!list || list.dataset.bound) return;
    list.dataset.bound = "true";
    const slug = list.dataset.paginatedShow;
    const more = document.querySelector("[data-show-more]");
    const status = document.querySelector("[data-show-load-status]");
    const input = document.querySelector("[data-show-search]");
    let searchGeneration = 0;
    const show = document.querySelector("[data-show-page]");
    const originalNextPage = list.dataset.nextPage;
    const original = Array.from(list.children).map((node) => node.outerHTML).join("");
    const appendPage = async () => {
      if (!list.dataset.nextPage || list.dataset.nextPage === "0") return;
      const generation = searchGeneration;
      more.disabled = true;
      if (status) status.textContent = t("loading_episodes");
      try {
        const payload = await episodeMetadata(`shows/${encodeURIComponent(slug)}/${list.dataset.nextPage}.json`);
        if (!Array.isArray(payload.episodes) || payload.show_slug !== slug) throw new Error("Invalid episode page");
        if (!list.isConnected || generation !== searchGeneration) return;
        list.insertAdjacentHTML("beforeend", payload.episodes.map((item) => searchEpisodeMarkup(item, show)).join(""));
        list.dataset.nextPage = String(payload.next_page || 0);
        more.hidden = !payload.next_page;
        setupEpisodes(); updateVisibleEpisodeActions(); updateVisibleEpisodeProgress();
        if (status) status.textContent = "";
      } catch { if (status?.isConnected && generation === searchGeneration) status.textContent = t("episodes_failed"); }
      finally { more.disabled = false; }
    };
    more?.addEventListener("click", () => { void appendPage(); });
    input?.addEventListener("input", async () => {
      const generation = ++searchGeneration;
      const query = normalizeSearchText(input.value);
      more.hidden = Boolean(query) || list.dataset.nextPage === "0";
      if (!query) {
        replaceEpisodeList(list, original);
        list.dataset.nextPage = originalNextPage;
        more.hidden = originalNextPage === "0";
        if (status) status.textContent = "";
        return;
      }
      try {
        const index = await loadSearchIndex();
        if (generation !== searchGeneration || !list.isConnected) return;
        const matches = index.filter((item) => item.show_slug === slug && searchScore(query, item.title, "", "") > 0);
        replaceEpisodeList(list, matches.map((item) => searchEpisodeMarkup(item, show)).join(""));
        if (status) status.textContent = matches.length ? "" : t("no_search_results");
      } catch { if (generation === searchGeneration && status) status.textContent = t("search_failed"); }
    });
  }

  function setupExplorePage() {
    const page = document.querySelector("[data-explore-page]");
    if (!page || page.dataset.bound) return;
    page.dataset.bound = "true";
    const grid = page.querySelector("[data-explore-grid]");
    const cards = Array.from(grid.querySelectorAll("[data-show-card]"));
    const filter = page.querySelector("[data-explore-filter]");
    const sort = page.querySelector("[data-explore-sort]");
    const render = () => {
      const query = normalizeSearchText(filter.value);
      const ordered = [...cards].sort((a, b) => sort.value === "alpha"
        ? a.dataset.showTitle.localeCompare(b.dataset.showTitle, html.lang)
        : String(b.dataset.showLatest).localeCompare(String(a.dataset.showLatest)));
      let visible = 0;
      ordered.forEach((card) => {
        card.hidden = !normalizeSearchText(`${card.dataset.showTitle} ${card.dataset.showAuthor}`).includes(query);
        if (!card.hidden) visible++;
        grid.appendChild(card);
      });
      page.querySelector("[data-explore-status]").textContent = `${visible} ${t("podcast_results")}`;
      page.querySelector("[data-explore-empty]").hidden = visible > 0;
    };
    filter.addEventListener("input", render);
    sort.addEventListener("change", render);
    document.addEventListener("torahpod:languagechange", render, { signal: listBindingsAbortController?.signal });
    render();
  }
