#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""通用 HTML 报告渲染器 — data → HTML file"""

import os
import json
from datetime import datetime
from jinja2 import Environment, FileSystemLoader, select_autoescape, Undefined

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")
DEFAULT_OUTPUT_DIR = os.path.join(BASE_DIR, "cache")


def render(data: dict, template_name: str, output_dir: str = None, filename: str = None) -> str:
    """
    Render analysis data to an HTML report file.

    Args:
        data:          Analysis result dict (from plans/ modules)
        template_name: Template name without .html extension
                       e.g. "stock_report", "concept_report", "global_macro"
        output_dir:    Output directory (default: cache/)
        filename:      Custom filename (default: auto-generated)

    Returns:
        Absolute path to the generated HTML file.
    """
    output_dir = output_dir or DEFAULT_OUTPUT_DIR
    os.makedirs(output_dir, exist_ok=True)

    env = Environment(
        loader=FileSystemLoader(TEMPLATES_DIR),
        autoescape=select_autoescape(["html"]),
        trim_blocks=True,
        lstrip_blocks=True,
    )

    # Register custom filters
    env.filters["default"] = lambda v, d="": d if v is None or isinstance(v, Undefined) else v

    template = env.get_template(f"{template_name}.html")
    now = datetime.now()

    # Generate filename if not provided
    if not filename:
        symbol = data.get("symbol", "unknown")
        ts = now.strftime("%Y%m%d_%H%M")
        filename = f"{template_name}_{symbol}_{ts}.html"

    filepath = os.path.join(output_dir, filename)
    html = template.render(data=data, now=now)

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(html)

    return os.path.abspath(filepath)


def render_from_json(json_path: str, template_name: str, **kwargs) -> str:
    """Render from a JSON file instead of a dict."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return render(data, template_name, **kwargs)


if __name__ == "__main__":
    # Quick test: render from stdin or file
    import sys
    if len(sys.argv) < 2:
        print("Usage: python html_renderer.py <template_name> [json_file]")
        sys.exit(1)

    tpl = sys.argv[1]
    if len(sys.argv) > 2:
        path = render_from_json(sys.argv[2], tpl)
    else:
        data = json.load(sys.stdin)
        path = render(data, tpl)

    print(path)
