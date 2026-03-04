import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import ErrorPage from "../src/pages/ErrorPage";

test("renders 404 and home link", () => {
  render(<MemoryRouter><ErrorPage /></MemoryRouter>);
  expect(screen.getByText("404")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /back to home/i })).toHaveAttribute("href", "/");
});
