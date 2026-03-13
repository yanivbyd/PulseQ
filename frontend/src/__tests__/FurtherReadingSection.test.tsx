import { render, screen } from "@testing-library/react";
import { describe, test, expect } from "vitest";
import FurtherReadingSection from "../components/FurtherReadingSection";
import type { FurtherReadingItem } from "../api";

const ITEMS: FurtherReadingItem[] = [
  { url: "https://example.com/post1", title: "Post One" },
  { url: "https://example.com/post2", title: "Post Two" },
];

describe("FurtherReadingSection", () => {
  test("renders nothing when list is empty", () => {
    const { container } = render(<FurtherReadingSection furtherReading={[]} />);
    expect(container.firstChild).toBeNull();
  });

  test("renders section heading and all links when items are provided", () => {
    render(<FurtherReadingSection furtherReading={ITEMS} />);
    expect(screen.getByText(/Further Reading/i)).toBeInTheDocument();
    const links = screen.getAllByRole("link");
    expect(links).toHaveLength(2);
    expect(links[0]).toHaveTextContent("Post One");
    expect(links[0]).toHaveAttribute("href", "https://example.com/post1");
    expect(links[1]).toHaveTextContent("Post Two");
    expect(links[1]).toHaveAttribute("href", "https://example.com/post2");
  });

  test("links open in a new tab with noopener noreferrer", () => {
    render(<FurtherReadingSection furtherReading={ITEMS} />);
    for (const link of screen.getAllByRole("link")) {
      expect(link).toHaveAttribute("target", "_blank");
      expect(link).toHaveAttribute("rel", "noopener noreferrer");
    }
  });
});
