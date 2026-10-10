#!/usr/bin/env python3
"""Startpunkt: CLI-Abfragen brauchen keine GUI-Bibliotheken."""
import argparse
from modules.model import PROJECT, VERSION


def main():
    parser = argparse.ArgumentParser(description=PROJECT['name'])
    parser.add_argument('--version', action='version', version=f"{PROJECT['name']} {VERSION}")
    parser.add_argument('--author', action='store_true', help='Mitwirkende anzeigen')
    parser.add_argument('--diagnose-admin', action='store_true', help='Einmalige erweiterte Abfrage mit anonymisierter Diagnose')
    args = parser.parse_args()
    if args.diagnose_admin:
        import json
        from modules.admin_probe import query_admin_sources, _safe_stderr
        result=query_admin_sources()
        print(json.dumps(dict(diagnostic=result['diagnostic'],sources={key:dict(status=value['status'],returncode=value.get('returncode'),captured_at=value['captured_at'],stderr=_safe_stderr(value.get('stderr',''))) for key,value in result['sources'].items()}),ensure_ascii=False,indent=2))
        return 0 if result['status']=='ok' else 1
    if args.author:
        print(', '.join(PROJECT['authors']) or 'Nicht hinterlegt / Not specified')
        return 0
    from modules.monitor_gui import Application
    return Application().run([])


if __name__ == '__main__':
    raise SystemExit(main())
