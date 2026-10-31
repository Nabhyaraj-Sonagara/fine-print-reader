# Fine Print Reader

Turn phone photos of a legal document into:

1. **A clean PDF**: pages cropped, straightened, and cleaned of shadows.
2. **A plain-language summary**: who, what, money, dates, and how to leave.
3. **A list of risky clauses**: each with the exact quote, what it means,
   a High/Medium/Low risk level, and a question to ask before signing.

It works on leases, loans, employment contracts, terms of service, insurance
policies, and other agreements. No legal knowledge is needed.

> This plugin is a reading aid, not legal advice. Laws differ by country and
> state. For important documents, talk to a lawyer or legal aid service.

## How to use

Send photos of every page (in order) and say something like:

- "What am I signing? Here's my lease."
- "Turn these photos into a clean PDF."
- "Check this contract for red flags."

You can also send a PDF or text file that is already digital. You'll get the
summary and flags, with no scanning step.

**Tips for good photos:** lay the page flat, use even light, and keep all
four corners in the frame. A dark or busy background behind the page helps
the cropping.

## What's inside

| Component | Purpose |
|---|---|
| Skill: `scan-document` | The full workflow, from photo to report |
| Reference: red-flag checklist | 10 risky clause types plus extra checks for leases, loans, jobs, terms of service, and insurance |
| Reference: report template | The fixed layout of the report |
| Script: `scan_to_pdf.py` | Crop, straighten, clean, and build the PDF |

## Requirements

- Python 3.9 or newer
- Python packages: `opencv-python-headless`, `pillow`, `numpy`

  ```bash
  python3 -m pip install opencv-python-headless pillow numpy
  ```

- Optional: [Tesseract](https://github.com/tesseract-ocr/tesseract) for a
  backup text file (`--ocr`). Claude reads the page images directly, so this
  is not required.
- Optional: `pillow-heif` for iPhone HEIC photos on Windows or Linux. On
  macOS, HEIC is converted with the built-in `sips` tool.

## Using the script on its own

```bash
python3 skills/scan-document/scripts/scan_to_pdf.py page1.jpg page2.jpg -o out.pdf
```

| Option | Effect |
|---|---|
| `--mode gray` | Default. Clean grayscale. |
| `--mode bw` | Pure black and white. Best for dark photos; smallest files. |
| `--mode color` | Keeps color (stamps, signatures, highlights). |
| `--no-crop` | Skip edge detection for photos that are already cropped. |
| `--ocr` | Also write `out.txt` with the text (needs Tesseract). |
| `--pages-dir DIR` | Also save each cleaned page as a PNG. |

The script prints a JSON summary per page. If it cannot find a page's edges,
it keeps the full photo and prints a warning instead of failing.

## Version 1 scope

- English documents only
- One or many pages per run
- Nothing is saved between sessions, and nothing is signed or sent

## Ideas for later

More languages, comparing two versions of a document, a negotiation helper
that drafts change requests, deadline extraction, and report export to Word
or PDF.
