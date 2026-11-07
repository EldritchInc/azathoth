# ADR 0115: Multimodal Prompts

- Status: Accepted
- Date: 2026-11-07
- Decided in: #140

## Context

A workflow can be given a PDF or an image, kept in the content store and
named by a content handle (ADR 0112), and a tool can read it as a file
(ADR 0114). A model step cannot yet see it: a prompt is text, and a handle
bound to a template variable is rendered into it as JSON, digest and all,
which tells a model nothing about the document.

Models that read images and PDFs are common, through OpenRouter and through
Bedrock, and their catalogs already say which input modalities each one
takes. What a prompt lacks is a way to show content, and a way to give a
provider the bytes without putting them where prompts are kept.

## Decision

### A prompt is its text, or its parts

A `Prompt` is its `text`, as it always was, or, when it shows a model
content, its `parts`: text and content in order, as many of each as it
needs.

```json
{"parts": [
  {"text": "Here is the claim form:\n"},
  {"content": {"digest": "<SHA-256>", "media_type": "application/pdf", "size_bytes": 482113}},
  {"text": "\nand the photo of the damage:\n"},
  {"content": {"digest": "<SHA-256>", "media_type": "image/jpeg", "size_bytes": 201554}},
  {"text": "\nDoes the photo match the damage the form describes?"}
]}
```

A content part is a content handle. A text part is never empty. A prompt
holds its text or its parts, never both, so it says what it holds once, and
a prompt of parts shows at least one piece of content: a prompt of text
alone holds it as its text. A prompt of text serializes as `{"text": ...}`,
as before, so no existing document's digest changes.

```text
A prompt holds its text, or parts that show content.
A prompt holds its text or its parts, not both.
A prompt's parts show content; a prompt of text alone holds it as its text.
```

### Content reaches a prompt through a template variable

A template variable whose value is exactly one content handle shows the
model that content where the variable stands; the template's text around it
becomes text parts, and a variable used twice shows its content twice. Any
other value is rendered as it always was: a list of handles, or a handle
with more keys, is JSON. A template that shows no content renders text.

While a template is formatted, each content variable stands as a marker
holding a random token drawn for that one rendering, so no text a bound
value carries can stand for content.

A fixed prompt cannot show content: a handle written into a workflow
document would name content no run was ever given. A prompt strategy whose
fixed prompt holds content parts is refused:

```text
Prompt strategy '<NAME>' shows content in a fixed prompt; content reaches a prompt only through a template variable bound to a content handle.
```

### Bytes are read as a prompt is sent, and given to its provider alone

A prompt names its content and never holds its bytes, so a prompt can be
recorded wherever it goes. Before a model is called, the engine checks each
piece the prompt shows exactly as it checks a tool's content inputs (ADR
0114): the run, or a run above it in its lineage, received it under the
handle's media type; the content store holds it under its digest; and it is
the handle's size. Each piece is read once. A prompt that fails a check is
refused before any provider is called:

```text
Prompt strategy '<NAME>' shows content, which this run cannot give: it has no content store.
Prompt strategy '<NAME>' shows content, which only a workflow step can give.
Prompt strategy '<NAME>' shows content <DIGEST>, which this run never received.
Prompt strategy '<NAME>' shows content <DIGEST> as <MEDIA_TYPE>, but this run received it as <MEDIA_TYPES>.
Content <DIGEST> is not in the content store.
Content <DIGEST> in the content store does not match its digest.
Prompt strategy '<NAME>' shows content <DIGEST> as <SIZE> bytes, but it holds <ACTUAL>.
```

The bytes are given to the provider for the length of the one call, by
digest, and a provider reads them there and nowhere else. A provider never
reaches the content store, and `LanguageModel.complete(prompt)` is
unchanged:

```text
Model <PROVIDER>/<MODEL> was not given the bytes of content <DIGEST>.
```

Until a provider sends content in its own form, it refuses a prompt of
parts before sending anything, rather than send its text alone:

```text
OpenRouter model '<MODEL>' cannot be shown content by this release.
Bedrock model '<MODEL>' cannot be shown content by this release.
```

## Consequences

- A model step can be shown the documents and images its run received, in
  the order its template places them, beside text.
- No prompt, event, journal entry or run holds content's bytes; each names
  content by its handle, and a prompt's bytes live only for one call.
- A prompt that names content its run never received fails before a model
  is called, whichever model it is bound to.
- Every existing prompt, template and workflow document is unchanged, and
  so are their digests.
- A workflow cannot show a model reference content of its own, such as a
  sample form; that waits for a way to give a run content it did not
  receive as input.

## Alternatives Considered

### Give every language model the bytes as an argument

Rejected. `complete(prompt, contents=...)` would change every language
model, and every test double of one, to carry what only two providers read.
Giving the bytes for the length of the call keeps the interface as it is.

### Let a provider read the content store

Rejected. A provider would need the run, its lineage and the store, and
would have to repeat the checks every tool's content inputs pass. The engine
checks once, before any provider is called.

### Show content in a fixed prompt by digest

Rejected for now. Nothing gives a run content it did not receive, so a
digest in a workflow document would name content outside what the run was
given, or nothing at all.
