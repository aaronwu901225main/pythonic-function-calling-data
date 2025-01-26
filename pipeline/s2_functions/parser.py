import re


def parse_signature(function: str) -> dict:
    signature_pattern = re.compile(
        r"def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*->\s*([A-Za-z_][\w\[\]]*)\s*:", re.DOTALL
    )

    match = signature_pattern.search(function)
    if match:
        func_name = match.group(1)
        params_str = match.group(2)
        return_type = match.group(3)

        # Pattern for parsing parameters
        param_pattern = re.compile(r"(\w+)\s*:\s*([\w\[\]]+)(?:\s*=\s*([^,]+))?")

        params = []
        for pm in param_pattern.finditer(params_str):
            p_name = pm.group(1)
            p_type = pm.group(2)
            p_default = pm.group(3)
            params.append((p_name, p_type, p_default))

        return {
            "function_name": func_name,
            "return_type": return_type,
            "parameters": params,
        }
    else:
        return {}
