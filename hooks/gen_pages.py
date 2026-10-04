"""Pulls the two track READMEs into the site so they stay the single source of truth.

Relative links in those READMEs point at repo files that are not part of the site, so each link is
rewritten: docs pages stay on the site, everything else points at the file on GitHub.
"""
import os
import posixpath
import re

import mkdocs_gen_files

REPO = "https://github.com/akashtalole/SNOWCOCO"
PAGES = {
    "tracks/risk_fraud_copilot/README.md": "prototype.md",
    "tracks/risk_fraud_copilot/coco/README.md": "snowflake-build.md",
}
LINK = re.compile(r"(?<!\!)\]\(([^)\s]+)((?:\s+\"[^\"]*\")?)\)")


def rewrite(source: str):
    base = posixpath.dirname(source)

    def fix(match):
        target, title = match.group(1), match.group(2)
        if re.match(r"^(https?:|mailto:|#)", target):
            return match.group(0)
        path, _, frag = target.partition("#")
        resolved = posixpath.normpath(posixpath.join(base, path))
        frag = f"#{frag}" if frag else ""
        if resolved in PAGES:
            return f"]({PAGES[resolved]}{frag}{title})"
        if resolved.startswith("docs/") and resolved.endswith(".md"):
            return f"]({resolved[len('docs/'):]}{frag}{title})"
        kind = "tree" if os.path.isdir(resolved) else "blob"
        return f"]({REPO}/{kind}/main/{resolved}{frag}{title})"

    return fix


for source, page in PAGES.items():
    with open(source, encoding="utf-8") as f:
        text = LINK.sub(rewrite(source), f.read())
    with mkdocs_gen_files.open(page, "w") as out:
        out.write(text)
    mkdocs_gen_files.set_edit_path(page, source)
