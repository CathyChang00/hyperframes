/**
 * Velocity curve analyzer — matches gesture recording segments to GSAP ease presets.
 *
 * Pure utility: no React, no DOM, no Studio imports.
 */

const DEFAULT_EASE = "power2.inOut";
const SAMPLE_COUNT = 21; // 0, 0.05, 0.10, ..., 1.0

function buildReferenceCurve(fn: (t: number) => number): number[] {
  const curve: number[] = [];
  for (let i = 0; i < SAMPLE_COUNT; i++) {
    curve.push(fn(i / (SAMPLE_COUNT - 1)));
  }
  return curve;
}

export const EASE_REFERENCE_CURVES: Record<string, number[]> = {
  linear: buildReferenceCurve((t) => t),

  "power1.out": buildReferenceCurve((t) => 1 - (1 - t) ** 2),

  "power2.out": buildReferenceCurve((t) => 1 - (1 - t) ** 3),

  "power3.out": buildReferenceCurve((t) => 1 - (1 - t) ** 4),

  "power2.in": buildReferenceCurve((t) => t ** 3),

  "power2.inOut": buildReferenceCurve((t) => (t < 0.5 ? 4 * t ** 3 : 1 - (-2 * t + 2) ** 3 / 2)),

  "power3.inOut": buildReferenceCurve((t) => (t < 0.5 ? 8 * t ** 4 : 1 - (-2 * t + 2) ** 4 / 2)),

  "back.out(1.7)": buildReferenceCurve((t) => {
    const c1 = 1.7;
    const c3 = c1 + 1;
    return 1 + c3 * (t - 1) ** 3 + c1 * (t - 1) ** 2;
  }),

  "expo.out": buildReferenceCurve((t) => (t === 1 ? 1 : 1 - 2 ** (-10 * t))),
};

/**
 * Linearly interpolate between two values.
 */
function lerp(a: number, b: number, frac: number): number {
  return a + (b - a) * frac;
}

/**
 * Resample an arbitrary set of (normalized) time/value pairs to SAMPLE_COUNT
 * evenly-spaced points via linear interpolation.
 */
function resampleToGrid(normalized: Array<{ t: number; v: number }>): number[] {
  const result: number[] = [];

  for (let i = 0; i < SAMPLE_COUNT; i++) {
    const target = i / (SAMPLE_COUNT - 1);

    // Find the two surrounding samples
    let lo = 0;
    let hi = normalized.length - 1;
    for (let j = 0; j < normalized.length - 1; j++) {
      if (normalized[j].t <= target && normalized[j + 1].t >= target) {
        lo = j;
        hi = j + 1;
        break;
      }
    }

    const tLo = normalized[lo].t;
    const tHi = normalized[hi].t;
    const span = tHi - tLo;
    const frac = span === 0 ? 0 : (target - tLo) / span;
    result.push(lerp(normalized[lo].v, normalized[hi].v, frac));
  }

  return result;
}

/**
 * Sum of squared differences between two same-length arrays.
 */
function ssd(a: number[], b: number[]): number {
  let sum = 0;
  for (let i = 0; i < a.length; i++) {
    const d = a[i] - b[i];
    sum += d * d;
  }
  return sum;
}

/**
 * Infer the best-matching GSAP ease name for a segment of raw gesture samples.
 *
 * @param rawSamples - Time/value pairs from the gesture recording
 * @param startTime - Segment start (inclusive)
 * @param endTime - Segment end (inclusive)
 * @returns GSAP ease name (e.g. "power2.out")
 */
export function inferSegmentEase(
  rawSamples: Array<{ time: number; value: number }>,
  startTime: number,
  endTime: number,
): string {
  const segment = rawSamples.filter((s) => s.time >= startTime && s.time <= endTime);

  if (segment.length < 3) return DEFAULT_EASE;

  const tMin = segment[0].time;
  const tMax = segment[segment.length - 1].time;
  const tRange = tMax - tMin;

  const vMin = Math.min(...segment.map((s) => s.value));
  const vMax = Math.max(...segment.map((s) => s.value));
  const vRange = vMax - vMin;

  // Degenerate segment — no meaningful motion
  if (tRange === 0 || vRange === 0) return DEFAULT_EASE;

  // Determine direction: if value decreases over time, flip the progress curve
  const increasing = segment[segment.length - 1].value >= segment[0].value;

  const normalized = segment.map((s) => ({
    t: (s.time - tMin) / tRange,
    v: increasing ? (s.value - vMin) / vRange : 1 - (s.value - vMin) / vRange,
  }));

  const resampled = resampleToGrid(normalized);

  let bestEase = DEFAULT_EASE;
  let bestScore = Infinity;

  for (const [name, ref] of Object.entries(EASE_REFERENCE_CURVES)) {
    const score = ssd(resampled, ref);
    if (score < bestScore) {
      bestScore = score;
      bestEase = name;
    }
  }

  return bestEase;
}

/**
 * Infer eases for all segments between consecutive simplified percentages.
 *
 * @param rawSamples - Time/properties pairs from the gesture recording
 * @param simplifiedPercentages - Sorted array of keyframe percentages (0-100)
 * @param totalDuration - Total gesture duration in the same unit as rawSamples[].time
 * @returns Map of percentage → ease name (ease applies to the segment ENDING at that percentage)
 */
export function inferAllEases(
  rawSamples: Array<{ time: number; properties: Record<string, number> }>,
  simplifiedPercentages: number[],
  totalDuration: number,
): Map<number, string> {
  const result = new Map<number, string>();

  if (simplifiedPercentages.length < 2) return result;

  for (let i = 1; i < simplifiedPercentages.length; i++) {
    const pctStart = simplifiedPercentages[i - 1];
    const pctEnd = simplifiedPercentages[i];

    const startTime = (pctStart / 100) * totalDuration;
    const endTime = (pctEnd / 100) * totalDuration;

    // Find the primary moving property (largest absolute delta in this segment)
    const segmentSamples = rawSamples.filter((s) => s.time >= startTime && s.time <= endTime);

    if (segmentSamples.length < 2) {
      result.set(pctEnd, DEFAULT_EASE);
      continue;
    }

    const firstSample = segmentSamples[0];
    const lastSample = segmentSamples[segmentSamples.length - 1];
    const allProps = Object.keys(firstSample.properties);

    let primaryProp = allProps[0];
    let maxDelta = 0;

    for (const prop of allProps) {
      const delta = Math.abs(
        (lastSample.properties[prop] ?? 0) - (firstSample.properties[prop] ?? 0),
      );
      if (delta > maxDelta) {
        maxDelta = delta;
        primaryProp = prop;
      }
    }

    const flatSamples = segmentSamples.map((s) => ({
      time: s.time,
      value: s.properties[primaryProp] ?? 0,
    }));

    result.set(pctEnd, inferSegmentEase(flatSamples, startTime, endTime));
  }

  return result;
}
