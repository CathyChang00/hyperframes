import { useCallback, useRef, useState } from "react";

// ── Types ──

export interface GestureSample {
  time: number;
  properties: Record<string, number>;
}

interface Modifiers {
  shift: boolean;
  alt: boolean;
  meta: boolean;
}

interface AccumulatedState {
  opacity: number;
  scale: number;
  z: number;
}

// ── Pure mapping function ──

/**
 * Maps raw pointer deltas, scroll delta, and modifier state to GSAP property
 * values. Pure and testable without DOM.
 *
 * Modifier-to-property mapping:
 *  - Plain drag        -> x, y (px delta from start)
 *  - Scroll wheel      -> z (accumulated scroll delta)
 *  - Shift + drag      -> rotationX (vert * 0.5), rotationY (horiz * 0.5)
 *  - Alt + drag horiz  -> rotation (horiz * 0.5)
 *  - Cmd/Ctrl + drag V -> opacity (vert delta mapped 0-1, clamped)
 *  - Cmd/Ctrl + scroll -> scale (scroll * 0.01, accumulated from 1.0)
 */
export function resolveGestureProperties(
  dx: number,
  dy: number,
  scrollDelta: number,
  modifiers: Modifiers,
  accumulatedState: AccumulatedState,
): {
  properties: Record<string, number>;
  nextState: AccumulatedState;
} {
  const properties: Record<string, number> = {};
  let nextOpacity = accumulatedState.opacity;
  let nextScale = accumulatedState.scale;
  let nextZ = accumulatedState.z;

  if (modifiers.meta) {
    // Cmd/Ctrl held: vertical drag -> opacity, scroll -> scale
    nextOpacity = Math.max(0, Math.min(1, accumulatedState.opacity - dy * 0.005));
    properties.opacity = nextOpacity;

    if (scrollDelta !== 0) {
      nextScale = Math.max(0.01, accumulatedState.scale + scrollDelta * 0.01);
      properties.scale = nextScale;
    }
  } else if (modifiers.shift) {
    // Shift held: drag -> rotationX/rotationY
    properties.rotationX = dy * 0.5;
    properties.rotationY = dx * 0.5;
  } else if (modifiers.alt) {
    // Alt held: horizontal drag -> rotation
    properties.rotation = dx * 0.5;
  } else {
    // Plain: drag -> x/y
    properties.x = dx;
    properties.y = dy;
  }

  // Scroll without Cmd/Ctrl -> z accumulation
  if (!modifiers.meta && scrollDelta !== 0) {
    nextZ = accumulatedState.z + scrollDelta;
    properties.z = nextZ;
  }

  return {
    properties,
    nextState: { opacity: nextOpacity, scale: nextScale, z: nextZ },
  };
}

// ── Hook ──

export function useGestureRecording() {
  const [isRecording, setIsRecording] = useState(false);
  const [samples, setSamples] = useState<GestureSample[]>([]);
  const [recordingDuration, setRecordingDuration] = useState(0);

  // Refs for high-frequency data (never useState for 60fps input)
  const pointerRef = useRef({ x: 0, y: 0 });
  const startPointerRef = useRef({ x: 0, y: 0 });
  const scrollDeltaRef = useRef(0);
  const modifiersRef = useRef<Modifiers>({ shift: false, alt: false, meta: false });
  const accumulatedRef = useRef<AccumulatedState>({ opacity: 1, scale: 1, z: 0 });

  const rafIdRef = useRef(0);
  const samplesRef = useRef<GestureSample[]>([]);
  const cleanupRef = useRef<(() => void) | null>(null);

  const startRecording = useCallback(
    (element: HTMLElement, _iframeEl: HTMLIFrameElement) => {
      if (isRecording) return;

      // Reset state
      samplesRef.current = [];
      setSamples([]);
      setRecordingDuration(0);
      accumulatedRef.current = { opacity: 1, scale: 1, z: 0 };
      scrollDeltaRef.current = 0;

      // Listeners target the overlay element (same div DomEditOverlay uses).
      // Passive so they never block scrolling.

      const handlePointerMove = (e: PointerEvent) => {
        pointerRef.current = { x: e.clientX, y: e.clientY };
        modifiersRef.current = {
          shift: e.shiftKey,
          alt: e.altKey,
          meta: e.metaKey || e.ctrlKey,
        };
      };

      const handleWheel = (e: WheelEvent) => {
        scrollDeltaRef.current += e.deltaY;
        modifiersRef.current = {
          shift: e.shiftKey,
          alt: e.altKey,
          meta: e.metaKey || e.ctrlKey,
        };
      };

      const handleKeyDown = (e: KeyboardEvent) => {
        modifiersRef.current = {
          shift: e.shiftKey,
          alt: e.altKey,
          meta: e.metaKey || e.ctrlKey,
        };
      };

      const handleKeyUp = (e: KeyboardEvent) => {
        modifiersRef.current = {
          shift: e.shiftKey,
          alt: e.altKey,
          meta: e.metaKey || e.ctrlKey,
        };
      };

      element.addEventListener("pointermove", handlePointerMove, { passive: true });
      element.addEventListener("wheel", handleWheel, { passive: true });
      document.addEventListener("keydown", handleKeyDown, { passive: true });
      document.addEventListener("keyup", handleKeyUp, { passive: true });

      // Capture initial pointer position from the first move; until then delta is 0.
      // We set it explicitly so the first RAF tick sees zero deltas.
      startPointerRef.current = { ...pointerRef.current };

      const startMs = performance.now();

      // Store pointer start once the first pointermove fires
      let startCaptured = false;
      const captureStart = (e: PointerEvent) => {
        if (!startCaptured) {
          startPointerRef.current = { x: e.clientX, y: e.clientY };
          startCaptured = true;
        }
      };
      element.addEventListener("pointermove", captureStart, { passive: true, once: true });

      // RAF loop — sample at ~60fps
      const tick = () => {
        const now = performance.now();
        const time = (now - startMs) / 1000;

        const dx = pointerRef.current.x - startPointerRef.current.x;
        const dy = pointerRef.current.y - startPointerRef.current.y;
        const scrollDelta = scrollDeltaRef.current;

        const { properties, nextState } = resolveGestureProperties(
          dx,
          dy,
          scrollDelta,
          modifiersRef.current,
          accumulatedRef.current,
        );

        accumulatedRef.current = nextState;
        // Reset scroll delta after consuming it — it's accumulated per-frame
        scrollDeltaRef.current = 0;

        const sample: GestureSample = { time, properties };
        samplesRef.current.push(sample);
        setRecordingDuration(time);

        rafIdRef.current = requestAnimationFrame(tick);
      };

      setIsRecording(true);
      rafIdRef.current = requestAnimationFrame(tick);

      // Store cleanup so stopRecording can tear everything down
      cleanupRef.current = () => {
        cancelAnimationFrame(rafIdRef.current);
        element.removeEventListener("pointermove", handlePointerMove);
        element.removeEventListener("wheel", handleWheel);
        document.removeEventListener("keydown", handleKeyDown);
        document.removeEventListener("keyup", handleKeyUp);
        element.removeEventListener("pointermove", captureStart);
      };
    },
    [isRecording],
  );

  const stopRecording = useCallback(() => {
    if (!isRecording) return;

    cleanupRef.current?.();
    cleanupRef.current = null;

    // Freeze samples into React state
    const frozen = samplesRef.current.slice();
    setSamples(frozen);
    setRecordingDuration(frozen.length > 0 ? frozen[frozen.length - 1].time : 0);
    setIsRecording(false);
  }, [isRecording]);

  const clearSamples = useCallback(() => {
    samplesRef.current = [];
    setSamples([]);
    setRecordingDuration(0);
    accumulatedRef.current = { opacity: 1, scale: 1, z: 0 };
    scrollDeltaRef.current = 0;
  }, []);

  return {
    startRecording,
    stopRecording,
    isRecording,
    samples,
    recordingDuration,
    clearSamples,
  };
}
