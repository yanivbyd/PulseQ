import { useState } from "react";
import { triggerGenerate } from "../api";
import HamburgerMenu from "../components/HamburgerMenu";
import styles from "./NewArticlePage.module.css";

const MAX_TOPIC_LENGTH = 1000;

export default function NewArticlePage() {
  const [mode, setMode] = useState<"random" | "custom">("random");
  const [topic, setTopic] = useState("");
  const [generating, setGenerating] = useState(false);
  const [triggered, setTriggered] = useState(false);
  const [statusMsg, setStatusMsg] = useState<string | null>(null);

  const canGenerate = !generating && !triggered && (mode === "random" || topic.trim().length > 0);

  async function handleGenerate() {
    if (!canGenerate) return;
    setGenerating(true);
    setStatusMsg(null);
    try {
      await triggerGenerate(mode === "custom" ? topic.trim() : undefined);
      setTriggered(true);
      setStatusMsg("Generating your article… you'll get a notification when it's ready.");
    } catch {
      setStatusMsg("Something went wrong. Try again in a minute.");
    } finally {
      setGenerating(false);
    }
  }

  return (
    <main className={styles.container}>
      <div className={styles.pageHeader}>
        <span className={styles.headerSpacer} />
        <h1 className={styles.pageTitle}>New Article</h1>
        <HamburgerMenu />
      </div>

      <div className={styles.modeRow}>
        <label className={styles.modeLabel}>
          <input
            type="radio"
            name="mode"
            value="random"
            checked={mode === "random"}
            onChange={() => setMode("random")}
          />
          Random
        </label>
        <label className={styles.modeLabel}>
          <input
            type="radio"
            name="mode"
            value="custom"
            checked={mode === "custom"}
            onChange={() => setMode("custom")}
          />
          Custom
        </label>
      </div>

      {mode === "custom" && (
        <textarea
          className={styles.topicInput}

          maxLength={MAX_TOPIC_LENGTH}
          value={topic}
          onChange={(e) => setTopic(e.target.value)}
          aria-label="Custom topic"
        />
      )}

      <button
        className={styles.generateBtn}
        disabled={!canGenerate}
        onClick={handleGenerate}
      >
        Generate
      </button>

      {statusMsg && <p className={styles.status}>{statusMsg}</p>}
    </main>
  );
}
