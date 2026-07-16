"""Conservative static discovery of dynamic claim-bearing annotations.

The scanner is deliberately not a general program evaluator.  It only marks
dynamic text at common figure-annotation sinks when the expression contains a
statistical-claim signal.  A mark asks for publication review; it does not
prevent rendering or constrain how an author builds a figure.
"""

from __future__ import annotations

import ast
import re

_CLAIM_NAME_RE = re.compile(
    r"(?:^|_)(?:p|q)(?:value|val)?(?:_|$)|claim|signif|stars?|stat(?:istic)?",
    re.IGNORECASE,
)
_CLAIM_FRAGMENT_RE = re.compile(r"\b(?:p|q)\s*(?:<=|<|=|>|≥|≤)", re.IGNORECASE)
_ANNOTATION_CALLS = {
    "add_annotation",
    "annotate",
    "axis",
    "bar_label",
    "clabel",
    "figtext",
    "ggtitle",
    "geom_label",
    "geom_signif",
    "geom_text",
    "grid.text",
    "legend",
    "labs",
    "mtext",
    "pie",
    "scale_x_discrete",
    "scale_y_discrete",
    "set_label",
    "set_xticks",
    "set_yticks",
    "setp",
    "set_text",
    "set_title",
    "set_xlabel",
    "set_xticklabels",
    "set_ylabel",
    "set_yticklabels",
    "suptitle",
    "table",
    "text",
    "title",
    "xlabel",
    "xticks",
    "ylabel",
    "yticks",
}
_WRAPPER_NAME_RE = re.compile(
    r"annotat|label|legend|text|title|decorate|draw|render|display|"
    r"(?:add|mark|show|write).*(?:claim|signif|(?:^|_)sig(?:_|$)|p.?value)",
    re.IGNORECASE,
)


def _call_name(call: ast.Call) -> str:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id.lower()
    if isinstance(func, ast.Attribute):
        return func.attr.lower()
    return ""


def _python_aliases(tree: ast.AST) -> dict[str, str]:
    aliases: dict[str, str] = {}
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if isinstance(node.value, ast.Attribute):
            aliases[target.id.lower()] = node.value.attr.lower()
        elif isinstance(node.value, ast.Name):
            aliases[target.id.lower()] = aliases.get(node.value.id.lower(), node.value.id.lower())
    return aliases


def _resolved_call_name(call: ast.Call, aliases: dict[str, str]) -> str:
    name = _call_name(call)
    visited: set[str] = set()
    while name in aliases and name not in visited:
        visited.add(name)
        name = aliases[name]
    return name


def _python_annotation_expressions(call: ast.Call, name: str) -> list[ast.AST]:
    """Return possible displayed-text expressions for known annotation calls."""

    if name not in _ANNOTATION_CALLS:
        return []
    expressions: list[ast.AST] = []
    keyword_names = {
        "celltext",
        "collabels",
        "fmt",
        "label",
        "labels",
        "rowlabels",
        "s",
        "t",
        "text",
        "tick_labels",
        "title",
    }
    expressions.extend(
        keyword.value for keyword in call.keywords if keyword.arg is not None and keyword.arg.lower() in keyword_names
    )
    positional_indexes: tuple[int, ...]
    if name in {"text", "figtext"}:
        # matplotlib uses index 2; PIL.ImageDraw.text uses index 1.
        positional_indexes = (1, 2)
    elif name == "annotate":
        positional_indexes = (0,)
    elif name == "legend":
        positional_indexes = (0, 1)
    elif name in {"axis", "set_xticks", "set_yticks", "xticks", "yticks"}:
        positional_indexes = (1, 2)
    elif name == "pie":
        positional_indexes = (1, 2)
    elif name == "table":
        positional_indexes = (0,)
    elif name == "bar_label":
        positional_indexes = ()
    elif name in {
        "clabel",
        "set_label",
        "set_text",
        "set_title",
        "set_xlabel",
        "set_xticklabels",
        "set_ylabel",
        "set_yticklabels",
        "suptitle",
        "title",
        "ggtitle",
        "mtext",
        "xlabel",
        "ylabel",
    }:
        positional_indexes = (0,)
    else:
        positional_indexes = ()
    expressions.extend(call.args[index] for index in positional_indexes if index < len(call.args))
    return expressions


def _python_assignments(tree: ast.AST) -> dict[str, ast.AST]:
    assignments: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            value = node.value
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                if isinstance(target, ast.Name) and value is not None:
                    assignments[target.id] = value
    return assignments


def _python_string_fragments(node: ast.AST) -> list[str]:
    return [child.value for child in ast.walk(node) if isinstance(child, ast.Constant) and isinstance(child.value, str)]


def _python_static_string(node: ast.AST, assignments: dict[str, ast.AST], seen: set[str]) -> str | None:
    """Fold only side-effect-free, bounded string expressions."""

    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.Name) and node.id in assignments and node.id not in seen:
        return _python_static_string(assignments[node.id], assignments, seen | {node.id})
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _python_static_string(node.left, assignments, seen)
        right = _python_static_string(node.right, assignments, seen)
        if left is not None and right is not None and len(left) + len(right) <= 4096:
            return left + right
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult):
        if isinstance(node.left, ast.Constant) and isinstance(node.left.value, str):
            if isinstance(node.right, ast.Constant) and isinstance(node.right.value, int):
                if 0 <= node.right.value <= 128:
                    return node.left.value * node.right.value
    return None


def _python_is_dynamic(node: ast.AST, assignments: dict[str, ast.AST], seen: set[str]) -> bool:
    if isinstance(node, ast.Constant):
        return False
    if isinstance(node, ast.Name):
        if node.id in assignments and node.id not in seen:
            return _python_is_dynamic(assignments[node.id], assignments, seen | {node.id})
        return True
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp):
        return _python_is_dynamic(node.left, assignments, seen) or _python_is_dynamic(node.right, assignments, seen)
    if isinstance(node, ast.Call):
        return True
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_python_is_dynamic(value, assignments, seen) for value in node.elts)
    if isinstance(node, ast.Dict):
        return any(_python_is_dynamic(value, assignments, seen) for value in node.values)
    return isinstance(node, (ast.Attribute, ast.Subscript, ast.IfExp, ast.Lambda))


def _python_is_dynamic_text(node: ast.AST, assignments: dict[str, ast.AST], seen: set[str]) -> bool:
    """Recognize text construction without treating numeric claim calculations as display."""

    if isinstance(node, ast.Name) and node.id in assignments and node.id not in seen:
        return _python_is_dynamic_text(assignments[node.id], assignments, seen | {node.id})
    if isinstance(node, ast.JoinedStr):
        return any(isinstance(value, ast.FormattedValue) for value in node.values)
    if isinstance(node, ast.BinOp):
        return bool(_python_string_fragments(node)) and _python_is_dynamic(node, assignments, seen)
    if isinstance(node, ast.Call):
        return bool(_python_string_fragments(node)) or (
            isinstance(node.func, ast.Attribute) and node.func.attr in {"format", "join"}
        )
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return any(_python_is_dynamic_text(value, assignments, seen) for value in node.elts)
    if isinstance(node, ast.Dict):
        return any(_python_is_dynamic_text(value, assignments, seen) for value in node.values)
    return False


def _python_has_claim_signal(node: ast.AST, assignments: dict[str, ast.AST], seen: set[str]) -> bool:
    static = _python_static_string(node, assignments, seen)
    fragments = static if static is not None else " ".join(_python_string_fragments(node))
    if _CLAIM_FRAGMENT_RE.search(fragments):
        return True
    if "*" in fragments:
        return True
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and _CLAIM_NAME_RE.search(child.id):
            return True
        if isinstance(child, ast.Attribute) and _CLAIM_NAME_RE.search(child.attr):
            return True
        if isinstance(child, ast.Name) and child.id in assignments and child.id not in seen:
            if _python_has_claim_signal(assignments[child.id], assignments, seen | {child.id}):
                return True
    return False


def _python_wrappers(tree: ast.AST, aliases: dict[str, str]) -> dict[str, tuple[list[str], set[str]]]:
    """Map simple local wrappers to parameters forwarded to annotation sinks."""

    wrappers: dict[str, tuple[list[str], set[str]]] = {}
    for function in (node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))):
        parameters = [argument.arg for argument in function.args.args]
        forwarded: set[str] = set()
        for call in (node for node in ast.walk(function) if isinstance(node, ast.Call)):
            name = _resolved_call_name(call, aliases)
            for expression in _python_annotation_expressions(call, name):
                forwarded.update(
                    child.id for child in ast.walk(expression) if isinstance(child, ast.Name) and child.id in parameters
                )
        if forwarded:
            wrappers[function.name.lower()] = (parameters, forwarded)
    return wrappers


def _python_wrapper_expressions(
    call: ast.Call,
    name: str,
    wrappers: dict[str, tuple[list[str], set[str]]],
) -> list[ast.AST]:
    if name not in wrappers:
        return []
    parameters, forwarded = wrappers[name]
    values: list[ast.AST] = []
    for index, argument in enumerate(call.args):
        if index < len(parameters) and parameters[index] in forwarded:
            values.append(argument)
    values.extend(keyword.value for keyword in call.keywords if keyword.arg is not None and keyword.arg in forwarded)
    return values


def _python_display_values(node: ast.AST) -> list[ast.AST]:
    if isinstance(node, (ast.List, ast.Tuple, ast.Set)):
        return [value for item in node.elts for value in _python_display_values(item)]
    if isinstance(node, ast.Dict):
        return [value for item in node.values for value in _python_display_values(item)]
    return [node]


def _source_segment(script_text: str, node: ast.AST) -> str:
    segment = ast.get_source_segment(script_text, node) or node.__class__.__name__
    return " ".join(segment.split())[:240]


def _python_analysis(script_text: str) -> tuple[list[str], bool, list[dict[str, str]]]:
    try:
        tree = ast.parse(script_text)
    except SyntaxError:
        return [], False, []
    literals = [node.value for node in ast.walk(tree) if isinstance(node, ast.Constant) and isinstance(node.value, str)]
    assignments = _python_assignments(tree)
    aliases = _python_aliases(tree)
    wrappers = _python_wrappers(tree, aliases)
    dynamic: list[dict[str, str]] = []
    for call in (node for node in ast.walk(tree) if isinstance(node, ast.Call)):
        name = _resolved_call_name(call, aliases)
        expressions = _python_annotation_expressions(call, name)
        expressions.extend(_python_wrapper_expressions(call, name, wrappers))
        if not expressions and _WRAPPER_NAME_RE.search(name):
            expressions = [*call.args, *(keyword.value for keyword in call.keywords)]
        elif not expressions:
            expressions = [
                expression
                for expression in [*call.args, *(keyword.value for keyword in call.keywords)]
                if _python_is_dynamic_text(expression, assignments, set())
                and _python_has_claim_signal(expression, assignments, set())
            ]
        expressions = [value for expression in expressions for value in _python_display_values(expression)]
        for expression in expressions:
            static = _python_static_string(expression, assignments, set())
            if static is not None:
                literals.append(static)
                continue
            if _python_is_dynamic(expression, assignments, set()) and _python_has_claim_signal(
                expression, assignments, set()
            ):
                dynamic.append(
                    {
                        "source": f"python_annotation:{name}",
                        "expression": _source_segment(script_text, expression),
                        "reason": "dynamic statistical-claim annotation cannot be verified statically",
                    }
                )
    return literals, True, _deduplicate(dynamic)


def _balanced_r_calls(script_text: str, allowed_names: set[str] | None = None) -> list[tuple[str, str]]:
    starts = re.finditer(r"\b([A-Za-z.][\w.]*)\s*\(", script_text)
    calls: list[tuple[str, str]] = []
    for match in starts:
        name = match.group(1).lower()
        if allowed_names is not None and name not in allowed_names:
            continue
        depth = 1
        quote = ""
        escaped = False
        index = match.end()
        while index < len(script_text) and depth:
            char = script_text[index]
            if quote:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == quote:
                    quote = ""
            elif char in {"'", '"'}:
                quote = char
            elif char == "(":
                depth += 1
            elif char == ")":
                depth -= 1
            index += 1
        if depth == 0:
            calls.append((name, script_text[match.start() : index]))
    return calls


def _r_split_arguments(call_text: str) -> list[str]:
    """Split a balanced R call without evaluating its arguments."""

    opening = call_text.find("(")
    if opening < 0 or not call_text.rstrip().endswith(")"):
        return []
    source = call_text[opening + 1 : call_text.rfind(")")]
    arguments: list[str] = []
    start = 0
    depths = {"(": 0, "[": 0, "{": 0}
    pairs = {")": "(", "]": "[", "}": "{"}
    quote = ""
    escaped = False
    for index, char in enumerate(source):
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
            continue
        if char in {"'", '"'}:
            quote = char
        elif char in depths:
            depths[char] += 1
        elif char in pairs:
            depths[pairs[char]] = max(0, depths[pairs[char]] - 1)
        elif char == "," and not any(depths.values()):
            arguments.append(source[start:index].strip())
            start = index + 1
    tail = source[start:].strip()
    if tail:
        arguments.append(tail)
    return arguments[:64]


def _r_named_argument(argument: str) -> tuple[str | None, str]:
    match = re.match(r"^\s*([A-Za-z.][\w.]*)\s*=\s*(?!=)(.+)$", argument, re.DOTALL)
    if match:
        return match.group(1).lower(), match.group(2).strip()
    return None, argument.strip()


def _r_annotation_expressions(call_text: str, name: str) -> list[str]:
    arguments = _r_split_arguments(call_text)
    named = [_r_named_argument(argument) for argument in arguments]
    keyword_names = {
        "label",
        "labels",
        "legend",
        "main",
        "sub",
        "text",
        "title",
        "xlab",
        "ylab",
    }
    expressions = [value for keyword, value in named if keyword in keyword_names]
    positional = [value for keyword, value in named if keyword is None]
    indexes: tuple[int, ...]
    if name == "text":
        indexes = (2,)
    elif name == "grid.text":
        indexes = (0,)
    elif name == "legend":
        indexes = (1,)
    elif name == "axis":
        indexes = (2,)
    elif name in {"mtext", "title", "ggtitle"}:
        indexes = (0,)
    else:
        indexes = ()
    expressions.extend(positional[index] for index in indexes if index < len(positional))

    # ggplot annotations commonly bury the display mapping in aes(label=...).
    if name in {"geom_label", "geom_text", "geom_signif"}:
        expressions.extend(value for _keyword, value in named if re.search(r"\blabel\s*=", value, re.IGNORECASE))
    return expressions


def _r_matching_brace(script_text: str, opening: int) -> int | None:
    depth = 1
    quote = ""
    escaped = False
    for index in range(opening + 1, len(script_text)):
        char = script_text[index]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = ""
        elif char in {"'", '"'}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return index
    return None


def _r_function_definitions(script_text: str) -> dict[str, tuple[list[str], str]]:
    """Collect bounded, brace-delimited local wrappers only."""

    definitions: dict[str, tuple[list[str], str]] = {}
    pattern = re.compile(r"(?m)^\s*([A-Za-z.][\w.]*)\s*(?:<-|=)\s*function\s*\(([^)]*)\)\s*\{")
    for match in list(pattern.finditer(script_text))[:128]:
        closing = _r_matching_brace(script_text, match.end() - 1)
        if closing is None:
            continue
        parameters = []
        for argument in _r_split_arguments(f"f({match.group(2)})"):
            parameter = argument.split("=", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z.][\w.]*", parameter):
                parameters.append(parameter)
        definitions[match.group(1).lower()] = (parameters, script_text[match.end() : closing])
    return definitions


def _r_aliases(script_text: str) -> dict[str, str]:
    aliases: dict[str, str] = {}
    pattern = re.compile(r"(?m)^\s*([A-Za-z.][\w.]*)\s*(?:<-|=)\s*([A-Za-z.][\w.]*)\s*(?:#.*)?$")
    for match in pattern.finditer(script_text):
        aliases[match.group(1).lower()] = match.group(2).lower()
    return aliases


def _r_resolved_name(name: str, aliases: dict[str, str]) -> str:
    visited: set[str] = set()
    while name in aliases and name not in visited:
        visited.add(name)
        name = aliases[name]
    return name


def _r_wrapper_expressions(
    call_text: str,
    name: str,
    wrappers: dict[str, tuple[list[str], set[str]]],
) -> list[str]:
    if name not in wrappers:
        return []
    parameters, forwarded = wrappers[name]
    values: list[str] = []
    positional_index = 0
    for argument in _r_split_arguments(call_text):
        keyword, value = _r_named_argument(argument)
        if keyword is not None:
            if keyword in forwarded:
                values.append(value)
            continue
        if positional_index < len(parameters) and parameters[positional_index] in forwarded:
            values.append(value)
        positional_index += 1
    return values


def _r_wrappers(script_text: str, aliases: dict[str, str]) -> dict[str, tuple[list[str], set[str]]]:
    """Map local R wrapper parameters forwarded into display-text sinks."""

    definitions = _r_function_definitions(script_text)
    wrappers: dict[str, tuple[list[str], set[str]]] = {}
    callable_names = set(_ANNOTATION_CALLS) | set(definitions) | set(aliases)
    for _depth in range(8):
        changed = False
        for function_name, (parameters, body) in definitions.items():
            forwarded = set(wrappers.get(function_name, (parameters, set()))[1])
            for raw_name, call_text in _balanced_r_calls(body, callable_names):
                name = _r_resolved_name(raw_name, aliases)
                if name in _ANNOTATION_CALLS:
                    expressions = _r_annotation_expressions(call_text, name)
                else:
                    expressions = _r_wrapper_expressions(call_text, name, wrappers)
                forwarded.update(
                    parameter
                    for parameter in parameters
                    if any(re.search(rf"\b{re.escape(parameter)}\b", expression) for expression in expressions)
                )
            previous = wrappers.get(function_name)
            current = (parameters, forwarded)
            if forwarded and previous != current:
                wrappers[function_name] = current
                changed = True
        if not changed:
            break
    return wrappers


def _r_analysis(script_text: str) -> tuple[list[str], bool, list[dict[str, str]]]:
    quoted = re.findall(r"(['\"])(.*?)(?<!\\)\1", script_text, flags=re.DOTALL)
    literals = [value for _quote, value in quoted]
    assignments: dict[str, str] = {}
    for match in re.finditer(r"(?m)^\s*([A-Za-z.][\w.]*)\s*(?:<-|=)\s*(.+?)\s*$", script_text):
        value = match.group(2).strip()
        if not value.lower().startswith("function"):
            assignments[match.group(1)] = value
    aliases = _r_aliases(script_text)
    wrappers = _r_wrappers(script_text, aliases)
    dynamic: list[dict[str, str]] = []
    dynamic_construct = re.compile(r"\b(?:paste0?|sprintf|glue|format)\s*\(", re.IGNORECASE)
    callable_names = set(_ANNOTATION_CALLS) | set(wrappers) | set(aliases)
    for raw_name, call_text in _balanced_r_calls(script_text, callable_names):
        name = _r_resolved_name(raw_name, aliases)
        expressions = (
            _r_annotation_expressions(call_text, name)
            if name in _ANNOTATION_CALLS
            else _r_wrapper_expressions(call_text, name, wrappers)
        )
        for expression in expressions:
            expanded = expression
            referenced_claim_value = False
            for variable, value in assignments.items():
                if re.search(rf"\b{re.escape(variable)}\b", expression) and (
                    _CLAIM_NAME_RE.search(variable)
                    or _CLAIM_FRAGMENT_RE.search(value)
                    or dynamic_construct.search(value)
                ):
                    expanded += " " + value
                    referenced_claim_value = True
            direct_claim_variable = bool(
                re.fullmatch(r"\s*([A-Za-z.][\w.]*)\s*", expression)
                and any(_CLAIM_NAME_RE.search(match) for match in re.findall(r"\b([A-Za-z.][\w.]*)\b", expression))
            )
            quoted_parts = [value for _quote, value in re.findall(r"(['\"])(.*?)(?<!\\)\1", expanded, flags=re.DOTALL)]
            collapsed_literals = "".join(quoted_parts)
            claim_signal = bool(
                _CLAIM_FRAGMENT_RE.search(expanded)
                or _CLAIM_FRAGMENT_RE.search(collapsed_literals)
                or re.search(r"['\"]\*{1,4}['\"]", expanded)
                or referenced_claim_value
                or direct_claim_variable
            )
            is_dynamic = bool(dynamic_construct.search(expanded) or referenced_claim_value or direct_claim_variable)
            if is_dynamic and claim_signal:
                dynamic.append(
                    {
                        "source": f"r_annotation:{name}",
                        "expression": " ".join(expression.split())[:240],
                        "reason": "dynamic statistical-claim annotation cannot be verified statically",
                    }
                )
    return literals, True, _deduplicate(dynamic)


def _deduplicate(items: list[dict[str, str]]) -> list[dict[str, str]]:
    return list({(item["source"], item["expression"]): item for item in items}.values())


def analyze_claim_script(script_text: str, suffix: str) -> tuple[list[str], bool, list[dict[str, str]]]:
    """Return string literals, parse status, and dynamic claim annotations."""

    if suffix == ".py":
        return _python_analysis(script_text)
    if suffix == ".r":
        return _r_analysis(script_text)
    return [], False, []


__all__ = ["analyze_claim_script"]
