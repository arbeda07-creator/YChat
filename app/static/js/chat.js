const messagesElement = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const bodyInput = document.querySelector("#body");
const sendButton = composer.querySelector("button[type='submit']");
const errorElement = document.querySelector("#composer-error");
const statusElement = document.querySelector("#connection-status");

let refreshInProgress = false;
let lastRenderedSignature = "";

function formatTime(isoTime) {
  const date = new Date(isoTime);
  if (Number.isNaN(date.getTime())) return isoTime;

  return new Intl.DateTimeFormat(undefined, {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderMessages(messages) {
  const signature = JSON.stringify(messages);
  if (signature === lastRenderedSignature) return;
  lastRenderedSignature = signature;

  const fragment = document.createDocumentFragment();

  if (messages.length === 0) {
    const emptyState = document.createElement("div");
    emptyState.className = "empty-state";
    emptyState.textContent = "No messages yet. Start the conversation.";
    fragment.append(emptyState);
  } else {
    messages.forEach((item) => {
      const article = document.createElement("article");
      article.className = "message";
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
      fragment.append(article);
    });
  }

  messagesElement.replaceChildren(fragment);
  messagesElement.scrollTo({ top: messagesElement.scrollHeight, behavior: "smooth" });
}

async function refreshMessages() {
  if (refreshInProgress) return;
  refreshInProgress = true;

  try {
    const response = await fetch(messagesElement.dataset.messagesUrl, {
      headers: { Accept: "application/json" },
      cache: "no-store",
    });
    if (!response.ok) throw new Error("Could not refresh messages.");

    const data = await response.json();
    renderMessages(data.messages);
    statusElement.classList.remove("status-offline");
    statusElement.lastChild.textContent = " Live";
  } catch (error) {
    statusElement.classList.add("status-offline");
    statusElement.lastChild.textContent = " Reconnecting";
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
