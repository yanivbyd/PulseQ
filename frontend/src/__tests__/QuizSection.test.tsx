import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, test, expect } from "vitest";
import QuizSection from "../components/QuizSection";
import type { QuizQuestion } from "../api";

const QUIZ: QuizQuestion[] = [
  { q: "What protocol?", options: ["QUIC", "TCP", "WebRTC"], answer: 0 },
];

const TWO_QUESTION_QUIZ: QuizQuestion[] = [
  { q: "What protocol?", options: ["QUIC", "TCP", "WebRTC"], answer: 0 },
  { q: "What layer?", options: ["Transport", "Network", "Application"], answer: 2 },
];

describe("QuizSection", () => {
  test("renders nothing when quiz is empty", () => {
    const { container } = render(<QuizSection quiz={[]} />);
    expect(container.firstChild).toBeNull();
  });

  test("renders card with title and question text", () => {
    render(<QuizSection quiz={QUIZ} />);
    expect(screen.getByText("Test your knowledge")).toBeInTheDocument();
    expect(screen.getByText("What protocol?")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /QUIC/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /TCP/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /WebRTC/i })).toBeInTheDocument();
  });

  test("clicking correct answer shows ✓ on that option", async () => {
    render(<QuizSection quiz={QUIZ} />);
    await userEvent.click(screen.getByRole("button", { name: /QUIC/i }));
    expect(screen.getByRole("button", { name: /QUIC/ })).toHaveTextContent("✓");
  });

  test("clicking wrong answer shows ✗ on selected option and highlights correct option", async () => {
    render(<QuizSection quiz={QUIZ} />);
    await userEvent.click(screen.getByRole("button", { name: /TCP/i }));
    expect(screen.getByRole("button", { name: /TCP/ })).toHaveTextContent("✗");
    // Correct option (QUIC) has the correct highlight class
    const quicBtn = screen.getByRole("button", { name: /QUIC/ });
    expect(quicBtn.className).toContain("correct");
  });

  test("changing answer updates the indicator to reflect the new selection", async () => {
    render(<QuizSection quiz={QUIZ} />);
    // Click wrong answer first
    await userEvent.click(screen.getByRole("button", { name: /TCP/i }));
    expect(screen.getByRole("button", { name: /TCP/ })).toHaveTextContent("✗");
    // Now click the correct answer
    await userEvent.click(screen.getByRole("button", { name: /QUIC/i }));
    expect(screen.getByRole("button", { name: /QUIC/ })).toHaveTextContent("✓");
    // TCP no longer shows ✗
    expect(screen.getByRole("button", { name: /^TCP$/ })).not.toHaveTextContent("✗");
  });

  test("each question tracks its selected answer independently", async () => {
    render(<QuizSection quiz={TWO_QUESTION_QUIZ} />);
    // Answer question 1 correctly (QUIC, index 0)
    await userEvent.click(screen.getByRole("button", { name: /QUIC/i }));
    // Answer question 2 wrongly (Transport, index 0; correct is Application, index 2)
    await userEvent.click(screen.getByRole("button", { name: /Transport/i }));

    expect(screen.getByRole("button", { name: /QUIC/ })).toHaveTextContent("✓");
    expect(screen.getByRole("button", { name: /Transport/ })).toHaveTextContent("✗");
    // Question 2's correct option is highlighted; question 1's others are not
    expect(screen.getByRole("button", { name: /Application/ }).className).toContain("correct");
  });
});
