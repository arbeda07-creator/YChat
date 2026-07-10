const directShell = document.querySelector(".direct-shell");
const summarySource = directShell || document.querySelector("[data-bottom-nav-summary-url]");
const privateBadges = document.querySelectorAll("[data-private-badge]");
const requestBadges = document.querySelectorAll("[data-request-badge]");
const privateList = document.querySelector("[data-private-list]");
const requestsList = document.querySelector("[data-requests-list]");

function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = value || "";
  return element.innerHTML;
}

function updateBadge(element, count) {
  if (!element) return;
  element.textContent = count;
  element.classList.toggle("is-hidden", !count);
}

function updateBadges(elements, count) {
  elements.forEach((element) => updateBadge(element, count));
}

function avatarMarkup(item) {
  if (item.avatar_url) {
    return `<img class="avatar" src="${escapeHtml(item.avatar_url)}" alt="">`;
  }
  return `<span class="avatar">${escapeHtml(item.initial || item.username.slice(0, 1).toUpperCase())}</span>`;
}

function refreshBadges(summary) {
  updateBadges(privateBadges, summary.private_unread_count || 0);
  updateBadges(requestBadges, summary.request_count || 0);
}

function formatConversationTime(isoTime) {
  const date = new Date(isoTime);
  if (Number.isNaN(date.getTime())) return "";

  const now = new Date();
  if (date.toDateString() === now.toDateString()) {
    return new Intl.DateTimeFormat(undefined, {
      hour: "numeric",
      minute: "2-digit",
    }).format(date);
  }

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return "Yesterday";

  return new Intl.DateTimeFormat(undefined, {
    month: "short",
    day: "numeric",
  }).format(date);
}

function conversationPreview(message) {
  if (message.message) return message.message;
  if (message.message_type === "voice") return "Voice message";
  return "Message";
}

function renderPrivateList(conversations) {
  if (!privateList) return;
  if (!conversations.length) {
    privateList.innerHTML = '<p class="empty-state-inline">No private conversations yet.</p>';
    return;
  }

  privateList.innerHTML = conversations.map((conversation) => `
    <a class="conversation-item" href="/dm/${encodeURIComponent(conversation.username)}">
      ${avatarMarkup(conversation)}
      <span class="conversation-copy">
        <strong>${escapeHtml(conversation.display_name || conversation.username)}</strong>
        <small>${escapeHtml(conversationPreview(conversation.last_message))}</small>
      </span>
      <span class="conversation-meta">
        <small>${escapeHtml(formatConversationTime(conversation.last_message.time))}</small>
        ${conversation.unread ? `<span class="badge">${conversation.unread}</span>` : ""}
      </span>
    </a>
  `).join("");
}

function renderRequestsList(requests) {
  if (!requestsList) return;
  if (!requests.length) {
    requestsList.innerHTML = '<p class="empty-state-inline">No message requests.</p>';
    return;
  }

  requestsList.innerHTML = requests.map((conversation) => `
    <article class="conversation-item request-item" data-request-user="${escapeHtml(conversation.username)}">
      ${avatarMarkup(conversation)}
      <span class="conversation-copy">
        <strong>${escapeHtml(conversation.display_name || conversation.username)}</strong>
        <small>${escapeHtml(conversationPreview(conversation.last_message))}</small>
      </span>
      <span class="request-actions">
        <button class="button button-primary" data-accept-url="/api/dm/${encodeURIComponent(conversation.username)}/accept">Accept</button>
        <button class="button button-ghost" data-reject-url="/api/dm/${encodeURIComponent(conversation.username)}/reject">Reject</button>
      </span>
    </article>
  `).join("");
}

function refreshDirect(summary) {
  refreshBadges(summary);
  renderPrivateList(summary.private || []);
  renderRequestsList(summary.requests || []);
}

async function fetchSummary() {
  if (!summarySource) return;

  try {
    const response = await fetch(summarySource.dataset.summaryUrl || summarySource.dataset.bottomNavSummaryUrl, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) return;
    refreshDirect(await response.json());
  } catch (error) {
    return;
  }
}

document.addEventListener("click", async (event) => {
  const acceptButton = event.target.closest("[data-accept-url]");
  const rejectButton = event.target.closest("[data-reject-url]");
  const button = acceptButton || rejectButton;
  if (!button) return;

  event.preventDefault();
  button.disabled = true;

  try {
    const response = await fetch(button.dataset.acceptUrl || button.dataset.rejectUrl, {
      method: "POST",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Request could not be updated.");

    if (data.redirect) {
      window.location.href = data.redirect;
      return;
    }

    button.closest("[data-request-user]")?.remove();
    await fetchSummary();
  } catch (error) {
    button.disabled = false;
  }
});

window.addEventListener("load", () => {
  fetchSummary();
  window.setInterval(fetchSummary, 3000);
});
