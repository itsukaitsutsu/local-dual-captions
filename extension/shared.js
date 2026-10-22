export const DEFAULTS = Object.freeze({
  token: "", port: 8765, profile: "balanced", vadMode: 2,
  fontSize: 26, opacity: 90, position: "bottom", showJapanese: true, keepSeconds: 12,
});

export function sanitize(input = {}) {
  const value = { ...DEFAULTS, ...input };
  const integer = (x, min, max, fallback) => Number.isFinite(Number(x))
    ? Math.min(max, Math.max(min, Math.round(Number(x)))) : fallback;
  return {
    token: String(value.token).trim().slice(0, 256),
    port: integer(value.port, 1024, 65535, 8765),
    profile: ["fast", "balanced", "context"].includes(value.profile) ? value.profile : "balanced",
    vadMode: [0, 1, 2, 3].includes(Number(value.vadMode)) ? Number(value.vadMode) : 2,
    fontSize: integer(value.fontSize, 18, 44, 26),
    opacity: integer(value.opacity, 55, 100, 90),
    position: value.position === "top" ? "top" : "bottom",
    showJapanese: Boolean(value.showJapanese),
    keepSeconds: integer(value.keepSeconds, 4, 30, 12),
  };
}

export async function loadSettings() {
  const { settings } = await chrome.storage.local.get("settings");
  return sanitize(settings);
}

export async function saveSettings(settings) {
  const safe = sanitize(settings);
  await chrome.storage.local.set({ settings: safe });
  return safe;
}

export function publicSettings(settings) {
  const { token, port, ...appearance } = sanitize(settings);
  return appearance;
}

export async function runnerStatus(settings) {
  if (settings.token.length < 32) throw new Error("Paste the pairing key from your local runner first.");
  let response;
  try {
    response = await fetch(`http://127.0.0.1:${settings.port}/status`, {
      headers: { "X-Caption-Key": settings.token }, signal: AbortSignal.timeout(5000),
      cache: "no-store", credentials: "omit",
    });
  } catch {
    throw new Error("Cannot reach the local runner. Open Start.cmd on this computer, then try again.");
  }
  if (response.status === 401) throw new Error("Pairing key does not match. Copy it again from data/pairing-key.txt.");
  if (!response.ok) throw new Error(`Local runner returned HTTP ${response.status}.`);
  const status = await response.json();
  if (!status.ready) throw new Error("The Whisper engine is still loading or has stopped. Check the runner terminal.");
  return status;
}
