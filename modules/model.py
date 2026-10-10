"""Projektangaben und kontrolliert gespeicherte Entwicklungseinstellungen."""
import json
import os
import shutil
import tempfile
import time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parent.parent
PROJECT = json.loads((ROOT / 'projekt.json').read_text('utf-8'))
PROGRAM_ID = PROJECT['program_id']
VERSION = (ROOT / 'VERSION').read_text('utf-8').strip()
DEFAULTS = dict(config_version=2, language='de', update_check=False,
                update_interval_value=1, update_interval_unit='weeks',
                update_url=PROJECT['update_url'], source_url=PROJECT['source_url'],
                last_update_check='', active_profile='', window_width=760, window_height=480,
                window_x=0, window_y=0, window_position_known=False, window_maximized=False)
DEFAULTS.update({field['key']: field['default'] for field in PROJECT['settings']})


def config_dir():
    # start.sh ist der Entwicklungsstart. Ein installierter Starter setzt diese
    # Variable nicht und schreibt ausschließlich in den Benutzerbereich.
    if os.environ.get('PYTHON_TEMPLATE_DEV') == '1':
        return ROOT / '.config'
    target = Path(os.environ.get('XDG_CONFIG_HOME', str(Path.home() / '.config'))) / PROGRAM_ID
    if ROOT == Path('/usr/share/pcmonitor'):
        registry = Path.home() / '.local/state/pcmonitor-locations.json'
        try:
            locations = json.loads(registry.read_text()).get('locations', []) if registry.exists() else []
            if str(target) not in locations:
                atomic_json(registry, dict(program_id=PROGRAM_ID, locations=locations + [str(target)]))
        except (OSError, ValueError, TypeError):
            pass
    return target


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def validate_settings(data):
    result = DEFAULTS.copy()
    if isinstance(data, dict):
        for key, default in DEFAULTS.items():
            value = data.get(key, default)
            if type(value) is type(default):
                result[key] = value
    result['config_version'] = DEFAULTS['config_version']
    result['update_url']=PROJECT['update_url']
    result['source_url']=PROJECT['source_url']
    for key in ('window_width', 'window_height'):
        result[key] = max(240, min(10000, result[key]))
    for key in ('window_x', 'window_y'):
        result[key] = max(-100000, min(100000, result[key]))
    result['update_interval_value'] = max(1, min(365, result['update_interval_value']))
    if result['update_interval_unit'] not in ('days', 'weeks', 'months'):
        result['update_interval_unit'] = 'weeks'
    for field in PROJECT['settings']:
        if field['type'] == 'number':
            result[field['key']] = max(field['min'], min(field['max'], result[field['key']]))
    return result


def settings():
    path = config_dir() / 'settings.json'
    try:
        return validate_settings(json.loads(path.read_text('utf-8')))
    except (OSError, ValueError, UnicodeError):
        return DEFAULTS.copy()


def save_settings(data):
    path = config_dir() / 'settings.json'
    if path.exists():
        try:
            old = json.loads(path.read_text('utf-8'))
            if not isinstance(old, dict):
                raise ValueError('Invalid settings')
        except (ValueError, UnicodeError):
            shutil.copy2(path, path.with_name(f'settings.invalid.{time.time_ns()}.json'))
    atomic_json(path, validate_settings(data))


def now():
    return datetime.now(timezone.utc).isoformat(timespec='seconds')


def update_due(options):
    if not options['update_check'] or not options['update_url'].strip():
        return False
    try:
        last = datetime.fromisoformat(options['last_update_check'])
        elapsed = (datetime.now(timezone.utc) - last).total_seconds()
    except (ValueError, TypeError):
        return True
    days = options['update_interval_value'] * {'days': 1, 'weeks': 7, 'months': 30}[options['update_interval_unit']]
    return elapsed >= days * 86400
