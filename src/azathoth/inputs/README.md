# Inputs

`azathoth.inputs` describes the external input a workflow is given
(ADR 0096). An input is either an inline value or a reference to content,
and always has a media type. A PDF or an image is binary content, given to
the workflow as a content handle (ADR 0112):

```json
{"value": {"text": "the old ones wait"}, "media_type": "application/json"}
{"uri": "file:///Users/you/chapter.md", "media_type": "text/markdown"}
{"uri": "s3://claims-intake/2026/11/claim-0412.pdf", "media_type": "application/pdf"}
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
`application/json`, a `text/*` media type requires a string value, and a
binary media type requires standard, padded base64 with no whitespace. Any
inline input may name its `origin`, an `InputOrigin` (see
[Binary Content](#binary-content)).

Either kind may name its `sensitivity`: `public`, `internal` or `restricted`
(ADR 0123). A source that names none is internal, and dumps exactly as it did
before labels existed, so its digest is unchanged. The label belongs to the
input, never to the content: the same bytes may be restricted in one run and
public in another, and the content store keeps them once.

`ReferenceInput` names its content by URI, and must state its media type.
The URI needs a scheme; a Windows drive letter is not one. Which schemes may
be resolved is decided by the entry point that receives the input, not by
the source.

The shape is closed. `decode_input_source(data)` reads one source from JSON
and raises `InputSourceError` when the data holds both or neither of `value`
and `uri`, a `uri` with an `origin`, or any key other than `media_type`,
`sensitivity` and, beside `value`, `origin`:

```text
An input source holds only 'value', 'media_type', 'origin' and 'sensitivity', or 'uri', 'media_type' and 'sensitivity'; got 'size'.
An input's sensitivity is 'public', 'internal' or 'restricted'; got 'secret'.
```

`WorkflowInputSource` is the
same union as a pydantic type, so a model can embed a source and parse it by
its key.

## Media Types

A media type is a lowercase `type/subtype` with no parameters.
`validate_media_type` accepts:

- `application/json`, decoded by parsing JSON;
- any `text/*` type, decoded as a string;
- `application/pdf`, `image/png`, `image/jpeg` and `image/webp`
  (`BINARY_MEDIA_TYPES`), never decoded: their content is kept and named by
  a content handle.

Any other media type is refused, naming those accepted.

`decode_content(content, media_type)` turns resolved bytes into the value a
workflow receives. Content is UTF-8, and a leading byte order mark is
dropped. JSON content may not contain `NaN` or infinities, which are not
JSON. Failures raise `InputContentError`.

`infer_media_type(name)` maps the extensions `.json`, `.txt`, `.md`,
`.markdown`, `.csv`, `.pdf`, `.png`, `.jpg`, `.jpeg` and `.webp` to their
media types, and returns `None` for any other.

## Resolving at the Edge

References are resolved by the entry point that receives them, before the
run starts, so steps only ever see values.

```python
from azathoth.inputs import (
    FileInputResolver,
    InputPolicy,
    SQLiteContentStore,
    decode_input_source,
    resolve_input,
)

policy = InputPolicy(resolvers={"file": FileInputResolver()})

resolved = resolve_input(
    decode_input_source({"uri": "file:///Users/you/chapter.md", "media_type": "text/markdown"}),
    policy=policy,
    store=SQLiteContentStore("azathoth.db"),
)
```

An `InputPolicy` is what one entry point accepts: a resolver per accepted
scheme, and `max_bytes`, which defaults to `DEFAULT_MAX_INPUT_BYTES`
(10 MiB). An `InputResolver` reads the content one URI names and refuses any
larger than the cap. `FileInputResolver` reads `file://` URIs naming an
absolute path on the local host, with an empty host or `localhost`, and reads
at most one byte past the cap. `file_uri(path)` makes a path absolute and
returns its URI.

`resolve_input` returns a `ResolvedInput`: the value and its media type. An
inline JSON or text value naming no origin is used as it is; any other
inline input is resolved as [Binary Content](#binary-content) describes. A reference is read, checked against the cap,
decoded as its media type, and saved in the content store; its
`InputProvenance` records the URI, media type, size and digest. A scheme the
policy does not accept is refused before anything is read, and nothing is
stored for content that is refused. Every refusal raises
`InputResolutionError`.

The CLI resolves `workflow run --input-file` and `workflow invoke
--input-file` under `azathoth.cli.CLI_INPUT_POLICY`, which accepts `file://`
only.

## Binary Content

Binary content is checked against its media type's signature before it is
kept (`check_binary_signature`): a PDF's `%PDF-` header within its first
1024 bytes, a PNG's signature, a JPEG's start-of-image marker, or a RIFF
container holding `WEBP`. It is never decoded. It is stored, and the
workflow receives a `ContentRef` as its value:

```json
{"content": {"digest": "<SHA-256>", "media_type": "application/pdf", "size_bytes": 482113}}
```

`content_ref_from_value(value)` returns the `ContentRef` a value is, or
`None` when it is not exactly one. A handle names content; it does not grant
it. Whatever reads content through a handle first checks that the digest was
recorded by a `workflow.input.resolved` event of its own run or lineage.

An inline input may hold binary content as base64, and any inline input may
name where its content durably lives:

```json
{
  "value": "JVBERi0xLjcK",
  "media_type": "application/pdf",
  "origin": {"uri": "s3://claims-intake/2026/11/claim-0412.pdf", "etag": "9b2cf535"}
}
```

`resolve_inline_input` checks base64 against the cap by its encoded length,
four characters for every three bytes, before decoding it, and by its size
after. An inline input that is binary, or names an origin, has an
`InputProvenance` marked `inline`, with no URI and with its origin; its
content is stored, a JSON value in its canonical form. An origin's `uri` is
an absolute URI with no fragment, of at most 2048 characters, and only an
`s3://` origin may name a `version_id` and an `etag`. An origin is recorded
as given, never read; a reference may not name one.

A resolver that reads versions offers `read_versioned` beside `read`, and is
a `VersionedInputResolver`. It returns `VersionedContent`: the bytes, and
the version ID and ETag of the object that held them, which `resolve_input`
records as the reference's origin. `S3InputResolver` is one;
`FileInputResolver` is not, so a `file://` reference records no origin.

## S3 References

`S3InputResolver` reads `s3://<BUCKET>/<KEY>` references to objects in
Amazon S3, but only inside the locations it is given (ADR 0108):

```python
from azathoth.inputs import (
    S3_SCHEME,
    InputPolicy,
    S3InputLocation,
    S3InputResolver,
)

allowed = (S3InputLocation.parse("azathoth-inputs/requests/"),)
policy = InputPolicy(resolvers={S3_SCHEME: S3InputResolver(allowed)})
```

A location is a bucket, which allows every key in it, or a bucket and a key
prefix, which allows the keys that start with it. A prefix is matched
literally, as S3 matches it: keys have no paths, so `azathoth-inputs/requests`
also allows `requests-old/`, and only a trailing `/` stops it. A resolver
with no locations allows nothing.

The key is the rest of the URI after the bucket, exactly as written. A URI
with a query or a fragment, such as `?versionId=`, is refused: a request
names an object, and the provenance's digest pins exactly which bytes ran.
The media type is the reference's own; S3's `Content-Type` is ignored.

An allowed object is read with one ranged GET of at most the cap plus one
byte, so an object beyond the cap is refused without downloading it. The
GET's `VersionId` and `ETag` are recorded as the reference's origin, naming
the exact object read; an empty object, which has no range to read, is read
once more, plainly, for them (ADR 0112). Each
refusal is an `InputResolutionError`, which an entry point reports to the
request's caller:

```text
Input s3://azathoth-other/chapter.md is not in an allowed location; allowed: azathoth-inputs/requests/.
Input s3://azathoth-inputs/requests/chapter.md does not exist.
Unable to read input s3://azathoth-inputs/requests/chapter.md: AccessDenied: Access Denied
Input s3://azathoth-inputs/requests/chapter.md is larger than the limit of 10485760 bytes.
Input s3://azathoth-inputs/requests/chapter.md?versionId=3 must name an object only, with no query or fragment.
```

S3 answers `AccessDenied` for a missing object, too, when the reader may
not list its bucket.

A read that never reached S3, because there are no credentials or no
network, is not the request's fault. It raises `InputUnavailableError`
instead, which stops an entry point rather than refusing one request. So
does reading without boto3, which is imported only on the first read of an
allowed object:

```text
s3:// inputs need boto3, which is not installed; install azathoth-ai[worker].
```

The client is boto3's, made on the first read, with AWS's own credential
chain and standard retries.

### Data Larger Than the Cap

The cap is for content the engine resolves into a run, whose decoded value
lands in the run's context, in the database. It is not the size of the
largest data a workflow can process. Data larger than the cap goes by
pointer (ADR 0108):

1. The request's input is an inline value naming the object, such as
   `{"value": "s3://intake/batch-0412.csv"}`. Inline values are not
   resolved, so neither the cap nor the allowed locations apply.
2. `split_s3_object`, from the standard tools, streams the object, writes
   chunk objects back to S3, and returns only their URIs (ADR 0110).
3. `map_workflow` runs a child over the chunks (ADR 0106); each child reads
   its own with `read_s3_object`, which decodes it as a resolved input is
   decoded.

Only URIs and small results pass between steps. What the tools read and
write is governed by the task's IAM role, not by the worker's allowed
locations. The [large-file example](../../../examples/large-file/README.md)
counts the words of a file this way.

## Input Events

`azathoth.workflows.create_workflow_input_events(resolved, producer=...)`
turns a resolved input into a run's initial events: the canonical
`workflow.input.received` event with the value, followed, for an input that
has provenance, by a `workflow.input.resolved` event holding it. A reference
always has provenance; an inline input has it when it is binary or names an
origin (ADR 0112). `resolve_input` keeps the source's label on the
`ResolvedInput`, and a labelled input's events end with a
`workflow.input.sensitivity` event holding it (see the context package's
[Sensitivity](../context/README.md#sensitivity)). An unlabelled input records
none.

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

`S3ContentStore` keeps content in Amazon S3 instead (ADR 0108), at an
`S3ContentLocation`: a bucket and a prefix, parsed from
`s3://<BUCKET>[/<PREFIX>]`. Content is kept at `<PREFIX>/sha256/<DIGEST>`.
`put` writes only if nothing is there yet, with S3's conditional
`If-None-Match: *`, and takes S3's answer that something is, or is being
written, as already stored. `get` and `contains` read the object. Every
failure, a call S3 refused or one that never reached it, raises
`ContentStoreError`, which is never the request's fault:

```text
Cannot store content in s3://<BUCKET>/<KEY>: <CODE>: <MESSAGE>
Cannot read s3://<BUCKET>/<KEY>: <CODE>: <MESSAGE>
```

`content_store_location(environment)` reads `AZATHOTH_CONTENT_STORE`, and
returns `None` when it is unset, which keeps content in the database. The
store makes boto3's client when it is made, with standard retries, and says
which extra to install without boto3:

```text
AZATHOTH_CONTENT_STORE names S3, but boto3 is not installed; install azathoth-ai[worker].
```

Nothing removes stored content yet.

## Job Envelopes

A job request embeds a `WorkflowInputSource` as its `input`, and is resolved
with the same `resolve_input`, under the policy of the entry point that
received it (ADR 0097). `azathoth job run` uses the CLI's policy, `file://`
only. A request's digest names a reference by its URI and media type, never
by its content, so a retried request is recognized without reading the
content again. An inline input's `origin` is part of the digest; one that
names none digests exactly as it did before inputs could name one.
