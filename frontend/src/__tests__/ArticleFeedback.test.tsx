import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { vi, describe, test, expect, beforeEach } from "vitest";
import ArticlePage from "../pages/ArticlePage";
import * as api from "../api";

vi.mock("../api", () => ({
  fetchArticle: vi.fn(),
  postFeedback: vi.fn(),
}));

const ARTICLE = {
  id: "abc12",
  title: "Test Article",
  accent: "#0d9488",
  creation_timestamp: "2026-03-05T08:00:00.000Z",
  html: "<p>Hello world</p>",
};

function renderArticlePage(id = "abc12") {
  return render(
    <MemoryRouter initialEntries={[`/${id}`]}>
      <Routes>
        <Route path="/:articleId" element={<ArticlePage />} />
      </Routes>
    </MemoryRouter>,
  );
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchArticle).mockResolvedValue(ARTICLE);
  vi.mocked(api.postFeedback).mockResolvedValue(undefined);
});

function isSelected(el: HTMLElement) {
  return el.className.includes("selected");
}

describe("ArticlePage feedback bar", () => {
  test("renders thumbs up and down buttons after article loads", async () => {
    renderArticlePage();
    expect(await screen.findByLabelText("Like")).toBeInTheDocument();
    expect(screen.getByLabelText("Dislike")).toBeInTheDocument();
  });

  test("clicking like calls postFeedback with correct args and highlights button", async () => {
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.click(screen.getByLabelText("Like"));
    expect(api.postFeedback).toHaveBeenCalledWith("abc12", "Test Article", "like", expect.stringMatching(/^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}/));
    expect(isSelected(screen.getByLabelText("Like"))).toBe(true);
    expect(isSelected(screen.getByLabelText("Dislike"))).toBe(false);
  });

  test("clicking dislike calls postFeedback and highlights dislike", async () => {
    renderArticlePage();
    await screen.findByLabelText("Dislike");
    await userEvent.click(screen.getByLabelText("Dislike"));
    expect(api.postFeedback).toHaveBeenCalledWith("abc12", "Test Article", "dislike", expect.any(String));
    expect(isSelected(screen.getByLabelText("Dislike"))).toBe(true);
  });

  test("clicking the already-selected button does not call postFeedback again", async () => {
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.click(screen.getByLabelText("Like"));
    await userEvent.click(screen.getByLabelText("Like"));
    expect(api.postFeedback).toHaveBeenCalledTimes(1);
  });

  test("switching reaction sends a new postFeedback call", async () => {
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.click(screen.getByLabelText("Like"));
    await userEvent.click(screen.getByLabelText("Dislike"));
    expect(api.postFeedback).toHaveBeenCalledTimes(2);
    expect(isSelected(screen.getByLabelText("Dislike"))).toBe(true);
  });

  test("shows error message and clears selection when postFeedback fails", async () => {
    vi.mocked(api.postFeedback).mockRejectedValue(new Error("network error"));
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.click(screen.getByLabelText("Like"));
    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
    expect(isSelected(screen.getByLabelText("Like"))).toBe(false);
  });
});
