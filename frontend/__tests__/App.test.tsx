import { render, screen } from "@testing-library/react";
import * as api from "../src/api";
import App from "../src/App";

vi.mock("../src/api");

// App uses BrowserRouter internally; jsdom starts at location "/", which renders HomePage.
test("renders home page at /", async () => {
  vi.mocked(api.fetchArticleSummaries).mockResolvedValue([]);
  render(<App />);
  expect(await screen.findByText("Nothing new to read.")).toBeInTheDocument();
});
