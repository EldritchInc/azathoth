# Inputs

`azathoth.inputs` describes the external input a workflow is given
(ADR 0096). An input is either an inline value or a reference to content,
and always has a media type:

```json
{"value": {"text": "the old ones wait"}, "media_type": "application/json"}
{"uri": "file:///Users/you/chapter.md", "media_type": "text/markdown"}
```

```python
from azathoth.inputs import (
    InlineInput,
    ReferenceInput,
    WorkflowInputSource,
    decode_content,
    decode_input_source,
)
```

## Sources

`InlineInput` holds its content. Its media type defaults to
`application/json`, and a `text/*` media type requires a string value.

`ReferenceInput` names its content by URI, and must state its media type.
The URI needs a scheme; a Windows drive letter is not one. Which schemes may
be resolved is decided by the entry point that receives the input, not by
the source.

The shape is closed. `decode_input_source(data)` reads one source from JSON
and raises `InputSourceError` when the data holds both or neither of `value`
and `uri`, or any key other than `media_type`. `WorkflowInputSource` is the
same union as a pydantic type, so a model can embed a source and parse it by
its key.

## Media Types

A media type is a lowercase `type/subtype` with no parameters.
`validate_media_type` accepts:

- `application/json`, decoded by parsing JSON;
- any `text/*` type, decoded as a string.

Binary media types are rejected until multimodal inputs arrive.

`decode_content(content, media_type)` turns resolved bytes into the value a
workflow receives. Content is UTF-8, and a leading byte order mark is
dropped. JSON content may not contain `NaN` or infinities, which are not
JSON. Failures raise `InputContentError`.

`infer_media_type(name)` maps the extensions `.json`, `.txt`, `.md`,
`.markdown` and `.csv` to their media types, and returns `None` for any
other.

## Content Store

Resolved content is kept by the digest of its bytes, so a run can always be
traced to, and re-read from, exactly the content it was given.

```python
from azathoth.inputs import (
    ContentStore,
    InMemoryContentStore,
    SQLiteContentStore,
    content_bytes_digest,
)
```

`content_bytes_digest(content)` is the lowercase hex SHA-256 of the bytes,
the same form as a revisioned document's content digest.

A `ContentStore` has three operations:

- `put(content)` stores content and returns its digest. Storing the same
  content again changes nothing;
- `get(digest)` returns the content, or `None` when it is not stored;
- `contains(digest)` says whether it is stored.

`SQLiteContentStore` keeps content in the `content_blobs` table of the
configured database, with its size and when it was first stored. It creates
the table on first use. `InMemoryContentStore` keeps content in process
memory, for tests and embedding.

Nothing removes stored content yet.
