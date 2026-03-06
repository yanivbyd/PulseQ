import { useState, useEffect, useRef } from "react";
import { Link } from "react-router-dom";
import { fetchArticleSummaries, triggerGenerate, triggerScout, postMarkRead, type ArticleSummary } from "../api";
import styles from "./HomePage.module.css";

type ActionState = "idle" | "active" | "cooldown";

export default function HomePage() {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [generateState, setGenerateState] = useState<ActionState>("idle");
  const [scoutState, setScoutState] = useState<ActionState>("idle");
  const [toast, setToast] = useState<string | null>(null);
  const generateCooldown = useRef<ReturnType<typeof setTimeout> | null>(null);
  const scoutCooldown = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

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
    return () => {
      if (generateCooldown.current) clearTimeout(generateCooldown.current);
      if (scoutCooldown.current) clearTimeout(scoutCooldown.current);
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  function showToast(msg: string) {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4_000);
  }

  async function handleGenerate() {
    if (generateState !== "idle") return;
    setGenerateState("active");
    try {
      await triggerGenerate();
      showToast("Generating… you'll get a notification when it's ready.");
    } catch {
      showToast("Something went wrong. Try again in a minute.");
    }
    setGenerateState("cooldown");
    generateCooldown.current = setTimeout(() => setGenerateState("idle"), 60_000);
  }

  async function handleScout() {
    if (scoutState !== "idle") return;
    setScoutState("active");
    try {
      await triggerScout();
      showToast("Topics are being refreshed.");
    } catch {
      showToast("Something went wrong. Try again in a minute.");
    }
    setScoutState("cooldown");
    scoutCooldown.current = setTimeout(() => setScoutState("idle"), 60_000);
  }

  async function handleMarkRead(article: ArticleSummary) {
    setArticles((prev) => prev.filter((a) => a.id !== article.id));
    const userId = import.meta.env.VITE_USER_ID as string;
    const idempotencyKey = crypto.randomUUID();
    try {
      await postMarkRead(userId, article.id, true, idempotencyKey);
    } catch {
      setArticles((prev) =>
        [...prev, article].sort((a, b) => b.creation_timestamp.localeCompare(a.creation_timestamp))
      );
      showToast("Failed to mark as read. Please try again.");
    }
  }

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;

  return (
    <main className={styles.container}>
      <ul className={styles.list}>
        {articles.length === 0
          ? <li className={styles.empty}>Nothing new to read.</li>
          : articles.map((a) => (
              <li key={a.id} className={styles.row}>
                <span className={styles.dot} aria-hidden="true" />
                <Link to={`/${a.id}`} className={styles.title}>{a.title}</Link>
                <button
                  className={styles.markReadBtn}
                  aria-label="Mark as read"
                  onClick={() => handleMarkRead(a)}
                >✓</button>
              </li>
            ))
        }
      </ul>
      {toast && <div className={styles.toast}>{toast}</div>}
      <div className={styles.bottomBar}>
        <button
          className={styles.barBtn}
          aria-label="Generate"
          disabled={generateState !== "idle"}
          onClick={handleGenerate}
        >✏️</button>
        <button
          className={styles.barBtn}
          aria-label="Scout"
          disabled={scoutState !== "idle"}
          onClick={handleScout}
        >📰</button>
      </div>
    </main>
  );
}
