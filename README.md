# Fine Print Reader

A Claude plugin that reads legal documents for you. Send photos of a lease,
loan, job contract, terms of service, or insurance policy, and get back:

1. **A clean PDF**: pages cropped, straightened, and cleaned of shadows.
2. **A plain-language summary**: who, what, money, dates, and how to leave.
3. **A list of risky clauses**: each with the exact quote, what it means for
   you, a High / Medium / Low risk level, and a question to ask before signing.

> This plugin is a reading aid, not legal advice. Laws differ by country and
> state. For important documents, talk to a lawyer or legal aid service.

## Install

### Claude Code

```
/plugin marketplace add Nabhyaraj-Sonagara/fine-print-reader
/plugin install fine-print-reader@fine-print-reader
```

The photo cleanup needs three Python packages:

```bash
python3 -m pip install opencv-python-headless pillow numpy
```

### Claude desktop app (Cowork)

Download the `.plugin` file from the
[Releases](https://github.com/Nabhyaraj-Sonagara/fine-print-reader/releases)
page if one is available, or zip the `fine-print-reader/` folder's contents
into `fine-print-reader.plugin`, then upload it in Cowork.

## Use

Send photos of every page, in order, and ask something like:

- "What am I signing? Here's my lease."
- "Turn these photos into a clean PDF."
- "Check this contract for red flags."

Already have a digital PDF? Send that instead and skip the scanning step.

**Photo tips:** lay the page flat, use even light, and keep all four corners
in the frame.

## What's inside

```
fine-print-reader/
├── .claude-plugin/plugin.json
├── skills/scan-document/
│   ├── SKILL.md                         # the workflow, photo to report
│   ├── references/red-flag-checklist.md # 10 risk types + per-document checks
│   ├── references/report-template.md    # fixed report layout
│   └── scripts/scan_to_pdf.py           # crop, straighten, clean, make PDF
└── README.md
```

See [fine-print-reader/README.md](fine-print-reader/README.md) for script
options and requirements.

## License

[MIT](LICENSE)
