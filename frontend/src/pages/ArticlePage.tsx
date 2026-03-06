import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { fetchArticle, postFeedback, type Article } from "../api";
import styles from "./ArticlePage.module.css";

export default function ArticlePage() {
  const { articleId } = useParams<{ articleId: string }>();
  const [article, setArticle] = useState<Article | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reaction, setReaction] = useState<"like" | "dislike" | null>(null);
  const [feedbackError, setFeedbackError] = useState(false);

  useEffect(() => {
    if (!articleId) return;
    fetchArticle(articleId)
      .then((a) => { setArticle(a); document.title = a.title; })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [articleId]);

  async function handleFeedback(picked: "like" | "dislike") {
    if (picked === reaction || !articleId || !article) return;
    const clientTimestamp = new Date().toISOString().replace(/:/g, "-");
    setReaction(picked);
    setFeedbackError(false);
    try {
      await postFeedback(articleId, article.title, picked, clientTimestamp);
    } catch {
      setReaction(null);
      setFeedbackError(true);
    }
  }

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;
  if (!article) return null;

  return (
    <>
      <div className={styles.bottomBar}>
        <a href="/" className={styles.barBtn} aria-label="Home">🏠</a>
      </div>
      <div
        className={styles.wrapper}
        dangerouslySetInnerHTML={{ __html: article.html }}
      />
      <hr className={styles.divider} />
      <div className={styles.feedback}>
        <p className={styles.feedbackLabel}>Did you enjoy this article?</p>
        <div className={styles.feedbackButtons}>
          <button
            className={`${styles.feedbackBtn} ${reaction === "like" ? styles.selected : ""}`}
            onClick={() => handleFeedback("like")}
            aria-label="Like"
          >👍</button>
          <button
            className={`${styles.feedbackBtn} ${reaction === "dislike" ? styles.selected : ""}`}
            onClick={() => handleFeedback("dislike")}
            aria-label="Dislike"
          >👎</button>
        </div>
        {feedbackError && <span className={styles.feedbackErr}>Something went wrong. Try again.</span>}
      </div>
    </>
  );
}
