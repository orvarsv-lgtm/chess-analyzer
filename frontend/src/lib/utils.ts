import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

// ─── CPL → Accuracy % conversion ───────────────────────

/**
 * Convert average centipawn loss to an accuracy percentage (legacy fallback).
 * Uses an exponential decay that maps:
 *   CPL 0 → 100%, ~10 → 90%, ~25 → 78%, ~50 → 60%, ~100 → 37%
 *
 * Prefer using backend-computed `accuracy` field when available (chess.com-style
 * win-probability-based accuracy).
 */
export function cplToAccuracy(cpl: number | null | undefined): number | null {
  if (cpl === null || cpl === undefined || cpl < 0) return null;
  return Math.round(
    Math.min(100, Math.max(0, 103.1668 * Math.exp(-0.01 * cpl) - 3.1668))
  );
}

/**
 * Get the best accuracy value available.
 * Prefers backend-computed accuracy (chess.com-style), falls back to CPL-based.
 */
export function getAccuracy(
  backendAccuracy: number | null | undefined,
  cpl: number | null | undefined
): number | null {
  if (backendAccuracy !== null && backendAccuracy !== undefined && backendAccuracy >= 0) {
    return Math.round(backendAccuracy);
  }
  return cplToAccuracy(cpl);
}

/** Color class for an accuracy percentage. */
export function accuracyColor(accuracy: number | null): string {
  if (accuracy === null) return "text-gray-500";
  if (accuracy >= 90) return "text-green-400";
  if (accuracy >= 75) return "text-green-300";
  if (accuracy >= 60) return "text-yellow-400";
  if (accuracy >= 45) return "text-orange-400";
  return "text-red-400";
}

/** Background class for accuracy percentage. */
export function accuracyBg(accuracy: number | null): string {
  if (accuracy === null) return "bg-surface-2";
  if (accuracy >= 90) return "bg-green-900/20";
  if (accuracy >= 75) return "bg-green-900/10";
  if (accuracy >= 60) return "bg-yellow-900/10";
  if (accuracy >= 45) return "bg-orange-900/10";
  return "bg-red-900/10";
}

/** Format accuracy for display, e.g. "87%" or "—" */
export function formatAccuracy(cpl: number | null | undefined, backendAccuracy?: number | null): string {
  const acc = getAccuracy(backendAccuracy ?? null, cpl);
  return acc !== null ? `${acc}%` : "—";
}

/** Move quality annotation symbol */
export function moveQualityAnnotation(quality: string | null): string {
  switch (quality) {
    case "Brilliant": return "!!";
    case "Great": return "!";
    case "Blunder": return "??";
    case "Mistake": return "?";
    case "Inaccuracy": return "?!";
    case "Missed Win": return "??";
    default: return "";
  }
}
