# Function Calling Dataset Generator

This repository contains the code used to generate the synthetic dataset for training Pythonic function calling model [Dria-Agent-a-7B](https://huggingface.co/driaforall/Dria-Agent-a-7B).

## Overview

The data generation pipeline consists of three main stages, executed sequentially to produce high-quality synthetic data for function calling scenarios. The pipeline leverages the [Dria framework](docs.dria.co) to generate data using multiple models across edge devices.

## Setup

This project uses [uv](https://github.com/astral-sh/uv) for dependency management.

1. Install uv:
```bash
pip install uv
```

2. Create and activate virtual environment:
```bash
uv venv
source .venv/bin/activate  # On Unix
# or
.venv\Scripts\activate  # On Windows
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
./start.sh
```

Or run stages individually:
```bash
chmod +x start.sh
uv run ./start.sh
```

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
