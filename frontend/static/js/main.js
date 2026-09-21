/**
 * CHIKITSASETU - Enterprise Hospital Management System
 * Vanilla JavaScript UI Controllers (Accessible, Responsive & Interactive)
 */

document.addEventListener("DOMContentLoaded", function () {
    // 1. Auto-dismiss Flash Alerts
    initFlashAlerts();

    // 2. Modal Controller & Keyboard Accessibility
    initModals();

    // 3. Responsive Mobile Sidebar Navigation
    initSidebar();

    // 4. Notification Dropdown Controller
    initNotificationDropdown();

    // 5. Client-Side Instant Table Search & Filtering
    initTableSearchAndFilters();

    // 6. Form Validation & Button Loading Indicators
    initFormInteractions();

    // 7. Global Keyboard Shortcuts (Escape to dismiss)
    initKeyboardShortcuts();
});

/* ==========================================================================
   1. Flash Alerts Auto-Dismiss
   ========================================================================== */
function initFlashAlerts() {
    const alerts = document.querySelectorAll(".alert");
    alerts.forEach(function (alert) {
        setTimeout(function () {
            alert.style.transition = "opacity 0.4s ease, transform 0.4s ease";
            alert.style.opacity = "0";
            alert.style.transform = "translateY(-10px)";
            setTimeout(function () {
                if (alert.parentNode) {
                    alert.remove();
                }
            }, 400);
        }, 5500);
    });
}

/* ==========================================================================
   2. Modals (Accessible Dialogs & Focus Management)
   ========================================================================== */
function initModals() {
    // Open modal triggers
    document.querySelectorAll("[data-modal-target]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            const targetId = this.getAttribute("data-modal-target");
            const modal = document.getElementById(targetId);
            if (modal) {
                openModal(modal);
            }
        });
    });

    // Close modal triggers
    document.querySelectorAll("[data-close-modal]").forEach(function (btn) {
        btn.addEventListener("click", function () {
            const modal = this.closest(".modal-backdrop");
            if (modal) {
                closeModal(modal);
            }
        });
    });

    // Backdrop click to dismiss
    document.querySelectorAll(".modal-backdrop").forEach(function (modal) {
        modal.addEventListener("click", function (e) {
            if (e.target === this) {
                closeModal(this);
            }
        });
    });
}

function openModal(modal) {
    modal.classList.add("active");
    modal.setAttribute("aria-hidden", "false");
    // Auto-focus first input or close button
    const focusable = modal.querySelector("input:not([type=hidden]), select, textarea, button:not([data-close-modal])");
    if (focusable) {
        setTimeout(() => focusable.focus(), 50);
    }
}

function closeModal(modal) {
    modal.classList.remove("active");
    modal.setAttribute("aria-hidden", "true");
}

/* ==========================================================================
   3. Responsive Mobile Sidebar Navigation
   ========================================================================== */
function initSidebar() {
    const sidebarToggle = document.getElementById("sidebar-toggle");
    const sidebarClose = document.getElementById("sidebarCloseBtn");
    const sidebar = document.querySelector(".app-sidebar");
    const overlay = document.getElementById("sidebarOverlay");

    function openSidebar() {
        if (sidebar) sidebar.classList.add("open");
        if (overlay) overlay.classList.add("active");
        document.body.style.overflow = "hidden"; // Prevent background scroll on mobile
    }

    function closeSidebar() {
        if (sidebar) sidebar.classList.remove("open");
        if (overlay) overlay.classList.remove("active");
        document.body.style.overflow = "";
    }

    if (sidebarToggle) {
        sidebarToggle.addEventListener("click", function (e) {
            e.stopPropagation();
            if (sidebar && sidebar.classList.contains("open")) {
                closeSidebar();
            } else {
                openSidebar();
            }
        });
    }

    if (sidebarClose) {
        sidebarClose.addEventListener("click", function () {
            closeSidebar();
        });
    }

    if (overlay) {
        overlay.addEventListener("click", function () {
            closeSidebar();
        });
    }

    // Auto-close sidebar on window resize larger than 900px
    window.addEventListener("resize", function () {
        if (window.innerWidth > 900) {
            closeSidebar();
        }
    });
}

/* ==========================================================================
   4. Notification Dropdown
   ========================================================================== */
function initNotificationDropdown() {
    window.addEventListener("click", function (e) {
        const wrapper = document.getElementById("notifDropdownWrapper");
        const panel = document.getElementById("notifDropdownPanel");
        if (wrapper && panel && !wrapper.contains(e.target)) {
            panel.style.display = "none";
        }
    });
}

function toggleNotifDropdown(event) {
    if (event) {
        event.stopPropagation();
    }
    const panel = document.getElementById("notifDropdownPanel");
    if (panel) {
        const isHidden = panel.style.display === "none" || panel.style.display === "";
        panel.style.display = isHidden ? "block" : "none";
        panel.setAttribute("aria-expanded", isHidden ? "true" : "false");
    }
}

/* ==========================================================================
   5. Instant Client-Side Table Search & Filter
   ========================================================================== */
function initTableSearchAndFilters() {
    // Inputs with data-table-search="#tableId" or data-table-search="table.my-table"
    const searchInputs = document.querySelectorAll("[data-table-search]");
    searchInputs.forEach(function (input) {
        const targetSelector = input.getAttribute("data-table-search");
        const table = document.querySelector(targetSelector);
        if (!table) return;

        const tbody = table.querySelector("tbody");
        if (!tbody) return;

        input.addEventListener("input", function () {
            const query = this.value.trim().toLowerCase();
            const rows = tbody.querySelectorAll("tr:not(.empty-state-row)");
            let visibleCount = 0;

            rows.forEach(function (row) {
                const text = row.textContent.toLowerCase();
                if (!query || text.includes(query)) {
                    row.style.display = "";
                    visibleCount++;
                } else {
                    row.style.display = "none";
                }
            });

            // Handle dynamic empty state if no rows match query
            let emptyRow = tbody.querySelector(".empty-state-row");
            if (visibleCount === 0 && query) {
                if (!emptyRow) {
                    const colCount = table.querySelectorAll("thead th").length || 6;
                    emptyRow = document.createElement("tr");
                    emptyRow.className = "empty-state-row";
                    emptyRow.innerHTML = `
                        <td colspan="${colCount}" style="padding: 2.5rem 1rem; text-align: center;">
                            <div class="empty-state">
                                <div class="empty-state-icon">🔍</div>
                                <div class="empty-state-title">No matching records</div>
                                <div class="empty-state-text">No results found matching "<strong>${escapeHtml(query)}</strong>". Try checking for typos or searching a different term.</div>
                            </div>
                        </td>
                    `;
                    tbody.appendChild(emptyRow);
                } else {
                    emptyRow.style.display = "";
                }
            } else if (emptyRow) {
                emptyRow.style.display = "none";
            }
        });
    });

    // Dropdowns with data-table-filter="columnIndex" and data-table-filter-target="#tableId"
    const filterSelects = document.querySelectorAll("[data-table-filter]");
    filterSelects.forEach(function (select) {
        const targetSelector = select.getAttribute("data-table-filter-target");
        const colIndex = parseInt(select.getAttribute("data-table-filter"), 10);
        const table = document.querySelector(targetSelector);
        if (!table || isNaN(colIndex)) return;

        const tbody = table.querySelector("tbody");
        if (!tbody) return;

        select.addEventListener("change", function () {
            const selectedVal = this.value.trim().toLowerCase();
            const rows = tbody.querySelectorAll("tr:not(.empty-state-row)");

            rows.forEach(function (row) {
                const cells = row.querySelectorAll("td");
                if (cells.length > colIndex) {
                    const cellText = cells[colIndex].textContent.trim().toLowerCase();
                    if (!selectedVal || cellText.includes(selectedVal)) {
                        row.style.display = "";
                    } else {
                        row.style.display = "none";
                    }
                }
            });
        });
    });
}

/* ==========================================================================
   6. Form Validation & Submission Loading State
   ========================================================================== */
function initFormInteractions() {
    document.querySelectorAll("form").forEach(function (form) {
        // Real-time invalid cleanup on user input
        form.querySelectorAll(".form-control").forEach(function (ctrl) {
            ctrl.addEventListener("input", function () {
                if (this.checkValidity()) {
                    this.classList.remove("is-invalid");
                    const feedback = this.parentElement.querySelector(".invalid-feedback");
                    if (feedback) feedback.style.display = "none";
                }
            });
        });

        // Form submit spinner trigger (for mutating POST/PUT actions)
        form.addEventListener("submit", function (e) {
            const method = (form.getAttribute("method") || "GET").toUpperCase();
            
            // Check HTML5 validity
            if (!form.checkValidity()) {
                // Let browser or custom feedback highlight
                const firstInvalid = form.querySelector(":invalid");
                if (firstInvalid) {
                    firstInvalid.classList.add("is-invalid");
                    firstInvalid.focus();
                }
                return;
            }

            // Only add loading indicator for mutating requests (POST) to avoid locking search forms
            if (method === "POST") {
                const submitBtn = form.querySelector("button[type='submit'], .btn-primary");
                if (submitBtn && !submitBtn.classList.contains("is-loading")) {
                    submitBtn.classList.add("is-loading");
                    submitBtn.disabled = true;
                    // Auto restore after 10s fallback in case page doesn't unload
                    setTimeout(function () {
                        submitBtn.classList.remove("is-loading");
                        submitBtn.disabled = false;
                    }, 10000);
                }
            }
        });
    });
}

/* ==========================================================================
   7. Keyboard Shortcuts (Escape key to dismiss overlays)
   ========================================================================== */
function initKeyboardShortcuts() {
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") {
            // Close any active modal
            const activeModal = document.querySelector(".modal-backdrop.active");
            if (activeModal) {
                closeModal(activeModal);
            }

            // Close mobile sidebar
            const sidebar = document.querySelector(".app-sidebar.open");
            const overlay = document.getElementById("sidebarOverlay");
            if (sidebar) {
                sidebar.classList.remove("open");
                if (overlay) overlay.classList.remove("active");
                document.body.style.overflow = "";
            }

            // Close notification dropdown
            const notifPanel = document.getElementById("notifDropdownPanel");
            if (notifPanel && notifPanel.style.display === "block") {
                notifPanel.style.display = "none";
            }
        }
    });
}

// Utility function to escape HTML in user search input
function escapeHtml(string) {
    const div = document.createElement("div");
    div.textContent = string;
    return div.innerHTML;
}
