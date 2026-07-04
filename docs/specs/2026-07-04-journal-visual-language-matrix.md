# Journal Visual-Language Matrix

Date: 2026-07-04

This matrix records public journal-track source anchors and FigOps encoded
tokens for Nature, Science, ACS, RSC, Elsevier, Wiley, and Cell. It does not
claim latest publisher compliance, complete publisher coverage, or automatic
publishability. Journal-specific feel is captured only where the evidence
supports it; tracks are not forced to look different.

The machine-readable source of this matrix is
`docs/specs/2026-07-04-journal-visual-language-matrix.json`.

## Summary

| Track | Official source entries | Encoded FigOps anchors | Non-official visual language | Deferred or unsupported |
| --- | ---: | --- | --- | --- |
| nature | 2 | 88/180 mm width slots, 5 pt text floor, 0.25 pt line floor, 247 mm height cap | Sparse sans-serif graphs, labelled axes, no decorative effects, accessibility-conscious color | No latest Nature-family compliance claim; no editable-text or font-embedding validation |
| science | 1 | 57/121/184 mm width slots, compact marker and stroke tokens | Compact high-density figures scaled for small final width | No full AAAS production or upload validation |
| acs | 1 | 84.67/177.8 mm width slots, 4.5 pt text floor, 0.5 pt line floor, 233 mm height cap | Chemistry-oriented accessible graphics, non-color-only encodings | No TOC, cover-art, image-manipulation, or ACS title-specific validation |
| rsc | 1 | 83/171 mm width slots, 7 pt text floor, 0.5 pt line floor, 233 mm height cap | Chemistry-publishing layout with legible labels and scale bars | No TOC, AI-figure licensing, or journal-specific exception validation |
| elsevier | 1 | 90/140/190 mm width slots, 7 pt normal-text rule-of-thumb, conservative FigOps line/height defaults | Broad uniform artwork, readable text, larger single-column canvas | No claim for every Elsevier journal-specific guide; no AQC/upload validation |
| wiley | 1 | 85/178 mm FigOps anchors within broad Wiley 80-180 mm source range | Quality-first figures with readable words and symbols | No claim that exact 85/178 mm geometry is a global Wiley rule |
| cell | 1 | 85/114/174 mm width slots, 6 pt text floor, 0.5 pt line floor, 200 mm height cap | Biomedical canvas with moderate line and marker scale | Official URL was Cloudflare-challenged; no latest Cell Press compliance claim |

## Official Submission Constraints

### Nature

- Official sources:
  - `https://research-figure-guide.nature.com/figures/preparing-figures-our-specifications/`
  - `https://www.nature.com/ncomms/submit/how-to-submit`
- Source date: 2026-07-04.
- Official constraints recorded:
  - Minimum graph text size of 5 pt.
  - Standard sans-serif fonts such as Arial or Helvetica.
  - Axes labelled with units, with axis lines and tick marks.
  - Avoid background gridlines, decorative effects, overlapping text, hard-to-read backgrounds, and reliance on colored text alone.
  - Nature Communications width anchors of 88 mm single column and 180 mm double column.

### Science

- Official source: `https://www.science.org/content/page/instructions-preparing-initial-manuscript`
- Source date: 2026-07-04.
- Official constraints recorded:
  - Printed figure widths usually use 5.7 cm, 12.1 cm, or 18.4 cm.
  - Other encoded floors remain FigOps safety defaults unless independently confirmed against a current official source.

### ACS

- Official source: `https://researcher-resources.acs.org/publish/author_guidelines?coden=cmatex`
- Source date: 2026-07-04.
- Official constraints recorded:
  - Single-column graphics up to 240 pt wide.
  - Double-column graphics between 300 pt and 504 pt wide.
  - Maximum graphics depth of 660 pt including caption allowance.
  - Lettering no smaller than 4.5 pt.
  - Helvetica or Arial work well for lettering.
  - Lines no thinner than 0.5 pt.
  - Avoid relying on color alone.

### RSC

- Official source: `https://www.rsc.org/publishing/publish-with-us/publish-a-journal-article/rsc-advances`
- Source date: 2026-07-04.
- Official constraints recorded:
  - Figures, schemes, and charts as TIFF at 600 dpi or greater; EPS or PDF can be supplied instead.
  - Images fit 8.3 cm single-column or 17.1 cm double-column width.
  - Images no longer than 23.3 cm and not larger than a single page.
  - Text, numerical data, and scale bars clearly legible.
  - Chemical-structure captions or atom labels use Arial/Helvetica 7 pt and 0.5 pt bond width.

### Elsevier

- Official source: `https://www.elsevier.com/about/policies-and-standards/author/artwork-and-media-instructions/artwork-sizing`
- Source date: 2026-07-04.
- Official constraints recorded:
  - Check the journal-specific guide for authors because some Elsevier journals have special instructions.
  - Normal text generally finishes at 7 pt, with subscripts and superscripts no smaller than 6 pt; Elsevier describes this as a rule of thumb.
  - Bitmap targets include 300 dpi halftone, 500 dpi combination art, and 1000 dpi line art.
  - Target sizes include 90 mm single column, 140 mm 1.5 column, and 190 mm double column.

### Wiley

- Official source: `https://authors.wiley.com/author-resources/Journal-Authors/Prepare/manuscript-preparation-guidelines.html/figure-preparation.html`
- Source date: 2026-07-04.
- Official constraints recorded:
  - All words and symbols should be large enough for easy reading.
  - Individual figure files should be less than 10 MB.
  - Figures should be created between 80 mm and 180 mm wide and between 300 dpi and 600 dpi.
  - Line art is preferably PDF and 600 dpi; images are preferably PNG or TIFF and 300 dpi.

### Cell

- Official source: `https://www.cell.com/figureguidelines`
- Source date: 2026-07-04.
- Access note: generic fetch and the Tier 1 blocked-site fetcher were challenged
  by Cloudflare in this session. The official publisher URL is recorded as the
  source anchor, but this matrix does not claim latest Cell Press revalidation.
- Encoded source anchors retained from FigOps:
  - 85 mm single column, 114 mm one-and-a-half column, and 174 mm full width.
  - 6 pt minimum type size, 0.5 pt minimum line weight, and 200 mm maximum figure height.

## Encoded FigOps Tokens

All encoded token values are taken from
`themes/style_profiles.py` `TARGET_FORMAT_PROFILE_TOKENS[*]["baseline"]` and
the post-release QA anchor in
`docs/specs/2026-07-04-post-release-total-qa-plan.md`.

| Track | Width mm | Height mm | Column widths mm | Min font pt | Min line pt | Max height mm | Marker pt | Line pt | Error line pt | Violin width |
| --- | ---: | ---: | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| nature | 88.0 | 71.0 | single 88.0; double/full 180.0 | 5.0 | 0.25 | 247.0 | 3.2 | 1.2 | 0.8 | 0.52 |
| science | 57.0 | 45.6 | single 57.0; double 121.0; full/triple 184.0 | 5.0 | 0.5 | 234.0 | 3.0 | 0.9 | 0.7 | 0.48 |
| acs | 84.67 | 67.736 | single 84.67; double/full 177.8 | 4.5 | 0.5 | 233.0 | 3.4 | 1.0 | 0.75 | 0.5 |
| rsc | 83.0 | 66.4 | single 83.0; one_half/double/full/triple 171.0 | 7.0 | 0.5 | 233.0 | 3.3 | 1.0 | 0.75 | 0.5 |
| elsevier | 90.0 | 72.0 | single 90.0; one_half 140.0; double/full/triple 190.0 | 7.0 | 0.5 | 234.0 | 3.6 | 1.05 | 0.8 | 0.5 |
| wiley | 85.0 | 68.0 | single 85.0; double/full 178.0 | 5.0 | 0.5 | 234.0 | 3.5 | 1.0 | 0.8 | 0.5 |
| cell | 85.0 | 68.0 | single 85.0; one_half 114.0; double/full/triple 174.0 | 6.0 | 0.5 | 200.0 | 3.4 | 1.0 | 0.8 | 0.5 |

Encoded tokens are not labelled official publisher claims. Width, text, line,
and height values may align with official sources, but FigOps marker, jitter,
KDE, colormap, and some safety-floor values are local implementation choices.

## Observed Visual Language

Every item in this section is non-official. These are visual-language
heuristics for implementation and review, not publisher requirements.

| Track | Non-official heuristic |
| --- | --- |
| nature | Clean, sparse graph treatment with labelled axes, standard sans-serif text, minimal decorative features, and accessibility-conscious color. |
| science | Compact, high-density graphics with reduced marker, error-cap, and jitter sizes for small final width. |
| acs | Chemistry-oriented graphics with clear sans-serif lettering and non-color-only encodings. |
| rsc | Chemistry-publishing layout with clear scale bars, legible labels, and a higher text floor. |
| elsevier | Broad uniform artwork with readable normal text and slightly larger marks for the 90 mm single-column canvas. |
| wiley | Quality-first figure handling over a broad width range, with readable words and symbols. |
| cell | Biomedical figure canvas with 85/114/174 mm slots and moderate line/marker scale; no decorative differentiation is forced. |

## Unsupported Or Deferred

- No claim of latest publisher compliance.
- No automatic publishability verdict.
- No file-format, resolution, upload, image-integrity, AI-figure licensing, font-embedding, editable-text, scale-bar, or panel-label hard gate is added by this matrix.
- No code changes are made by this task.
- Cell official source access was Cloudflare-challenged in this session; the official URL and existing FigOps source anchor are recorded, but latest-rule revalidation is deferred.
