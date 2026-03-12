import { useState } from "react";
import { triggerFollowUp } from "../api";
import styles from "./FollowUpSection.module.css";

const MAX_CONTEXT_LENGTH = 1000;

interface Props {
  articleId: string;
}

export default function FollowUpSection({ articleId }: Props) {
  const [context, setContext] = useState("");
  const [generating, setGenerating] = useState(false);
  const [triggered, setTriggered] = useState(false);
  const [error, setError] = useState(false);

  const canGenerate = !generating && !triggered && context.trim().length > 0;

  async function handleGenerate() {
    if (!canGenerate) return;
    setGenerating(true);
    setError(false);
    try {
      await triggerFollowUp(articleId, context.trim());
      setTriggered(true);
    } catch {
      setError(true);
    } finally {
      setGenerating(false);
    }
  }

  return (
    <div className={styles.section}>
      <div className={styles.card}>
        <p className={styles.title}><span>🪝</span> Go Deeper</p>
        <textarea
          className={styles.input}
          placeholder="e.g. focus on the regulatory implications"
          maxLength={MAX_CONTEXT_LENGTH}
          value={context}
          onChange={(e) => setContext(e.target.value)}
          aria-label="Follow-up context"
        />
        <div className={styles.actions}>
          <button
            className={styles.generateBtn}
            disabled={!canGenerate}
            onClick={handleGenerate}
          >
            Generate Follow-up
          </button>
        </div>
        {triggered && (
          <p className={styles.status}>Generating your follow-up… you'll get a notification when it's ready.</p>
        )}
        {error && (
          <p className={styles.status}>Something went wrong. Try again in a minute.</p>
        )}
      </div>
    </div>
  );
}
