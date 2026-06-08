import { memo, useMemo } from "react";
import type { GestureSample } from "../../hooks/useGestureRecording";

interface GestureTrailOverlayProps {
  samples: GestureSample[];
  simplifiedPoints?: Map<number, Record<string, number>>;
  canvasRect: { left: number; top: number; width: number; height: number };
  mode: "recording" | "preview";
  accentColor?: string;
}

export const GestureTrailOverlay = memo(function GestureTrailOverlay({
  samples,
  simplifiedPoints,
  canvasRect,
  mode,
  accentColor = "#3CE6AC",
}: GestureTrailOverlayProps) {
  const trailPoints = useMemo(() => {
    if (samples.length === 0) return "";
    return samples
      .filter((s) => s.properties.x != null && s.properties.y != null)
      .map((s) => `${s.properties.x},${s.properties.y}`)
      .join(" ");
  }, [samples]);

  const simplifiedPath = useMemo(() => {
    if (!simplifiedPoints || simplifiedPoints.size === 0) return "";
    const pts: Array<{ x: number; y: number; pct: number }> = [];
    for (const [pct, props] of simplifiedPoints) {
      if (props.x != null && props.y != null) {
        pts.push({ x: props.x, y: props.y, pct });
      }
    }
    pts.sort((a, b) => a.pct - b.pct);
    if (pts.length === 0) return "";
    return pts.map((p) => `${p.x},${p.y}`).join(" ");
  }, [simplifiedPoints]);

  const diamondPositions = useMemo(() => {
    if (!simplifiedPoints || simplifiedPoints.size === 0) return [];
    const pts: Array<{ x: number; y: number; pct: number }> = [];
    for (const [pct, props] of simplifiedPoints) {
      if (props.x != null && props.y != null) {
        pts.push({ x: props.x, y: props.y, pct });
      }
    }
    return pts.sort((a, b) => a.pct - b.pct);
  }, [simplifiedPoints]);

  if (samples.length < 2 && !simplifiedPoints) return null;

  return (
    <svg
      className="pointer-events-none absolute"
      style={{
        left: canvasRect.left,
        top: canvasRect.top,
        width: canvasRect.width,
        height: canvasRect.height,
      }}
      viewBox={`0 0 ${canvasRect.width} ${canvasRect.height}`}
    >
      {mode === "recording" && trailPoints && (
        <polyline
          points={trailPoints}
          fill="none"
          stroke={accentColor}
          strokeWidth="2"
          strokeOpacity="0.6"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      )}

      {mode === "preview" && (
        <>
          {trailPoints && (
            <polyline
              points={trailPoints}
              fill="none"
              stroke={accentColor}
              strokeWidth="1"
              strokeOpacity="0.2"
              strokeDasharray="4 3"
              strokeLinecap="round"
            />
          )}
          {simplifiedPath && (
            <polyline
              points={simplifiedPath}
              fill="none"
              stroke={accentColor}
              strokeWidth="2"
              strokeOpacity="0.8"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          )}
          {diamondPositions.map((pt) => (
            <g key={pt.pct} transform={`translate(${pt.x}, ${pt.y})`}>
              <rect
                x="-4"
                y="-4"
                width="8"
                height="8"
                rx="1"
                transform="rotate(45)"
                fill={accentColor}
                fillOpacity="0.9"
              />
            </g>
          ))}
        </>
      )}
    </svg>
  );
});
