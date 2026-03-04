import { fetchArticleSummaries, fetchArticle, triggerGenerate } from "../src/api";

const SUMMARIES = [
  { id: "abc12", title: "How Load Balancers Work", accent: "#0d9488", creation_timestamp: "2026-03-01T00:00:00.000Z" },
];
const ARTICLE = { ...SUMMARIES[0], html: '<div class="header-card"><h1>How Load Balancers Work</h1></div>' };

beforeEach(() => { vi.stubGlobal("fetch", vi.fn()); });
afterEach(() => { vi.unstubAllGlobals(); });

function mockFetch(ok: boolean, data?: unknown, status = 200) {
  (fetch as ReturnType<typeof vi.fn>).mockResolvedValue({
    ok,
    status,
    json: () => Promise.resolve(data),
  });
}

describe("fetchArticleSummaries", () => {
  test("returns summaries and calls correct URL", async () => {
    mockFetch(true, SUMMARIES);
    const result = await fetchArticleSummaries("user1");
    expect(result).toEqual(SUMMARIES);
    expect(fetch).toHaveBeenCalledWith("/api/article-summaries?userId=user1");
  });

  test("throws on HTTP error", async () => {
    mockFetch(false, undefined, 500);
    await expect(fetchArticleSummaries("user1")).rejects.toThrow("500");
  });
});

describe("fetchArticle", () => {
  test("returns article and calls correct URL", async () => {
    mockFetch(true, ARTICLE);
    const result = await fetchArticle("abc12");
    expect(result).toEqual(ARTICLE);
    expect(fetch).toHaveBeenCalledWith("/api/article/abc12");
  });

  test("throws on 404", async () => {
    mockFetch(false, undefined, 404);
    await expect(fetchArticle("missing")).rejects.toThrow("404");
  });
});

describe("triggerGenerate", () => {
  test("sends POST /api/generate and resolves on 202", async () => {
    mockFetch(true, { status: "generating" }, 202);
    await expect(triggerGenerate()).resolves.toBeUndefined();
    expect(fetch).toHaveBeenCalledWith("/api/generate", { method: "POST" });
  });

  test("throws on 5xx", async () => {
    mockFetch(false, undefined, 500);
    await expect(triggerGenerate()).rejects.toThrow("500");
  });
});
