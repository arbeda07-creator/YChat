const messagesElement = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const bodyInput = document.querySelector("#body");
const sendButton = composer.querySelector("button[type='submit']");
const errorElement = document.querySelector("#composer-error");
const statusElement = document.querySelector("#connection-status");

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

  meta.append(username, time);
  article.append(meta, message);
  return article;
}

function appendNewMessages(messages) {
  const newMessages = messages.filter((item) => !seenMessageIds.has(String(item.id)));

  if (newMessages.length === 0) {
    if (messages.length === 0 && seenMessageIds.size === 0) {
      messagesElement.querySelector(".empty-state").textContent =
        "No messages yet. Start the conversation.";
    }
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

refreshMessages();
window.setInterval(refreshMessages, 2000);
