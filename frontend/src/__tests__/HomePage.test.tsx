import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, test, expect, beforeEach } from "vitest";
import HomePage from "../pages/HomePage";
import * as api from "../api";

vi.mock("../api", () => ({
  fetchArticleSummaries: vi.fn(),
  triggerGenerate: vi.fn(),
  postMarkRead: vi.fn(),
}));

vi.stubEnv("VITE_USER_ID", "user1");

const ARTICLES: api.ArticleSummary[] = [
  { id: "a1", title: "Article One", accent: "#0d9488", creation_timestamp: "2026-03-05T09:00:00.000Z" },
  { id: "a2", title: "Article Two", accent: "#0d9488", creation_timestamp: "2026-03-04T09:00:00.000Z" },
];

function renderHomePage() {
  return render(<MemoryRouter><HomePage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue(ARTICLES);
  vi.mocked(api.triggerGenerate).mockResolvedValue(undefined);
  vi.mocked(api.postMarkRead).mockResolvedValue(undefined);
});

describe("HomePage article list", () => {
  test("renders unread articles as rows with title and mark-read button", async () => {
    renderHomePage();
    expect(await screen.findByText("Article One")).toBeInTheDocument();
    expect(screen.getByText("Article Two")).toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "Mark as read" })).toHaveLength(2);
  });

  test("shows empty state when no articles", async () => {
    vi.mocked(api.fetchArticleSummaries).mockResolvedValue([]);
    renderHomePage();
    expect(await screen.findByText("Nothing new to read.")).toBeInTheDocument();
  });

  test("clicking mark-as-read removes the row and calls API", async () => {
    renderHomePage();
    await screen.findByText("Article One");
    await userEvent.click(screen.getAllByRole("button", { name: "Mark as read" })[0]);
    expect(screen.queryByText("Article One")).not.toBeInTheDocument();
    expect(screen.getByText("Article Two")).toBeInTheDocument();
    expect(api.postMarkRead).toHaveBeenCalledWith("user1", "a1", true, expect.any(String));
  });

  test("restores row and shows toast on mark-as-read failure", async () => {
    vi.mocked(api.postMarkRead).mockRejectedValue(new Error("network error"));
    renderHomePage();
    await screen.findByText("Article One");
    await userEvent.click(screen.getAllByRole("button", { name: "Mark as read" })[0]);
    await waitFor(() => expect(screen.getByText("Article One")).toBeInTheDocument());
    expect(screen.getByText(/failed to mark as read/i)).toBeInTheDocument();
  });
});

describe("HomePage bottom bar", () => {
  test("renders generate button and topics link", async () => {
    renderHomePage();
    expect(await screen.findByRole("button", { name: "Generate" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Topics" })).toBeInTheDocument();
  });

  test("topics link points to /topics", async () => {
    renderHomePage();
    const link = await screen.findByRole("link", { name: "Topics" });
    expect(link).toHaveAttribute("href", "/topics");
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
