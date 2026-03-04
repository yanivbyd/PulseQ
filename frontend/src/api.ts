export interface ArticleSummary {
  id: string;
  title: string;
  accent: string;
  creation_timestamp: string;
}

export interface Article extends ArticleSummary {
  html: string;
}

export async function fetchArticleSummaries(userId: string): Promise<ArticleSummary[]> {
  const res = await fetch(`/api/article-summaries?userId=${encodeURIComponent(userId)}`);
  if (!res.ok) throw new Error(`Failed to fetch articles: ${res.status}`);
  return res.json();
}

export async function fetchArticle(articleId: string): Promise<Article> {
  const res = await fetch(`/api/article/${encodeURIComponent(articleId)}`);
  if (!res.ok) throw new Error(`Failed to fetch article: ${res.status}`);
  return res.json();
}

export async function triggerGenerate(): Promise<void> {
  const res = await fetch("/api/generate", { method: "POST" });
  if (!res.ok) throw new Error(`Failed to generate: ${res.status}`);
}
