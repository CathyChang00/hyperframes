import { Composition } from "remotion";
import { AbsoluteFill, useCurrentFrame, interpolate } from "remotion";

export const Main: React.FC = () => {
  const frame = useCurrentFrame();
  const opacity = interpolate(frame, [0, 30], [0, 1], { extrapolateRight: "clamp" });
  return (
    <AbsoluteFill
      style={{ backgroundColor: "#0b1020", justifyContent: "center", alignItems: "center" }}
    >
      <h1 style={{ color: "white", opacity, fontSize: 80 }}>Quarterly Recap</h1>
    </AbsoluteFill>
  );
};

export const RemotionRoot: React.FC = () => (
  <Composition
    id="Main"
    component={Main}
    durationInFrames={150}
    fps={30}
    width={1920}
    height={1080}
  />
);
