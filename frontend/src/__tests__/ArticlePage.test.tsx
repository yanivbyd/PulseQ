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

describe("ArticlePage bottom bar", () => {
  test("renders a home link in the bottom bar", async () => {
    renderArticlePage();
    const homeLink = await screen.findByRole("link", { name: "Home" });
    expect(homeLink).toHaveAttribute("href", "/");
  });
});

describe("ArticlePage feedback bar", () => {
  test("renders reaction buttons and free-text textarea independently on load", async () => {
    renderArticlePage();
    expect(await screen.findByLabelText("Like")).toBeInTheDocument();
    expect(screen.getByLabelText("Dislike")).toBeInTheDocument();
    expect(screen.getByLabelText("Anything to add?")).toBeInTheDocument();
  });

  test("clicking like calls postFeedback with reaction content; textarea state unaffected", async () => {
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.type(screen.getByLabelText("Anything to add?"), "some text");
    await userEvent.click(screen.getByLabelText("Like"));
    expect(api.postFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ articleId: "abc12", articleTitle: "Test Article" }),
      { type: "reaction", reaction: "like" },
    );
    expect(isSelected(screen.getByLabelText("Like"))).toBe(true);
    // Free-text textarea still has its text
    expect(screen.getByLabelText("Anything to add?")).toHaveValue("some text");
  });

  test("clicking dislike calls postFeedback with dislike content and highlights dislike", async () => {
    renderArticlePage();
    await screen.findByLabelText("Dislike");
    await userEvent.click(screen.getByLabelText("Dislike"));
    expect(api.postFeedback).toHaveBeenCalledWith(
      expect.objectContaining({ articleId: "abc12" }),
      { type: "reaction", reaction: "dislike" },
    );
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

  test("submit button is disabled when textarea is empty, enabled when non-empty", async () => {
    renderArticlePage();
    await screen.findByLabelText("Like");
    const submitBtn = screen.getByRole("button", { name: "Submit" });
    expect(submitBtn).toBeDisabled();
    await userEvent.type(screen.getByLabelText("Anything to add?"), "hello");
    expect(submitBtn).not.toBeDisabled();
  });

  test("submitting free text calls postFeedback with freeText content and clears textarea; reaction state unaffected", async () => {
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.click(screen.getByLabelText("Like"));
    const textarea = screen.getByLabelText("Anything to add?");
    await userEvent.type(textarea, "Great article");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(textarea).toHaveValue(""));
    expect(api.postFeedback).toHaveBeenLastCalledWith(
      expect.objectContaining({ articleId: "abc12", articleTitle: "Test Article" }),
      { type: "freeText", text: "Great article" },
    );
    // Reaction selection is unaffected
    expect(isSelected(screen.getByLabelText("Like"))).toBe(true);
  });

  test("reaction error and free-text error are shown independently", async () => {
    vi.mocked(api.postFeedback)
      .mockRejectedValueOnce(new Error("reaction network error"))
      .mockRejectedValueOnce(new Error("freetext network error"));

    renderArticlePage();
    await screen.findByLabelText("Like");

    // Trigger reaction error
    await userEvent.click(screen.getByLabelText("Like"));
    await waitFor(() => expect(screen.getAllByText(/something went wrong/i)).toHaveLength(1));
    expect(isSelected(screen.getByLabelText("Like"))).toBe(false);

    // Now trigger free-text error — reaction error area should not duplicate
    await userEvent.type(screen.getByLabelText("Anything to add?"), "test");
    await userEvent.click(screen.getByRole("button", { name: "Submit" }));
    await waitFor(() => expect(screen.getAllByText(/something went wrong/i)).toHaveLength(2));
  });

  test("shows reaction error and clears selection when postFeedback fails for reaction", async () => {
    vi.mocked(api.postFeedback).mockRejectedValue(new Error("network error"));
    renderArticlePage();
    await screen.findByLabelText("Like");
    await userEvent.click(screen.getByLabelText("Like"));
    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
    expect(isSelected(screen.getByLabelText("Like"))).toBe(false);
  });
});
