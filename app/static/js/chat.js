const messagesElement = document.querySelector("#messages");
const composer = document.querySelector("#composer");
const bodyInput = document.querySelector("#body");
const sendButton = composer.querySelector("button[type='submit']");
const errorElement = document.querySelector("#composer-error");
const statusElement = document.querySelector("#connection-status");
const deleteChatButton = document.querySelector("[data-delete-chat-url]");
const replyPreview = document.querySelector("#reply-preview");
const replyName = document.querySelector("#reply-name");
const replyText = document.querySelector("#reply-text");
const replyCancel = document.querySelector("#reply-cancel");
const voiceButton = document.querySelector("#voice-button");
const recordingBar = document.querySelector("#recording-bar");
const recordingStop = document.querySelector("#recording-stop");
const recordingLabel = document.querySelector("#recording-label");

const reactionEmojis = ["❤️", "😂", "👍", "😮", "😢", "🔥"];
let refreshInProgress = false;
let currentReply = null;
let mediaRecorder = null;
let activeMicrophoneStream = null;
let recordingTimeout = null;
let recordingStartInProgress = false;
let lastRenderedSignature = "";

function withCacheBust(path) {
  const separator = path.includes("?") ? "&" : "?";
  return `${path}${separator}_=${Date.now()}`;
}

function replaceTrailingMessageId(path, messageId, suffix = "") {
  const ending = suffix ? `/0/${suffix}` : "/0";
  const replacement = suffix ? `/${messageId}/${suffix}` : `/${messageId}`;
  return path.endsWith(ending)
    ? `${path.slice(0, -ending.length)}${replacement}`
    : path;
}

function formatTime(isoTime) {
  const date = new Date(isoTime);
  if (Number.isNaN(date.getTime())) return isoTime;

  const now = new Date();
  const time = new Intl.DateTimeFormat(undefined, {
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
  if (date.toDateString() === now.toDateString()) return time;

  const yesterday = new Date(now);
  yesterday.setDate(now.getDate() - 1);
  if (date.toDateString() === yesterday.toDateString()) return `Yesterday, ${time}`;

  return new Intl.DateTimeFormat(undefined, {
    day: "numeric",
    month: "short",
    year: date.getFullYear() === now.getFullYear() ? undefined : "numeric",
    hour: "numeric",
    minute: "2-digit",
  }).format(date);
}

function setError(message) {
  errorElement.textContent = message || "";
}

function messageSummary(item) {
  if (item.message) return item.message;
  if (item.message_type === "voice") return "Voice message";
  return "Message";
}

function createAvatar(item) {
  const avatar = document.createElement(item.avatar_url ? "img" : "span");
  avatar.className = "message-avatar";
  if (item.avatar_url) {
    avatar.src = item.avatar_url;
    avatar.alt = "";
  } else {
    avatar.textContent = item.initial || item.username.slice(0, 1).toUpperCase();
  }
  return avatar;
}

function createReplyQuote(reply) {
  const quote = document.createElement("button");
  quote.className = "message-reply-quote";
  quote.type = "button";
  quote.dataset.scrollToMessage = reply.id;

  const name = document.createElement("strong");
  name.textContent = reply.display_name || "Reply";

  const text = document.createElement("span");
  text.textContent = reply.deleted ? "Deleted message" : reply.message;

  quote.append(name, text);
  return quote;
}

function createAudioPlayer(item) {
  const wrap = document.createElement("div");
  wrap.className = "voice-player";

  const audio = document.createElement("audio");
  audio.preload = "metadata";
  audio.src = item.audio_url;
  audio.playsInline = true;

  const playButton = document.createElement("button");
  playButton.type = "button";
  playButton.className = "voice-play-button";
  playButton.setAttribute("aria-label", "Play voice message");
  const playIcon = document.createElement("span");
  playIcon.textContent = "▶";
  playButton.append(playIcon);

  const progress = document.createElement("input");
  progress.className = "voice-progress";
  progress.type = "range";
  progress.min = "0";
  progress.max = "1000";
  progress.value = "0";
  progress.setAttribute("aria-label", "Voice message progress");

  const time = document.createElement("span");
  time.className = "voice-time";
  time.textContent = "0:00";

  const formatDuration = (seconds) => {
    if (!Number.isFinite(seconds) || seconds < 0) return "0:00";
    const minutes = Math.floor(seconds / 60);
    const remainder = Math.floor(seconds % 60).toString().padStart(2, "0");
    return `${minutes}:${remainder}`;
  };

  const updateProgress = () => {
    progress.value = audio.duration
      ? Math.round((audio.currentTime / audio.duration) * 1000).toString()
      : "0";
    time.textContent = formatDuration(audio.currentTime || audio.duration);
  };

  playButton.addEventListener("click", async () => {
    if (audio.paused) {
      document.querySelectorAll(".voice-player audio").forEach((otherAudio) => {
        if (otherAudio !== audio) otherAudio.pause();
      });
      try {
        await audio.play();
      } catch (error) {
        time.textContent = "Error";
      }
    } else {
      audio.pause();
    }
  });
  progress.addEventListener("input", () => {
    if (audio.duration) audio.currentTime = (Number(progress.value) / 1000) * audio.duration;
  });
  audio.addEventListener("loadedmetadata", () => {
    time.textContent = formatDuration(audio.duration);
  });
  audio.addEventListener("timeupdate", updateProgress);
  audio.addEventListener("play", () => {
    playIcon.textContent = "❚❚";
    playButton.setAttribute("aria-label", "Pause voice message");
  });
  audio.addEventListener("pause", () => {
    playIcon.textContent = "▶";
    playButton.setAttribute("aria-label", "Play voice message");
  });
  audio.addEventListener("ended", () => {
    audio.currentTime = 0;
    updateProgress();
  });
  audio.addEventListener("error", () => {
    playButton.disabled = true;
    time.textContent = "Error";
  });

  wrap.append(audio, playButton, progress, time);
  return wrap;
}

function createReactions(item) {
  const wrap = document.createElement("div");
  wrap.className = "message-reactions";

  (item.reactions || []).forEach((reaction) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "reaction-pill";
    if (item.my_reaction === reaction.emoji) button.classList.add("active");
    button.dataset.reaction = reaction.emoji;
    button.dataset.messageId = item.id;
    button.textContent = `${reaction.emoji} ${reaction.count}`;
    wrap.append(button);
  });

  return wrap;
}

function createActions(item) {
  const actions = document.createElement("div");
  actions.className = "message-actions";

  const replyButton = document.createElement("button");
  replyButton.type = "button";
  replyButton.dataset.replyMessageId = item.id;
  replyButton.textContent = "Reply";

  const reactionButton = document.createElement("button");
  reactionButton.type = "button";
  reactionButton.dataset.openReactions = item.id;
  reactionButton.textContent = "React";

  actions.append(replyButton, reactionButton);

  if (
    messagesElement.dataset.deleteMessageUrlTemplate
    && item.username === messagesElement.dataset.currentUser
  ) {
    const deleteButton = document.createElement("button");
    deleteButton.type = "button";
    deleteButton.className = "message-delete";
    deleteButton.dataset.deleteMessageId = item.id;
    deleteButton.textContent = "Delete";
    actions.append(deleteButton);
  }

  return actions;
}

function createToolsButton(item) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "message-tools-button";
  button.dataset.toggleMessageActions = item.id;
  button.setAttribute("aria-label", "Message actions");
  button.setAttribute("aria-expanded", "false");
  button.textContent = "•••";
  return button;
}

function createReactionPicker(item) {
  const picker = document.createElement("div");
  picker.className = "reaction-picker is-hidden";
  picker.dataset.reactionPickerFor = item.id;

  reactionEmojis.forEach((emoji) => {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.reaction = emoji;
    button.dataset.messageId = item.id;
    button.className = item.my_reaction === emoji ? "active" : "";
    button.textContent = emoji;
    picker.append(button);
  });

  return picker;
}

function createMessageElement(item) {
  const article = document.createElement("article");
  article.className = "message";
  article.dataset.messageId = item.id;
  article.dataset.replyName = item.display_name || item.username;
  article.dataset.replyText = messageSummary(item);
  article.dataset.renderSignature = messageRenderSignature(item);
  if (item.username === messagesElement.dataset.currentUser) {
    article.classList.add("message-own");
  }

  const meta = document.createElement("div");
  meta.className = "message-meta";

  const username = document.createElement("strong");
  username.textContent = item.display_name || item.username;

  const time = document.createElement("time");
  time.dateTime = item.time;
  time.textContent = formatTime(item.time);

  meta.append(username, time, createToolsButton(item));
  article.append(createAvatar(item), meta);

  if (item.reply) {
    article.append(createReplyQuote(item.reply));
  }

  if (item.message) {
    const message = document.createElement("p");
    message.textContent = item.message;
    article.append(message);
  }

  if (item.audio_url) {
    article.append(createAudioPlayer(item));
  }

  if (item.username === messagesElement.dataset.currentUser && item.is_read) {
    const receipt = document.createElement("small");
    receipt.className = "message-read-receipt";
    receipt.textContent = "Seen";
    article.append(receipt);
  }

  article.append(createReactions(item), createActions(item), createReactionPicker(item));
  return article;
}

function messageRenderSignature(item) {
  return JSON.stringify({
    id: item.id,
    message: item.message,
    type: item.message_type,
    audio: item.audio_url,
    reply: item.reply,
    reactions: item.reactions,
    mine: item.my_reaction,
    read: item.is_read,
  });
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

function renderMessages(messages) {
  const visibleMessages = visibleConversationMessages(messages);
  const signature = JSON.stringify(visibleMessages.map(messageRenderSignature));

  if (signature === lastRenderedSignature) return;
  lastRenderedSignature = signature;

  const shouldStickToBottom =
    messagesElement.scrollHeight - messagesElement.scrollTop - messagesElement.clientHeight < 80;
  const containerTop = messagesElement.getBoundingClientRect().top;
  const anchor = Array.from(messagesElement.querySelectorAll(".message")).find((element) => (
    element.getBoundingClientRect().bottom > containerTop
  ));
  const anchorId = anchor?.dataset.messageId;
  const anchorOffset = anchor ? anchor.getBoundingClientRect().top - containerTop : 0;

  if (visibleMessages.length === 0) {
    messagesElement.replaceChildren();
    showEmptyState();
    return;
  }

  const existing = new Map(
    Array.from(messagesElement.querySelectorAll(".message")).map((element) => (
      [element.dataset.messageId, element]
    ))
  );
  const nextElements = visibleMessages.map((item) => {
    const element = existing.get(String(item.id));
    const itemSignature = messageRenderSignature(item);
    return element?.dataset.renderSignature === itemSignature
      ? element
      : createMessageElement(item);
  });
  messagesElement.replaceChildren(...nextElements);

  if (shouldStickToBottom) {
    window.requestAnimationFrame(() => {
      messagesElement.scrollTop = messagesElement.scrollHeight;
    });
  } else if (anchorId) {
    const nextAnchor = messagesElement.querySelector(`[data-message-id="${anchorId}"]`);
    if (nextAnchor) {
      messagesElement.scrollTop += nextAnchor.getBoundingClientRect().top - containerTop - anchorOffset;
    }
  }
}

function showEmptyState() {
  const emptyState = document.createElement("div");
  emptyState.className = "empty-state";
  emptyState.textContent = "No messages yet. Start the conversation.";
  messagesElement.append(emptyState);
}

function setConnectionStatus(isLive, label) {
  statusElement.classList.toggle("status-offline", !isLive);
  statusElement.lastChild.textContent = ` ${label}`;
}

async function refreshMessages() {
  if (refreshInProgress) return;
  refreshInProgress = true;

  try {
    const response = await fetch(withCacheBust(messagesElement.dataset.messagesUrl), {
      headers: { Accept: "application/json" },
      cache: "no-store",
      credentials: "same-origin",
    });
    if (!response.ok) throw new Error("Could not refresh messages.");

    const data = await response.json();
    renderMessages(data.messages);
    setConnectionStatus(true, "Live");
  } catch (error) {
    setConnectionStatus(false, "Reconnecting");
  } finally {
    refreshInProgress = false;
  }
}

function setReply(item) {
  currentReply = item;
  replyName.textContent = item.name;
  replyText.textContent = item.text;
  replyPreview.classList.remove("is-hidden");
  bodyInput.focus();
}

function clearReply() {
  currentReply = null;
  replyPreview.classList.add("is-hidden");
  replyName.textContent = "Reply";
  replyText.textContent = "";
}

function isMessageListNearBottom() {
  return messagesElement.scrollHeight - messagesElement.scrollTop - messagesElement.clientHeight < 80;
}

function resizeComposerInput() {
  const wasNearBottom = isMessageListNearBottom();
  const previousHeight = bodyInput.offsetHeight;

  bodyInput.style.height = "0px";
  const nextHeight = Math.min(bodyInput.scrollHeight, 96);
  bodyInput.style.height = `${nextHeight}px`;

  if (wasNearBottom && bodyInput.offsetHeight !== previousHeight) {
    messagesElement.scrollTop = messagesElement.scrollHeight;
  }
}

function setupMobileViewport() {
  if (!document.body.classList.contains("chat-page")) return;

  document.documentElement.classList.add("chat-document");
  const viewport = window.visualViewport;
  let largestViewportHeight = viewport?.height || window.innerHeight;
  let previousViewportHeight = largestViewportHeight;
  let keyboardOpen = false;

  const updateViewport = () => {
    const viewportHeight = Math.round(viewport?.height || window.innerHeight);
    const inputFocused = document.activeElement === bodyInput;
    const heightLoss = largestViewportHeight - viewportHeight;
    const nextKeyboardOpen = heightLoss > Math.max(100, largestViewportHeight * 0.18)
      && (inputFocused || keyboardOpen);
    const viewportChanged = viewportHeight !== previousViewportHeight;

    document.documentElement.style.setProperty("--chat-viewport-height", `${viewportHeight}px`);
    document.body.classList.toggle("keyboard-open", nextKeyboardOpen);

    if (nextKeyboardOpen && (!keyboardOpen || viewportChanged)) {
      window.requestAnimationFrame(() => {
        messagesElement.scrollTop = messagesElement.scrollHeight;
      });
    }

    keyboardOpen = nextKeyboardOpen;
    previousViewportHeight = viewportHeight;
    if (!keyboardOpen && !inputFocused) {
      largestViewportHeight = viewportHeight;
    }
  };

  viewport?.addEventListener("resize", updateViewport);
  viewport?.addEventListener("scroll", updateViewport);
  window.addEventListener("resize", updateViewport);
  bodyInput.addEventListener("focus", updateViewport);
  bodyInput.addEventListener("blur", updateViewport);
  window.addEventListener("orientationchange", () => {
    largestViewportHeight = viewport?.height || window.innerHeight;
    updateViewport();
  });
  updateViewport();
}

async function sendMessage({ voiceBlob } = {}) {
  const message = bodyInput.value.trim();
  if (!message && !voiceBlob) return;

  sendButton.disabled = true;
  voiceButton.disabled = true;
  setError("");

  try {
    let response;
    if (voiceBlob) {
      const formData = new FormData();
      formData.append("message", message);
      formData.append("voice", voiceBlob, voiceFilename(voiceBlob.type));
      if (currentReply) formData.append("reply_to", currentReply.id);

      response = await fetch(messagesElement.dataset.sendUrl, {
        method: "POST",
        body: formData,
        credentials: "same-origin",
        headers: { Accept: "application/json" },
      });
    } else {
      response = await fetch(messagesElement.dataset.sendUrl, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          Accept: "application/json",
        },
        credentials: "same-origin",
        body: JSON.stringify({
          message,
          reply_to: currentReply ? currentReply.id : null,
        }),
      });
    }

    const data = await response.json();
    if (!response.ok) throw new Error(data.error || "Message could not be sent.");

    bodyInput.value = "";
    clearReply();
    await refreshMessages();
    bodyInput.focus();
  } catch (error) {
    setError(error.message);
  } finally {
    sendButton.disabled = false;
    voiceButton.disabled = false;
  }
}

function voiceFilename(mimeType) {
  const normalizedType = (mimeType || "").split(";", 1)[0].toLowerCase();
  const extension = {
    "audio/mp4": "m4a",
    "audio/ogg": "ogg",
    "audio/webm": "webm",
  }[normalizedType] || "webm";
  return `voice-message.${extension}`;
}

async function sendReaction(messageId, emoji) {
  const url = replaceTrailingMessageId(
    messagesElement.dataset.reactionUrlTemplate,
    messageId,
    "reaction"
  );

  const response = await fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    credentials: "same-origin",
    body: JSON.stringify({ emoji }),
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Reaction could not be saved.");
  await refreshMessages();
}

function recordingErrorMessage(error) {
  switch (error?.name) {
    case "NotAllowedError":
    case "PermissionDeniedError":
      return "تم رفض إذن الميكروفون. اسمح للموقع باستخدامه من إعدادات المتصفح ثم أعد تحميل الصفحة.";
    case "NotFoundError":
    case "DevicesNotFoundError":
      return "لم يعثر المتصفح على ميكروفون. تأكد من توصيله وتفعيله في إعدادات الجهاز.";
    case "NotReadableError":
    case "TrackStartError":
      return "الميكروفون مشغول أو غير متاح. أغلق التطبيقات الأخرى التي تستخدمه ثم حاول مجددًا.";
    case "SecurityError":
      return "منع المتصفح تشغيل الميكروفون بسبب قيود الأمان.";
    case "AbortError":
      return "فشل بدء الميكروفون. حاول مرة أخرى.";
    case "TypeError":
      return "تعذر تشغيل التسجيل بسبب عدم توافق واجهة الميكروفون في هذا المتصفح.";
    case "NotSupportedError":
      return "هذا المتصفح لا يدعم تسجيل الصوت بصيغة متوافقة.";
    default:
      return "تعذر بدء التسجيل الصوتي. تحقق من الميكروفون وحاول مرة أخرى.";
  }
}

function logRecordingError(error) {
  console.error(error.name, error.message, error);
}

function stopMicrophoneTracks(stream) {
  if (!stream) return;
  stream.getTracks().forEach((track) => track.stop());
  if (activeMicrophoneStream === stream) activeMicrophoneStream = null;
}

function preferredRecordingMimeType() {
  if (typeof window.MediaRecorder?.isTypeSupported !== "function") return null;

  // Chrome and Edge record WebM reliably. The server converts it to M4A so
  // Safari on iPhone can play the saved message.
  const preferredTypes = [
    "audio/webm;codecs=opus",
    "audio/webm",
    "audio/mp4",
    "audio/ogg;codecs=opus",
  ];
  return preferredTypes.find((type) => window.MediaRecorder.isTypeSupported(type)) || null;
}

function isPlayableAudioBlob(blob) {
  return new Promise((resolve) => {
    const audio = document.createElement("audio");
    const objectUrl = URL.createObjectURL(blob);
    const timeout = window.setTimeout(() => finish(false), 5000);

    const finish = (isPlayable) => {
      window.clearTimeout(timeout);
      audio.removeEventListener("canplay", handleCanPlay);
      audio.removeEventListener("error", handleError);
      audio.removeAttribute("src");
      audio.load();
      URL.revokeObjectURL(objectUrl);
      resolve(isPlayable);
    };
    const handleCanPlay = () => finish(true);
    const handleError = () => finish(false);

    audio.preload = "auto";
    audio.addEventListener("canplay", handleCanPlay, { once: true });
    audio.addEventListener("error", handleError, { once: true });
    audio.src = objectUrl;
    audio.load();
  });
}

async function startRecording() {
  if (recordingStartInProgress || mediaRecorder) return;
  if (!navigator.mediaDevices) {
    setError("هذا المتصفح لا يوفر واجهة الوصول إلى الميكروفون.");
    return;
  }
  if (typeof navigator.mediaDevices.getUserMedia !== "function") {
    setError("هذا المتصفح لا يدعم طلب الوصول إلى الميكروفون.");
    return;
  }
  if (typeof window.MediaRecorder !== "function") {
    setError("هذا المتصفح لا يدعم تسجيل الصوت.");
    return;
  }

  setError("");
  recordingStartInProgress = true;
  voiceButton.disabled = true;
  let stream = null;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    activeMicrophoneStream = stream;

    if (stream.getAudioTracks().length === 0) {
      throw new DOMException("The stream contains no audio tracks.", "NotFoundError");
    }

    const recordedChunks = [];
    const mimeType = preferredRecordingMimeType();
    const recorder = mimeType
      ? new window.MediaRecorder(stream, { mimeType })
      : new window.MediaRecorder(stream);
    let recordingFailed = false;
    mediaRecorder = recorder;

    recorder.addEventListener("dataavailable", (event) => {
      if (event.data.size > 0) recordedChunks.push(event.data);
    });
    recorder.addEventListener("error", (event) => {
      const error = event.error || new DOMException("MediaRecorder failed.", "AbortError");
      recordingFailed = true;
      logRecordingError(error);
      window.clearTimeout(recordingTimeout);
      stopMicrophoneTracks(stream);
      recordingBar.classList.add("is-hidden");
      voiceButton.disabled = false;
      setError(recordingErrorMessage(error));
      if (recorder.state === "recording") recorder.stop();
    });
    recorder.addEventListener("stop", async () => {
      window.clearTimeout(recordingTimeout);
      stopMicrophoneTracks(stream);
      recordingBar.classList.add("is-hidden");
      voiceButton.disabled = false;

      if (mediaRecorder === recorder) mediaRecorder = null;
      if (recordingFailed) {
        return;
      }

      const voiceType = recorder.mimeType || recordedChunks[0]?.type || "audio/webm";
      const voiceBlob = new Blob(recordedChunks, { type: voiceType });
      if (voiceBlob.size === 0) {
        setError("لم يتم تسجيل أي صوت. حاول مرة أخرى.");
        return;
      }
      if (voiceBlob.size > 2 * 1024 * 1024) {
        setError("الرسالة الصوتية كبيرة جدًا. سجّل رسالة أقصر.");
        return;
      }
      if (!await isPlayableAudioBlob(voiceBlob)) {
        setError("The voice recording is invalid. Please record it again.");
        return;
      }
      await sendMessage({ voiceBlob });
    });

    recorder.start();
    voiceButton.disabled = true;
    recordingBar.classList.remove("is-hidden");
    recordingLabel.textContent = "جارٍ تسجيل الرسالة الصوتية...";
    recordingTimeout = window.setTimeout(() => {
      if (recorder.state === "recording") recorder.stop();
    }, 60000);
  } catch (error) {
    stopMicrophoneTracks(stream);
    mediaRecorder = null;
    recordingBar.classList.add("is-hidden");
    voiceButton.disabled = false;
    logRecordingError(error);
    setError(recordingErrorMessage(error));
  } finally {
    recordingStartInProgress = false;
  }
}

composer.addEventListener("submit", async (event) => {
  event.preventDefault();
  await sendMessage();
});

bodyInput.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    composer.requestSubmit();
  }
});
bodyInput.addEventListener("input", resizeComposerInput);

replyCancel.addEventListener("click", clearReply);

voiceButton.addEventListener("click", startRecording);

recordingStop.addEventListener("click", () => {
  if (mediaRecorder?.state === "recording") {
    recordingLabel.textContent = "جارٍ حفظ الرسالة الصوتية...";
    mediaRecorder.stop();
  }
});

window.addEventListener("pagehide", () => {
  stopMicrophoneTracks(activeMicrophoneStream);
});

messagesElement.addEventListener("click", async (event) => {
  const toolsButton = event.target.closest("[data-toggle-message-actions]");
  const replyButton = event.target.closest("[data-reply-message-id]");
  const openReactions = event.target.closest("[data-open-reactions]");
  const reactionButton = event.target.closest("[data-reaction]");
  const deleteButton = event.target.closest("[data-delete-message-id]");
  const quoteButton = event.target.closest("[data-scroll-to-message]");

  if (toolsButton) {
    const message = toolsButton.closest(".message");
    const actions = message?.querySelector(".message-actions");
    const willOpen = !actions?.classList.contains("is-open");
    messagesElement.querySelectorAll(".message-actions.is-open").forEach((element) => {
      element.classList.remove("is-open");
      element.closest(".message")?.querySelector("[data-toggle-message-actions]")
        ?.setAttribute("aria-expanded", "false");
    });
    actions?.classList.toggle("is-open", willOpen);
    toolsButton.setAttribute("aria-expanded", String(willOpen));
    return;
  }

  if (replyButton) {
    const message = replyButton.closest(".message");
    setReply({
      id: replyButton.dataset.replyMessageId,
      name: message.dataset.replyName,
      text: message.dataset.replyText,
    });
    return;
  }

  if (openReactions) {
    const picker = messagesElement.querySelector(
      `[data-reaction-picker-for="${openReactions.dataset.openReactions}"]`
    );
    messagesElement.querySelectorAll(".reaction-picker").forEach((element) => {
      if (element !== picker) element.classList.add("is-hidden");
    });
    picker?.classList.toggle("is-hidden");
    return;
  }

  if (reactionButton) {
    try {
      await sendReaction(reactionButton.dataset.messageId, reactionButton.dataset.reaction);
    } catch (error) {
      setError(error.message);
    }
    return;
  }

  if (deleteButton) {
    const url = replaceTrailingMessageId(
      messagesElement.dataset.deleteMessageUrlTemplate,
      deleteButton.dataset.deleteMessageId
    );
    deleteButton.disabled = true;

    try {
      const response = await fetch(url, {
        method: "DELETE",
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error("Message could not be deleted.");
      lastRenderedSignature = "";
      await refreshMessages();
    } catch (error) {
      deleteButton.disabled = false;
      setError(error.message);
    }
    return;
  }

  if (quoteButton) {
    const target = messagesElement.querySelector(
      `[data-message-id="${quoteButton.dataset.scrollToMessage}"]`
    );
    target?.scrollIntoView({ behavior: "smooth", block: "center" });
    target?.classList.add("message-highlight");
    window.setTimeout(() => target?.classList.remove("message-highlight"), 1000);
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
    setError(error.message);
  }
});

setupMobileViewport();
resizeComposerInput();
refreshMessages();
if (!window.ychatMessagePoll) {
  window.ychatMessagePoll = window.setInterval(() => {
    if (document.visibilityState === "visible") refreshMessages();
  }, 2000);
}
