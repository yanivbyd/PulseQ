import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { fetchArticleSummaries, triggerGenerate, type ArticleSummary } from "../api";
import styles from "./HomePage.module.css";

type GenerateState = "idle" | "generating" | "cooldown";

export default function HomePage() {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generateState, setGenerateState] = useState<GenerateState>("idle");
  const [generateError, setGenerateError] = useState(false);
  const cooldownTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    // VITE_USER_ID is statically substituted by Vite at build time; this guard
    // catches a missing .env.local at dev startup and cannot be unit-tested.
    const userId = import.meta.env.VITE_USER_ID as string | undefined;
    /* v8 ignore next 3 */
    if (!userId) {
      setError("VITE_USER_ID is not configured");
      setLoading(false);
      return;
    }
    fetchArticleSummaries(userId)
      .then(setArticles)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    return () => { if (cooldownTimer.current) clearTimeout(cooldownTimer.current); };
  }, []);

  async function handleGenerate() {
    setGenerateState("generating");
    setGenerateError(false);
    try {
      await triggerGenerate();
    } catch {
      setGenerateError(true);
    }
    setGenerateState("cooldown");
    cooldownTimer.current = setTimeout(() => setGenerateState("idle"), 60_000);
  }

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;

  return (
    <main className={styles.container}>
      <h1 className={styles.header}>PulseQ</h1>
      <div className={styles.list}>
        {articles.length === 0
          ? <p className={styles.empty}>No articles yet.</p>
          : articles.map((a) => (
              <Link
                key={a.id}
                to={`/${a.id}`}
                className={styles.card}
                style={{ background: a.accent }}
              >
                <span className={styles.title}>{a.title}</span>
              </Link>
            ))
        }
      </div>
      <hr className={styles.divider} />
      <div className={styles.generateSection}>
        <button
          className={styles.generateBtn}
          disabled={generateState !== "idle"}
          onClick={handleGenerate}
        >
          {generateState === "generating" ? "Generating…" : "Generate New Article"}
        </button>
        {generateState !== "idle" && (
          <p className={styles.generateMsg}>
            {generateError
              ? "Something went wrong. Try again in a minute."
              : "Generating… you'll get a notification when it's ready."}
          </p>
        )}
      </div>
    </main>
  );
}
