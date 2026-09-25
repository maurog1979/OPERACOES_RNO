import importlib.util
from pathlib import Path
from unittest.mock import MagicMock

import pytest

path=Path(__file__).resolve().parents[1]/'tools/maintenance/sincronizar_projeto.py'
spec=importlib.util.spec_from_file_location('maintenance',path)
maintenance=importlib.util.module_from_spec(spec)
spec.loader.exec_module(maintenance)


def test_restore_requires_confirmation(tmp_path,monkeypatch):
    source=tmp_path/'backup.sql'
    source.write_text('SELECT 1;')
    run=MagicMock()
    monkeypatch.setattr(maintenance.subprocess,'run',run)
    monkeypatch.setattr('builtins.input',lambda prompt:'N')
    assert maintenance.restaurar_backup(source,'mysql') is False
    run.assert_not_called()


def test_failed_backup_preserves_latest(tmp_path,monkeypatch):
    latest=tmp_path/'ultimo_backup.sql'
    latest.write_text('original')
    monkeypatch.setattr(maintenance.subprocess,'run',MagicMock(side_effect=RuntimeError('failed')))
    with pytest.raises(RuntimeError): maintenance.fazer_backup(tmp_path,'mysqldump')
    assert latest.read_text()=='original'
    assert not list(tmp_path.glob('*.tmp'))


def test_backup_binary_no_shell(tmp_path,monkeypatch):
    def run(args,**kwargs):
        assert isinstance(args,list)
        assert not kwargs.get('shell')
        assert not any('--password' in arg for arg in args)
        kwargs['stdout'].write(b'SELECT 1;\n')
    monkeypatch.setattr(maintenance.subprocess,'run',run)
    target=maintenance.fazer_backup(tmp_path,'mysqldump')
    assert target.read_bytes()==b'SELECT 1;\n'
    assert (tmp_path/'ultimo_backup.sql').read_bytes()==target.read_bytes()
