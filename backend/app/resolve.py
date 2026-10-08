import posixpath

from .parsing import ImportRef

JS_EXTS = (".ts", ".tsx", ".js", ".jsx")


class Resolver:
    def __init__(self, paths: dict[str, int]):
        self.paths = paths
        # "backend/app/db.py" is reachable as backend.app.db, app.db and db
        self.py_modules: dict[str, set[str]] = {}
        for path in paths:
            if not path.endswith(".py"):
                continue
            parts = path[:-3].split("/")
            if parts[-1] == "__init__":
                parts = parts[:-1]
            for i in range(len(parts)):
                self.py_modules.setdefault(".".join(parts[i:]), set()).add(path)

    def resolve(self, importer: str, language: str | None, ref: ImportRef) -> list[str]:
        if language == "python":
            return self._python(importer, ref)
        return self._js(importer, ref.module)

    # ---------- python ----------
    def _module_at(self, base: str) -> list[str]:
        return [p for p in (f"{base}.py", f"{base}/__init__.py") if p in self.paths]

    def _lookup(self, key: str, importer: str) -> list[str]:
        cands = self.py_modules.get(key)
        if not cands:
            return []
        if "." not in key:
            # a bare name like "json" or "github" is usually third-party/stdlib,
            # so only accept a file at the repo root
            cands = {c for c in cands if "/" not in c}
            if not cands:
                return []
        return [self._closest(cands, importer)]

    @staticmethod
    def _closest(cands: set[str], importer: str) -> str:
        imp_dir = importer.split("/")[:-1]

        def shared(path: str) -> int:
            n = 0
            for a, b in zip(imp_dir, path.split("/")[:-1]):
                if a != b:
                    break
                n += 1
            return n

        return max(sorted(cands), key=shared)

    def _python(self, importer: str, ref: ImportRef) -> list[str]:
        found: list[str] = []
        if ref.level > 0:
            base = posixpath.dirname(importer)
            for _ in range(ref.level - 1):
                base = posixpath.dirname(base)
            mod = posixpath.join(base, *ref.module.split(".")) if ref.module else base
            found += self._module_at(mod)
            for name in ref.names:                      # from . import auth
                found += self._module_at(posixpath.join(mod, name))
        else:
            found += self._lookup(ref.module, importer)
            for name in ref.names:                      # from app import db
                found += self._lookup(f"{ref.module}.{name}", importer)
        return found

    # ---------- javascript / typescript ----------
    def _js(self, importer: str, spec: str) -> list[str]:
        if not spec.startswith("."):
            return []  # packages (react, express...) are not part of the repo
        base = posixpath.normpath(posixpath.join(posixpath.dirname(importer), spec))
        cands = [base]
        cands += [base + e for e in JS_EXTS]
        cands += [f"{base}/index{e}" for e in JS_EXTS]
        root, ext = posixpath.splitext(base)
        if ext in (".js", ".jsx"):                      # ESM style "./x.js" -> x.ts
            cands += [root + ".ts", root + ".tsx"]
        for c in cands:
            if c in self.paths:
                return [c]
        return []