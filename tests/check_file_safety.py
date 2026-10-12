"""Exercise report-path preflight and generated-output discovery via the real CLI."""
import test_paths  # Resolve the repository for direct test execution.
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile

import simplify_ass as s

HERE = Path(__file__).resolve().parents[1]
SCRIPT = HERE / 'simplify_ass.py'
checks = 0
aliases_tested = []


def check(condition, detail=''):
    global checks
    assert condition, detail
    checks += 1


HEADER = '''[Script Info]
ScriptType: v4.00+
PlayResX: 640
PlayResY: 360
[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,24,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,1,0,2,10,10,10,1
[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
Dialogue: 0,0:00:01.00,0:00:03.00,Default,,0,0,0,,Hello
'''


def cli(*args, cwd=None, script=SCRIPT):
    return subprocess.run([sys.executable, str(script), *map(str, args),
                           '--no-font-spacing'], cwd=cwd,
                          capture_output=True, text=True)


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob('*') if p.is_file()}


def reject_unchanged(root, *args):
    before = snapshot(root)
    result = cli(*args)
    check(result.returncode == 2, result.stderr)
    check('--stats-json would overwrite a subtitle:' in result.stderr, result.stderr)
    check(snapshot(root) == before, 'Collision changed or created a file')
    check('->' not in result.stdout, 'Conversion began before preflight failed')


with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'source.ass'
    source.write_text(HEADER, encoding='utf-8')
    output = root / 'source.simple.ass'
    reject_unchanged(root, source, '--stats-json', source)
    reject_unchanged(root, source, '--stats-json', output)
    reject_unchanged(root, source, '--stats-json', root / '.' / 'source.ass')
    # Existing outputs, including generated files omitted from folder scans.
    output.write_text(s.GENERATED_MARKER + '\n' + HEADER, encoding='utf-8')
    reject_unchanged(root, root, '--stats-json', output)
    custom = root / 'source.custom.ass'
    reject_unchanged(root, source, '--suffix', '.custom', '--stats-json', custom)
    custom.write_text(s.GENERATED_MARKER + '\n' + HEADER, encoding='utf-8')
    reject_unchanged(root, root, '--suffix', '.custom', '--stats-json', custom)
    orphan = root / 'orphan.custom.ass'
    orphan.write_text(s.GENERATED_MARKER + '\n' + HEADER, encoding='utf-8')
    reject_unchanged(root, root, '--suffix', '.custom', '--stats-json', orphan)
    # A collision with the last input must prevent writes for the first one.
    second = root / 'z-last.ssa'
    second.write_text(HEADER, encoding='utf-8')
    reject_unchanged(root, source, second, '--stats-json', second)
    reject_unchanged(root, source, second, '--stats-json', root / 'z-last.simple.ssa')
    # Same-file aliases whose report names end in .json rather than .ass.
    for label, target, linker in (
            ('symlink-input', source, lambda a, b: a.symlink_to(b)),
            ('symlink-output', output, lambda a, b: a.symlink_to(b)),
            ('symlink-future-output', root / 'z-last.simple.ssa', lambda a, b: a.symlink_to(b)),
            ('hardlink-input', source, lambda a, b: os.link(b, a)),
            ('hardlink-output', output, lambda a, b: os.link(b, a))):
        alias = root / (label + '.json')
        try:
            linker(alias, target)
        except (OSError, NotImplementedError):
            continue
        aliases_tested.append(label)
        reject_unchanged(root, source, second, '--stats-json', alias)
    parent_alias = root / 'linked-parent'
    try:
        parent_alias.symlink_to(root, target_is_directory=True)
    except (OSError, NotImplementedError):
        pass
    else:
        aliases_tested.append('symlink-parent')
        reject_unchanged(root, source, '--stats-json', parent_alias / output.name)
        parent_alias.unlink()
    before = snapshot(root)
    result = cli('source.ass', '--stats-json', './source.ass', cwd=root)
    check(result.returncode == 2 and snapshot(root) == before, result.stderr)
    if os.name == 'nt':
        result = cli(source, '--stats-json', str(source).swapcase())
        check(result.returncode == 2 and snapshot(root) == before, result.stderr)

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    # No marker line-number limit; BOM and explicit legacy encodings agree
    # with input decoding. Long comments include non-ASCII characters.
    for encoding in ('utf-8', 'utf-8-sig', 'utf-16', 'utf-32',
                     'utf-16-le', 'utf-32-be', 'cp1252'):
        folder = root / encoding
        folder.mkdir()
        marked = ('; café preamble\n' * 1000 + HEADER.replace(
            '[Script Info]\n', '[Script Info]\n' + '; info\n' * 1000 +
            s.GENERATED_MARKER + '\n', 1))
        generated = folder / 'source.custom.ass'
        generated.write_bytes(marked.encode(encoding))
        override = encoding if encoding in {'utf-16-le', 'utf-32-be', 'cp1252'} else None
        check(s.has_generated_marker(generated, override), encoding)
        check(s.iter_inputs([str(folder)], False, '.custom', encoding=override) == [], encoding)
        check(s.iter_inputs([str(generated)], False, '.custom', encoding=override) == [generated])
    for preamble in ('; x\n' * 45, '; x\n' * 10000, '; ' + 'x' * (2 * 1024 * 1024) + '\n'):
        p = root / 'long.custom.ass'
        p.write_text(preamble + HEADER.replace('[Script Info]\n',
                     '[sCrIpT iNfO]\n \t' + s.GENERATED_MARKER + ' \t\n', 1))
        check(s.has_generated_marker(p))
    # Outputs are always UTF-8, even when the originals need an override.
    utf8_output = root / 'utf8-output.custom.ass'
    utf8_output.write_text(HEADER.replace('[Script Info]\n',
                          '[Script Info]\n' + s.GENERATED_MARKER + '\n'), encoding='utf-8')
    for override in ('utf-16', 'utf-16-le', 'utf-32-be', 'cp1252'):
        check(s.has_generated_marker(utf8_output, override), override)
    unmarked = root / 'unmarked.custom.ass'
    unmarked.write_text(HEADER + s.GENERATED_MARKER + '\n')
    check(not s.has_generated_marker(unmarked), 'Event-section marker was treated as header')
    unmarked.write_text(HEADER.replace('Hello', s.GENERATED_MARKER))
    check(not s.has_generated_marker(unmarked), 'Dialogue text was treated as marker')
    unmarked.write_text(HEADER.replace('ScriptType:', '; Simplified by somebody else\nScriptType:'))
    check(not s.has_generated_marker(unmarked))
    check(unmarked in s.iter_inputs([str(root)], False, '.custom'))
    old_default = root / 'old.simple.ass'
    old_default.write_text(HEADER)
    check(old_default not in s.iter_inputs([str(root)], False))
    check(old_default in s.iter_inputs([str(root)], False, '.custom'))
    malformed = root / 'malformed.ass'
    malformed.write_bytes(b'\xff\xfe[not valid UTF-16')
    check(malformed in s.iter_inputs([str(root)], False, '.custom'))

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    nested = root / 'nested'
    nested.mkdir()
    source = nested / 'source.ass'
    source.write_text('; preamble\n' * 45 + HEADER)
    before_source = source.read_bytes()
    report = root / 'reports' / 'statistics.json'
    result = cli(root, '-r', '--suffix', '.custom', '--stats-json', report)
    check(result.returncode == 0, result.stderr)
    entry = json.loads(report.read_text())['tracks'][0]
    output = nested / 'source.custom.ass'
    check(entry['input'] == str(source.resolve()) and entry['output'] == str(output.resolve()))
    check(entry['stats']['output'] == 1)
    check(output.read_text().splitlines().index(s.GENERATED_MARKER) > 40)
    check(source.read_bytes() == before_source)
    before_output = output.read_bytes()
    # Repeat a recursive folder conversion; only the original is processed.
    for _ in range(2):
        report.write_text('previous JSON report')
        result = cli(root, '-r', '--suffix', '.custom', '--stats-json', report)
        check(result.returncode == 0, result.stderr)
        check(len(json.loads(report.read_text())['tracks']) == 1)
        check(not (nested / 'source.custom.custom.ass').exists())
        check(output.read_bytes() == before_output and source.read_bytes() == before_source)
    result = cli(output, '--suffix', '.again', '--stats-json', report)
    check(result.returncode == 0 and (nested / 'source.custom.again.ass').is_file(), result.stderr)
    # A custom-looking unmarked source remains eligible during folder scans.
    check(s.iter_inputs([str(nested)], False, '.custom') == [source])

with tempfile.TemporaryDirectory() as temp:
    root = Path(temp)
    source = root / 'legacy.ass'
    source.write_bytes(('; preamble\n' * 45 + HEADER).encode('utf-16-le'))
    report = root / 'stats.json'
    for _ in range(2):
        result = cli(root, '--encoding', 'utf-16-le', '--suffix', '.custom', '--stats-json', report)
        check(result.returncode == 0, result.stderr)
        check(len(json.loads(report.read_text())['tracks']) == 1)
        check(not (root / 'legacy.custom.custom.ass').exists())

print(checks, 'file-safety checks passed; aliases:', ', '.join(aliases_tested))
validation = HERE / 'validation'
validation.mkdir(exist_ok=True)
(validation / 'file-safety-checks.json').write_text(json.dumps({
    'version': s.__version__, 'checks': checks, 'platform': sys.platform,
    'aliases_tested': aliases_tested}, indent=2) + '\n')
