import re
import ast


def parse_signature(function: str) -> dict:
    """Parse a Python function signature (with optional docstring/body) into structured metadata.

    Priority:
    1. AST-based parsing (robust; supports complex annotations like Optional[List[int]], Union[str,int], dict[str,int]).
    2. Fallback to legacy regex for extremely malformed but simple signatures.

    Returns dict:
        {
          'function_name': str,
          'return_type': str | None,
          'parameters': [(name, type_str, default_str_or_None), ...]
        }
    """
    cleaned = function.strip()
    # Attempt AST parse
    try:
        module = ast.parse(cleaned)
        func_node = None
        for node in module.body:
            if isinstance(node, ast.FunctionDef):
                func_node = node
                break
        if func_node is None:
            raise ValueError("No function def found")
        func_name = func_node.name
        # Return annotation
        if func_node.returns is not None:
            try:
                return_type = ast.unparse(func_node.returns)  # type: ignore[attr-defined]
            except Exception:
                return_type = getattr(func_node.returns, 'id', None)
        else:
            return_type = None

        # Map defaults: last N args get defaults list order
        params = []
        args = func_node.args.args
        defaults = func_node.args.defaults
        num_positional = len(args)
        num_defaults = len(defaults)
        default_start = num_positional - num_defaults
        for i, arg in enumerate(args):
            p_name = arg.arg
            # Annotation
            if arg.annotation is not None:
                try:
                    p_type = ast.unparse(arg.annotation)  # type: ignore[attr-defined]
                except Exception:
                    p_type = getattr(arg.annotation, 'id', 'Any')
            else:
                p_type = 'Any'
            # Default value
            p_default = None
            if i >= default_start:
                default_node = defaults[i - default_start]
                try:
                    # Try to produce a simple literal form
                    p_default = ast.unparse(default_node)  # type: ignore[attr-defined]
                except Exception:
                    try:
                        p_default = getattr(default_node, 'value', None)
                    except Exception:
                        p_default = None
            params.append((p_name, p_type, p_default))

        return {
            'function_name': func_name,
            'return_type': return_type,
            'parameters': params,
        }
    except Exception:
        # Legacy regex fallback (simple pattern) to preserve previous behavior
        signature_pattern = re.compile(
            r"def\s+([A-Za-z_]\w*)\s*\((.*?)\)\s*->\s*([A-Za-z_][\w\[\]]*)\s*:", re.DOTALL
        )
        match = signature_pattern.search(cleaned)
        if match:
            func_name = match.group(1)
            params_str = match.group(2)
            return_type = match.group(3)
            param_pattern = re.compile(r"(\w+)\s*:\s*([\w\[\]]+)(?:\s*=\s*([^,]+))?")
            params = []
            for pm in param_pattern.finditer(params_str):
                p_name = pm.group(1)
                p_type = pm.group(2)
                p_default = pm.group(3)
                params.append((p_name, p_type, p_default))
            return {
                'function_name': func_name,
                'return_type': return_type,
                'parameters': params,
            }
        return {}
