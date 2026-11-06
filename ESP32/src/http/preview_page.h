#pragma once

// Served from flash. All recent evidence is held by the browser, not the ESP32.
static const char PREVIEW_PAGE[] PROGMEM = R"HTML(<!doctype html>
<html lang="en"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>COMP4990 Camera Preview</title>
<style>
body{font:16px system-ui;background:#101820;color:#edf4fa;max-width:900px;margin:40px auto;padding:0 20px}
h1{font-size:28px}p{line-height:1.6;color:#b9cbd8}button{font:inherit;padding:10px 18px;margin:4px;border:0;border-radius:6px;cursor:pointer}
button:disabled{opacity:.45;cursor:default}img{display:block;width:100%;max-width:640px;aspect-ratio:4/3;object-fit:contain;background:#060b10;border-radius:10px;margin:20px 0}
#status{color:#9ee1ce}a{color:#9dcaff}
</style>
<h1>ESP32 camera preview</h1>
<p>COMP4990 · JPEG snapshot preview · 640 × 480</p>
<button id="start">Start preview</button><button id="stop" disabled>Stop</button>
<button id="export" disabled>Export recent frames</button><button id="clear">Clear buffer</button>
<p id="status" role="status">Ready. Start to connect to the camera.</p>
<img id="preview" alt="Camera preview appears here when started">
<p id="stats" aria-live="polite">0 frames buffered</p>
<p>Preview requests target up to 5 frames/second. Evidence is sampled at most once
per second and expires after 30 seconds, including while stopped. Limits: 30 frames
or 6 MiB. Brief events may be missed. Background tabs may sample more slowly.</p>
<p>Export saves JPEGs and timestamps in one JSON file. It contains camera images;
buffer contents otherwise stay in this browser tab and disappear on reload.
Laptop receive times are not exact camera exposure times.</p>
<a href="/api/v1/status">Device status</a> · <a href="/api/v1/capture">Single JPEG</a>
<script>
'use strict';
const el = id => document.getElementById(id);
let frames = [], running = false, generation = 0, timer, controller, previewUrl;
let lastSample = -Infinity, exporting = false;
const MAX_BYTES = 6 * 1024 * 1024;
function prune(now = performance.now()) {
  frames = frames.filter(frame => now - frame.monotonicMs < 30000);
  let bytes = frames.reduce((sum, frame) => sum + frame.blob.size, 0);
  while (frames.length > 30 || bytes > MAX_BYTES) bytes -= frames.shift().blob.size;
  const span = frames.length > 1 ? (frames.at(-1).monotonicMs - frames[0].monotonicMs) / 1000 : 0;
  el('stats').textContent = `${frames.length} frames · ${span.toFixed(1)} seconds between samples · ${(bytes / 1048576).toFixed(2)} MiB`;
  el('export').disabled = exporting || !frames.length;
}
function stop() {
  running = false; generation++; clearTimeout(timer); controller?.abort();
  el('start').disabled = false; el('stop').disabled = true;
  if (previewUrl) URL.revokeObjectURL(previewUrl);
  previewUrl = null; el('preview').removeAttribute('src');
  el('status').textContent = 'Stopped. Buffered evidence continues to expire.';
  prune();
}
async function capture(token) {
  if (!running || token !== generation) return;
  const started = performance.now(), requestedAt = new Date().toISOString();
  const request = new AbortController(); controller = request;
  const timeout = setTimeout(() => request.abort(), 5000);
  try {
    const response = await fetch('/api/v1/capture', {cache:'no-store', signal:request.signal});
    if (!response.ok) throw new Error(`Camera returned HTTP ${response.status}`);
    if (!(response.headers.get('Content-Type') || '').startsWith('image/jpeg')) throw new Error('Expected a JPEG');
    const blob = await response.blob();
    if (!blob.size || blob.size > 2 * 1024 * 1024) throw new Error('Invalid frame size');
    if (!running || token !== generation) return;
    const now = performance.now(), url = URL.createObjectURL(blob);
    el('preview').src = url;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = url;
    if (now - lastSample >= 1000) {
      frames.push({blob, monotonicMs:now, requestedAt, receivedAt:new Date().toISOString(),
        deviceId:response.headers.get('X-Device-Id'), captureUptimeUs:response.headers.get('X-Capture-Uptime-Us')});
      lastSample = now;
    }
    prune(now);
    el('status').textContent = 'Live · collecting recent evidence';
  } catch (error) {
    if (running && token === generation) {
      el('status').textContent = `Camera unavailable: ${error.message}. Retrying…`;
      if (previewUrl) URL.revokeObjectURL(previewUrl);
      previewUrl = null; el('preview').removeAttribute('src');
      prune();
    }
  } finally {
    clearTimeout(timeout);
    if (running && token === generation) timer = setTimeout(() => capture(token), Math.max(200 - (performance.now() - started), 50));
  }
}
el('start').onclick = () => {
  if (running) return;
  running = true; el('start').disabled = true; el('stop').disabled = false;
  el('status').textContent = 'Connecting…'; capture(++generation);
};
el('stop').onclick = stop;
el('clear').onclick = () => { frames = []; lastSample = -Infinity; prune(); };
function asDataUrl(blob) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader(); reader.onload = () => resolve(reader.result);
    reader.onerror = () => reject(new Error('Could not encode frame')); reader.readAsDataURL(blob);
  });
}
el('export').onclick = async () => {
  prune(); const snapshot = frames.slice(); if (!snapshot.length || exporting) return;
  exporting = true; prune();
  try {
    const evidence = await Promise.all(snapshot.map(async ({blob, monotonicMs, ...metadata}) =>
      ({...metadata, jpegDataUrl:await asDataUrl(blob)})));
    const payload = {sourceType:'esp32', evidenceType:'sampled_frames', frameCount:evidence.length,
      timeWindow:{start:evidence[0].requestedAt, end:evidence.at(-1).receivedAt,
        clock:'Laptop UTC request/receive bounds; device capture uptime is separate'},
      limitations:'Sparse samples can miss events. Device uptime resets on reboot.', frames:evidence};
    const url = URL.createObjectURL(new Blob([JSON.stringify(payload)], {type:'application/json'}));
    const link = document.createElement('a'); link.href = url; link.download = `esp32-evidence-${Date.now()}.json`;
    link.click(); setTimeout(() => URL.revokeObjectURL(url), 1000);
  } catch (error) { el('status').textContent = `Export failed: ${error.message}`; }
  finally { exporting = false; prune(); }
};
setInterval(prune, 500);
window.addEventListener('pagehide', stop);
</script></html>)HTML";
