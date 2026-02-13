"use client";

import { Howl } from "howler";

// ─── Sound Effects ─────────────────────────────────────
// Uses Web Audio API via Howler.js for chess training sounds.
// All sounds are generated programmatically via Tone.js-style synthesis
// to avoid external audio file dependencies.

let soundEnabled = true;

export function toggleSound(on?: boolean) {
  soundEnabled = on ?? !soundEnabled;
  return soundEnabled;
}

export function isSoundEnabled() {
  return soundEnabled;
}

// Lazy-init sounds to avoid SSR issues
let _moveSound: Howl | null = null;
let _correctSound: Howl | null = null;
let _incorrectSound: Howl | null = null;
let _streakSound: Howl | null = null;
let _warmupCompleteSound: Howl | null = null;

// Use simple data URI beeps (sine wave tone)
function createToneDataUri(frequency: number, duration: number, volume = 0.3): string {
  // Generate a simple WAV sine wave
  const sampleRate = 44100;
  const numSamples = Math.floor(sampleRate * duration);
  const numChannels = 1;
  const bytesPerSample = 2;

  const buffer = new ArrayBuffer(44 + numSamples * numChannels * bytesPerSample);
  const view = new DataView(buffer);

  // WAV header
  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + numSamples * numChannels * bytesPerSample, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true); // chunk size
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
  view.setUint16(32, numChannels * bytesPerSample, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeString(36, "data");
  view.setUint32(40, numSamples * numChannels * bytesPerSample, true);

  // Write sine wave
  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate;
    // Fade out over last 20% to avoid clicks
    const fadeStart = duration * 0.8;
    const envelope = t > fadeStart ? 1 - (t - fadeStart) / (duration * 0.2) : 1;
    const sample = Math.sin(2 * Math.PI * frequency * t) * volume * envelope;
    const intSample = Math.max(-32768, Math.min(32767, Math.floor(sample * 32767)));
    view.setInt16(offset, intSample, true);
    offset += 2;
  }

  // Convert to base64
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return "data:audio/wav;base64," + btoa(binary);
}

function createChordDataUri(frequencies: number[], duration: number, volume = 0.2): string {
  const sampleRate = 44100;
  const numSamples = Math.floor(sampleRate * duration);
  const numChannels = 1;
  const bytesPerSample = 2;

  const buffer = new ArrayBuffer(44 + numSamples * numChannels * bytesPerSample);
  const view = new DataView(buffer);

  const writeString = (offset: number, str: string) => {
    for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i));
  };
  writeString(0, "RIFF");
  view.setUint32(4, 36 + numSamples * numChannels * bytesPerSample, true);
  writeString(8, "WAVE");
  writeString(12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, numChannels, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * numChannels * bytesPerSample, true);
  view.setUint16(32, numChannels * bytesPerSample, true);
  view.setUint16(34, bytesPerSample * 8, true);
  writeString(36, "data");
  view.setUint32(40, numSamples * numChannels * bytesPerSample, true);

  let offset = 44;
  for (let i = 0; i < numSamples; i++) {
    const t = i / sampleRate;
    const fadeStart = duration * 0.7;
    const envelope = t > fadeStart ? 1 - (t - fadeStart) / (duration * 0.3) : 1;
    let sample = 0;
    for (const freq of frequencies) {
      sample += Math.sin(2 * Math.PI * freq * t);
    }
    sample = (sample / frequencies.length) * volume * envelope;
    const intSample = Math.max(-32768, Math.min(32767, Math.floor(sample * 32767)));
    view.setInt16(offset, intSample, true);
    offset += 2;
  }

  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) binary += String.fromCharCode(bytes[i]);
  return "data:audio/wav;base64," + btoa(binary);
}

function getMoveSound() {
  if (!_moveSound) {
    _moveSound = new Howl({ src: [createToneDataUri(440, 0.08, 0.15)], volume: 0.5 });
  }
  return _moveSound;
}

function getCorrectSound() {
  if (!_correctSound) {
    // Ascending two-note (C5 → E5)
    _correctSound = new Howl({ src: [createChordDataUri([523, 659], 0.25, 0.25)], volume: 0.6 });
  }
  return _correctSound;
}

function getIncorrectSound() {
  if (!_incorrectSound) {
    // Low buzz (E2)
    _incorrectSound = new Howl({ src: [createToneDataUri(82, 0.3, 0.2)], volume: 0.5 });
  }
  return _incorrectSound;
}

function getStreakSound() {
  if (!_streakSound) {
    // Triumphant chord (C major)
    _streakSound = new Howl({ src: [createChordDataUri([523, 659, 784], 0.4, 0.3)], volume: 0.7 });
  }
  return _streakSound;
}

function getWarmupCompleteSound() {
  if (!_warmupCompleteSound) {
    // Fanfare (C major arpeggio-ish)
    _warmupCompleteSound = new Howl({ src: [createChordDataUri([523, 659, 784, 1047], 0.6, 0.25)], volume: 0.7 });
  }
  return _warmupCompleteSound;
}

// ─── Public API ────────────────────────────────────────

export function playMove() {
  if (!soundEnabled) return;
  try { getMoveSound().play(); } catch {}
}

export function playCorrect() {
  if (!soundEnabled) return;
  try { getCorrectSound().play(); } catch {}
}

export function playIncorrect() {
  if (!soundEnabled) return;
  try { getIncorrectSound().play(); } catch {}
}

export function playStreak() {
  if (!soundEnabled) return;
  try { getStreakSound().play(); } catch {}
}

export function playWarmupComplete() {
  if (!soundEnabled) return;
  try { getWarmupCompleteSound().play(); } catch {}
}
