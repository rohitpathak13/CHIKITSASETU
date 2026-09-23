/**
 * CHIKITSASETU AI Health Assistant - Frontend Interactive Controller
 * Handles widget UI states, AJAX messaging, file uploads, CSRF authentication, and response rendering.
 */
document.addEventListener("DOMContentLoaded", function () {
    const launcher = document.getElementById("cbLauncher");
    const panel = document.getElementById("cbPanel");
    const minimizeBtn = document.getElementById("cbMinimizeBtn");
    const expandBtn = document.getElementById("cbExpandBtn");
    const clearBtn = document.getElementById("cbClearBtn");
    const messagesContainer = document.getElementById("cbMessages");
    const form = document.getElementById("cbForm");
    const input = document.getElementById("cbInput");
    const attachBtn = document.getElementById("cbAttachBtn");
    const fileInput = document.getElementById("cbFileInput");
    const uploadPreviewBar = document.getElementById("cbUploadPreviewBar");
    const uploadFileName = document.getElementById("cbUploadFileName");
    const uploadFileSize = document.getElementById("cbUploadFileSize");
    const uploadIcon = document.getElementById("cbUploadIcon");
    const uploadRemoveBtn = document.getElementById("cbUploadRemoveBtn");
    const quickActionsBar = document.getElementById("cbQuickActions");

    if (!launcher || !panel) return;

    let currentFileId = null;
    let isWaitingForResponse = false;

    // Helper: Extract CSRF Token from meta tag
    function getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute("content") : "";
    }

    // Toggle Panel Open/Close
    launcher.addEventListener("click", function () {
        panel.classList.toggle("cb-hidden");
        if (!panel.classList.contains("cb-hidden")) {
            input.focus();
            scrollToBottom();
        }
    });

    minimizeBtn.addEventListener("click", function () {
        panel.classList.add("cb-hidden");
    });

    expandBtn.addEventListener("click", function () {
        panel.classList.toggle("cb-expanded");
        scrollToBottom();
    });

    // Clear Message History
    clearBtn.addEventListener("click", function () {
        if (confirm("Clear conversation history?")) {
            messagesContainer.innerHTML = `
                <div class="cb-msg-row cb-msg-bot">
                    <div class="cb-avatar-bot">🤖</div>
                    <div class="cb-bubble">
                        <p><strong>Namaste! Welcome to CHIKITSASETU AI Health Assistant.</strong></p>
                        <p>I can help you understand your medicines, doctor prescriptions, laboratory reports, X-ray findings, and symptoms in simple English, Hindi, or Hinglish.</p>
                        <p style="font-size: 0.78rem; color: #94A3B8; margin-top: 0.4rem;">
                            💡 <em>Tip: You can type your question below or click the 📎 paperclip to upload a report (PDF) or health photo (JPG/PNG).</em>
                        </p>
                    </div>
                </div>
            `;
            clearCurrentUpload();
        }
    });

    // Quick Action Chips
    if (quickActionsBar) {
        quickActionsBar.addEventListener("click", function (e) {
            const chip = e.target.closest(".cb-chip");
            if (!chip) return;
            const promptText = chip.getAttribute("data-prompt");
            const category = chip.getAttribute("data-category");
            if (promptText) {
                input.value = promptText;
                input.focus();
            }
        });
    }

    // File Attachment Trigger
    attachBtn.addEventListener("click", function () {
        fileInput.click();
    });

    // Handle File Selection & AJAX Upload
    fileInput.addEventListener("change", function () {
        if (!fileInput.files || fileInput.files.length === 0) return;
        const file = fileInput.files[0];

        // Client-side size check (10MB)
        if (file.size > 10 * 1024 * 1024) {
            alert("File size exceeds 10MB limit. Please upload a smaller file.");
            fileInput.value = "";
            return;
        }

        const formData = new FormData();
        formData.append("file", file);

        // Update preview UI to uploading state
        uploadPreviewBar.style.display = "flex";
        uploadIcon.textContent = "⏳";
        uploadFileName.textContent = `Uploading ${file.name}...`;
        uploadFileSize.textContent = "";

        fetch("/chatbot/api/upload", {
            method: "POST",
            headers: {
                "X-CSRFToken": getCsrfToken()
            },
            body: formData
        })
        .then(response => response.json())
        .then(res => {
            if (res.success && res.data) {
                currentFileId = res.data.file_id;
                uploadIcon.textContent = res.data.file_type === "pdf" ? "📄" : "🖼️";
                uploadFileName.textContent = res.data.original_filename;
                const kb = Math.round(res.data.size_bytes / 1024);
                uploadFileSize.textContent = `(${kb} KB)`;
            } else {
                alert("Upload failed: " + (res.error || "Unknown error"));
                clearCurrentUpload();
            }
        })
        .catch(err => {
            console.error("Upload error:", err);
            alert("Error uploading file. Please try again.");
            clearCurrentUpload();
        });
    });

    // Remove Uploaded File
    uploadRemoveBtn.addEventListener("click", function () {
        clearCurrentUpload();
    });

    function clearCurrentUpload() {
        currentFileId = null;
        fileInput.value = "";
        uploadPreviewBar.style.display = "none";
    }

    // Handle Message Send
    form.addEventListener("submit", function (e) {
        e.preventDefault();
        const text = input.value.trim();
        if ((!text && !currentFileId) || isWaitingForResponse) return;

        // Render user message bubble
        let userBubbleContent = escapeHtml(text);
        if (currentFileId) {
            const fname = uploadFileName.textContent;
            userBubbleContent = `<div>📎 <em>Attached: ${escapeHtml(fname)}</em></div>` + (userBubbleContent ? `<div style="margin-top: 0.35rem;">${userBubbleContent}</div>` : "");
        }
        appendMessageRow("user", userBubbleContent);

        // Clear input field and cache file ID
        const fileIdToSend = currentFileId;
        input.value = "";
        clearCurrentUpload();
        isWaitingForResponse = true;

        // Render typing indicator
        const typingIndicator = showTypingIndicator();
        scrollToBottom();

        // AJAX POST to /chatbot/api/message
        fetch("/chatbot/api/message", {
            method: "POST",
            headers: {
                "Content-Type": "application/json",
                "X-CSRFToken": getCsrfToken()
            },
            body: JSON.stringify({
                message: text,
                file_id: fileIdToSend
            })
        })
        .then(response => response.json())
        .then(res => {
            removeTypingIndicator(typingIndicator);
            isWaitingForResponse = false;

            if (res.success && res.data) {
                renderBotResponse(res.data);
            } else {
                appendMessageRow("bot", "I encountered an error processing your request. Please try asking again.");
            }
            scrollToBottom();
        })
        .catch(err => {
            console.error("Chatbot request error:", err);
            removeTypingIndicator(typingIndicator);
            isWaitingForResponse = false;
            appendMessageRow("bot", "Network connection error. Please ensure you are logged in and try again.");
            scrollToBottom();
        });
    });

    // Render Bot Response with Markdown & Action Buttons
    function renderBotResponse(data) {
        const isEmergency = data.safety && data.safety.is_emergency;
        const html = formatMarkdownToHtml(data.reply);

        // Action buttons (Doctor booking, prescriptions)
        let actionsHtml = "";
        if (data.suggested_actions && data.suggested_actions.length > 0) {
            actionsHtml += '<div class="cb-actions-container">';
            data.suggested_actions.forEach(action => {
                actionsHtml += `<a href="${escapeHtml(action.url)}" class="cb-action-btn" target="_self">${escapeHtml(action.label)}</a>`;
            });
            actionsHtml += '</div>';
        }

        const fullContent = html + actionsHtml;
        appendMessageRow("bot", fullContent, isEmergency);
    }

    // Append Message Row
    function appendMessageRow(sender, htmlContent, isEmergency = false) {
        const row = document.createElement("div");
        row.className = `cb-msg-row cb-msg-${sender}`;

        let inner = "";
        if (sender === "bot") {
            inner += '<div class="cb-avatar-bot">🤖</div>';
        }

        const emergencyClass = isEmergency ? "cb-bubble cb-bubble-emergency" : "cb-bubble";
        inner += `<div class="${emergencyClass}">${htmlContent}</div>`;
        row.innerHTML = inner;

        messagesContainer.appendChild(row);
        scrollToBottom();
    }

    // Typing Indicator
    function showTypingIndicator() {
        const row = document.createElement("div");
        row.className = "cb-msg-row cb-msg-bot";
        row.id = "cbTypingRow";
        row.innerHTML = `
            <div class="cb-avatar-bot">🤖</div>
            <div class="cb-bubble">
                <div class="cb-typing">
                    <div class="cb-typing-dot"></div>
                    <div class="cb-typing-dot"></div>
                    <div class="cb-typing-dot"></div>
                </div>
            </div>
        `;
        messagesContainer.appendChild(row);
        return row;
    }

    function removeTypingIndicator(indicator) {
        if (indicator && indicator.parentNode) {
            indicator.parentNode.removeChild(indicator);
        }
    }

    function scrollToBottom() {
        messagesContainer.scrollTop = messagesContainer.scrollHeight;
    }

    function escapeHtml(str) {
        if (!str) return "";
        return str
            .replace(/&/g, "&amp;")
            .replace(/</g, "&lt;")
            .replace(/>/g, "&gt;")
            .replace(/"/g, "&quot;")
            .replace(/'/g, "&#039;");
    }

    // Simple Safe Markdown Formatter
    function formatMarkdownToHtml(markdownText) {
        if (!markdownText) return "";
        let html = markdownText;

        // Escape raw HTML first
        html = escapeHtml(html);

        // Headers ### Header
        html = html.replace(/^### (.*$)/gim, "<h3>$1</h3>");
        html = html.replace(/^## (.*$)/gim, "<h3>$1</h3>");

        // Bold **text**
        html = html.replace(/\*\*(.*?)\*\*/gim, "<strong>$1</strong>");

        // Italic *text*
        html = html.replace(/\*(.*?)\*/gim, "<em>$1</em>");

        // Code `text`
        html = html.replace(/`(.*?)`/gim, "<code>$1</code>");

        // Bullet lists
        html = html.replace(/^\s*-\s+(.*$)/gim, "<li>$1</li>");
        html = html.replace(/(<li>.*<\/li>)/s, "<ul>$1</ul>");

        // Line breaks & paragraphs
        html = html.replace(/\n\n+/g, "</p><p>");
        html = html.replace(/\n/g, "<br>");
        html = `<p>${html}</p>`;

        // Clean up empty paragraphs
        html = html.replace(/<p><\/p>/g, "");
        html = html.replace(/<p><h3/g, "<h3");
        html = html.replace(/<\/h3><\/p>/g, "</h3>");

        return html;
    }
});
