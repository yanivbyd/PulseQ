import { render, screen, waitFor, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
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

test("renders article rows on success", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  renderPage();
  await waitFor(() => expect(screen.getByText("How Load Balancers Work")).toBeInTheDocument());
  expect(screen.getByRole("link", { name: "How Load Balancers Work" })).toHaveAttribute("href", "/abc12");
  expect(screen.queryByRole("link", { name: "Home" })).not.toBeInTheDocument();
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

describe("Generate button", () => {
  beforeEach(() => {
    vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  });

  test("button is in idle state on load", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole("button", { name: "Generate" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Generate" })).not.toBeDisabled();
  });

  test("clicking button disables it and shows notification toast on success", async () => {
    vi.mocked(api.triggerGenerate).mockResolvedValue(undefined);
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: "Generate" }));
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/you'll get a notification/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  test("shows error toast and keeps button disabled on failure", async () => {
    vi.mocked(api.triggerGenerate).mockRejectedValue(new Error("Server error"));
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: "Generate" }));
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/Something went wrong/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  test("button re-enables after 60 seconds", async () => {
    vi.useFakeTimers();
    vi.mocked(api.triggerGenerate).mockResolvedValue(undefined);
    renderPage();
    await act(async () => {}); // flush fetchArticleSummaries + React state
    fireEvent.click(screen.getByRole("button", { name: "Generate" }));
    await act(async () => {}); // flush triggerGenerate promise + state updates
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(screen.getByRole("button", { name: "Generate" })).not.toBeDisabled();
    vi.useRealTimers();
  });
});

describe("Scout button", () => {
  beforeEach(() => {
    vi.mocked(api.fetchArticleSummaries).mockResolvedValue(SUMMARIES);
  });

  test("button is in idle state on load", async () => {
    renderPage();
    await waitFor(() => expect(screen.getByRole("button", { name: "Scout" })).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Scout" })).not.toBeDisabled();
  });

  test("clicking button disables it and shows message on success", async () => {
    vi.mocked(api.triggerScout).mockResolvedValue(undefined);
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: "Scout" }));
    await userEvent.click(screen.getByRole("button", { name: "Scout" }));
    await waitFor(() => expect(screen.getByText("Topics are being refreshed.")).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Scout" })).toBeDisabled();
  });

  test("shows error toast and keeps button disabled on failure", async () => {
    vi.mocked(api.triggerScout).mockRejectedValue(new Error("Server error"));
    renderPage();
    await waitFor(() => screen.getByRole("button", { name: "Scout" }));
    await userEvent.click(screen.getByRole("button", { name: "Scout" }));
    await waitFor(() => expect(screen.getByText(/Something went wrong/)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Scout" })).toBeDisabled();
  });

  test("button re-enables after 60 seconds", async () => {
    vi.useFakeTimers();
    vi.mocked(api.triggerScout).mockResolvedValue(undefined);
    renderPage();
    await act(async () => {}); // flush fetchArticleSummaries + React state
    fireEvent.click(screen.getByRole("button", { name: "Scout" }));
    await act(async () => {}); // flush triggerScout promise + state updates
    expect(screen.getByRole("button", { name: "Scout" })).toBeDisabled();
    act(() => { vi.advanceTimersByTime(60_000); });
    expect(screen.getByRole("button", { name: "Scout" })).not.toBeDisabled();
    vi.useRealTimers();
  });
});
