# DecompRCA project page

Project page for *Where Root Cause Analysis Fails: A Retrieval-Reranking Decomposition* (NeurIPS 2026).
Static HTML, no build step. Built on the [Academic Project Page Template](https://github.com/eliahuhorwitz/Academic-project-page-template) (CC BY-SA 4.0).

## Files

- `index.html`: page content and meta tags
- `static/css/index.css`, `static/css/bulma.min.css`: template styles (unchanged)
- `static/js/fontawesome.all.min.js`: icons (rendered as inline SVG; no webfonts needed)
- `static/css/decomp.css`: styles for the failure ledger, saturation explorer, findings and results table
- `static/js/index.js`: template helpers (BibTeX copy, scroll-to-top); carousel and More Works code removed
- `static/js/teaser.js`: animated teaser (illustrative, not a dataset case). Part 1: direct vs propagating fault ranked by magnitude. Part 2: two cases of the propagating fault with a Retrieval / Reranking scorecard (A: retrieval failure, B: reranking failure). Text and timings are in `NARR` and `T` at the top
- `static/js/decomp.js`: interactive figures; all numbers are copied from the camera-ready tables and `method/results/retrieval_saturation.csv`
- `static/images/overview.png`: Figure 1, rendered from `figures/overview_neurips.pdf`
- `static/images/social_preview.png`: 1200x630 link-preview image

## Later

- Add an OpenReview button once the forum is public
- Replace the BibTeX entry with the official proceedings entry

## Deploy on GitHub Pages

Option A: push these files to a `gh-pages` branch of `cruiseresearchgroup/DecompRCA`, then
Settings → Pages → Deploy from branch → `gh-pages` / root.

Option B: put them in a `docs/` folder on `main` and choose `main` / `docs`.

Preview locally with `python3 -m http.server` in this folder.
