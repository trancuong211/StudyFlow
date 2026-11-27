// Shared interactions: theme toggle, mobile sidebar, modal helpers, task check toggle.
(function () {
  // ---- Theme ----
  var root = document.documentElement;
  var saved = localStorage.getItem("sf-theme");
  if (saved) root.setAttribute("data-theme", saved);
  window.sfToggleTheme = function () {
    var cur = root.getAttribute("data-theme");
    var next = cur === "dark" ? "light" : "dark";
    root.setAttribute("data-theme", next);
    localStorage.setItem("sf-theme", next);
    // swap icon
    document.querySelectorAll("[data-theme-icon]").forEach(function (el) {
      el.textContent = next === "dark" ? "☀" : "☾";
    });
  };

  // ---- Mobile sidebar ----
  window.sfOpenSidebar = function () {
    document.querySelector(".sidebar")?.classList.add("open");
    document.querySelector(".sidebar-backdrop")?.classList.add("open");
  };
  window.sfCloseSidebar = function () {
    document.querySelector(".sidebar")?.classList.remove("open");
    document.querySelector(".sidebar-backdrop")?.classList.remove("open");
  };

  // ---- Modal ----
  window.sfOpenModal = function (id) {
    var m = document.getElementById(id);
    if (m) m.classList.add("open");
  };
  window.sfCloseModal = function (id) {
    var m = document.getElementById(id);
    if (m) m.classList.remove("open");
  };

  // ---- Task checkbox toggle (demo) ----
  document.addEventListener("click", function (e) {
    var check = e.target.closest("[data-task-toggle]");
    if (check) {
      var row = check.closest(".task-row");
      if (row) row.classList.toggle("is-done");
    }
  });

  // Close modal on overlay click
  document.addEventListener("click", function (e) {
    if (e.target.classList?.contains("modal-overlay")) {
      e.target.classList.remove("open");
    }
  });

  // Esc closes any open modal
  document.addEventListener("keydown", function (e) {
    if (e.key === "Escape") {
      document.querySelectorAll(".modal-overlay.open").forEach(function (m) {
        m.classList.remove("open");
      });
      sfCloseSidebar();
    }
  });
})();
