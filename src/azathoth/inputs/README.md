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
