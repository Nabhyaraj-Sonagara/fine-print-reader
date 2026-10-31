---
name: scan-document
description: >
  This skill should be used when the user shares photos or a file of a legal
  document (lease, rental agreement, loan, credit card terms, employment
  contract, offer letter, terms of service, insurance policy) and wants to
  understand it, or asks to "scan this document", "turn these photos into a
  PDF", "make a clean PDF from these pictures", "read the fine print", "what
  am I signing", "is there anything bad in this contract", "check this lease
  for red flags", or "summarize this agreement". It produces a clean cropped
  PDF, a plain-language summary, and a list of risky clauses with exact
  quotes and risk levels.
metadata:
  version: "0.1.0"
---

# Scan Document

Turn photos of a legal document into a clean PDF, a plain-language summary,
and a list of risky clauses. The user needs no legal knowledge. Write
everything the user sees in short, plain sentences.

Bundled files:

- `scripts/scan_to_pdf.py`: crops, straightens, and cleans photos into one PDF.
- `references/red-flag-checklist.md`: the clause categories, risk levels, and
  rules for judging them. Read it in full before flagging anything.
- `references/report-template.md`: the fixed report layout. Follow it exactly.

## Workflow

### 1. Receive

Collect the document from the user.

- **Photos:** treat the order they were sent as the page order. If the order
  is unclear (file names out of sequence, page numbers visible in the wrong
  order), say which order will be used and fix it if the user objects.
- **A PDF or text file** that is already digital: skip steps 2 and 3 and go
  to step 4. The user still gets the summary and flags.
- **Images shown in chat with no file on disk:** the script needs files. Read
  the images directly for the report, and tell the user that attaching the
  photos as files will also produce the clean PDF.

If there is no document yet, ask the user to send clear photos of every page,
taken flat, in good light, with the whole page in the frame.

### 2. Crop and clean

Run the script on all page photos in one call, in page order:

```bash
python3 "${CLAUDE_PLUGIN_ROOT}/skills/scan-document/scripts/scan_to_pdf.py" \
  page1.jpg page2.jpg page3.jpg \
  -o "<output folder>/<short-name>-clean.pdf" \
  --pages-dir "<temp folder>/pages"
```

- Save the PDF to the session's outputs folder if one exists, otherwise to
  the current working directory. Name it after the document, for example
  `lease-clean.pdf`.
- Put `--pages-dir` in a temporary folder. The cleaned page PNGs are for the
  quality check in step 3.
- If `${CLAUDE_PLUGIN_ROOT}` is not set, use the directory this SKILL.md is
  in: the script is at `scripts/scan_to_pdf.py` next to it.
- If Python packages are missing, the script says so. Install them with
  `python3 -m pip install opencv-python-headless pillow numpy`, then run it
  again.

Options:

| Option | When to use |
|---|---|
| `--mode gray` | Default. Best for most documents. |
| `--mode bw` | Very dark or shadowy photos, or when the smallest file is wanted. Gives pure black text on white. |
| `--mode color` | The document has color that matters: stamps, signatures, highlights, colored forms. |
| `--no-crop` | The photos are already cropped scans or screenshots. |
| `--ocr` | Also write a `.txt` file of the text. Needs Tesseract. Optional backup only. |

The script prints JSON with one entry per page: `cropped` (page edges found
or not), `deskew_deg` (how much it straightened the page), and `sharpness`.
Warnings go to stderr:

- `page edges not found; kept the full image.` The page is still in the PDF,
  uncropped. Check it in step 3; this is fine when the page fills the photo.
- `low sharpness`: the photo may be blurry. Check it closely in step 3.

### 3. Check quality

Look at every cleaned page image in the `--pages-dir` folder. For each page,
confirm that:

- the whole page is there, with no text cut off at the edges;
- the text is sharp enough to read every word;
- the page is the right way up.

If a page fails, tell the user which page and what is wrong, and ask for a
new photo of just that page, with a tip (hold the phone flat, more light,
step back so all four corners show). Re-run the script with the new photo
in its place. If the user cannot retake it, continue, and list the problem
under "Unclear or unreadable parts" in the report.

Do not guess at words that cannot be read. Mark them as unreadable.

### 4. Read the text

Read the cleaned page images directly. This is the main way to get the text.
For a digital PDF or text file, read the file.

Use OCR text (from `--ocr`) only as a backup, for example to double-check a
number. If the OCR text and the image disagree, trust the image.

Keep track of which page each clause is on. Page numbers follow photo order.

If the document is not in English, tell the user that this version is built
for English documents. Still deliver the clean PDF. Offer a best-effort
summary only if the user wants it, and say clearly that the risk review may
miss things.

If the document is not a legal document at all (a receipt, a letter, a
menu), deliver the clean PDF and a short summary, and skip the flags.

### 5. Identify the document type

Decide the type from the title and content: lease, loan or credit,
employment, terms of service, insurance, or other (for example NDA, service
contract, purchase agreement, waiver). The type decides which extra checks
in `references/red-flag-checklist.md` apply. If it is unclear, pick the
closest type and say so in the report.

### 6. Summarize

Fill in the Summary and Key facts sections of the template:

- the parties;
- what each side must do;
- the money and the dates;
- how to leave the agreement.

Keep the Summary under 150 words.

### 7. Flag risks

Read `references/red-flag-checklist.md`. Go through the document clause by
clause. Compare each clause with the ten categories and the extra checks for
the document type.

For each flag, record:

1. the risk level (High, Medium, or Low), using the checklist's default level
   and its rules for moving up or down;
2. the exact quote and page number;
3. a plain explanation of what it means for the user;
4. a question the user can ask.

Then verify before writing the report:

- Re-read each quote against the page image. It must match word for word.
  If it does not, fix it or drop the flag. No quote means no flag (the only
  exception is a missing-item flag, as the checklist explains).
- Remove duplicates. If two flags quote the same clause, keep the one with
  the higher risk level and merge the explanations.
- Check the balance. A fair document should not get a long list of flags.
  Drop Low flags that would only add noise.

### 8. Deliver

1. Give the user the clean PDF.
2. Write the report in chat using `references/report-template.md` exactly.
3. Offer, in one line, to save the report as a file (Markdown, Word, or PDF)
   if the user wants to keep or share it. Do not save it unless they ask.

Delete the temporary page images when done.

## Safeguards

- **Not legal advice.** Every report ends with the disclaimer from the
  template. Tell the user to talk to a lawyer or legal aid service for
  high-value documents or High flags they do not understand.
- **Quote, do not invent.** Never put words in quotation marks that are not
  on the page.
- **State uncertainty.** Name the page and part that was hard to read.
- **Local law differs.** The disclaimer says so; repeat it next to any flag
  where enforceability depends heavily on location (non-competes, deposit
  limits, arbitration).
- **Privacy.** Do not save, upload, or share the document or report anywhere
  except the clean PDF the user asked for, unless the user asks.
- **No false comfort.** Never say a document is safe, fair, or fine to sign,
  even when no flags are found.
- **No pressure either way.** Explain risks; do not tell the user whether to
  sign.
