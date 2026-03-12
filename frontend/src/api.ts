export interface Topic { title: string; description: string; }

export async function fetchTopics(userId: string): Promise<Topic[]> {
  const res = await fetch(`/api/topics?userId=${encodeURIComponent(userId)}`);
  if (!res.ok) throw new Error(`Failed to fetch topics: ${res.status}`);
  const data = await res.json();
  return data.topics as Topic[];
}

export interface ArticleSummary {
  articleId: string;
  title: string;
  creation_timestamp: string;
}

export interface QuizQuestion {
  q: string;
  options: string[];
  answer: number;
}

export interface Article {
  articleId: string;
  title: string;
  html: string;
  quiz: QuizQuestion[];
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
  const userId = import.meta.env.VITE_USER_ID as string;
  const res = await fetch("/api/generate", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId }),
  });
  if (!res.ok) throw new Error(`Failed to generate: ${res.status}`);
}

export async function triggerScout(): Promise<void> {
  const userId = import.meta.env.VITE_USER_ID as string;
  const res = await fetch("/api/scout", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId }),
  });
  if (!res.ok) throw new Error(`Failed to refresh topics: ${res.status}`);
}

export async function postMarkRead(userId: string, articleId: string, is_read: boolean, idempotencyKey: string): Promise<void> {
  const res = await fetch("/api/mark-read", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ userId, articleId, is_read, idempotencyKey }),
  });
  if (!res.ok) throw new Error(`Failed to mark read: ${res.status}`);
}

export interface FeedbackMeta {
  articleId: string;
  articleTitle: string;
  clientTimestamp: string;
}

export type FeedbackContent =
  | { type: "reaction"; reaction: "like" | "dislike" }
  | { type: "freeText"; text: string };

export async function postFeedback(meta: FeedbackMeta, content: FeedbackContent): Promise<void> {
  const userId = import.meta.env.VITE_USER_ID as string;
  const res = await fetch("/api/feedback", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ ...meta, userId, content }),
  });
  if (!res.ok) throw new Error(`Failed to post feedback: ${res.status}`);
}
