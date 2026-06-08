import { useCallback } from "react";
import type { DomEditSelection } from "../components/editor/domEditing";

interface GestureCommitParams {
  commitMutation: (
    selection: DomEditSelection,
    mutation: Record<string, unknown>,
    options: { label: string; softReload: boolean },
  ) => Promise<void>;
}

export function useGestureCommit({ commitMutation }: GestureCommitParams) {
  const commitGestureKeyframes = useCallback(
    async (
      selection: DomEditSelection,
      animationId: string,
      keyframes: Map<number, Record<string, number>>,
      eases: Map<number, string>,
    ) => {
      const sortedPcts = Array.from(keyframes.keys()).sort((a, b) => a - b);
      if (sortedPcts.length < 2) return;

      await commitMutation(
        selection,
        { type: "convert-to-keyframes" as const, animationId },
        { label: "Convert to keyframes for gesture recording", softReload: false },
      );

      for (const pct of sortedPcts) {
        const props = keyframes.get(pct);
        if (!props) continue;

        for (const [prop, value] of Object.entries(props)) {
          await commitMutation(
            selection,
            {
              type: "add-keyframe" as const,
              animationId,
              percentage: pct,
              property: prop,
              value,
              ease: eases.get(pct),
            },
            {
              label: `Record keyframe at ${pct}%`,
              softReload: pct === sortedPcts[sortedPcts.length - 1],
            },
          );
        }
      }
    },
    [commitMutation],
  );

  return { commitGestureKeyframes };
}
