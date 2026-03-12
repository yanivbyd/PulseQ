import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, test, expect, beforeEach } from "vitest";
import HomePage from "../pages/HomePage";
import * as api from "../api";

vi.mock("../api", () => ({
  fetchArticleSummaries: vi.fn(),
}));

vi.stubEnv("VITE_USER_ID", "user1");

const ARTICLES: api.ArticleSummary[] = [
  { articleId: "a1", title: "Article One", creation_timestamp: "2026-03-05T09:00:00.000Z" },
  { articleId: "a2", title: "Article Two", creation_timestamp: "2026-03-04T09:00:00.000Z" },
];

function renderHomePage() {
  return render(<MemoryRouter><HomePage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue(ARTICLES);
});

describe("HomePage article list", () => {
  test("renders page title and articles", async () => {
    renderHomePage();
    expect(await screen.findByRole("heading", { name: "Articles" })).toBeInTheDocument();
    expect(screen.getByText("Article One")).toBeInTheDocument();
    expect(screen.getByText("Article Two")).toBeInTheDocument();
  });

  test("shows empty state when no articles", async () => {
    vi.mocked(api.fetchArticleSummaries).mockResolvedValue([]);
    renderHomePage();
    expect(await screen.findByText("Nothing new to read.")).toBeInTheDocument();
  });

  test("does not render a generate button", async () => {
    renderHomePage();
    await screen.findByRole("heading", { name: "Articles" });
    expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
  });
});
