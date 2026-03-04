import { useState, useEffect } from "react";
import { Link } from "react-router-dom";
import { fetchArticleSummaries, type ArticleSummary } from "../api";
import styles from "./HomePage.module.css";

export default function HomePage() {
  const [articles, setArticles] = useState<ArticleSummary[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

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

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;

  return (
    <main className={styles.container}>
      <div className={styles.header}>
        <h1>PulseQ</h1>
      </div>
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
    </main>
  );
}
