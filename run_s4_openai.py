import asyncio
import json
import logging
import os
import re
from typing import Any, Dict, List, Set, Tuple

from tqdm import tqdm
from openai_utils import render_template, extract_tags, extract_code_fence, chat_complete
from pipeline.s2_functions.parser import parse_signature

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")


def _collect_used_function_names(trace: List[Dict[str, str]]) -> List[str]:
    names: List[str] = []
    call_re = re.compile(r"^\s*([A-Za-z_]\w*)\s*\(")
    for t in trace:
        if "function_call" in t:
            s = t["function_call"].strip()
            m = re.match(r"^\s*([A-Za-z_]\w*)\s*\(", s)
            if m:
                names.append(m.group(1))
    return names


def _build_forbidden_keywords(sample: Dict[str, Any]) -> str:
    # Aggregate query texts as forbidden context
    texts: List[str] = []
    for t in sample.get("trace", []):
        if "query" in t:
            texts.append(t["query"])
    # Include domain/subdomain as forbidden hints
    if sample.get("domain"):
        texts.append(str(sample["domain"]))
    if sample.get("subdomain"):
        texts.append(str(sample["subdomain"]))
    # Return a compact joined string (prompt will treat as forbidden topics)
    return " \n".join(texts)[:4000]


def _dedup_signatures(sigs: List[str]) -> List[str]:
    seen: Set[str] = set()
    out: List[str] = []
    for s in sigs:
        key = s.strip()
        if key not in seen:
            seen.add(key)
            out.append(s)
    return out


async def generate_pseudo_functions_openai(run_id: str):
    base_dir = f"pipeline/data/{run_id}"
    # Load step3 output (multi-turn as default input)
    multi_turn_fp = os.path.join(base_dir, "multi_turn_queries.json")
    if not os.path.exists(multi_turn_fp):
        raise FileNotFoundError("multi_turn_queries.json not found. Please run Step 3 first.")

    with open(multi_turn_fp, "r", encoding="utf-8") as f:
        multi_turn_data: List[Dict[str, Any]] = json.load(f)

    # Load functions to know real schemas and map names
    with open(os.path.join(base_dir, "functions.json"), "r", encoding="utf-8") as f:
        functions_data: List[Dict[str, Any]] = json.load(f)

    # Build a global mapping for real function names and signatures for reference
    real_function_schemas_all: List[str] = []
    real_name_set: Set[str] = set()
    for entry in functions_data:
        for func in entry.get("functions", []):
            sig: str = func["function"]
            real_function_schemas_all.append(sig)
            try:
                parsed = parse_signature(sig)
                name = parsed.get("function_name")
                if name:
                    real_name_set.add(name)
            except Exception:
                pass

    # Config
    template_path = "pipeline/s4_pseudo_functions/prompt.md"
    num_pseudo = int(os.getenv("S4_PSEUDO_PER_SAMPLE", "6"))
    max_retries = int(os.getenv("S4_MAX_RETRIES", "2"))
    topup_extra = int(os.getenv("S4_TOPUP_EXTRA", "2"))  # ask a bit more on retries

    output_samples: List[Dict[str, Any]] = []
    global_pseudo_set: Set[str] = set()  # signature-based dedup across samples

    outer_bar = tqdm(total=len(multi_turn_data), desc="Step4 Pseudo Functions", dynamic_ncols=True)
    for idx, sample in enumerate(multi_turn_data):
        # Gather forbidden keywords from queries and domain hints
        forbidden_keywords = _build_forbidden_keywords(sample)
        # Real functions per sample (schemas) from the sample field
        real_schemas_this = sample.get("function_schemas", [])
        if not real_schemas_this:
            # Fallback to all
            real_schemas_this = real_function_schemas_all

        # Also pass used function names to reduce overlap chances (prompt will see as context via schemas)
        used_names = _collect_used_function_names(sample.get("trace", []))

        filtered: List[str] = []
        # Per-sample progress bar towards requested count
        try:
            sample_bar = tqdm(total=num_pseudo, desc=f"sample {idx}", leave=False, dynamic_ncols=True)
        except Exception:
            sample_bar = None
        attempts = 0
        need = num_pseudo
        while attempts == 0 or (len(filtered) < num_pseudo and attempts <= max_retries):
            req_num = need if attempts == 0 else max(1, need) + topup_extra
            prompt = render_template(
                template_path,
                {
                    "real_function_schemas": json.dumps(real_schemas_this, ensure_ascii=False),
                    "queries_text": forbidden_keywords,
                    "forbidden_keywords": forbidden_keywords,
                    "num_pseudo": str(req_num),
                },
            )
            system = (
                "You are a careful data generator. Produce only out-of-scope pseudo functions that cannot help answer the given queries."
            )
            content = chat_complete(prompt=prompt, system=system)

            pf_blocks = extract_tags(content, "pseudo_function")
            pseudo_sigs: List[str] = []
            for pb in pf_blocks:
                sig_blocks = extract_tags(pb, "signature")
                if not sig_blocks:
                    continue
                code_blocks = extract_code_fence(sig_blocks[0], lang="python")
                if not code_blocks:
                    continue
                sig = code_blocks[0]
                pseudo_sigs.append(sig)

            pseudo_sigs = _dedup_signatures(pseudo_sigs)

            # Safety filters: drop if colliding with real/used or global dups
            added_this_round = 0
            for sig in pseudo_sigs:
                try:
                    parsed = parse_signature(sig)
                    name = parsed.get("function_name")
                except Exception:
                    name = None
                if not name:
                    continue
                if name in real_name_set:
                    continue
                if name in used_names:
                    continue
                key = sig.strip()
                if key in global_pseudo_set:
                    continue
                global_pseudo_set.add(key)
                filtered.append(sig)
                added_this_round += 1

            need = max(0, num_pseudo - len(filtered))
            # update per-sample progress
            if sample_bar is not None and added_this_round > 0:
                try:
                    sample_bar.update(min(added_this_round, max(0, num_pseudo - sample_bar.n)))
                except Exception:
                    pass
            attempts += 1

        output_samples.append(
            {
                "sample_index": idx,
                "domain": sample.get("domain"),
                "subdomain": sample.get("subdomain"),
                "pseudo_functions": filtered[:num_pseudo],
            }
        )
        # close and update outer progress
        if sample_bar is not None:
            try:
                sample_bar.close()
            except Exception:
                pass
        try:
            outer_bar.update(1)
            outer_bar.set_postfix({"last": f"{min(len(filtered), num_pseudo)}/{num_pseudo}"})
        except Exception:
            pass

    # Write outputs
    os.makedirs(base_dir, exist_ok=True)
    with open(os.path.join(base_dir, "pseudo_functions.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(output_samples, ensure_ascii=False, indent=2))

    # Also write a global unique list (flat)
    all_unique = []
    for s in output_samples:
        for sig in s["pseudo_functions"]:
            all_unique.append(sig)
    with open(os.path.join(base_dir, "pseudo_functions_global.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(_dedup_signatures(all_unique), ensure_ascii=False, indent=2))
    try:
        outer_bar.close()
    except Exception:
        pass


async def main():
    with open("run_id", "r", encoding="utf-8") as run_id_fp:
        run_id = run_id_fp.read().strip()
    logging.info(f"Run ID: {run_id}")
    await generate_pseudo_functions_openai(run_id)
    logging.info("Generated Pseudo Functions (OpenAI Step 4)")


if __name__ == "__main__":
    asyncio.run(main())
