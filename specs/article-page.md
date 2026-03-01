# Spec: Article Web Page with Shareable Link

## Questions for Clarification

### Q1 (one-way-door candidate): Where should the page be hosted?
Options range from zero-infrastructure (GitHub Pages, a raw S3 public URL) to running a proper server (Next.js on Vercel/Amplify). Choosing a hosting platform now could tie the article URL structure and deployment workflow to that platform permanently.

> Answer: github pages

**Answer:** Yes — **GitHub Pages** is the simplest option available right now:
- You already have a GitHub repo (`PulseQ`)
- Enable GitHub Pages on the repo → files placed under `docs/` are served at `https://<username>.github.io/PulseQ/<filename>`
- Zero infrastructure, no AWS account, no CDK, no cost
- The short-ID filename becomes the URL: `docs/x7k2q.html` → `https://<username>.github.io/PulseQ/x7k2q.html`
- Fully reversible: when the AWS stack is ready, the same HTML file moves to S3+CloudFront with no changes


> GitHub Pages

---

### Q2 (one-way-door candidate): Should this use the future Next.js frontend, or be a standalone page?
Starting with Next.js scaffolds the full frontend now and commits us to that framework and its deployment model. A standalone HTML file is self-contained, fast, and can later be absorbed into any framework.

> Start with a standalone HTML, unless it's too complex

**Answer:** Standalone HTML it is. A single `.html` file with inline CSS, no framework, no build step.

---

### Q3: Should the URL be human-readable (slug) or opaque (short ID)?

> Short ID — it is planned as personalized content

**Answer:** Short ID. The HTML filename is the ID (e.g. `x7k2q.html`). The shareable link is the direct file URL.

---

### Q4: Is the goal to render `article.txt` specifically, or to build the reusable article viewer for all future PulseQ briefs?

> Start simplest with this article

**Answer:** One-off page for this specific article. No reusability requirements at this stage.

---

## Approach

A single hand-written HTML file (`docs/x7k2q.html`) containing:
- The article content from `article.txt`, converted to HTML manually
- Inline CSS only — no external dependencies, no JavaScript
- Mobile-first layout (max-width 680px, comfortable line height)
- `prefers-color-scheme` for dark/light mode

The file is placed in `docs/` so GitHub Pages serves it at a public URL.

### What this avoids committing to
- No hosting platform lock-in — the file works on S3, Netlify, Vercel, or any static host unchanged
- No frontend framework decision
- No URL scheme tied to a database
- No build tooling or scripts

### File layout
```
docs/
  x7k2q.html    ← the article page (short ID is the filename)
```

### Styling goals
- `max-width: 680px`, centered, comfortable `line-height: 1.7`
- System font stack (no web fonts)
- Inline `<style>` block — page is fully self-contained
- Dark/light via `@media (prefers-color-scheme: dark)`
- Article title as `<h1>`, sections as `<h2>`, code blocks styled

---

## Commit Plan

- `add: article page and GitHub Pages setup` — adds `docs/x7k2q.html` (the styled article page) and enables GitHub Pages via the `docs/` folder on `main`
