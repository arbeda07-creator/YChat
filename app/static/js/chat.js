const messagesElement = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const bodyInput = document.querySelector("#body");
const sendButton = composer.querySelector("button[type='submit']");
const errorElement = document.querySelector("#composer-error");
const statusElement = document.querySelector("#connection-status");
const deleteChatButton = document.querySelector("[data-delete-chat-url]");

let refreshInProgress = false;
const seenMessageIds = new Set();

function formatTime(isoTime) {
  const date = new Date(isoTime);
  if (Number.isNaN(date.getTime())) return isoTime;

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function createMessageElement(item) {
  const article = document.createElement("article");
  article.className = "message";
  article.dataset.messageId = item.id;
  if (item.username === messagesElement.dataset.currentUser) {
    article.classList.add("message-own");
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const username = document.createElement("strong");
  username.textContent = item.username;

  const time = document.createElement("time");
  time.dateTime = item.time;
  time.textContent = formatTime(item.time);

  const message = document.createElement("p");
  message.textContent = item.message;

  const deleteButton = document.createElement("button");
  deleteButton.className = "message-delete";
  deleteButton.type = "button";
  deleteButton.dataset.messageId = item.id;
  deleteButton.textContent = "Delete";

  meta.append(username, time);
  article.append(meta, message);
  if (messagesElement.dataset.deleteMessageUrlTemplate) {
    article.append(deleteButton);
  }
  return article;
}

function visibleConversationMessages(messages) {
  const conversationUser = messagesElement.dataset.conversationUser;
  const currentUser = messagesElement.dataset.currentUser;

  return messages.filter((item) => {
    if (!conversationUser) return true;
    return (
      (item.username === currentUser && item.receiver === conversationUser) ||
      (item.username === conversationUser && item.receiver === currentUser)
    );
  });
}

function syncRemovedMessages(messages) {
  const visibleIds = new Set(messages.map((item) => String(item.id)));
  messagesElement.querySelectorAll("[data-message-id]").forEach((element) => {
    if (!visibleIds.has(element.dataset.messageId)) {
      element.remove();
    }
  });
}

function showEmptyState() {
  if (messagesElement.querySelector(".empty-state")) return;

  const emptyState = document.createElement("div");
  emptyState.className = "empty-state";
  emptyState.textContent = "No messages yet. Start the conversation.";
  messagesElement.append(emptyState);
}

function appendNewMessages(messages) {
  const visibleMessages = visibleConversationMessages(messages);
  syncRemovedMessages(visibleMessages);
  const newMessages = visibleMessages.filter((item) => !seenMessageIds.has(String(item.id)));

  if (newMessages.length === 0) {
    if (visibleMessages.length === 0) showEmptyState();
    return;
  }

  messagesElement.querySelector(".empty-state")?.remove();
  const fragment = document.createDocumentFragment();

  newMessages.forEach((item) => {
    seenMessageIds.add(String(item.id));
    fragment.append(createMessageElement(item));
  });

  messagesElement.append(fragment);
  messagesElement.scrollTop = messagesElement.scrollHeight;
}

function setConnectionStatus(isLive, label) {
  statusElement.classList.toggle("status-offline", !isLive);
  statusElement.lastChild.textContent = ` ${label}`;
}

async function refreshMessages() {
  if (refreshInProgress) return;
  refreshInProgress = true;

  try {
    const url = new URL(messagesElement.dataset.messagesUrl, window.location.origin);
    url.searchParams.set("_", Date.now());
    const response = await fetch(url, {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Could not refresh messages.");

    const data = await response.json();
    appendNewMessages(data.messages);
    setConnectionStatus(true, "Live");
  } catch (error) {
    setConnectionStatus(false, "Reconnecting");
  } finally {
    refreshInProgress = false;
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = bodyInput.value.trim();
  if (!message) return;

  sendButton.disabled = true;
  errorElement.textContent = "";

  try {
    const response = await fetch(messagesElement.dataset.sendUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Accept: "application/json",
      },
      body: JSON.stringify({ message }),
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Message could not be sent.");

    bodyInput.value = "";
    await refreshMessages();
    bodyInput.focus();
  } catch (error) {
    errorElement.textContent = error.message;
  } finally {
    sendButton.disabled = false;
  }
});

bodyInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});

messagesElement.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-message-id]");
  if (!button || !button.classList.contains("message-delete")) return;

  const url = new URL(messagesElement.dataset.deleteMessageUrlTemplate, window.location.origin);
  url.pathname = url.pathname.replace(/\/0$/, `/${button.dataset.messageId}`);
  button.disabled = true;

  try {
    const response = await fetch(url, {
      method: "DELETE",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Message could not be deleted.");
    button.closest(".message")?.remove();
    await refreshMessages();
  } catch (error) {
    button.disabled = false;
    errorElement.textContent = error.message;
  }
});

deleteChatButton?.addEventListener("click", async () => {
  if (!window.confirm("Delete this chat?")) return;

  deleteChatButton.disabled = true;
  try {
    const response = await fetch(deleteChatButton.dataset.deleteChatUrl, {
      method: "DELETE",
      headers: { Accept: "application/json" },
      credentials: "same-origin",
    });
    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Chat could not be deleted.");
    window.location.href = data.redirect || "/";
  } catch (error) {
    deleteChatButton.disabled = false;
    errorElement.textContent = error.message;
  }
});

refreshMessages();
window.setInterval(refreshMessages, 2000);
