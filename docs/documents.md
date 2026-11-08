# Reading Documents and Citing Them

A workflow can be given a PDF or an image, and a step can answer from it,
citing the passage behind each answer. Every citation is checked against the
document's text before it is kept, so an answer that names a passage the
document does not hold never reaches a later step (ADR 0112 to ADR 0117).

This guide reads a two-page insurance claim: first without a model, to see
how Azathoth divides it, then with one, which answers two questions about it
and cites the claim for each. It ends by exporting those citations as
[W3C Web Annotations](https://www.w3.org/TR/annotation-model/), which point
back into the PDF.

This guide covers macOS and Windows. Each command is shown twice:

- for the macOS Terminal (zsh or bash);
- for Windows PowerShell 7.

On Linux, the macOS commands work unchanged.

## What You Need

- Azathoth installed in a venv, as in [Installing Azathoth](install.md), and
  that venv active, with a database initialized.
- A clone of the repository, for the example claim and workflows, as in
  [Getting Started](getting-started.md). Run every command from its root.
- For section 3, an OpenRouter key and an authorized model, as in
  [Connecting OpenRouter](openrouter.md). Sections 1 and 2 need no model.

## 1. Install the Documents Extra

Azathoth reads PDFs with pdfminer.six, an optional extra. Install it into the
venv Azathoth is in:

```bash
python -m pip install "azathoth-ai[documents]"
```

```powershell
python -m pip install "azathoth-ai[documents]"
```

## 2. Divide the Claim Into Segments

`examples/documents/claim.pdf` is the claim. Give it to
`examples/documents/segment-claim.json`, a workflow of one step: the
standard `segment_pdf` tool, which `azathoth init` installed.

```bash
azathoth workflow import examples/documents/segment-claim.json
azathoth workflow run a1000000-0000-4000-8000-0000000000c0 --input-file examples/documents/claim.pdf --output result
```

```powershell
azathoth workflow import examples/documents/segment-claim.json
azathoth workflow run a1000000-0000-4000-8000-0000000000c0 --input-file examples/documents/claim.pdf --output result
```

The PDF goes in by reference. Azathoth checks that its bytes are a PDF,
keeps them in its content store, and gives the workflow a handle naming
their digest. `segment_pdf` divides the PDF into segments, one per text box,
and keeps them as the step's extraction; the run prints the extraction's
handle:

```text
{"extraction": {"tool": "segment_pdf", "version": "1.0.0 (pdfminer.six <PDFMINER_VERSION>; line_overlap=0.5,char_margin=2.0,line_margin=0.5,word_margin=0.1,boxes_flow=0.5)", "digest": "<EXTRACTION_DIGEST>", "source_digest": "9bc3db695946b626972580aa8ed59d6bb008c72f5ca51d79910d22c7feaaa185", "media_type": "application/pdf"}}
```

Each segment has an ID naming its page, and its place on it. A step whose
prompt binds the extraction to a variable, here `claim`, shows it to its
model like this, so the model can cite a segment by its ID:

```text
<source name="claim">
[p1.s1] Claim 0412

[p1.s2] Filed by Ada Marsh, the insured,
on behalf of Marsh Bakery.

[p1.s3] The claim was received on December 14.

[p2.s1] The adjuster inspected the oven on December 19
and found its door hinge cracked.

[p2.s2] Repair is approved up to $1,200.
</source>
```

The extraction names the version of the tool, of pdfminer.six and of the
layout it used, since each can change what is extracted: a run records
exactly what its model was shown.

## 3. Answer From the Claim, Citing It

`examples/documents/answer-from-claim.json` divides the claim the same way,
then asks a model when the claim was received and what repair is approved.
Its second step is a cited step: its prompt shows the extraction, asks for
a citation behind each answer, and names a citation policy:

```json
{
  "output_format": "json",
  "citations": {
    "on_unverified": "fail"
  }
}
```

The prompt tells the model how to cite, in its own words: a citation is any
object of exactly `source`, `segment` and `quote`. The workflow names no
model; the step runs on one you have authorized that reads and writes
text. With your key set, import and run it:

```bash
azathoth workflow import examples/documents/answer-from-claim.json
azathoth workflow run a1000000-0000-4000-8000-0000000000c2 --input-file examples/documents/claim.pdf --output result
```

```powershell
azathoth workflow import examples/documents/answer-from-claim.json
azathoth workflow run a1000000-0000-4000-8000-0000000000c2 --input-file examples/documents/claim.pdf --output result
```

Before the reply is kept, every citation in it is checked against the
segment it names, with no model involved, and replaced by its check. Here
is the first answer, shown on several lines; your model may word its
answers, and choose its quotes, its own way:

```json
{
  "received": {
    "answer": "December 14",
    "citation": {
      "source": "claim",
      "segment": "p1.s3",
      "quote": "received on December 14",
      "status": "verified",
      "anchor": {
        "digest": "9bc3db695946b626972580aa8ed59d6bb008c72f5ca51d79910d22c7feaaa185",
        "media_type": "application/pdf",
        "origin": {
          "uri": "file:///<CHECKOUT>/examples/documents/claim.pdf"
        },
        "selectors": [
          {
            "type": "TextQuoteSelector",
            "exact": "received on December 14",
            "prefix": "of Marsh Bakery.\n\nThe claim was ",
            "suffix": ".\n\nThe adjuster inspected the ov"
          },
          {
            "type": "TextPositionSelector",
            "start": 87,
            "end": 110
          },
          {
            "type": "FragmentSelector",
            "value": "page=1&viewrect=72,182.48,220.74,12",
            "conformsTo": "http://tools.ietf.org/rfc/rfc3778"
          }
        ],
        "extraction": {
          "tool": "segment_pdf",
          "version": "1.0.0 (pdfminer.six <PDFMINER_VERSION>; line_overlap=0.5,char_margin=2.0,line_margin=0.5,word_margin=0.1,boxes_flow=0.5)",
          "digest": "<EXTRACTION_DIGEST>"
        }
      }
    }
  }
}
```

A quote found exactly is `verified`; one found only once curly quotes and
dashes are read as plain ones and runs of whitespace as one space is
`verified_normalized`. Both are verified; case always counts.
The anchor says where the quote is: in which document, by its digest and
the place it was read from, in which words of the extraction, and on which
page, in which rectangle, measured in points from the page's top-left
corner.

Under `on_unverified` `fail`, a citation that is neither fails the step's
attempt, saying why, and the step's retry policy, here two attempts, asks
the model again:

```text
Prompt strategy '<NAME>' cites '<QUOTE>' from segment <SEGMENT> of source '<SOURCE>', which the segment does not hold.
Prompt strategy '<NAME>' cites segment <SEGMENT> of source '<SOURCE>', which has no such segment.
```

Under `keep`, every check is kept, those that failed among them, and what to
make of them is a later step's choice. Either way the checks are kept in the
content store, apart from the reply, so no later step can write `verified`
into a value and have it taken for a check.

## 4. Export the Citations

Every run is recorded. Find the run's ID, then export its citations:

```bash
azathoth workflow runs a1000000-0000-4000-8000-0000000000c2 --limit 1
azathoth run annotations <RUN_ID>
```

```powershell
azathoth workflow runs a1000000-0000-4000-8000-0000000000c2 --limit 1
azathoth run annotations <RUN_ID>
```

`run annotations` prints one W3C Web Annotation collection of every
verified citation the run kept. Each annotation targets the PDF, as the
place it was read from names it, with the anchor's selectors:

```json
{
  "type": "SpecificResource",
  "source": "file:///<CHECKOUT>/examples/documents/claim.pdf",
  "selector": [
    {
      "type": "TextQuoteSelector",
      "exact": "approved up to $1,200",
      "prefix": " door hinge cracked.\n\nRepair is ",
      "suffix": "."
    },
    {
      "type": "TextPositionSelector",
      "start": 205,
      "end": 226
    },
    {
      "type": "FragmentSelector",
      "value": "page=2&viewrect=72,182.48,174.1,12",
      "conformsTo": "http://tools.ietf.org/rfc/rfc3778"
    }
  ]
}
```

Any tool that reads Web Annotations can highlight the passage. A citation
that was not verified is left out, and the collection's label counts it.

## Going Further

- **Documents in S3.** A worker given an `s3://` input records the object's
  version and ETag as the input's origin, so an anchor names the exact
  object even after its key is overwritten, and `invocation show --links`
  follows each verified citation with a presigned link to its page (see
  the [CLI Reference](../src/azathoth/cli/README.md) and
  [Citations](../src/azathoth/citations/README.md#linking-to-citations)).
- **Showing the document itself.** A prompt can show the PDF or an image to
  a model that reads it, beside or instead of its extraction (see
  [Showing Content](../src/azathoth/prompting/README.md#showing-content)).
- **Citations in benchmarks.** A run's citation score is the share of its
  citations that were verified; benchmarks and optimization score it beside
  quality, reliability, latency and cost (see
  [Workflows](../src/azathoth/workflows/README.md)).
- **Contracts.** A workflow can declare the schema of its input and of its
  result, and every production invocation is held to them (see
  [Workflows](../src/azathoth/workflows/README.md)).

## Troubleshooting

**`segment_pdf needs pdfminer.six, which is not installed; install
azathoth-ai[documents].`**: install the extra into the venv Azathoth runs
in, as in section 1. The tool runs with the venv's `python`, so it must be
the venv's.

**`segment_pdf cannot read the document: it is encrypted with a
password.`**: a PDF that needs a password to open cannot be read. One that
only restricts printing or copying opens as any other.

**A cited step fails every attempt**: the model's quotes are not the
document's words. Read the failure, which names the quote and the segment;
a prompt that asks for the words copied exactly, and a model that follows
instructions closely, are the remedy, or `keep`, to see every check.
