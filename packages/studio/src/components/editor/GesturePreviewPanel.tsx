import { memo, useCallback, useMemo, useState } from "react";
import type { GestureSample } from "../../hooks/useGestureRecording";
import { simplifyGestureSamples } from "../../utils/rdpSimplify";
import { inferAllEases } from "../../utils/inferEase";
import { SliderControl } from "./propertyPanelPrimitives";
import { LABEL } from "./propertyPanelHelpers";
import { P } from "./panelTokens";

interface GesturePreviewPanelProps {
  samples: GestureSample[];
  totalDuration: number;
  onCommit: (keyframes: Map<number, Record<string, number>>, eases: Map<number, string>) => void;
  onDiscard: () => void;
  onReRecord: () => void;
  onSimplifiedChange?: (simplified: Map<number, Record<string, number>>) => void;
}

export const GesturePreviewPanel = memo(function GesturePreviewPanel({
  samples,
  totalDuration,
  onCommit,
  onDiscard,
  onReRecord,
  onSimplifiedChange,
}: GesturePreviewPanelProps) {
  const [epsilon, setEpsilon] = useState(5);

  const simplified = useMemo(() => {
    const result = simplifyGestureSamples(samples, totalDuration, epsilon);
    onSimplifiedChange?.(result);
    return result;
  }, [samples, totalDuration, epsilon, onSimplifiedChange]);

  const eases = useMemo(() => {
    const pcts = Array.from(simplified.keys()).sort((a, b) => a - b);
    return inferAllEases(
      samples.map((s) => ({
        time: s.time,
        properties: s.properties,
      })),
      pcts,
      totalDuration,
    );
  }, [samples, simplified, totalDuration]);

  const keyframeCount = simplified.size;
  const propertyList = useMemo(() => {
    const keys = new Set<string>();
    for (const props of simplified.values()) {
      for (const k of Object.keys(props)) keys.add(k);
    }
    return Array.from(keys);
  }, [simplified]);

  const handleEpsilonChange = useCallback((v: number) => {
    setEpsilon(Math.round(v * 10) / 10);
  }, []);

  const handleCommit = useCallback(() => {
    onCommit(simplified, eases);
  }, [onCommit, simplified, eases]);

  return (
    <div className="space-y-3 rounded-lg border border-neutral-800 bg-neutral-900/80 p-3">
      <div className="flex items-center justify-between">
        <span className="text-[12px] font-semibold text-panel-text-1">Gesture Recording</span>
        <span className="text-[10px] text-panel-text-3">{keyframeCount} keyframes</span>
      </div>

      <div className="space-y-1.5">
        <span className={LABEL}>Smoothing</span>
        <SliderControl
          value={epsilon}
          min={0.5}
          max={30}
          step={0.5}
          displayValue={epsilon.toFixed(1)}
          formatDisplayValue={(v) => v.toFixed(1)}
          onCommit={handleEpsilonChange}
        />
        <div className="flex justify-between text-[9px] text-panel-text-4">
          <span>Detailed</span>
          <span>Smooth</span>
        </div>
      </div>

      {propertyList.length > 0 && (
        <div className="space-y-1">
          <span className={LABEL}>Recorded properties</span>
          <div className="flex flex-wrap gap-1">
            {propertyList.map((prop) => (
              <span
                key={prop}
                className="rounded bg-panel-input px-1.5 py-0.5 text-[10px] font-medium text-panel-text-2"
              >
                {prop}
              </span>
            ))}
          </div>
        </div>
      )}

      {eases.size > 0 && (
        <div className="space-y-1">
          <span className={LABEL}>Inferred eases</span>
          <div className="flex flex-wrap gap-1">
            {Array.from(eases.entries())
              .sort(([a], [b]) => a - b)
              .map(([pct, ease]) => (
                <span
                  key={pct}
                  className="rounded bg-panel-input px-1.5 py-0.5 text-[10px] text-panel-text-3"
                >
                  {pct}% → {ease}
                </span>
              ))}
          </div>
        </div>
      )}

      <div className="flex gap-2 pt-1">
        <button
          type="button"
          onClick={handleCommit}
          className="flex-1 rounded-md py-1.5 text-[11px] font-semibold transition-colors"
          style={{ background: P.accent, color: "#09090B" }}
        >
          Commit
        </button>
        <button
          type="button"
          onClick={onReRecord}
          className="flex-1 rounded-md border border-neutral-700 py-1.5 text-[11px] font-medium text-panel-text-2 transition-colors hover:bg-neutral-800"
        >
          Re-record
        </button>
        <button
          type="button"
          onClick={onDiscard}
          className="rounded-md border border-neutral-700 px-3 py-1.5 text-[11px] font-medium text-red-400 transition-colors hover:bg-red-500/10"
        >
          Discard
        </button>
      </div>
    </div>
  );
});
