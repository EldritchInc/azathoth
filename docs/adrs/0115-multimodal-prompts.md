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

### OpenRouter is sent content parts, and reads PDFs natively

A prompt of text is sent to OpenRouter as it always was: one user message
whose content is the text. A prompt of parts is sent as one user message of
OpenRouter's content parts, in the prompt's order. Text is a `text` part, an
image an `image_url` part holding a data URL, and a PDF a `file` part
holding one, named `document-<N>.pdf` in the order the prompt shows them:

```json
{"model": "<MODEL>", "messages": [{"role": "user", "content": [
  {"type": "text", "text": "Here is the claim form:\n"},
  {"type": "file", "file": {"filename": "document-1.pdf", "file_data": "data:application/pdf;base64,<BASE64>"}},
  {"type": "text", "text": "\nand the photo of the damage:\n"},
  {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,<BASE64>"}}
]}],
 "plugins": [{"id": "file-parser", "pdf": {"engine": "native"}}]}
```

OpenRouter gives a PDF to a model that cannot read files by extracting its
text first, by default with an OCR service charged per page, and the model
then reads text Azathoth never saw. A request that holds a PDF therefore
pins the file parser to the `native` engine: the model reads the PDF
itself, charged as its own input tokens. Which models can read a PDF is the
catalog's to say: OpenRouter lists `file` among their input modalities.

OpenRouter documents no limit on the size of a part, so none is checked
before sending; a request OpenRouter refuses fails as any failed request
does. The request is built, and every piece's bytes found, before anything
is sent, so a prompt whose bytes were not given sends nothing.

### Bedrock is sent Converse blocks, within Converse's limits

A prompt of text is sent to Bedrock as it always was: one user message of
one text block. A prompt of parts is one user message of Converse content
blocks, in order, each holding its raw bytes. Text is a `text` block, an
image an `image` block of format `png`, `jpeg` or `webp`, and a PDF a
`document` block of format `pdf`:

```json
[
  {"text": "Here is the claim form:\n"},
  {"document": {"format": "pdf", "name": "document-1", "source": {"bytes": "<BYTES>"}}},
  {"text": "\nand the photo of the damage:\n"},
  {"image": {"format": "jpeg", "source": {"bytes": "<BYTES>"}}}
]
```

A document is named `document-<N>` in the order the prompt shows it.
Bedrock warns that a model may read a document's name as an instruction and
asks for a neutral one; a name drawn from the input, such as its file name,
would put text from outside the workflow in front of the model unchecked.

Converse takes at most 20 images, each at most 3.75 MB, and at most 5
documents, each at most 4.5 MB, in one message, and a message holding a
document must also hold text. Each is checked before anything is sent,
taking a megabyte as a million bytes, the stricter reading; an image's
dimensions, at most 8000 pixels a side, are left to Bedrock, since checking
them would mean decoding the image:

```text
Bedrock model '<MODEL>' is shown at most 20 images in one prompt; this one shows <COUNT>.
Bedrock model '<MODEL>' is shown at most 5 documents in one prompt; this one shows <COUNT>.
Bedrock model '<MODEL>' is shown images of at most 3750000 bytes; content <DIGEST> is <SIZE>.
Bedrock model '<MODEL>' is shown documents of at most 4500000 bytes; content <DIGEST> is <SIZE>.
Bedrock model '<MODEL>' is shown a document only beside text; this prompt has none.
```

### The operator says which Bedrock models read documents

Bedrock's model listing reports a model's input modalities as text, image,
speech or video, and says nothing of documents, though Converse gives
documents to many models. The operator's Bedrock pricing document (ADR
0103) may therefore add input modalities by model ID, beside its prices:

```json
{
  "version": 1,
  "models": {},
  "input_modalities": {"us.anthropic.claude-sonnet-4-20250514-v1:0": ["file"]}
}
```

The modalities a document names are added to those Bedrock reports, and
never take one away; a model it adds `image` to is one with vision. A model
may be named without a price. Without the entry, a Bedrock model reads the
images Bedrock says it reads, and no PDFs. The document's version is
unchanged, since every document of version 1 still means what it meant.

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

### Let OpenRouter choose how to read a PDF

Rejected. Its default for a model without native file support extracts the
text with a paid OCR service, so a model would answer from text no one
checked, at a cost no step declared.

### Let a provider read the content store

Rejected. A provider would need the run, its lineage and the store, and
would have to repeat the checks every tool's content inputs pass. The engine
checks once, before any provider is called.

### Name a Bedrock document after its file

Rejected. A document's name is text the model reads, and Bedrock warns it
may be read as an instruction. A file name comes from outside the workflow,
so it is never put there.

### Guess which Bedrock models read documents

Rejected. Converse's support for documents differs by model and changes
with Bedrock's releases, and a guess would send PDFs to models that refuse
them, or keep them from models that read them. The operator, who chose the
region and the models, says.

### Show content in a fixed prompt by digest

Rejected for now. Nothing gives a run content it did not receive, so a
digest in a workflow document would name content outside what the run was
given, or nothing at all.
