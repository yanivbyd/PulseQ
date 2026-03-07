import { render, screen, act, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, test, expect, beforeEach, afterEach } from "vitest";
import TopicsPage from "../pages/TopicsPage";
import * as api from "../api";

vi.mock("../api", () => ({
  fetchTopics: vi.fn(),
  triggerScout: vi.fn(),
}));

vi.stubEnv("VITE_USER_ID", "user1");

const TOPICS: api.Topic[] = [
  { title: "AI News", description: "Latest AI" },
  { title: "Cloud Computing", description: "Cloud updates" },
];

function renderTopicsPage() {
  return render(<MemoryRouter><TopicsPage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.fetchTopics).mockResolvedValue(TOPICS);
  vi.mocked(api.triggerScout).mockResolvedValue(undefined);
});

afterEach(() => {
  vi.useRealTimers();
});

describe("TopicsPage topic list", () => {
  test("renders topic titles", async () => {
    renderTopicsPage();
    expect(await screen.findByText("AI News")).toBeInTheDocument();
    expect(screen.getByText("Cloud Computing")).toBeInTheDocument();
  });

  test("shows empty state when no topics", async () => {
    vi.mocked(api.fetchTopics).mockResolvedValue([]);
    renderTopicsPage();
    expect(await screen.findByText("No topics configured.")).toBeInTheDocument();
  });

  test("shows error state when fetch fails", async () => {
    vi.mocked(api.fetchTopics).mockRejectedValue(new Error("network failure"));
    renderTopicsPage();
    expect(await screen.findByText("network failure")).toBeInTheDocument();
  });

  test("calls fetchTopics with userId on mount", async () => {
    renderTopicsPage();
    await screen.findByText("AI News");
    expect(api.fetchTopics).toHaveBeenCalledWith("user1");
  });
});

describe("TopicsPage bottom bar", () => {
  test("renders home link and refresh button", async () => {
    renderTopicsPage();
    await screen.findByText("AI News");
    expect(screen.getByRole("link", { name: "Home" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Refresh Topics" })).toBeInTheDocument();
  });

  test("home link points to /", async () => {
    renderTopicsPage();
    const link = await screen.findByRole("link", { name: "Home" });
    expect(link).toHaveAttribute("href", "/");
  });
});

describe("TopicsPage refresh", () => {
  test("clicking Refresh Topics triggers scout and shows toast", async () => {
    const user = userEvent.setup();
    renderTopicsPage();
    await screen.findByText("AI News");
    await user.click(screen.getByRole("button", { name: "Refresh Topics" }));
    expect(api.triggerScout).toHaveBeenCalledTimes(1);
    expect(screen.getByText("Topics are being refreshed.")).toBeInTheDocument();
  });

  test("shows error toast when triggerScout fails", async () => {
    const user = userEvent.setup();
    vi.mocked(api.triggerScout).mockRejectedValue(new Error("network error"));
    renderTopicsPage();
    await screen.findByText("AI News");
    await user.click(screen.getByRole("button", { name: "Refresh Topics" }));
    expect(screen.getByText(/something went wrong/i)).toBeInTheDocument();
  });

  test("Refresh button is disabled after clicking", async () => {
    vi.useFakeTimers();
    renderTopicsPage();
    await act(async () => {}); // flush initial fetchTopics + state
    fireEvent.click(screen.getByRole("button", { name: "Refresh Topics" }));
    await act(async () => {}); // flush triggerScout + state updates
    expect(screen.getByRole("button", { name: "Refresh Topics" })).toBeDisabled();
  });
});

describe("TopicsPage polling", () => {
  test("polls and shows 'Topics updated' when titles change", async () => {
    vi.useFakeTimers();
    const updatedTopics: api.Topic[] = [
      ...TOPICS,
      { title: "Kubernetes", description: "K8s updates" },
    ];
    vi.mocked(api.fetchTopics)
      .mockResolvedValueOnce(TOPICS)         // initial load
      .mockResolvedValueOnce(TOPICS)         // poll 1 — no change
      .mockResolvedValueOnce(updatedTopics); // poll 2 — changed

    renderTopicsPage();
    await act(async () => {}); // flush initial fetchTopics

    fireEvent.click(screen.getByRole("button", { name: "Refresh Topics" }));
    await act(async () => {}); // flush triggerScout

    // Poll 1 — no change
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    // Poll 2 — change detected
    await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });

    expect(screen.getByText("Topics updated (2 \u2192 3)")).toBeInTheDocument();
    expect(screen.getByText("Kubernetes")).toBeInTheDocument();
  });

  test("shows 'Topics unchanged' after 10 polls with no change", async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchTopics).mockResolvedValue(TOPICS); // always same

    renderTopicsPage();
    await act(async () => {}); // flush initial fetchTopics

    fireEvent.click(screen.getByRole("button", { name: "Refresh Topics" }));
    await act(async () => {}); // flush triggerScout

    for (let i = 0; i < 10; i++) {
      await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    }

    expect(screen.getByText("Topics unchanged \u2014 try again later.")).toBeInTheDocument();
  });

  test("shows 'Topics unchanged' after 10 polls when fetchTopics throws each time", async () => {
    vi.useFakeTimers();
    vi.mocked(api.fetchTopics)
      .mockResolvedValueOnce(TOPICS) // initial load
      .mockRejectedValue(new Error("network error")); // all polls throw

    renderTopicsPage();
    await act(async () => {}); // flush initial fetchTopics

    fireEvent.click(screen.getByRole("button", { name: "Refresh Topics" }));
    await act(async () => {}); // flush triggerScout

    for (let i = 0; i < 10; i++) {
      await act(async () => { await vi.advanceTimersByTimeAsync(3_000); });
    }

    expect(screen.getByText("Topics unchanged \u2014 try again later.")).toBeInTheDocument();
  });
});
