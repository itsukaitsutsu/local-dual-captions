(() => {
  if (globalThis.__localDualCaptionsLoaded) return;
  globalThis.__localDualCaptionsLoaded = true;
  let host, panel, japanese, english, notice, label, timer;
  let settings = { fontSize: 26, opacity: 90, position: "bottom", showJapanese: true, keepSeconds: 12 };
  let active = false;
  let lastSeek = 0;
  let dragged = false;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text) node.textContent = text;
    return node;
  }

  function build() {
    if (host?.isConnected) return;
    host = element("div");
    host.id = "local-dual-captions-overlay";
    const shadow = host.attachShadow({ mode: "closed" });
    const style = element("style");
    style.textContent = `
      :host{all:initial;position:fixed;inset:0;display:block;z-index:2147483647;pointer-events:none;color-scheme:dark;font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI","Noto Sans JP",sans-serif}
      *{box-sizing:border-box}.panel{position:absolute;left:50%;bottom:7%;transform:translateX(-50%);width:max-content;min-width:280px;max-width:min(920px,92vw);padding:13px 22px 17px;border:1px solid #ffffff22;border-radius:13px;background:rgba(14,18,27,.9);box-shadow:0 8px 40px #0005;backdrop-filter:blur(14px);text-align:center;pointer-events:auto}
      .header{display:flex;align-items:center;justify-content:space-between;gap:25px;color:#a4b4c8;font-size:9px;letter-spacing:1.2px;margin-bottom:9px;cursor:grab;touch-action:none;user-select:none}.header:active{cursor:grabbing}.left{display:flex;align-items:center;gap:7px}.light{width:5px;height:5px;background:#9de5c9;border-radius:50%;box-shadow:0 0 8px #9de5c940}.right{display:flex;align-items:center;gap:12px}.grip{letter-spacing:2px;color:#7b8a9f}.stop{border:0;background:transparent;color:#b4c2d3;font:inherit;padding:2px 3px;cursor:pointer;letter-spacing:0}.stop:hover{color:#ffbcb5}.ja,.en{margin:0;overflow-wrap:anywhere;display:-webkit-box;-webkit-box-orient:vertical;-webkit-line-clamp:3;overflow:hidden;white-space:pre-wrap;line-height:1.5;text-wrap:pretty}.ja{font-size:var(--caption-font,26px);color:#fafbfe;font-weight:500;letter-spacing:.025em}.en{font-size:calc(var(--caption-font,26px)*.88);color:#a6ead2;margin-top:5px;font-weight:450}.en.waiting{font-size:13px;color:#92a3b5}.notice{font-size:11px;line-height:1.5;color:#e3bf91;max-width:650px;margin-top:7px;letter-spacing:0}[hidden]{display:none!important}
      @media(max-width:500px){.panel{padding:10px 15px 13px;min-width:220px}.header{font-size:8px}.ja{font-size:calc(var(--caption-font)*.82)}.en{font-size:calc(var(--caption-font)*.74)}}
    `;
    panel = element("section", "panel");
    panel.setAttribute("aria-label", "Japanese and English live captions");
    const header = element("div", "header");
    const left = element("div", "left");
    left.append(element("i", "light"));
    label = element("span", "", "JA → EN  /  LOCAL");
    left.append(label);
    const right = element("div", "right");
    right.append(element("span", "grip", "⠿"));
    const stop = element("button", "stop", "✕");
    stop.title = "Stop captioning and audio capture";
    stop.setAttribute("aria-label", "Stop captions");
    stop.addEventListener("click", () => {
      // Content scripts cannot issue privileged popup commands. A dedicated,
      // tab-validated stop request is handled by the service worker.
      chrome.runtime.sendMessage({ target: "background", type: "OVERLAY_STOP" }).catch(() => {});
    });
    right.append(stop);
    header.append(left, right);
    japanese = element("p", "ja");
    japanese.lang = "ja";
    english = element("p", "en waiting", "Listening for Japanese speech…");
    english.lang = "en";
    english.setAttribute("aria-live", "polite");
    notice = element("div", "notice");
    notice.hidden = true;
    panel.append(header, japanese, english, notice);
    shadow.append(style, panel);
    attach();
    makeDraggable(header, stop);
    apply();
  }

  function attach() {
    const fullscreen = document.fullscreenElement;
    // Appending inside VIDEO/IFRAME (replaced elements) does not render an
    // overlay. Container fullscreen works; native video fullscreen may not.
    if (fullscreen && !["VIDEO", "IFRAME"].includes(fullscreen.tagName)) fullscreen.append(host);
    else document.documentElement.append(host);
    if (fullscreen && ["VIDEO", "IFRAME"].includes(fullscreen.tagName)) {
      showNotice("This player's native fullscreen may hide captions. Use theatre mode or exit fullscreen.");
    }
  }

  function apply() {
    if (!panel) return;
    panel.style.setProperty("--caption-font", `${settings.fontSize}px`);
    panel.style.background = `rgba(14,18,27,${settings.opacity / 100})`;
    japanese.hidden = !settings.showJapanese;
    if (!dragged) {
      panel.style.top = settings.position === "top" ? "7%" : "auto";
      panel.style.bottom = settings.position === "top" ? "auto" : "7%";
      panel.style.left = "50%";
      panel.style.transform = "translateX(-50%)";
    }
  }

  function showNotice(message) {
    if (!notice) return;
    notice.textContent = message;
    notice.hidden = !message;
  }

  function makeDraggable(handle, stopButton) {
    let drag;
    handle.addEventListener("pointerdown", event => {
      if (event.target === stopButton || event.button !== 0) return;
      const rect = panel.getBoundingClientRect();
      drag = { x: event.clientX - rect.left, y: event.clientY - rect.top };
      dragged = true;
      panel.style.transform = "none";
      panel.style.bottom = "auto";
      panel.style.left = `${rect.left}px`;
      panel.style.top = `${rect.top}px`;
      handle.setPointerCapture(event.pointerId);
      event.preventDefault();
    });
    handle.addEventListener("pointermove", event => {
      if (!drag) return;
      const x = Math.max(5, Math.min(innerWidth - panel.offsetWidth - 5, event.clientX - drag.x));
      const y = Math.max(5, Math.min(innerHeight - panel.offsetHeight - 5, event.clientY - drag.y));
      panel.style.left = `${x}px`;
      panel.style.top = `${y}px`;
    });
    handle.addEventListener("pointerup", () => { drag = null; });
    handle.addEventListener("lostpointercapture", () => { drag = null; });
  }

  chrome.runtime.onMessage.addListener(message => {
    if (message.type === "LDC_START") {
      active = true;
      settings = { ...settings, ...message.settings };
      dragged = false;
      build();
      panel.hidden = false;
      apply();
    } else if (message.type === "LDC_CAPTION" && active) {
      build();
      const caption = message.caption;
      japanese.textContent = caption.ja || "";
      english.textContent = caption.translating ? "Translating locally…" : (caption.en || "Translation unavailable");
      english.classList.toggle("waiting", Boolean(caption.translating));
      label.textContent = caption.translating ? "JA → EN  /  TRANSLATING" : "JA → EN  /  LOCAL";
      showNotice(caption.rtf > 1.05 ? "Processing is slower than live audio. Try Fast mode or a smaller model." : "");
      panel.hidden = false;
      clearTimeout(timer);
      timer = setTimeout(() => { if (panel) panel.hidden = true; }, settings.keepSeconds * 1000);
    } else if (message.type === "LDC_SETTINGS") {
      const moved = settings.position !== message.settings.position;
      settings = { ...settings, ...message.settings };
      if (moved) dragged = false;
      apply();
    } else if (message.type === "LDC_NOTICE" && active) {
      showNotice(message.message);
    } else if (message.type === "LDC_CLEAR" && panel) {
      japanese.textContent = "";
      english.textContent = "Listening after seek…";
      panel.hidden = false;
    } else if (message.type === "LDC_STOP") {
      active = false;
      clearTimeout(timer);
      host?.remove();
      host = panel = japanese = english = notice = label = null;
    }
  });

  document.addEventListener("fullscreenchange", () => { if (active && host) { dragged = false; attach(); apply(); } });
  document.addEventListener("seeking", () => {
    if (active && Date.now() - lastSeek > 500) {
      lastSeek = Date.now();
      chrome.runtime.sendMessage({ target: "background", type: "MEDIA_SEEK" }).catch(() => {});
    }
  }, true);
})();
