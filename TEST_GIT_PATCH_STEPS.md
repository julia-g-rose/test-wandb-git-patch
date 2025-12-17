## Goal

Use this repo to empirically test what W&B stores for code + git patches (tracked/untracked, staged/unstaged, `.gitignore`, secrets), while also producing a single Weave trace from one OpenAI call.

References:
- W&B Code panel docs: `https://docs.wandb.ai/models/app/features/panels/code`
- Comet Experiment reference (comparison): `https://www.comet.com/docs/v2/api-and-sdk/python-sdk/reference/Experiment/`

## One-time setup

1) Create a `.env` (do NOT commit it):

```bash
cat > .env <<'EOF'
WANDB_API_KEY=...
OPENAI_API_KEY=...
WANDB_ENTITY=your-entity
WANDB_PROJECT=git-patch-weave-smoke
# Optional: override where Weave traces go
# WEAVE_PROJECT=git-patch-weave-smoke
EOF
```

2) Create a git repo and commit the baseline (needed for meaningful diffs):

```bash
git init
git add .
git commit -m "baseline smoke test"
```

3) Install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Baseline run (no repo changes)

Run once to establish the baseline W&B run files and Weave trace:

```bash
python run.py
```

In the resulting W&B run page, inspect:
- **Code panel** and/or the **Files** tab for uploaded code artifacts/files
- Any uploaded `*.patch` / `*.diff` files (names vary by version)
- Git metadata (commit hash, dirty/clean indicators)

Also open Weave and confirm you see exactly **one traced op** (`call_openai_once`) for this execution.

## Q1 — Does the code comparer include the patch for uncommitted changes?

1) Make an unstaged edit to a tracked file, e.g. `prompts/system_prompt.txt`:

```bash
echo "Extra line to force a diff." >> prompts/system_prompt.txt
```

2) Run again:

```bash
python run.py
```

3) Inspect the new run:
- In **Files**, look for patch/diff files; open them and confirm your uncommitted change appears.
- In the **Code** view, check whether the UI can show a diff vs commit state (behavior depends on W&B version).

Expected/typical behavior: W&B logs a patch representing working tree changes relative to HEAD when `save_code=True` / `run.log_code()` is used.

## Q2 — Do we respect `.gitignore`?

This repo’s `.gitignore` includes `.env`, `ignored_test.txt`, and `ignored_dir/`.

1) Create ignored files:

```bash
echo "should be ignored" > ignored_test.txt
mkdir -p ignored_dir
echo "should be ignored" > ignored_dir/ignored.txt
```

2) Run again:

```bash
python run.py
```

3) Inspect the run’s **Files** and **Code** listing:
- Confirm `ignored_test.txt` and `ignored_dir/ignored.txt` are **not** uploaded as code files.
- Also confirm `.env` is not uploaded.

If you see ignored files show up, note whether they appear as raw files vs patches (and which feature uploaded them).

## Q3 — Do we filter out secrets?

This is a “treat as sensitive” check.

1) Add a fake secret string to a **tracked** file (NOT `.env`), e.g. append to `prompts/system_prompt.txt`:

```bash
echo "FAKE_SECRET=shh_this_should_not_be_here" >> prompts/system_prompt.txt
```

2) Run:

```bash
python run.py
```

3) Inspect patch/code artifacts in the run:
- Search in the patch/diff or code listing for `FAKE_SECRET`.

Interpretation:
- If it appears, **secrets are not filtered** from diffs/code capture (common).
- If it does not appear, verify whether the file itself was uploaded and whether the patch was generated at all.

Safety note: never place real secrets in tracked files if code capture is enabled.

## Q4 — Do we include untracked files when storing the patch?

1) Create a new untracked *non-ignored* file:

```bash
echo "hello untracked" > untracked_note.txt
git status --porcelain
```

2) Run:

```bash
python run.py
```

3) Inspect the run:
- Check if `untracked_note.txt` appears anywhere in **Files** / **Code**.\n
- Check if any patch/diff includes it.\n

Interpretation:
- `git diff` typically does **not** include untracked files; they may only be included if a tool explicitly snapshots the workspace or runs `git status` and uploads extras.\n

## Q5 — Why do we have two patch files?

1) Make sure you have both staged and unstaged changes:

```bash
echo "unstaged change" >> prompts/system_prompt.txt
echo "staged change" >> config/hparams.yaml
git add config/hparams.yaml
git status
```

2) Run:

```bash
python run.py
```

3) Inspect the run’s uploaded patch/diff files:
- Open both patch files and note which changes each contains.\n
- Record whether one corresponds to **staged** changes and the other to **unstaged**, or whether they differ by base (e.g. commit vs working tree).\n

Fill in your observations here once you’ve looked:
- Patch file A name: __________ contains: __________\n
- Patch file B name: __________ contains: __________\n

## Q6 — Do the tracked “code files” include uncommitted changes, or match the git commit?

1) With an uncommitted change present (from any step above), open the run:
- Download/view the uploaded version of the edited file (e.g. `prompts/system_prompt.txt`) from the W&B run.
- Compare it to your local HEAD version and your current working tree.\n

Interpretation:
- If the uploaded file matches HEAD and the diff is in a patch: W&B stores a **clean snapshot + patch**.\n
- If the uploaded file already includes your uncommitted edits: W&B stores a **workspace snapshot** (patch may still exist).\n

## “Function call” toggle test (easy extra diff)

This repo includes `tools/tool_call.py` and a toggle in `config/hparams.yaml`:\n
- Flip `enable_tool_call: true/false` and rerun\n
- Or edit/delete `optional_tool(...)` in `tools/tool_call.py` and rerun\n

This gives you an additional small change target beyond prompt + hyperparameters.


