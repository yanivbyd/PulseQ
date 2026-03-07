import { useState, useEffect, useRef } from "react";
import { fetchTopics, triggerScout, type Topic } from "../api";
import styles from "./TopicsPage.module.css";

type ActionState = "idle" | "active" | "cooldown";

export default function TopicsPage() {
  const [topics, setTopics] = useState<Topic[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [scoutState, setScoutState] = useState<ActionState>("idle");
  const [toast, setToast] = useState<string | null>(null);
  const scoutCooldown = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const toastTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const userId = import.meta.env.VITE_USER_ID as string | undefined;

  useEffect(() => {
    // VITE_USER_ID is statically substituted by Vite at build time; this guard
    // catches a missing .env.local at dev startup and cannot be unit-tested.
    /* v8 ignore next 3 */
    if (!userId) {
      setError("VITE_USER_ID is not configured");
      setLoading(false);
      return;
    }
    fetchTopics(userId)
      .then(setTopics)
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    return () => {
      if (scoutCooldown.current) clearTimeout(scoutCooldown.current);
      if (pollRef.current) clearTimeout(pollRef.current);
      if (toastTimer.current) clearTimeout(toastTimer.current);
    };
  }, []);

  function showToast(msg: string) {
    setToast(msg);
    if (toastTimer.current) clearTimeout(toastTimer.current);
    toastTimer.current = setTimeout(() => setToast(null), 4_000);
  }

  function schedulePoll(snapshot: string[], attemptsLeft: number) {
    pollRef.current = setTimeout(async () => {
      try {
        const fresh = await fetchTopics(userId!);
        const freshTitles = fresh.map((t) => t.title);
        if (JSON.stringify(freshTitles) !== JSON.stringify(snapshot)) {
          setTopics(fresh);
          showToast(`Topics updated (${snapshot.length} \u2192 ${fresh.length})`);
        } else if (attemptsLeft > 1) {
          schedulePoll(snapshot, attemptsLeft - 1);
        } else {
          showToast("Topics unchanged \u2014 try again later.");
        }
      } catch {
        if (attemptsLeft > 1) {
          schedulePoll(snapshot, attemptsLeft - 1);
        } else {
          showToast("Topics unchanged \u2014 try again later.");
        }
      }
    }, 3_000);
  }

  async function handleScout() {
    if (scoutState !== "idle") return;
    setScoutState("active");
    const snapshot = topics.map((t) => t.title);
    try {
      await triggerScout();
      showToast("Topics are being refreshed.");
      schedulePoll(snapshot, 10);
    } catch {
      showToast("Something went wrong. Try again in a minute.");
    }
    setScoutState("cooldown");
    scoutCooldown.current = setTimeout(() => setScoutState("idle"), 60_000);
  }

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;

  return (
    <main className={styles.container}>
      <ul className={styles.list}>
        {topics.length === 0
          ? <li className={styles.empty}>No topics configured.</li>
          : topics.map((t) => (
              <li key={t.title} className={styles.row}>{t.title}</li>
            ))
        }
      </ul>
      {toast && <div className={styles.toast}>{toast}</div>}
      <div className={styles.bottomBar}>
        <a href="/" className={styles.barBtn} aria-label="Home">&#127968;</a>
        <button
          className={styles.barBtn}
          aria-label="Refresh Topics"
          disabled={scoutState !== "idle"}
          onClick={handleScout}
        >&#128240;</button>
      </div>
    </main>
  );
}
