"""Measure source descriptions without importing or starting the MCP application."""

import ast
import json
from pathlib import Path


def tool_profile(node: ast.FunctionDef | ast.AsyncFunctionDef) -> dict:
    descriptions = []
    for argument in node.args.args:
        if argument.annotation is None:
            continue
        for call in ast.walk(argument.annotation):
            if not isinstance(call, ast.Call):
                continue
            for keyword in call.keywords:
                if keyword.arg == "description" and isinstance(keyword.value, ast.Constant):
                    descriptions.append(str(keyword.value.value))
    return {
        "name": node.name,
        "description_chars": len(ast.get_docstring(node) or ""),
        "literal_parameter_description_chars": sum(map(len, descriptions)),
        "parameters": len(node.args.args),
    }


def main() -> None:
    root = Path(__file__).resolve().parents[2]
    profiles = []
    instructions = ""
    for path in sorted((root / "src").rglob("*.py")):
        tree = ast.parse(path.read_text())
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and any(
                isinstance(target, ast.Name) and target.id == "INSTRUCTIONS"
                for target in node.targets
            ):
                instructions = ast.literal_eval(node.value)
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if any(
                isinstance(decorator, ast.Call)
                and isinstance(decorator.func, ast.Attribute)
                and decorator.func.attr == "tool"
                for decorator in node.decorator_list
            ):
                profiles.append(tool_profile(node))
    print(json.dumps({
        "method": "Static AST; docstrings and literal parameter descriptions only. No application imports, network or tokenization.",
        "limitations": "Excludes JSON schema structure, dynamic f-string parameter descriptions, output schemas, host framing, loaded skills and results. Not a tools/list or hidden-context measurement.",
        "tools_count": len(profiles),
        "tools": profiles,
        "total_description_chars": sum(
            item["description_chars"] + item["literal_parameter_description_chars"]
            for item in profiles
        ),
        "instructions_chars": len(instructions),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
