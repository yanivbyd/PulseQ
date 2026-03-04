import { useState, useEffect } from "react";
import { useParams } from "react-router-dom";
import { fetchArticle, type Article } from "../api";
import styles from "./ArticlePage.module.css";

export default function ArticlePage() {
  const { articleId } = useParams<{ articleId: string }>();
  const [article, setArticle] = useState<Article | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!articleId) return;
    fetchArticle(articleId)
      .then((a) => { setArticle(a); document.title = a.title; })
      .catch((err: Error) => setError(err.message))
      .finally(() => setLoading(false));
  }, [articleId]);

  if (loading) return <div className={styles.status}>Loading...</div>;
  if (error) return <div className={styles.status}>{error}</div>;
  if (!article) return null;

  return (
    <>
      <a href="/" className={styles.fab} aria-label="Home">🏡</a>
      <div
        className={styles.wrapper}
        dangerouslySetInnerHTML={{ __html: article.html }}
      />
    </>
  );
}
