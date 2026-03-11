import { render, screen, fireEvent } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, test, expect } from "vitest";
import HamburgerMenu from "../components/HamburgerMenu";

function renderMenu() {
  return render(<MemoryRouter><HamburgerMenu /></MemoryRouter>);
}

describe("HamburgerMenu", () => {
  test("renders toggle button, menu closed by default", () => {
    renderMenu();
    expect(screen.getByRole("button", { name: "Open menu" })).toBeInTheDocument();
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  test("opens menu with Articles and Topics links on toggle click", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    expect(screen.getByRole("navigation")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Articles" })).toHaveAttribute("href", "/");
    expect(screen.getByRole("link", { name: "Topics" })).toHaveAttribute("href", "/topics");
    expect(screen.getByRole("button", { name: "Close menu" })).toBeInTheDocument();
  });

  test("closes menu on second toggle click", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    await userEvent.click(screen.getByRole("button", { name: "Close menu" }));
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  test("closes menu on Escape key", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  test("closes menu on outside click", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    fireEvent.mouseDown(document.body);
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });

  test("closes menu when a nav link is clicked", async () => {
    renderMenu();
    await userEvent.click(screen.getByRole("button", { name: "Open menu" }));
    await userEvent.click(screen.getByRole("link", { name: "Articles" }));
    expect(screen.queryByRole("navigation")).not.toBeInTheDocument();
  });
});
