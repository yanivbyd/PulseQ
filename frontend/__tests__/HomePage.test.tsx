import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import HomePage from "../src/pages/HomePage";
import * as api from "../src/api";

vi.mock("../src/api");

const SUMMARIES = [
  { articleId: "abc12", title: "How Load Balancers Work", creation_timestamp: "2026-03-01T00:00:00.000Z" },
];

const renderPage = () => render(<MemoryRouter><HomePage /></MemoryRouter>);

test("shows loading state initially", () => {
  vi.mocked(api.fetchArticleSummaries).mockReturnValue(new Promise(() => {}));
  renderPage();
  expect(screen.getByText("Loading...")).toBeInTheDocument();
});

test("renders article rows on success", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  renderPage();
  await waitFor(() => expect(screen.getByText("How Load Balancers Work")).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "How Load Balancers Work" })).toHaveAttribute("href", "/abc12");
});

test("renders empty state when no articles", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue([]);
  renderPage();
  await waitFor(() => expect(screen.getByText("Nothing new to read.")).toBeInTheDocument());
});

test("renders error message on fetch failure", async () => {
  vi.mocked(api.fetchArticleSummaries).mockRejectedValue(new Error("Network error"));
  renderPage();
  await waitFor(() => expect(screen.getByText("Network error")).toBeInTheDocument());
});

test("does not render a generate button", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  renderPage();
  await waitFor(() => expect(screen.getByText("How Load Balancers Work")).toBeInTheDocument());
  expect(screen.queryByRole("button", { name: "Generate" })).not.toBeInTheDocument();
});

describe("Hamburger menu", () => {
  beforeEach(() => {
    vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  });

  test("opens nav menu with Articles, Topics and New Article links", async () => {
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: "Open menu" }));
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(screen.getByRole("link", { name: "Articles" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Topics" })).toHaveAttribute("href", "/topics");
    expect(screen.getByRole("link", { name: "New Article" })).toHaveAttribute("href", "/generate");
  });
});
