import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, test, expect, beforeEach } from "vitest";
import HomePage from "../pages/HomePage";
import * as api from "../api";

vi.mock("../api", () => ({
  fetchArticleSummaries: vi.fn(),
  triggerGenerate: vi.fn(),
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
  vi.mocked(api.triggerGenerate).mockResolvedValue(undefined);
});

describe("HomePage article list", () => {
  test("renders page title and articles", async () => {
    renderHomePage();
    expect(await screen.findByRole("heading", { name: "Articles" })).toBeInTheDocument();
    expect(screen.getByText("Article One")).toBeInTheDocument();
    expect(screen.getByText("Article Two")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Mark as read" })).not.toBeInTheDocument();
  });

  test("shows empty state when no articles", async () => {
    vi.mocked(api.fetchArticleSummaries).mockResolvedValue([]);
    renderHomePage();
    expect(await screen.findByText("Nothing new to read.")).toBeInTheDocument();
  });
});

describe("HomePage bottom bar", () => {
  test("renders generate button and hamburger toggle", async () => {
    renderHomePage();
    expect(await screen.findByRole("button", { name: "Generate" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Open menu" })).toBeInTheDocument();
  });

  test("clicking generate calls triggerGenerate and shows toast", async () => {
    renderHomePage();
    await screen.findByRole("button", { name: "Generate" });
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(api.triggerGenerate).toHaveBeenCalledTimes(1);
    await waitFor(() => expect(screen.getByText(/generating/i)).toBeInTheDocument());
  });

  test("generate button is disabled while active", async () => {
    vi.mocked(api.triggerGenerate).mockImplementation(() => new Promise(() => {}));
    renderHomePage();
    await screen.findByRole("button", { name: "Generate" });
    userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled());
  });

  test("shows error toast when generate fails", async () => {
    vi.mocked(api.triggerGenerate).mockRejectedValue(new Error("error"));
    renderHomePage();
    await screen.findByRole("button", { name: "Generate" });
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
  });
});
