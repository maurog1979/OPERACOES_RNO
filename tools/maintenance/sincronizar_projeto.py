"""Diagnóstico, backup e restauração explícita do banco configurado no portal."""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from config import Config


def mysql_args(executable):
    return [executable, '--host=' + Config.DB_HOST, '--port=' + str(Config.DB_PORT),
            '--user=' + Config.DB_USER, '--default-character-set=utf8mb4', Config.DB_NAME]


def mysql_env():
    env = os.environ.copy()
    env['MYSQL_PWD'] = Config.DB_PASSWORD
    return env


def fazer_backup(directory, executable):
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d_%H%M%S_%f')
    target = directory / f'safra_backup_{stamp}.sql'
    temporary = target.with_suffix('.sql.tmp')
    try:
        args = mysql_args(executable)
        args[1:1] = ['--single-transaction', '--quick', '--hex-blob']
        with temporary.open('wb') as output:
            subprocess.run(args, stdout=output, stderr=subprocess.PIPE,
                           env=mysql_env(), check=True)
        if not temporary.stat().st_size:
            raise RuntimeError('O backup retornou um arquivo vazio.')
        temporary.replace(target)
        latest = directory / 'ultimo_backup.sql.tmp'
        shutil.copy2(target, latest)
        latest.replace(directory / 'ultimo_backup.sql')
        print(f'Backup concluído: {target}')
        return target
    finally:
        temporary.unlink(missing_ok=True)


def restaurar_backup(source, executable, confirmed=False):
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError('Informe um backup SQL existente e não vazio.')
    if not confirmed:
        answer = input(f'Substituir dados de {Config.DB_NAME} em {Config.DB_HOST}? Digite RESTAURAR: ')
        if answer != 'RESTAURAR':
            print('Restauração cancelada.')
            return False
    with source.open('rb') as content:
        subprocess.run(mysql_args(executable), stdin=content, stdout=subprocess.PIPE,
                       stderr=subprocess.PIPE, env=mysql_env(), check=True)
    print('Restauração concluída.')
    return True


def diagnostico():
    import pymysql
    connection = pymysql.connect(**Config.db_config_pymysql())
    try:
        with connection.cursor() as cursor:
            cursor.execute('SHOW TABLES')
            tables = [row[0] for row in cursor.fetchall()]
        print(json.dumps({'host': Config.DB_HOST, 'banco': Config.DB_NAME,
                          'tabelas': tables}, ensure_ascii=False, indent=2))
    finally:
        connection.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument('--backup', action='store_true')
    actions.add_argument('--restore', action='store_true')
    actions.add_argument('--status', action='store_true')
    actions.add_argument('--diagnostico', action='store_true')
    parser.add_argument('--backup-dir', type=Path, default=ROOT / 'database/dumps')
    parser.add_argument('--file', type=Path, help='Arquivo a restaurar; padrão: ultimo_backup.sql')
    parser.add_argument('--mysql', default=os.getenv('MYSQL_BIN', 'mysql'))
    parser.add_argument('--mysqldump', default=os.getenv('MYSQLDUMP_BIN', 'mysqldump'))
    parser.add_argument('--yes', action='store_true', help='Confirma a restauração solicitada por --restore')
    args = parser.parse_args()
    if args.yes and not args.restore:
        parser.error('--yes exige --restore')
    try:
        if args.backup:
            fazer_backup(args.backup_dir, args.mysqldump)
        elif args.restore:
            restaurar_backup(args.file or args.backup_dir / 'ultimo_backup.sql', args.mysql, args.yes)
        elif args.status or args.diagnostico:
            diagnostico()
        else:
            parser.print_help()
        return 0
    except Exception as exc:
        print(f'Operação não concluída: {type(exc).__name__}. Verifique conexão, permissões e executáveis.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
