import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { vi, describe, test, expect, beforeEach } from "vitest";
import NewArticlePage from "../pages/NewArticlePage";
import * as api from "../api";

vi.mock("../api", () => ({
  triggerGenerate: vi.fn(),
}));

vi.stubEnv("VITE_USER_ID", "user1");

function renderPage() {
  return render(<MemoryRouter><NewArticlePage /></MemoryRouter>);
}

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.triggerGenerate).mockResolvedValue(undefined);
});

describe("NewArticlePage mode selector", () => {
  test("renders Random and Custom radio buttons, Random selected by default", () => {
    renderPage();
    expect(screen.getByRole("radio", { name: "Random" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Custom" })).not.toBeChecked();
  });

  test("custom topic textarea is hidden in Random mode", () => {
    renderPage();
    expect(screen.queryByRole("textbox", { name: "Custom topic" })).not.toBeInTheDocument();
  });

  test("switching to Custom reveals the textarea", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    expect(screen.getByRole("textbox", { name: "Custom topic" })).toBeInTheDocument();
  });

  test("switching back to Random hides the textarea", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    await userEvent.click(screen.getByRole("radio", { name: "Random" }));
    expect(screen.queryByRole("textbox", { name: "Custom topic" })).not.toBeInTheDocument();
  });
});

describe("NewArticlePage Generate button state", () => {
  test("Generate button is enabled in Random mode", () => {
    renderPage();
    expect(screen.getByRole("button", { name: "Generate" })).not.toBeDisabled();
  });

  test("Generate button is disabled in Custom mode when topic is empty", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  test("Generate button is enabled in Custom mode when topic is non-empty", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Custom topic" }), "AI trends");
    expect(screen.getByRole("button", { name: "Generate" })).not.toBeDisabled();
  });

  test("Generate button is disabled while generating", async () => {
    vi.mocked(api.triggerGenerate).mockImplementation(() => new Promise(() => {}));
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });
});

describe("NewArticlePage API call payload", () => {
  test("Random mode calls triggerGenerate with no argument", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(api.triggerGenerate).toHaveBeenCalledWith(undefined);
  });

  test("Custom mode calls triggerGenerate with the trimmed topic text", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    await userEvent.type(screen.getByRole("textbox", { name: "Custom topic" }), "  quantum computing  ");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(api.triggerGenerate).toHaveBeenCalledWith("quantum computing");
  });

  test("textarea enforces 1000 character maxLength", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("radio", { name: "Custom" }));
    expect(screen.getByRole("textbox", { name: "Custom topic" })).toHaveAttribute("maxLength", "1000");
  });
});

describe("NewArticlePage status messages", () => {
  test("shows success status message after generation and stays on page", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/generating your article/i)).toBeInTheDocument());
    expect(screen.getByRole("heading", { name: "New Article" })).toBeInTheDocument();
  });

  test("shows error status message when generate fails", async () => {
    vi.mocked(api.triggerGenerate).mockRejectedValue(new Error("error"));
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
  });

  test("Generate button stays disabled after successful generation", async () => {
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/generating your article/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Generate" })).toBeDisabled();
  });

  test("Generate button re-enables after a failed generation", async () => {
    vi.mocked(api.triggerGenerate).mockRejectedValue(new Error("error"));
    renderPage();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(screen.getByText(/something went wrong/i)).toBeInTheDocument());
    expect(screen.getByRole("button", { name: "Generate" })).not.toBeDisabled();
  });
});
