let stream, playbackContext, captureContext, worklet, socket, heartbeat;
let intentionalStop = false;
let session = 0;

function notify(event) {
  return chrome.runtime.sendMessage({ target: "background", type: "EVENT", event }).catch(() => {});
}

async function cleanup() {
  if (heartbeat) clearInterval(heartbeat);
  heartbeat = null;
  if (worklet) { worklet.port.onmessage = null; worklet.disconnect(); }
  worklet = null;
  if (stream) for (const track of stream.getTracks()) track.stop();
  stream = null;
  const contexts = [playbackContext, captureContext];
  playbackContext = captureContext = null;
  for (const context of contexts) if (context && context.state !== "closed") await context.close().catch(() => {});
  if (socket) {
    socket.onclose = socket.onerror = socket.onmessage = null;
    socket.close();
  }
  socket = null;
}

async function stop() {
  intentionalStop = true;
  session++;
  if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "stop" }));
  await cleanup();
}

async function fail(message, id) {
  if (id !== session || intentionalStop) return;
  intentionalStop = true;
  session++;
  await cleanup();
  await notify({ type: "error", message });
}

async function connect(settings, id) {
  return new Promise((resolve, reject) => {
    const ws = new WebSocket(`ws://127.0.0.1:${settings.port}/live`);
    socket = ws;
    let accepted = false;
    const timer = setTimeout(() => {
      reject(new Error("Local connection timed out. Check the pairing key and runner terminal."));
      ws.close();
    }, 5000);
    ws.onopen = () => ws.send(JSON.stringify({ type: "hello", token: settings.token,
      profile: settings.profile, vadMode: settings.vadMode }));
    ws.onmessage = ({ data }) => {
      let event;
      try { event = JSON.parse(data); } catch { return; }
      if (event.type === "ready") { accepted = true; clearTimeout(timer); resolve(event); }
      else if (event.type === "error" && !accepted) { clearTimeout(timer); reject(new Error(event.message)); }
      else if (["caption", "warning", "reset"].includes(event.type)) notify(event);
      else if (event.type === "error") fail(event.message, id);
    };
    ws.onerror = () => {
      if (!accepted) { clearTimeout(timer); reject(new Error("Could not connect to the local caption runner.")); }
    };
    ws.onclose = event => {
      clearTimeout(timer);
      if (!accepted) reject(new Error(event.code === 1008 ? "Pairing was rejected. Check your pairing key." : "The local runner closed the connection."));
      else fail("Local runner disconnected. Audio capture has stopped; open Start.cmd and click Start again.", id);
    };
  });
}

async function start(streamId, settings) {
  await stop();
  intentionalStop = false;
  const id = ++session;
  try {
    await connect(settings, id);
    stream = await navigator.mediaDevices.getUserMedia({
      audio: { mandatory: { chromeMediaSource: "tab", chromeMediaSourceId: streamId } }, video: false,
    });
    if (id !== session) throw new Error("Capture was stopped.");
    // tabCapture normally suppresses the tab's own speaker output. This graph
    // restores it at the native rate, rather than playing low-bandwidth 16 kHz audio.
    playbackContext = new AudioContext({ latencyHint: "interactive" });
    playbackContext.createMediaStreamSource(stream).connect(playbackContext.destination);
    await playbackContext.resume();

    captureContext = new AudioContext({ sampleRate: 16000, latencyHint: "interactive" });
    if (captureContext.sampleRate !== 16000) throw new Error("This Chrome audio device could not create a 16 kHz capture context.");
    await captureContext.audioWorklet.addModule(chrome.runtime.getURL("pcm-worklet.js"));
    worklet = new AudioWorkletNode(captureContext, "pcm-capture", {
      numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
      channelCount: 1, channelCountMode: "explicit",
    });
    captureContext.createMediaStreamSource(stream).connect(worklet);
    worklet.connect(captureContext.destination); // outputs zeros; original playback uses the other graph
    worklet.port.onmessage = ({ data }) => {
      if (id !== session || socket?.readyState !== WebSocket.OPEN) return;
      if (data.type === "pcm") {
        if (socket.bufferedAmount > 256 * 1024) {
          fail("The local audio connection is backed up. Capture stopped instead of accumulating unlimited delay.", id);
          return;
        }
        socket.send(data.data);
      }
    };
    for (const track of stream.getTracks()) track.onended = () => fail("Chrome ended tab-audio capture. Click Start to reconnect.", id);
    await captureContext.resume();
    heartbeat = setInterval(() => {
      if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ping" }));
    }, 15000);
    return { ok: true };
  } catch (error) {
    intentionalStop = true;
    session++;
    await cleanup();
    throw error;
  }
}

chrome.runtime.onMessage.addListener((message, sender, respond) => {
  if (message.target !== "offscreen") return false;
  let promise;
  if (message.type === "START") promise = start(message.streamId, message.settings);
  else if (message.type === "STOP") promise = stop().then(() => ({ ok: true }));
  else if (message.type === "RESET") {
    if (socket?.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "reset" }));
    promise = Promise.resolve({ ok: true });
  } else return false;
  promise.then(respond).catch(error => respond({ ok: false, error: error.message }));
  return true;
});
