import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import ArticlePage from "../src/pages/ArticlePage";
import * as api from "../src/api";

vi.mock("../src/api");

const ARTICLE = {
  id: "abc12",
  title: "How Load Balancers Work",
  accent: "#0d9488",
  creation_timestamp: "2026-03-01T00:00:00.000Z",
  html: '<div class="header-card"><h1>How Load Balancers Work</h1></div>',
};

const renderPage = (articleId = "abc12") =>
  render(
    <MemoryRouter initialEntries={[`/${articleId}`]}>
      <Routes>
        <Route path="/:articleId" element={<ArticlePage />} />
      </Routes>
    </MemoryRouter>,
  );

test("shows loading state initially", () => {
  vi.mocked(api.fetchArticle).mockReturnValue(new Promise(() => {}));
  renderPage();
  expect(screen.getByText("Loading...")).toBeInTheDocument();
});

test("renders article HTML and home FAB, sets page title", async () => {
  vi.mocked(api.fetchArticle).mockResolvedValue(ARTICLE);
  renderPage();
  await waitFor(() => expect(screen.getByText("How Load Balancers Work")).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "Home" })).toHaveAttribute("href", "/");
  expect(document.title).toBe("How Load Balancers Work");
});

test("calls fetchArticle with the route articleId", async () => {
  vi.mocked(api.fetchArticle).mockResolvedValue(ARTICLE);
  renderPage("abc12");
  await waitFor(() => expect(api.fetchArticle).toHaveBeenCalledWith("abc12"));
});

test("renders error message on fetch failure", async () => {
  vi.mocked(api.fetchArticle).mockRejectedValue(new Error("Not found"));
  renderPage();
  await waitFor(() => expect(screen.getByText("Not found")).toBeInTheDocument());
});
