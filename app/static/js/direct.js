const directShell = document.querySelector(".direct-shell");
const privateBadge = document.querySelector("[data-private-badge]");
const requestBadge = document.querySelector("[data-request-badge]");
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

function refreshBadges(summary) {
  updateBadge(privateBadge, summary.private_unread_count || 0);
  updateBadge(requestBadge, summary.request_count || 0);
}

function renderPrivateList(conversations) {
  if (!privateList) return;
  if (!conversations.length) {
    privateList.innerHTML = '<p class="empty-state-inline">No private conversations yet.</p>';
    return;
  }

  privateList.innerHTML = conversations.map((conversation) => `
    <a class="conversation-item" href="/dm/${encodeURIComponent(conversation.username)}">
      <span class="avatar">${escapeHtml(conversation.username.slice(0, 1).toUpperCase())}</span>
      <span class="conversation-copy">
        <strong>${escapeHtml(conversation.username)}</strong>
        <small>${escapeHtml(conversation.last_message.message)}</small>
      </span>
      ${conversation.unread ? `<span class="badge">${conversation.unread}</span>` : ""}
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
      <span class="avatar">${escapeHtml(conversation.username.slice(0, 1).toUpperCase())}</span>
      <span class="conversation-copy">
        <strong>${escapeHtml(conversation.username)}</strong>
        <small>${escapeHtml(conversation.last_message.message)}</small>
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
  if (!directShell) return;

  try {
    const response = await fetch(directShell.dataset.summaryUrl, {
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

  if (!window.io) {
    window.setInterval(fetchSummary, 3000);
    return;
  }

  const socket = window.io({ transports: ["polling", "websocket"] });
  socket.on("dm_update", refreshDirect);
});
