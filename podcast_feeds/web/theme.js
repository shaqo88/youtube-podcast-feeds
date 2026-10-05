(() => {
  const key = "torahpod:v1:theme";
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let preference = "system";
  try { preference = localStorage.getItem(key) || "system"; } catch { /* Device preference remains available. */ }
  function apply() {
    if (!["system", "light", "dark"].includes(preference)) preference = "system";
    document.documentElement.dataset.theme = preference === "system" ? (media.matches ? "dark" : "light") : preference;
    document.querySelectorAll("[data-theme-select]").forEach((select) => { select.value = preference; });
    document.querySelector('meta[name="theme-color"]')?.setAttribute("content", document.documentElement.dataset.theme === "dark" ? "#171e1c" : "#f7f8f5");
  }
  apply();
  media.addEventListener("change", apply);
  document.addEventListener("DOMContentLoaded", apply);
  document.addEventListener("torahpod:navigation", apply);
  document.addEventListener("change", (event) => {
    if (!event.target.matches("[data-theme-select]")) return;
    preference = event.target.value;
    try { localStorage.setItem(key, preference); } catch { /* Theme still applies for this session. */ }
    apply();
  });
})();
