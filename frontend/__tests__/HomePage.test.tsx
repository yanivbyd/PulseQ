import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import HomePage from "../src/pages/HomePage";
import * as api from "../src/api";

vi.mock("../src/api");

const SUMMARIES = [
  { id: "abc12", title: "How Load Balancers Work", accent: "#0d9488", creation_timestamp: "2026-03-01T00:00:00.000Z" },
];

const renderPage = () => render(<MemoryRouter><HomePage /></MemoryRouter>);

test("shows loading state initially", () => {
  vi.mocked(api.fetchArticleSummaries).mockReturnValue(new Promise(() => {}));
  renderPage();
  expect(screen.getByText("Loading...")).toBeInTheDocument();
});

test("renders article cards on success", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  renderPage();
  await waitFor(() => expect(screen.getByText("How Load Balancers Work")).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "How Load Balancers Work" })).toHaveAttribute("href", "/abc12");
  expect(screen.queryByRole("link", { name: "Home" })).not.toBeInTheDocument();
});

test("renders empty state when no articles", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue([]);
  renderPage();
  await waitFor(() => expect(screen.getByText("No articles yet.")).toBeInTheDocument());
});

test("renders error message on fetch failure", async () => {
  vi.mocked(api.fetchArticleSummaries).mockRejectedValue(new Error("Network error"));
  renderPage();
  await waitFor(() => expect(screen.getByText("Network error")).toBeInTheDocument());
});

