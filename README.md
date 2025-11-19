# Function Calling Dataset Generator

This repository contains the code used to generate the synthetic [dataset](https://huggingface.co/datasets/driaforall/pythonic-function-calling) for training Pythonic function calling model [Dria-Agent-a-7B](https://huggingface.co/driaforall/Dria-Agent-a-7B).

## Overview

The data generation pipeline consists of three main stages, executed sequentially to produce high-quality synthetic data for function calling scenarios. The pipeline leverages the [Dria framework](https://docs.dria.co) to generate data using multiple models across edge devices.

## Setup

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

Make sure you have rust installed:

```bash
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
source "$HOME/.cargo/env"
```

### Linux
Install the following dependencies for `libsecp256k1` on linux:

```bash
sudo apt-get update
sudo apt-get install -y \
    automake \
    autoconf \
    libtool \
    pkg-config \
    libffi-dev \

## Export to multi_turn_eng.jsonl and Validate

Some finetuning pipelines expect a JSONL format like `example/multi_turn_eng.jsonl` (each line is one sample with `tools` JSON schemas and `messages` with function `tool_calls`).

After running Stage 3 and generating `pipeline/data/<run_id>/multi_turn_queries.json`, you can convert to the `multi_turn_eng.jsonl` format and validate it.

1) Convert

```powershell
# Assumes the file `run_id` exists (created by earlier stages)
uv run python pipeline/tools/convert_to_multi_turn_eng.py
# Output: pipeline/data/<run_id>/multi_turn_eng.jsonl
```

2) Validate

```powershell
uv run python pipeline/tools/validate_multi_turn_eng.py pipeline/data/<run_id>/multi_turn_eng.jsonl
```

Notes:
- The converter builds the `tools` list by parsing function signatures from `functions.json` and mapping Python types to JSON Schema.
- The converter reconstructs `messages` from the multi-turn `trace`. It supports both:
    - Single-call turns (legacy): `<query>`, `<function_call>`, `<tool>` repeated.
    - Multi-call turns (new): a `<query>` followed by multiple `<function_call>/<tool>` pairs in the same turn. These are grouped into a single assistant message with multiple `tool_calls`.
- If you prefer to generate directly in this format, we can add an alternate Stage 3 template and schema; the converter is the least invasive path for now.
    libssl-dev \
    python3-dev
sudo apt-get install -y build-essential
```

### MacOS

Install xcode tools for gcc:

```bash
xcode-select --install
```

Install brew and dependencies:

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
brew install automake libtool pkg-config
```

If you're having issues on macOS, see:
- [TKInter Related Issues](https://docs.dria.co/installation/#tkinter-related-issues-on-macos)
- [GCC Related Issues](https://docs.dria.co/installation/#gcc-related-issues-on-macos)

## Installation

1. Install uv:
```bash
pip install uv
```

2. Create and activate virtual environment:
```bash
uv venv
source .venv/bin/activate
```

3. Install dependencies:
```bash
uv pip install -e .
```


## Pipeline Stages

1. **Scenario Generation** (`run_s1.py`)
   - Generates base scenarios from curriculum
   - Uses curriculum.csv as input
   - Produces scenarios.json

2. **Function Generation** (`run_s2.py`)
   - Generates function definitions and schemas
   - Takes scenarios.json as input
   - Produces functions.json

3. **Conversation Generation** (`run_s3.py`)
   - Generates conversation flows and function calls
   - Combines scenarios and functions
   - Produces final dataset entries

## Generated Data Types

| Type | Description | Percentage |
|------|-------------|------------|
| simple | Single function schema, single function call | 27.6% |
| parallel | Single function schema, multiple function calls | 27.5% |
| multiple | Multiple function schemas, single function call | 12.2% |
| step_by_step* | Multiple function schemas, multiple function calls, with step by step reasoning | 21.5% |
| multi_turn | Multiple function schemas, multiple function calls, multi-turn | 11.1% |

*Note: This repository does not include the code for generating the step_by_step category, which accounts for 21.5% of the final dataset.

## Usage

Run the complete pipeline:
```bash
chmod +x start.sh
uv run ./start.sh
```

Or run stages separately:
```bash
uv run run_s1.py
uv run run_s2.py
3. **Conversation Generation** (`run_s3.py`)
```

And you're set. The pipeline will generate the dataset in the `pipeline/data` folder.

4. **Pseudo Functions (Distractors)** (`run_s4_openai.py`)
    - Generates many out-of-scope pseudo functions per multi-turn sample
    - Input: Stage 3 `multi_turn_queries.json` (+ Stage 2 `functions.json` for reference)
    - Ensures pseudo functions are unrelated to the queries and real functions
    - Outputs:
      - `pseudo_functions.json` (per-sample list)
      - `pseudo_functions_global.json` (flat unique list)

#### Including Pseudo Functions in Export

During conversion to `multi_turn_eng.jsonl` you can append the per-sample pseudo functions as distractor tools. Set the environment variable `INCLUDE_PSEUDO_TOOLS=1` when running the converter:

```bash
INCLUDE_PSEUDO_TOOLS=1 uv run python pipeline/tools/convert_to_multi_turn_eng.py
```

Each appended pseudo tool now carries an extra marker field:

```json
{
    "name": "generate_random_username",
    "description": "Auto-generated tool for function generate_random_username",
    "parameters": { "type": "object", "properties": {"base_name": {"type": "string"}, "length": {"type": "integer"}}, "required": ["base_name"] },
    "x_pseudo": true
}
```

Notes:
- Real function tools do NOT have `x_pseudo`; only distractors are tagged.
- Messages (assistant tool calls) never invoke pseudo tools; they appear solely as extra schemas to increase selection difficulty.
- Downstream training can filter pseudo tools with a simple predicate (`if tool.get('x_pseudo'):`) if needed.

Quick inspection snippet (first line only):

```bash
python - <<'PY'
import json, pathlib
run_id=pathlib.Path('run_id').read_text().strip()
fp=pathlib.Path('pipeline/data')/run_id/'multi_turn_eng.jsonl'
first=json.loads(fp.open().readline())
total=len(first['tools'])
pseudo=sum(1 for t in first['tools'] if t.get('x_pseudo'))
print('Total tools:', total, 'Pseudo tools:', pseudo)
print('Pseudo names:', [t['name'] for t in first['tools'] if t.get('x_pseudo')])
PY
```

If you omit `INCLUDE_PSEUDO_TOOLS=1`, the converter will ignore `pseudo_functions.json` and only include real function tools.

_"Data generation takes time!"_ - _Unknown_

### Optional: OpenAI-only mode (no Dria network)

If you cannot reach Dria's token endpoint or prefer to use your own OpenAI API directly, you can run Stage 1 with OpenAI only:

1) Set your OpenAI API key (PowerShell):
```powershell
$env:OPENAI_API_KEY = "sk-..."
 You can include Step 4 pseudo tools by setting `INCLUDE_PSEUDO_TOOLS=1` during conversion; the converter will append pseudo functions (as tools) per-sample if `pseudo_functions.json` exists.
```

2) Optionally set a model (defaults to gpt-4o-mini):
```powershell
$env:OPENAI_MODEL = "gpt-4o-mini"
```

3) Run Stage 1 (OpenAI mode):
 # Optional Step 4 (OpenAI):
 uv run python run_s4_openai.py
```bash
uv run python run_s1_openai.py
### OpenAI-only multi-turn with pseudo functions

```bash
chmod +x start_openai_multiturn_with_pseudo.sh
./start_openai_multiturn_with_pseudo.sh

# Optionally export with pseudo tools appended
INCLUDE_PSEUDO_TOOLS=1 uv run python pipeline/tools/convert_to_multi_turn_eng.py
```

```

This will read `pipeline/data/curriculum.csv`, use `pipeline/s1_scenario/prompt.md` to prompt the model, parse `<scenario>` tags, and write `pipeline/data/<run_id>/scenarios.json`.

Notes:
- You can control the number of scenarios per row with `S1_NUM_SCENARIOS` env var (default: 10).
- You can still use the original pipeline for subsequent stages, or we can extend OpenAI-only runners for Stage 2/3 on request.

## Pipeline Folder Structure

```
├── pipeline/
│   ├── data/              
│   ├── s1_scenario/           # Stage 1: Scenario generation
│   │   ├── __init__.py
│   │   ├── prompt.md
│   │   └── task.py
│   ├── s2_functions/          # Stage 2: Function generation
│   │   ├── __init__.py
│   │   ├── parser.py
│   │   ├── prompt.md
│   │   └── task.py
│   └── s3_queries/            # Stage 3: Query generation
│       ├── multiturn/         # Multi-turn conversation generation
│       │   ├── __init__.py
│       │   ├── prompt.md
│       │   └── task.py
│       ├── parallel/          # Parallel function calls generation
│       │   ├── __init__.py
│       │   ├── prompt.md
│       │   └── task.py
│       └── simple/            # Simple function calls generation
│           ├── __init__.py
│           ├── prompt.md
│           └── task.py
```

## Output

The pipeline generates data in the following format:

```python
{
    "id": string,
    "domain": string,
    "subdomain": string,
    "tools": string,
    "conversations": [
        {
            "content": string,
            "role": string
        }
    ],
    "type": string
}
```
## License

Apache 2.0

## Additional Information

Filtering and multi-turn data generation with RLEF is not included in this repo. 

For more information about the generated dataset and its applications, see:
- [Dataset Documentation](https://huggingface.co/datasets/driaforall/pythonic_function_calling)
- [Model Documentation](https://huggingface.co/driaforall/Dria-Agent-a-7B)
- [Dria Framework](docs.dria.co)
