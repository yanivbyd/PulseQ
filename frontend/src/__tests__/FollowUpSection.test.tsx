import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { vi, describe, test, expect, beforeEach } from "vitest";
import FollowUpSection from "../components/FollowUpSection";
import * as api from "../api";

vi.mock("../api", () => ({
  triggerFollowUp: vi.fn(),
}));

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(api.triggerFollowUp).mockResolvedValue(undefined);
});

function renderSection(articleId = "abc12") {
  return render(<FollowUpSection articleId={articleId} />);
}

describe("FollowUpSection", () => {
  test("renders textarea with correct placeholder and generate button", async () => {
    renderSection();
    expect(screen.getByLabelText("Follow-up context")).toBeInTheDocument();

    expect(screen.getByRole("button", { name: "Generate Follow-up" })).toBeInTheDocument();
  });

  test("generate button is disabled when textarea is empty", () => {
    renderSection();
    expect(screen.getByRole("button", { name: "Generate Follow-up" })).toBeDisabled();
  });

  test("generate button is enabled when textarea has non-empty text", async () => {
    renderSection();
    await userEvent.type(screen.getByLabelText("Follow-up context"), "focus on regulatory implications");
    expect(screen.getByRole("button", { name: "Generate Follow-up" })).not.toBeDisabled();
  });

  test("textarea enforces maxLength of 1000", () => {
    renderSection();
    expect(screen.getByLabelText("Follow-up context")).toHaveAttribute("maxLength", "1000");
  });

  test("clicking generate calls triggerFollowUp with articleId and trimmed context", async () => {
    renderSection("article-xyz");
    await userEvent.type(screen.getByLabelText("Follow-up context"), "  deep dive on costs  ");
    await userEvent.click(screen.getByRole("button", { name: "Generate Follow-up" }));
    expect(api.triggerFollowUp).toHaveBeenCalledWith("article-xyz", "deep dive on costs");
  });

  test("on success: button is disabled and success message shown", async () => {
    renderSection();
    await userEvent.type(screen.getByLabelText("Follow-up context"), "regulatory angle");
    await userEvent.click(screen.getByRole("button", { name: "Generate Follow-up" }));
    await waitFor(() =>
      expect(screen.getByText(/Generating your follow-up/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Generate Follow-up" })).toBeDisabled();
  });

  test("on error: error message shown and button re-enabled", async () => {
    vi.mocked(api.triggerFollowUp).mockRejectedValue(new Error("network error"));
    renderSection();
    await userEvent.type(screen.getByLabelText("Follow-up context"), "more depth");
    await userEvent.click(screen.getByRole("button", { name: "Generate Follow-up" }));
    await waitFor(() =>
      expect(screen.getByText(/Something went wrong/)).toBeInTheDocument(),
    );
    expect(screen.getByRole("button", { name: "Generate Follow-up" })).not.toBeDisabled();
  });

  test("success message not shown on error; error message not shown on success", async () => {
    vi.mocked(api.triggerFollowUp).mockRejectedValue(new Error("fail"));
    renderSection();
    await userEvent.type(screen.getByLabelText("Follow-up context"), "context");
    await userEvent.click(screen.getByRole("button", { name: "Generate Follow-up" }));
    await waitFor(() => expect(screen.getByText(/Something went wrong/)).toBeInTheDocument());
    expect(screen.queryByText(/Generating your follow-up/)).not.toBeInTheDocument();
  });
});
