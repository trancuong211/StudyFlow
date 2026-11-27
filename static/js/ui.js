// StudyFlow shared interactions: theme, mobile sidebar, modals, messages.
(function () {
  "use strict";

  var root = document.documentElement;
  var mobileQuery = window.matchMedia("(max-width: 1100px)");

  function getSidebar() {
    return document.getElementById("sidebar");
  }

  function getBackdrop() {
    return document.getElementById("sidebarBackdrop");
  }

  function getMain() {
    return document.getElementById("mainContent");
  }

  function isMobile() {
    return mobileQuery.matches;
  }

  function syncSidebarAccess() {
    var sidebar = getSidebar();
    var main = getMain();
    var open = !!sidebar && sidebar.classList.contains("open");
    var mobile = isMobile();

    if (sidebar) sidebar.inert = mobile && !open;
    if (main) main.inert = mobile && open;
  }

  function setSidebarExpanded(expanded) {
    document.querySelectorAll("[data-sidebar-open]").forEach(function (button) {
      button.setAttribute("aria-expanded", expanded ? "true" : "false");
    });
  }

  function openSidebar() {
    var sidebar = getSidebar();
    var backdrop = getBackdrop();
    if (!sidebar) return;

    sidebar.classList.add("open");
    if (backdrop) backdrop.classList.add("open");
    document.body.classList.add("overflow-hidden");
    setSidebarExpanded(true);
    syncSidebarAccess();

    var firstLink = sidebar.querySelector("a, button");
    if (firstLink) firstLink.focus();
  }

  function closeSidebar(returnFocus) {
    var sidebar = getSidebar();
    var backdrop = getBackdrop();
    if (!sidebar) return;

    var wasOpen = sidebar.classList.contains("open");
    sidebar.classList.remove("open");
    if (backdrop) backdrop.classList.remove("open");
    document.body.classList.remove("overflow-hidden");
    setSidebarExpanded(false);
    syncSidebarAccess();

    if (wasOpen && returnFocus) {
      var toggle = document.querySelector("[data-sidebar-open]");
      if (toggle) toggle.focus();
    }
  }

  function toggleSidebar() {
    var sidebar = getSidebar();
    if (!sidebar) return;
    if (sidebar.classList.contains("open")) closeSidebar(true);
    else openSidebar();
  }

  function updateThemeControls(theme) {
    var dark = theme === "dark";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      button.setAttribute("aria-pressed", dark ? "true" : "false");
      button.setAttribute("aria-label", dark ? "Chuyển sang giao diện sáng" : "Chuyển sang giao diện tối");
      button.setAttribute("title", dark ? "Giao diện sáng" : "Giao diện tối");
    });
  }

  function applyTheme(theme) {
    root.setAttribute("data-theme", theme);
    try {
      localStorage.setItem("sf-theme", theme);
    } catch (error) {
      // localStorage can be unavailable in private mode.
    }
    updateThemeControls(theme);
  }

  function initTheme() {
    var saved = null;
    try {
      saved = localStorage.getItem("sf-theme");
    } catch (error) {
      saved = null;
    }
    if (saved === "dark" || saved === "light") {
      root.setAttribute("data-theme", saved);
      updateThemeControls(saved);
    } else {
      updateThemeControls(root.getAttribute("data-theme") || "light");
    }
  }

  function openModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.add("open");
    modal.setAttribute("aria-hidden", "false");
    var focusable = modal.querySelector("input, select, textarea, button, a[href]");
    if (focusable) focusable.focus();
  }

  function closeModal(id) {
    var modal = document.getElementById(id);
    if (!modal) return;
    modal.classList.remove("open");
    modal.setAttribute("aria-hidden", "true");
  }

  function closeOpenModals() {
    document.querySelectorAll(".modal-overlay.open").forEach(function (modal) {
      modal.classList.remove("open");
      modal.setAttribute("aria-hidden", "true");
    });
  }

  function bindLoadingForms(scope) {
    (scope || document).querySelectorAll("[data-loading-form]").forEach(function (form) {
      if (form.dataset.loadingBound === "true") return;
      form.dataset.loadingBound = "true";
      form.addEventListener("submit", function () {
        var button = form.querySelector('button[type="submit"], button:not([type])');
        if (button) {
          button.disabled = true;
          button.textContent = "Đang xử lý…";
        }
      });
    });
  }

  window.sfOpenSidebar = openSidebar;
  window.sfCloseSidebar = closeSidebar;
  window.sfToggleSidebar = toggleSidebar;
  window.sfToggleTheme = function () {
    var next = root.getAttribute("data-theme") === "dark" ? "light" : "dark";
    applyTheme(next);
  };
  window.sfOpenModal = openModal;
  window.sfCloseModal = closeModal;

  document.addEventListener("click", function (event) {
    var opener = event.target.closest("[data-sidebar-open]");
    if (opener) {
      event.preventDefault();
      openSidebar();
      return;
    }

    var closer = event.target.closest("[data-sidebar-close]");
    if (closer) {
      event.preventDefault();
      closeSidebar(true);
      return;
    }

    var themeToggle = event.target.closest("[data-theme-toggle]");
    if (themeToggle) {
      event.preventDefault();
      window.sfToggleTheme();
      return;
    }

    var modalOpener = event.target.closest("[data-modal-open]");
    if (modalOpener) {
      event.preventDefault();
      openModal(modalOpener.getAttribute("data-modal-open"));
      return;
    }

    var modalCloser = event.target.closest("[data-modal-close]");
    if (modalCloser) {
      event.preventDefault();
      closeModal(modalCloser.getAttribute("data-modal-close"));
      return;
    }

    var dismiss = event.target.closest("[data-dismiss]");
    if (dismiss) {
      var message = dismiss.closest(".message");
      if (message) message.remove();
      return;
    }

    var taskToggle = event.target.closest("[data-task-toggle]");
    if (taskToggle) {
      var row = taskToggle.closest(".task-row");
      if (row) row.classList.toggle("is-done");
    }

    if (event.target.classList && event.target.classList.contains("modal-overlay")) {
      event.target.classList.remove("open");
      event.target.setAttribute("aria-hidden", "true");
    }
  });

  document.addEventListener("keydown", function (event) {
    if (event.key !== "Escape") return;
    closeOpenModals();
    closeSidebar(true);
  });

  window.addEventListener("resize", function () {
    if (!isMobile()) closeSidebar(false);
    syncSidebarAccess();
  });

  document.querySelectorAll(".message[data-autodismiss]").forEach(function (message) {
    window.setTimeout(function () {
      message.remove();
    }, 5000);
  });

  var sidebar = getSidebar();
  if (sidebar) {
    sidebar.querySelectorAll("a").forEach(function (link) {
      link.addEventListener("click", function () {
        if (isMobile()) closeSidebar(false);
      });
    });
  }

  initTheme();
  syncSidebarAccess();
  bindLoadingForms(document);

  console.log("StudyFlow application initialized.");
})();
