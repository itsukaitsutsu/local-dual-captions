import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import vm from "node:vm";
import { sanitize, publicSettings } from "../extension/shared.js";

test("settings are bounded and secrets never reach the overlay", () => {
  const settings = sanitize({ fontSize: 999, port: -1, profile: "remote", token: " private " });
  assert.equal(settings.fontSize, 44);
  assert.equal(settings.port, 1024);
  assert.equal(settings.profile, "balanced");
  assert.equal(settings.token, "private");
  assert.equal("token" in publicSettings(settings), false);
  assert.equal("port" in publicSettings(settings), false);
});

test("AudioWorklet outputs 100 ms little-endian PCM16 and never audible audio", () => {
  let Processor;
  const messages = [];
  const sandbox = {
    AudioWorkletProcessor: class { constructor() { this.port = { postMessage: x => messages.push(x) }; } },
    registerProcessor: (name, type) => { assert.equal(name, "pcm-capture"); Processor = type; },
    ArrayBuffer, DataView, Math,
  };
  vm.runInNewContext(fs.readFileSync(new URL("../extension/pcm-worklet.js", import.meta.url), "utf8"), sandbox);
  const node = new Processor();
  const samples = new Float32Array(128).fill(.5);
  const output = new Float32Array(128).fill(1);
  for (let i = 0; i < 13; i++) node.process([[samples]], [[output]]);
  const pcm = messages.find(x => x.type === "pcm");
  assert.equal(pcm.data.byteLength, 3200);
  assert.equal(new DataView(pcm.data).getInt16(0, true), 16383);
  assert.equal(output.every(x => x === 0), true);
});
