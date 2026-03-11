import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { fetchArticle, postFeedback, type Article } from "../api";
import HamburgerMenu from "../components/HamburgerMenu";
import QuizSection from "../components/QuizSection";
import styles from "./ArticlePage.module.css";

export default function ArticlePage() {
  const { articleId } = useParams<{ articleId: string }>();
  const [article, setArticle] = useState<Article | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [reaction, setReaction] = useState<"like" | "dislike" | null>(null);
  const [reactionError, setReactionError] = useState(false);
  const [freeText, setFreeText] = useState("");
  const [freeTextError, setFreeTextError] = useState(false);

  useEffect(() => {
    if (!articleId) return;
    fetchArticle(articleId)
      .then((a) => { setArticle(a); document.title = a.title; })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [articleId]);

  function makeMeta(article: Article) {
    return {
      articleId: article.id,
      articleTitle: article.title,
      clientTimestamp: new Date().toISOString().replace(/:/g, "-"),
    };
  }

  async function handleReactionFeedback(picked: "like" | "dislike") {
    if (picked === reaction || !article) return;
    setReaction(picked);
    setReactionError(false);
    try {
      await postFeedback(makeMeta(article), { type: "reaction", reaction: picked });
    } catch {
      setReaction(null);
      setReactionError(true);
    }
  }

  async function handleFreeTextSubmit() {
    if (!freeText || !article) return;
    setFreeTextError(false);
    try {
      await postFeedback(makeMeta(article), { type: "freeText", text: freeText });
      setFreeText("");
    } catch {
      setFreeTextError(true);
    }
  }

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;
  if (!article) return null;

  return (
    <>
      <div className={styles.topBar}>
        <HamburgerMenu />
      </div>
      <div
        className={styles.wrapper}
        dangerouslySetInnerHTML={{ __html: article.html }}
      />
      <QuizSection quiz={article.quiz} />
      <div className={styles.feedback}>
        <div className={styles.feedbackCard}>
          <p className={styles.feedbackTitle}><span>🏎️</span> Tune the Signal</p>
          <div className={styles.reactionRow}>
            <span className={styles.reactionLabel}>Hit or miss?</span>
            <div className={styles.feedbackButtons}>
              <button
                className={`${styles.feedbackBtn} ${reaction === "like" ? styles.selected : ""}`}
                onClick={() => handleReactionFeedback("like")}
                aria-label="Like"
              >👍</button>
              <button
                className={`${styles.feedbackBtn} ${reaction === "dislike" ? styles.selected : ""}`}
                onClick={() => handleReactionFeedback("dislike")}
                aria-label="Dislike"
              >👎</button>
            </div>
          </div>
          {reactionError && <span className={styles.feedbackErr}>Something went wrong. Try again.</span>}
          <hr className={styles.feedbackDivider} />
          <div className={styles.freeTextSection}>
            <label htmlFor="freeTextInput" className={styles.freeTextLabel}>Anything to add?</label>
            <textarea
              id="freeTextInput"
              className={styles.freeTextInput}
              value={freeText}
              onChange={(e) => setFreeText(e.target.value)}
              rows={3}
            />
            <div className={styles.freeTextActions}>
              <button
                className={styles.submitBtn}
                onClick={handleFreeTextSubmit}
                disabled={!freeText}
              >Submit</button>
            </div>
          </div>
          {freeTextError && <span className={styles.feedbackErr}>Something went wrong. Try again.</span>}
        </div>
      </div>
    </>
  );
}
