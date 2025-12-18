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


def _dedup_with_dups(sigs: List[str]) -> Tuple[List[str], List[str]]:
    """Return (unique, duplicates_removed)."""
    uniq: List[str] = []
    dups: List[str] = []
    seen: Set[str] = set()
    for s in sigs:
        k = s.strip()
        if k in seen:
            dups.append(s)
        else:
            seen.add(k)
            uniq.append(s)
    return uniq, dups


def _write_debug(enabled: bool, path: str, rec: Dict[str, Any]):
    if not enabled:
        return
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _dedup_with_dups(sigs: List[str]) -> Tuple[List[str], List[str]]:
    """Return (unique_list, duplicates_removed) by signature string (stripped)."""
    seen: Set[str] = set()
    unique: List[str] = []
    dups: List[str] = []
    for s in sigs:
        key = s.strip()
        if key in seen:
            dups.append(s)
        else:
            seen.add(key)
            unique.append(s)
    return unique, dups


def _write_debug(debug_enabled: bool, debug_out_path: str, record: Dict[str, Any]):
    if not debug_enabled:
        return
    try:
        os.makedirs(os.path.dirname(debug_out_path), exist_ok=True)
        with open(debug_out_path, "a", encoding="utf-8") as df:
            df.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        pass

# Fallback regex for function headers
DEF_HEADER_RE = re.compile(r"^def\s+([A-Za-z_]\w*)\s*\(.*?\)\s*->\s*[^:]+:")

def _fallback_extract_functions(full_text: str) -> List[str]:
    """Attempt to salvage function snippets when no <pseudo_function> tags are present.
    Strategy:
    1. Extract ALL python fenced blocks from the entire completion text.
    2. Inside each block, scan lines; when header matches DEF_HEADER_RE, capture until an unindented 'pass' or blank line after docstring.
    3. Return unique snippets.
    """
    code_blocks = extract_code_fence(full_text, lang="python")
    salvaged: List[str] = []
    for block in code_blocks:
        lines = block.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i]
            if DEF_HEADER_RE.match(line.strip()):
                fn_lines = [line]
                i += 1
                while i < len(lines):
                    nxt = lines[i]
                    if nxt.strip().startswith("def "):
                        break
                    fn_lines.append(nxt)
                    if nxt.strip() == "pass":
                        i += 1
                        break
                    i += 1
                salvaged.append("\n".join(fn_lines))
            else:
                i += 1
    # Deduplicate
    out: List[str] = []
    seen: Set[str] = set()
    for s in salvaged:
        k = s.strip()
        if k not in seen:
            seen.add(k)
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
    # Style switch: "distractor" (original out-of-scope) or "related" (contextually complementary)
    style = os.getenv("PSEUDO_STYLE", "distractor").strip().lower()
    if style not in {"distractor", "related"}:
        style = "distractor"
    template_path = (
        "pipeline/s4_pseudo_functions/prompt_related.md"
        if style == "related"
        else "pipeline/s4_pseudo_functions/prompt.md"
    )
    num_pseudo = int(os.getenv("S4_PSEUDO_PER_SAMPLE", "6"))
    max_retries = int(os.getenv("MAX_RETRIES", "2"))
    topup_extra = int(os.getenv("S4_TOPUP_EXTRA", "2"))  # ask a bit more on retries

    output_samples: List[Dict[str, Any]] = []
    global_pseudo_set: Set[str] = set()  # signature-based dedup across samples
    debug_enabled = os.getenv("PSEUDO_DEBUG", "0") == "1"
    debug_path = os.path.join(base_dir, "pseudo_functions_debug.jsonl")

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
        debug_info: Dict[str, List[Dict[str, Any]]] = {"accepted": [], "rejected": []} if debug_enabled else {}
        # Per-sample progress bar towards requested count
        try:
            sample_bar = tqdm(total=num_pseudo, desc=f"sample {idx}", leave=False, dynamic_ncols=True)
        except Exception:
            sample_bar = None
        attempts = 0
        need = num_pseudo
        while attempts == 0 or (len(filtered) < num_pseudo and attempts <= max_retries):
            req_num = need if attempts == 0 else max(1, need) + topup_extra
            # For related style, still pass queries_text; forbidden_keywords kept for backwards compatibility.
            prompt = render_template(
                template_path,
                {
                    "real_function_schemas": json.dumps(real_schemas_this, ensure_ascii=False),
                    "queries_text": forbidden_keywords,
                    "forbidden_keywords": forbidden_keywords,
                    "num_pseudo": str(req_num),
                },
            )
            if style == "related":
                system = (
                    "You generate complementary, non-equivalent helper functions strictly related to the context without duplicating existing semantics."
                )
            else:
                system = (
                    "You are a careful data generator. Produce only out-of-scope pseudo functions that cannot help answer the given queries."
                )
            content = chat_complete(prompt=prompt, system=system)

            pf_blocks = extract_tags(content, "pseudo_function")
            pseudo_sigs: List[str] = []
            if not pf_blocks:
                # Salvage attempt
                salvaged = _fallback_extract_functions(content)
                if salvaged:
                    pf_blocks = [f"<signature>```python\n{sig}\n```</signature>" for sig in salvaged]
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "fallback",
                            "event": "salvaged_functions",
                            "count": len(salvaged),
                        })
                else:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "extract",
                            "event": "none",
                            "reason": "no_pseudo_function_blocks",
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "extract", "reason": "no_pseudo_function_blocks"})
            for pb in pf_blocks:
                sig_blocks = extract_tags(pb, "signature")
                if not sig_blocks:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "extract",
                            "event": "rejected",
                            "reason": "no_signature_block",
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "extract", "reason": "no_signature_block"})
                    continue
                code_blocks = extract_code_fence(sig_blocks[0], lang="python")
                if not code_blocks:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "extract",
                            "event": "rejected",
                            "reason": "no_code_fence",
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "extract", "reason": "no_code_fence"})
                    continue
                pseudo_sigs.append(code_blocks[0])

            pseudo_sigs, inner_dups = _dedup_with_dups(pseudo_sigs)
            for d in inner_dups:
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempts,
                        "phase": "dedup",
                        "event": "rejected",
                        "reason": "duplicate_within_response",
                        "signature": d,
                        "style": style,
                    })
                    debug_info["rejected"].append({"phase": "dedup", "reason": "duplicate_within_response", "signature": d})

            # Safety filters: drop if colliding with real/used or global dups
            added_this_round = 0
            for sig in pseudo_sigs:
                try:
                    parsed = parse_signature(sig)
                    name = parsed.get("function_name")
                except Exception:
                    name = None
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "parse",
                            "event": "rejected",
                            "reason": "parse_failed",
                            "signature": sig,
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "parse", "reason": "parse_failed", "signature": sig})
                if not name:
                    continue
                if name in real_name_set:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "filter",
                            "event": "rejected",
                            "reason": "name_in_real",
                            "signature": sig,
                            "name": name,
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "filter", "reason": "name_in_real", "signature": sig, "name": name})
                    continue
                if name in used_names:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "filter",
                            "event": "rejected",
                            "reason": "name_in_used_trace",
                            "signature": sig,
                            "name": name,
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "filter", "reason": "name_in_used_trace", "signature": sig, "name": name})
                    continue
                key = sig.strip()
                if key in global_pseudo_set:
                    if debug_enabled:
                        _write_debug(debug_enabled, debug_path, {
                            "sample_index": idx,
                            "attempt": attempts,
                            "phase": "filter",
                            "event": "rejected",
                            "reason": "duplicate_global",
                            "signature": sig,
                            "name": name,
                            "style": style,
                        })
                        debug_info["rejected"].append({"phase": "filter", "reason": "duplicate_global", "signature": sig, "name": name})
                    continue
                global_pseudo_set.add(key)
                filtered.append(sig)
                added_this_round += 1
                if debug_enabled:
                    _write_debug(debug_enabled, debug_path, {
                        "sample_index": idx,
                        "attempt": attempts,
                        "phase": "filter",
                        "event": "accepted",
                        "signature": sig,
                        "name": name,
                        "style": style,
                    })
                    debug_info["accepted"].append({"phase": "filter", "signature": sig, "name": name})

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
                "style": style,
                "debug_info": debug_info if debug_enabled else None,
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
