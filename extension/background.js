import { loadSettings, publicSettings, runnerStatus, sanitize, saveSettings } from "./shared.js";

const POPUP = chrome.runtime.getURL("popup.html");
const OFFSCREEN = chrome.runtime.getURL("offscreen.html");
let creating;
let operation = Promise.resolve();

chrome.storage.local.setAccessLevel({ accessLevel: "TRUSTED_CONTEXTS" }).catch(() => {});

async function state() {
  return (await chrome.storage.session.get("state")).state || { active: false, phase: "idle", tabId: null };
}

async function setState(patch) {
  const next = { ...await state(), ...patch };
  await chrome.storage.session.set({ state: next });
  const badge = next.active ? "ON" : (next.phase === "error" ? "!" : "");
  await chrome.action.setBadgeText({ text: badge });
  await chrome.action.setBadgeBackgroundColor({ color: next.phase === "error" ? "#b55e55" : "#246d5d" });
  chrome.runtime.sendMessage({ target: "popup", type: "STATE", state: next }).catch(() => {});
  return next;
}

async function tellTab(tabId, message) {
  if (Number.isInteger(tabId)) await chrome.tabs.sendMessage(tabId, message).catch(() => {});
}

async function ensureOffscreen() {
  if ((await chrome.runtime.getContexts({ contextTypes: ["OFFSCREEN_DOCUMENT"], documentUrls: [OFFSCREEN] })).length) return;
  if (!creating) {
    creating = chrome.offscreen.createDocument({
      url: "offscreen.html", reasons: ["USER_MEDIA"],
      justification: "Capture tab audio and stream PCM only to the user's local caption engine.",
    }).finally(() => { creating = null; });
  }
  await creating;
}

async function stop(reason = "", isError = false) {
  const old = await state();
  await setState({ active: false, phase: isError ? "error" : "idle", message: reason, warning: null, caption: null });
  await chrome.runtime.sendMessage({ target: "offscreen", type: "STOP" }).catch(() => {});
  await tellTab(old.tabId, { type: "LDC_STOP" });
  await setState({ tabId: null });
  return { ok: true };
}

async function start(tabId) {
  const current = await state();
  if (current.active) throw new Error("A tab is already being captioned. Stop it before starting another.");
  const settings = await loadSettings();
  const status = await runnerStatus(settings);
  if (status.busy) throw new Error("The local runner already has an active connection. Stop the other session first.");
  const tab = await chrome.tabs.get(tabId);
  if (!/^https?:\/\//.test(tab.url || "")) {
    throw new Error("Open an ordinary HTTP/HTTPS media webpage first. Chrome settings, the Web Store, and PDF viewer pages cannot host this overlay.");
  }
  await chrome.scripting.executeScript({ target: { tabId }, files: ["content.js"] });
  await ensureOffscreen();
  await setState({ active: false, phase: "starting", tabId, message: "Connecting locally…", warning: null, caption: null });
  try {
    const streamId = await chrome.tabCapture.getMediaStreamId({ targetTabId: tabId });
    await tellTab(tabId, { type: "LDC_START", settings: publicSettings(settings) });
    const result = await chrome.runtime.sendMessage({ target: "offscreen", type: "START", streamId, settings });
    if (!result?.ok) throw new Error(result?.error || "Could not start audio capture.");
    const updated = await state();
    if (updated.phase === "error") throw new Error(updated.message || "Capture failed.");
    await setState({ active: true, phase: "listening", tabId, backend: status.backend,
                     message: "Listening for Japanese audio", caption: null, startedAt: Date.now() });
    return { ok: true };
  } catch (error) {
    await stop(error.message, true);
    throw error;
  }
}

async function route(message, sender) {
  if (message.target !== "background" || sender.id !== chrome.runtime.id) return;
  if (sender.url === OFFSCREEN && message.type === "EVENT") {
    const event = message.event;
    const current = await state();
    if (event.type === "caption") {
      if (!current.active) return { ok: true };
      const next = await setState({ caption: event, phase: "listening", message: "Captions processed on this computer" });
      await tellTab(next.tabId, { type: "LDC_CAPTION", caption: event });
    } else if (event.type === "warning") {
      await setState({ message: event.message, warning: event.message });
      await tellTab(current.tabId, { type: "LDC_NOTICE", message: event.message });
    } else if (event.type === "error") {
      // Do not send a blocking STOP back to the offscreen document while its
      // own cleanup is waiting for this notification to complete.
      await setState({ active: false, phase: "error", message: event.message, caption: null });
      await tellTab(current.tabId, { type: "LDC_STOP" });
      await setState({ tabId: null });
    } else if (event.type === "reset") {
      await setState({ caption: null });
      await tellTab(current.tabId, { type: "LDC_CLEAR" });
    }
    return { ok: true };
  }
  if (message.type === "OVERLAY_STOP" && sender.tab) {
    const current = await state();
    if (current.active && current.tabId === sender.tab.id) {
      operation = operation.catch(() => {}).then(() => stop());
      return operation;
    }
    return { ok: true };
  }
  if (message.type === "MEDIA_SEEK" && sender.tab) {
    const current = await state();
    if (current.active && current.tabId === sender.tab.id) {
      await chrome.runtime.sendMessage({ target: "offscreen", type: "RESET" }).catch(() => {});
    }
    return { ok: true };
  }
  if (sender.url !== POPUP) return;
  if (message.type === "GET_STATE") return { ok: true, state: await state() };
  if (message.type === "START") {
    operation = operation.catch(() => {}).then(() => start(message.tabId));
    return operation;
  }
  if (message.type === "STOP") {
    operation = operation.catch(() => {}).then(() => stop());
    return operation;
  }
  if (message.type === "SETTINGS") {
    const settings = await saveSettings(sanitize(message.settings));
    const current = await state();
    await tellTab(current.tabId, { type: "LDC_SETTINGS", settings: publicSettings(settings) });
    return { ok: true };
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target !== "background") return false;
  route(message, sender).then(result => respond(result || { ok: true }))
    .catch(error => respond({ ok: false, error: error.message || "Unexpected extension error." }));
  return true;
});

chrome.tabs.onRemoved.addListener(async tabId => {
  if ((await state()).tabId === tabId) await stop("Captured tab was closed.");
});
chrome.tabs.onUpdated.addListener(async (tabId, change) => {
  const current = await state();
  if (current.active && current.tabId === tabId && change.status === "loading") {
    await stop("Page navigated. Click Start again on the new page.");
  }
});

// A browser restart destroys capture streams. Session storage also clears;
// there is intentionally no automatic recording restart.
chrome.runtime.onStartup.addListener(() => setState({ active: false, phase: "idle", tabId: null, caption: null }));
