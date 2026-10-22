import { loadSettings, runnerStatus, sanitize } from "./shared.js";

const $ = id => document.getElementById(id);
let settings = await loadSettings();
let active = false;
let busy = false;
let checked = false;
const ids = ["token", "port", "profile", "vadMode", "fontSize", "opacity", "position", "showJapanese"];

function getForm() {
  return sanitize({ ...settings,
    ...Object.fromEntries(ids.map(id => [id, id === "showJapanese" ? $(id).value === "true" : $(id).value])),
  });
}

function form() {
  for (const id of ids) $(id).value = String(settings[id]);
  updatePreview();
  if (settings.token) $("pairing").open = false;
}

function updatePreview() {
  const value = getForm();
  $("fontValue").value = `${value.fontSize} px`;
  $("opacityValue").value = `${value.opacity}%`;
  $("sampleJa").hidden = !value.showJapanese;
  $("sampleJa").style.fontSize = `${Math.round(value.fontSize * .62)}px`;
  $("sampleEn").style.fontSize = `${Math.round(value.fontSize * .5)}px`;
}

async function send(type, extra = {}) {
  const response = await chrome.runtime.sendMessage({ target: "background", type, ...extra });
  if (!response?.ok) throw new Error(response?.error || "The extension did not respond. Reload it at chrome://extensions.");
  return response;
}

function showError(message = "") {
  $("error").textContent = message;
  $("error").hidden = !message;
}

function setBusy(value) {
  busy = value;
  $("start").disabled = value;
  $("check").disabled = value;
}

function render(state = {}) {
  active = Boolean(state.active);
  $("start").classList.toggle("stopping", active);
  $("startLabel").textContent = active ? "Stop captions" : "Caption this tab";
  $("startIcon").textContent = active ? "■" : "▶";
  $("captureInfo").textContent = active ? "Capturing tab audio · original playback stays on" : "Captures this tab's audio only, not your microphone.";
  if (active) {
    checked = true;
    $("statusDot").className = "dot good";
    $("connectionLabel").textContent = "Captioning locally";
    $("connectionDetail").textContent = state.message || "Listening for Japanese audio…";
    $("backend").textContent = state.backend || "local";
  } else if (state.phase === "error") {
    $("statusDot").className = "dot bad";
    $("connectionLabel").textContent = "Capture stopped";
    $("connectionDetail").textContent = state.message || "Check your runner and retry.";
  } else if (state.phase === "idle") {
    $("statusDot").className = checked ? "dot good" : "dot";
    $("connectionLabel").textContent = checked ? "Local runner ready" : "Connect your local runner";
    $("connectionDetail").textContent = state.message || "Capture is off. No tab audio is being sent.";
  }
  if (state.warning && active) showError(state.warning);
  const caption = state.caption;
  $("metrics").hidden = !active || !caption || caption.translating;
  if (caption && !caption.translating) {
    $("latency").textContent = `Chunk-tail lag ${(caption.lagMs / 1000).toFixed(1)} s`;
    $("rtf").textContent = `RTF ${caption.rtf?.toFixed(2) || "—"}`;
  }
}

async function save() {
  settings = getForm();
  await send("SETTINGS", { settings });
}

async function check() {
  if (busy) return;
  setBusy(true);
  showError();
  try {
    await save();
    const result = await runnerStatus(settings);
    checked = true;
    if (!active) {
      $("statusDot").className = "dot good";
      $("connectionLabel").textContent = "Local runner ready";
      $("backend").textContent = result.backend;
      $("connectionDetail").textContent = "Requested ASR backend shown above · translation runs on CPU.";
    }
    $("pairing").open = false;
  } catch (error) {
    checked = false;
    if (!active) {
      $("statusDot").className = "dot bad";
      $("connectionLabel").textContent = "Runner not connected";
      $("connectionDetail").textContent = "Start the local runner, then check again.";
    }
    showError(error.message);
    if (!settings.token) $("pairing").open = true;
  } finally { setBusy(false); }
}

for (const id of ids) {
  $(id).addEventListener("input", updatePreview);
  $(id).addEventListener("change", () => {
    if (["token", "port"].includes(id)) checked = false;
    save().catch(error => showError(error.message));
  });
}
$("check").addEventListener("click", check);
$("start").addEventListener("click", async () => {
  if (busy) return;
  setBusy(true);
  showError();
  try {
    await save();
    if (active) await send("STOP");
    else {
      const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
      if (!tab?.id) throw new Error("No active media tab found.");
      await send("START", { tabId: tab.id });
    }
    render((await send("GET_STATE")).state);
  } catch (error) { showError(error.message); }
  finally { setBusy(false); }
});

chrome.runtime.onMessage.addListener(message => {
  if (message.target === "popup" && message.type === "STATE") render(message.state);
});

form();
try { render((await send("GET_STATE")).state); }
catch (error) { showError(error.message); }
if (settings.token && !active && !checked) check();
