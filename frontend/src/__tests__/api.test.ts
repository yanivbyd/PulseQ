import { vi, describe, test, expect, beforeEach } from "vitest";
import { fetchTopics } from "../api";

const mockFetch = vi.fn();
vi.stubGlobal("fetch", mockFetch);

beforeEach(() => {
  vi.clearAllMocks();
});

describe("fetchTopics", () => {
  const TOPICS = [
    { title: "AI News", description: "Latest AI" },
    { title: "Cloud", description: "Cloud updates" },
  ];

  test("returns topics array on success", async () => {
    mockFetch.mockResolvedValue({
      ok: true,
      json: () => Promise.resolve({ topics: TOPICS }),
    });
    const result = await fetchTopics("user1");
    expect(result).toEqual(TOPICS);
    expect(mockFetch).toHaveBeenCalledWith("/api/topics?userId=user1");
  });

  test("throws on non-ok response", async () => {
    mockFetch.mockResolvedValue({ ok: false, status: 500 });
    await expect(fetchTopics("user1")).rejects.toThrow("Failed to fetch topics: 500");
  });
});
