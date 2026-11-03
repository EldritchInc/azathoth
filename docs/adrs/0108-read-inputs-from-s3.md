# ADR 0108: Read Inputs From S3

- Status: Accepted
- Date: 2026-11-02
- Decided in: #126

## Context

A job request carries its input inline or by reference (ADR 0096). The
command line accepts `file://` references, read from the operator's own
disk. The queue worker accepts none (ADR 0107): a message from a queue must
never read the worker's disk, and an SQS message is too small to carry a
document inline. So a worker had no way to take a document as its input.

On AWS, the documents a job reads live in S3. ADR 0096 planned for that: an
`s3://` scheme the worker accepts from allow-listed buckets, a size cap that
becomes a setting once deployments differ, and a content store in S3. The
store matters because every resolved input is kept by the digest of its
bytes, and in a deployment those bytes would otherwise fill the database.

## Decision

### `s3://` references

An `s3://<BUCKET>/<KEY>` reference names one object. The key is the rest of
the URI after the bucket, exactly as written. A URI with a query or a
fragment is refused, so a request names an object and not a version of it;
the provenance's digest pins exactly which bytes ran. The media type is the
request's, never S3's `Content-Type`: the request is the contract
(ADR 0096).

### Allowed locations

`azathoth worker run --allow-input-bucket <BUCKET>[/<PREFIX>]`, given as
often as needed, names where references may point. A bucket allows every key
in it; a bucket and a prefix allow the keys that start with the prefix,
matched literally, as S3 matches it. A worker allowed no location accepts no
reference at all, as before, and no worker ever accepts `file://`.

An input outside every allowed location is refused before S3 is asked:

```text
Input s3://azathoth-other/requests/review.json is not in an allowed location; allowed: azathoth-inputs/requests/.
```

The command line still accepts `file://` only. An operator with S3 copies
the object first.

### Reading within the cap

An allowed object is read with one ranged GET of at most the cap plus one
byte, so an object beyond the cap is refused without downloading it. The
cap is the worker's `--max-input-bytes`, 10 MiB by default, from 1 byte to
100 MiB. A resolved input is decoded into its run's context, which is in the
database, so the ceiling protects the database as much as the worker. The
command line keeps its fixed 10 MiB.

### Whose fault a failure is

An input that is outside the allowed locations, missing, unreadable or too
large is the request's fault. It is `rejected` as `invalid_input`, and its
message deleted:

```text
Input s3://azathoth-inputs/requests/review.json does not exist.
Unable to read input s3://azathoth-inputs/requests/review.json: AccessDenied: Access Denied
```

S3 that cannot be reached at all, as without credentials, is not. It raises
`InputUnavailableError`, which stops the worker with its message left on the
queue, as any other failure of the worker does (ADR 0107). A worker allowed
a location makes its S3 client at startup, so one without boto3 stops before
it receives anything:

```text
s3:// inputs need boto3, which is not installed; install azathoth-ai[worker].
```

### The content store in S3

`AZATHOTH_CONTENT_STORE=s3://<BUCKET>[/<PREFIX>]` keeps every command's
resolved content in S3, at `<PREFIX>/sha256/<DIGEST>`, instead of in the
database's `content_blobs` table. Unset, nothing changes. Content is
immutable, so it is written only when nothing is there yet, with S3's
conditional `If-None-Match: *`, and S3's answer that something is there, or
is being written, counts as stored.

The store is made the first time a command stores content, so a command
that stores none never imports boto3; the worker opens it at startup. A
store that is misconfigured, lacks boto3 or refuses a write raises
`ContentStoreError`, which stops the command in one line before anything
runs. It is never the request's fault.

### Packaging

S3 needs boto3, which the `worker` extra already installs, and the image
installs that extra (ADR 0107). No extra is added.

### Data larger than the cap

The cap is for content the engine resolves into a run, not for the data a
workflow may process. Data larger than the cap goes by pointer: a request's
inline value names the object, a process tool that declares the `AWS_*`
variables streams it and splits it into chunk objects (ADR 0099), and
`map_workflow` runs a child over the chunks (ADR 0106). Only keys and small
results pass through the context, so the database never holds the data, and
a map stopped halfway resumes without reading its finished chunks again. The
worker's allowed locations do not govern what a tool reads; the task's IAM
role does.

### Verified without AWS

Every S3 call is tested against botocore's `Stubber`: the ranged GET and its
range, the conditional PUT and its answers, and every refusal. The worker is
tested end to end, from a queue message whose input is an `s3://` reference
to the run's recorded provenance and the stored bytes.

### Not decided here

- A standard tool that splits an S3 object into chunk objects, for the
  pattern above.
- `s3://` inputs on the command line.
- Removing content no run refers to any more.

## Consequences

### Positive

- A worker takes documents as its input, from exactly the places it is
  allowed to read.
- A request cannot make a worker read its own disk, another bucket, or more
  than the cap.
- Every resolved input stays traceable to its object, size and digest, as an
  input file is.
- A deployment keeps its inputs' bytes in S3 instead of the database.
- The cap fits each deployment, and nobody reads it as the size of the
  largest job Azathoth can do.

### Negative

- A prefix matched literally allows its namesakes, `requests` allowing
  `requests-old/`, unless it ends with `/`.
- Without `s3:ListBucket`, S3 answers `AccessDenied` for a missing object,
  so the refusal says the object cannot be read rather than that it does not
  exist.
- A request cannot name an object's version.
- The decoded input is still kept in the run's context, in the database; the
  S3 store moves only the second copy, its bytes.
- No test reaches real S3 before a deployment does.

## Alternatives Considered

### Allow buckets, without prefixes

Rejected. A deployment usually shares a bucket with other data, and a worker
should be allowed one folder of it.

### Accept `?versionId=`

Deferred. The digest already records which bytes ran, and a version adds a
second way to name an object before anyone needs one.

### Check the size with `HeadObject` first

Rejected. It doubles every read, and the object can change between the two
calls; the ranged GET reads what it checks.

### Use S3's `Content-Type`

Rejected. The request says how its input is decoded, whatever stored it.

### Raise the cap to gigabytes

Rejected. The decoded input lands in the run's context, in the database, and
no model reads gigabytes in one prompt. Large data goes by pointer.

### Keep the content store in the database

Rejected for deployments, kept as the default. The bytes are a second copy
of the input, and in S3 they cost what objects cost rather than what
database storage does.

### Write content after a `HeadObject` check

Rejected. It doubles every write, and two workers can both find nothing in
between; the conditional write lets S3 decide in one call.
