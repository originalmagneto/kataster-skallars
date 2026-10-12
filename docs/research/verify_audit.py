"""Focused offline checks of reviewed upstream functions; no dependencies or live data."""
import ast
import importlib.util
import json
from pathlib import Path
import re
import sys
import tempfile

sys.dont_write_bytecode = True
repo = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[2]

def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, repo / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

parser = load('audit_lv_parser', 'src/kataster_mcp/parsers/lv.py')
title = '<p>VÝPIS Z LISTU VLASTNÍCTVA č. 999999</p>'
results = {}
for name, body in {
    'missing_C': '',
    'empty_C': '<p>ČASŤ C: ŤARCHY</p>',
    'explicit_no_encumbrances': '<p>ČASŤ C: ŤARCHY</p><p>Bez tiarch.</p>',
}.items():
    result = parser.parse_lv(title + body)
    results[name] = {'tarchy': result['tarchy'], 'cast_c': result['cast_c']}
assert results['missing_C']['tarchy'] == results['empty_C']['tarchy'] == 'none'

# Execute only the reviewed pure fits() function; avoid importing its application dependencies.
tree = ast.parse((repo / 'src/kataster_mcp/osoba.py').read_text())
function = next(n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == 'fits')
namespace = {'re': re}
exec(compile(ast.Module(body=[function], type_ignores=[]), 'upstream:osoba.fits', 'exec'), namespace)
results['invalid_ico_matches_owner_without_ico'] = namespace['fits']({'ico': None}, [], 'abc')
results['valid_ico_does_not_match_owner_without_ico'] = namespace['fits']({'ico': None}, [], '12345678')
assert results['invalid_ico_matches_owner_without_ico'] is True
assert results['valid_ico_does_not_match_owner_without_ico'] is False

cache_module = load('audit_cache', 'src/kataster_mcp/cache.py')
with tempfile.TemporaryDirectory(prefix='kataster-audit-') as directory:
    cache = cache_module.Cache(Path(directory) / 'synthetic.sqlite', private=True)
    cache.put('lv_import', 'synthetic-v1', '999999|999999', {'data_date': '2026-10-12'})
    cache.put('lv_import', 'synthetic-v1', '999999|999999', {'data_date': '2025-01-01'})
    results['cache_latest_write_wins'] = cache.get('lv_import', 'synthetic-v1', '999999|999999', None)[0]
    assert results['cache_latest_write_wins']['data_date'] == '2025-01-01'
    cache.db.close()

tools = []
for path in sorted((repo / 'src').rglob('*.py')):
    module = ast.parse(path.read_text())
    for node in ast.walk(module):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                   and d.func.attr == 'tool' for d in node.decorator_list):
                tools.append(node.name)
assert len(tools) == 11
results['registered_tools'] = sorted(tools)
results['scope'] = 'Focused synthetic offline reproduction, not a full pytest suite or a live LV validation.'
Path(__file__).with_name('audit-evidence.json').write_text(json.dumps(results, ensure_ascii=False, indent=2) + '\n')
print(json.dumps(results, ensure_ascii=False, indent=2))
