import re
from dataclasses import dataclass, field

import tree_sitter_javascript as tsjs
import tree_sitter_python as tspython
import tree_sitter_typescript as tsts
from tree_sitter import Language, Parser

LANGS = {
    "python": Language(tspython.language()),
    "javascript": Language(tsjs.language()),          # also handles JSX
    "typescript": Language(tsts.language_typescript()),
    "tsx": Language(tsts.language_tsx()),
}

HTTP_METHODS = {"get", "post", "put", "delete", "patch"}
PY_ROUTE = re.compile(
    r"@\s*[\w.]+\.(get|post|put|delete|patch)\(\s*[\"']([^\"']*)[\"']"
)
# app.get(...) / router.post(...) yes, axios.get(...) no
JS_ROUTER_NAME = re.compile(r"(app|router|server|\w*router|\w*app)", re.IGNORECASE)


@dataclass
class SymbolInfo:
    name: str
    kind: str  # function | class | method | route | interface
    start_line: int
    end_line: int


@dataclass
class ImportRef:
    module: str                  # python: "app.db" or "db"; js/ts: "./utils"
    level: int = 0               # python relative imports: number of leading dots
    names: list[str] = field(default_factory=list)


@dataclass
class ParseResult:
    symbols: list[SymbolInfo]
    imports: list[ImportRef]


def make_parsers() -> dict[str, Parser]:
    """Parsers aren't thread-safe, so create a fresh set per analysis run."""
    return {name: Parser(lang) for name, lang in LANGS.items()}


def _text(node) -> str:
    return node.text.decode("utf-8", errors="replace")


def _sym(name: str, kind: str, node) -> SymbolInfo:
    return SymbolInfo(name[:255], kind, node.start_point[0] + 1, node.end_point[0] + 1)


def parse_python(parser: Parser, source: str) -> ParseResult:
    tree = parser.parse(source.encode("utf-8"))
    symbols: list[SymbolInfo] = []
    imports: list[ImportRef] = []
    stack = [(tree.root_node, False)]  # (node, directly inside a class?)

    while stack:
        node, in_class = stack.pop()
        t = node.type
        child_in_class = in_class

        if t == "function_definition":
            name = node.child_by_field_name("name")
            if name is not None:
                symbols.append(_sym(_text(name), "method" if in_class else "function", node))
            child_in_class = False
        elif t == "class_definition":
            name = node.child_by_field_name("name")
            if name is not None:
                symbols.append(_sym(_text(name), "class", node))
            child_in_class = True
        elif t == "decorated_definition":
            definition = node.child_by_field_name("definition")
            for dec in node.children:
                if dec.type == "decorator" and definition is not None:
                    m = PY_ROUTE.search(_text(dec))
                    if m:
                        symbols.append(_sym(f"{m.group(1).upper()} {m.group(2)}", "route", definition))
        elif t == "import_statement":
            for n in node.children_by_field_name("name"):
                if n.type == "aliased_import":
                    n = n.child_by_field_name("name")
                imports.append(ImportRef(module=_text(n)))
            continue
        elif t == "import_from_statement":
            mod = node.child_by_field_name("module_name")
            raw = _text(mod) if mod is not None else ""
            names = []
            for n in node.children_by_field_name("name"):
                if n.type == "aliased_import":
                    n = n.child_by_field_name("name")
                names.append(_text(n))
            imports.append(ImportRef(
                module=raw.lstrip("."), level=len(raw) - len(raw.lstrip(".")), names=names,
            ))
            continue

        for child in reversed(node.children):
            stack.append((child, child_in_class))

    return ParseResult(symbols, imports)


def _string_value(node) -> str:
    return _text(node).strip("\"'`")


def parse_js(parser: Parser, source: str) -> ParseResult:
    tree = parser.parse(source.encode("utf-8"))
    symbols: list[SymbolInfo] = []
    imports: list[ImportRef] = []
    stack = [tree.root_node]

    while stack:
        node = stack.pop()
        t = node.type

        if t in ("function_declaration", "generator_function_declaration"):
            name = node.child_by_field_name("name")
            if name is not None:
                symbols.append(_sym(_text(name), "function", node))
        elif t in ("class_declaration", "abstract_class_declaration"):
            name = node.child_by_field_name("name")
            if name is not None:
                symbols.append(_sym(_text(name), "class", node))
        elif t == "interface_declaration":
            name = node.child_by_field_name("name")
            if name is not None:
                symbols.append(_sym(_text(name), "interface", node))
        elif t == "method_definition":
            name = node.child_by_field_name("name")
            if name is not None:
                symbols.append(_sym(_text(name), "method", node))
        elif t == "variable_declarator":
            # const Foo = () => {...}, only at module level to avoid noise
            name = node.child_by_field_name("name")
            value = node.child_by_field_name("value")
            gp = node.parent.parent if node.parent is not None else None
            if (
                name is not None and value is not None and gp is not None
                and value.type in ("arrow_function", "function_expression", "function")
                and gp.type in ("program", "export_statement")
            ):
                symbols.append(_sym(_text(name), "function", node))
        elif t in ("import_statement", "export_statement"):
            src = node.child_by_field_name("source")
            if src is not None:
                imports.append(ImportRef(module=_string_value(src)))
        elif t == "call_expression":
            fn = node.child_by_field_name("function")
            args = node.child_by_field_name("arguments")
            first = args.named_children[0] if args is not None and args.named_children else None
            if fn is not None and first is not None:
                if fn.type in ("identifier", "import") and _text(fn) in ("require", "import") \
                        and first.type == "string":
                    imports.append(ImportRef(module=_string_value(first)))
                elif fn.type == "member_expression" and first.type in ("string", "template_string"):
                    obj = fn.child_by_field_name("object")
                    prop = fn.child_by_field_name("property")
                    if (
                        obj is not None and prop is not None
                        and _text(prop) in HTTP_METHODS
                        and JS_ROUTER_NAME.fullmatch(_text(obj))
                    ):
                        symbols.append(_sym(f"{_text(prop).upper()} {_string_value(first)}", "route", node))

        stack.extend(reversed(node.children))

    return ParseResult(symbols, imports)


def parse_file(parsers: dict[str, Parser], path: str, language: str | None,
               source: str) -> ParseResult | None:
    if language == "python":
        return parse_python(parsers["python"], source)
    if language == "typescript":
        return parse_js(parsers["tsx" if path.endswith(".tsx") else "typescript"], source)
    if language == "javascript":
        return parse_js(parsers["javascript"], source)
    return None