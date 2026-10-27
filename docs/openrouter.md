# Connecting OpenRouter

Azathoth calls language models through [OpenRouter](https://openrouter.ai),
which gives you hundreds of models from many vendors behind one API key.

This guide covers getting a key and making it available to Azathoth. Then it
covers choosing which models Azathoth may use, and adding the judges that
score semantic benchmark cases. Each command is shown for the macOS Terminal
and for Windows PowerShell.

Start with Azathoth installed and its venv active. See
[Installing Azathoth](install.md).

## How Azathoth Uses Models

Workflows in the examples don't name a model. Each prompt step states
requirements instead, such as text in and text out, or a minimum context
window. Azathoth fills each step from the models you have authorized.

Two separate lists are involved:

- **available models**: what OpenRouter offers right now. `azathoth model list`
  shows these. They come from OpenRouter each time a command needs them.
- **authorized models (the portfolio)**: the models you allow Azathoth to use.
  `azathoth model portfolio` shows these. They are stored in your database.

A step can run only on a model that is both available and authorized.

## 1. Get a Key

1. Sign in at [openrouter.ai](https://openrouter.ai).
2. Add credit to your account. Most models are paid by the token. A few are
   free, but they are rate-limited.
3. Open [Keys](https://openrouter.ai/keys) and create a key. Give it a name
   such as `azathoth`, and set a credit limit so that a runaway loop can't
   spend more than you intend.
4. Copy the key. OpenRouter shows it only once.

Treat the key like a password. Never put it in a workflow document, a
benchmark, or anything you commit to git. Azathoth reads it only from the
environment and never stores it.

## 2. Make the Key Available

Azathoth reads the key from the `OPENROUTER_API_KEY` environment variable.

### For this terminal only

Typing the key straight into a command saves it in your shell history. These
commands prompt for it instead, without showing it:

```bash
printf 'OpenRouter key: '; read -rs OPENROUTER_API_KEY; echo
export OPENROUTER_API_KEY
```

```powershell
$secret = Read-Host -AsSecureString "OpenRouter key"
$env:OPENROUTER_API_KEY = [System.Net.NetworkCredential]::new("", $secret).Password
Remove-Variable secret
```

The key lasts until you close the window.

### For every new terminal

To avoid entering the key each time, store it in your user environment.

#### macOS

macOS uses zsh by default, and zsh reads `~/.zshrc` whenever a terminal
opens. This appends an `export` line for the key to that file, again without
showing the key:

```bash
printf 'OpenRouter key: '; read -rs key; echo
printf 'export OPENROUTER_API_KEY=%q\n' "$key" >> ~/.zshrc
unset key
```

Run it once. If you replace the key later, edit `~/.zshrc` and remove the old
line, rather than appending a second one.

#### Windows

Store the key in your user environment variables:

```powershell
$secret = Read-Host -AsSecureString "OpenRouter key"
[Environment]::SetEnvironmentVariable(
    "OPENROUTER_API_KEY",
    [System.Net.NetworkCredential]::new("", $secret).Password,
    "User"
)
Remove-Variable secret
```

#### After storing it

On either platform, the stored key reaches only terminals opened afterwards. Close the
terminal, open a new one, and activate the venv again.

### Check it

Check that the variable is set, without printing the key:

```bash
test -n "$OPENROUTER_API_KEY" && echo "key is set" || echo "key is NOT set"
```

```powershell
if ($env:OPENROUTER_API_KEY) { "key is set" } else { "key is NOT set" }
```

## 3. Find Models

List everything OpenRouter offers right now:

```bash
azathoth model list
```

```powershell
azathoth model list
```

Each line shows a model's identifier and its display name:

```text
openrouter/<vendor>/<model>  <Display Name>
```

The list is long. To narrow it, filter by vendor or name:

```bash
azathoth model list | grep -i anthropic
```

```powershell
azathoth model list | Select-String -Pattern anthropic
```

Look at one model before you choose it:

```bash
azathoth model show openrouter/<vendor>/<model>
```

```powershell
azathoth model show openrouter/<vendor>/<model>
```

`model show` reports the model's modalities, capabilities, context window,
maximum output and price per million tokens.

OpenRouter adds and retires models often. Use identifiers from your own
`model list` output rather than ones copied from a guide.

## 4. Authorize Models

Authorize a model to let Azathoth use it:

```bash
azathoth model authorize openrouter/<vendor>/<model>
azathoth model portfolio
```

```powershell
azathoth model authorize openrouter/<vendor>/<model>
azathoth model portfolio
```

The portfolio keeps the order in which models were authorized. When a step
runs, Azathoth uses the first authorized model that is available and meets
the step's requirements. So authorize your everyday default first.

### What to authorize for the examples

- **One capable, general text model** is enough for every example except the
  novel. Authorize it first.
- **One model with a context window of at least 200,000 tokens** is needed
  for the novel: its final editorial review reads the whole book at once.
  `model show` reports the context window.
- **One or more cheaper models** let the optimizer do something interesting.
  `azathoth workflow optimize` with `--generations 2` or more tries each
  authorized model that is strictly cheaper than the current one and still
  meets the step's requirements. Then it reports which candidate did best on
  quality, latency and cost.

### Removing a model

```bash
azathoth model deauthorize openrouter/<vendor>/<model>
```

```powershell
azathoth model deauthorize openrouter/<vendor>/<model>
```

Azathoth refuses to deauthorize a model in two cases:

- **A promoted workflow depends on it.** The refusal names each dependent
  workflow and step, and `--force` overrides it.
- **It is a judge.** Remove it from the judges first; `--force` doesn't
  override this.

To see everything that depends on a model, use `azathoth model usage`.

## 5. Add Judges

Some benchmark cases are *semantic*: whether an answer is correct is a
judgment ("is the reply polite and does it route the ticket correctly?")
rather than an exact match. Azathoth asks a language model, the judge, to
make that call. The examples' benchmarks for ticket triage, the workflow
writer, code review and the novel all have semantic cases.

A judge must be an authorized model. Add one:

```bash
azathoth judge add openrouter/<vendor>/<model>
azathoth judge list
```

```powershell
azathoth judge add openrouter/<vendor>/<model>
azathoth judge list
```

One judge is enough. With several, each case is always assigned the same
judge, so every candidate is graded by the same judge on that case. If that
judge fails, the next judge in the list is tried. Pick a strong model for
judging: a weak judge makes the benchmark noisy.

Judge calls are Azathoth's own cost. They are recorded, but they are never
added to a workflow run's cost or to a benchmark's totals.

Remove a judge with:

```bash
azathoth judge remove openrouter/<vendor>/<model>
```

```powershell
azathoth judge remove openrouter/<vendor>/<model>
```

## 6. Try It

From inside the cloned repository (see
[Get the Examples](install.md#6-get-the-examples)), import a one-step
model-backed workflow and run it once:

```bash
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth workflow run 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"I love this keyboard."'
```

```powershell
azathoth workflow import examples/workflows/classify-sentiment.json
azathoth workflow run 5e2e0b6a-3c1d-4b7e-9f20-000000000001 --input '"I love this keyboard."'
```

The run shows the model it used, the tokens it took, its latency and cost,
and its answer: `positive`.

## Costs

You pay OpenRouter for every model call your workflows and judges make.

- A single run of a small example costs a fraction of a cent.
- Optimizing a workflow runs every candidate against every benchmark case,
  and semantic cases add judge calls on top.
- The novel is by far the most expensive example: it writes, reviews and
  revises a whole book.

The credit limit on your key is the simplest safeguard. OpenRouter's activity
page shows exactly what was spent.

## Troubleshooting

**`azathoth model list` prints nothing**: `OPENROUTER_API_KEY` isn't set in
this terminal. Check it (step 2). Remember that a stored key reaches only
terminals opened after you stored it.

**`No executable prompt candidate could be generated`**: no authorized,
available model meets that step's requirements. Run `azathoth model portfolio`
to see what you have authorized. Then check the step's requirements: the novel
needs a 200,000-token context window.

**`Model '…' is not currently available`**: OpenRouter no longer offers that
identifier, or the key isn't set. Choose another model from `model list`.

**`Model '…' is not authorized`** when adding a judge: authorize the model
first (step 4).

**`Value must be valid JSON`** for an `--input` value on Windows: you are in
Windows PowerShell 5.1, which strips the inner quotes. Use PowerShell 7 (see
[Installing Azathoth](install.md#windows)).

**Requests fail with an authentication or payment error**: the key was
revoked, mistyped, or has reached its credit limit. Check it on the
[Keys](https://openrouter.ai/keys) page.

## Next

- [Examples Tour](examples.md): every example, in order.
