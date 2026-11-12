"""Offline database operations and consistent online SQLite backups."""
import argparse
import datetime
import hashlib
import os
import secrets
import sqlite3
from pathlib import Path
from contextlib import contextmanager
import server


@contextmanager
def source_connection(database):
    path = Path(database).resolve()
    if not path.is_file():
        raise ValueError('数据库不存在：' + str(path))
    connection = sqlite3.connect(path.as_uri() + '?mode=ro', uri=True, timeout=15)
    try:
        yield connection
    finally:
        connection.close()


def backup_database(database, output):
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation prevents accidentally overwriting a previous backup.
    descriptor = os.open(output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    os.close(descriptor)
    try:
        with source_connection(database) as source:
            target = sqlite3.connect(output)
            try:
                source.backup(target)
                if target.execute('PRAGMA quick_check').fetchone()[0] != 'ok':
                    raise ValueError('备份校验失败')
            finally:
                target.close()
    except Exception:
        output.unlink(missing_ok=True)
        raise
    os.chmod(output, 0o600)
    return output


def backup_path(prefix='cleaner'):
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    return Path(os.environ.get('BACKUP_DIR', str(Path(server.DB).parent / 'backups'))) / (prefix + '-' + stamp + '-' + secrets.token_hex(3) + '.sqlite3')


def reset_admin(password_file):
    password = Path(password_file).read_text(encoding='utf-8').rstrip('\r\n')
    if not 6 <= len(password) <= 256:
        raise ValueError('管理员密码需要6至256位')
    if not Path(server.DB).is_file():
        raise ValueError('请先初始化数据库')
    salt = secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac('sha256', password.encode(), salt.encode(), 600000).hex()
    with server.connect() as connection:
        user = connection.execute('SELECT id,admin FROM users WHERE username=?', ('admin',)).fetchone()
        if not user or not user['admin']:
            raise ValueError('未找到admin管理员，未修改数据库')
        connection.execute('UPDATE users SET salt=?,password=? WHERE id=?', (salt, digest, user['id']))
        connection.execute('DELETE FROM sessions WHERE user=?', (user['id'],))


def restore_database(backup, confirmed, preserve_sessions=False):
    if not confirmed:
        raise ValueError('请先停止backend服务，再传入--confirm-stopped')
    if Path(backup).resolve() == Path(server.DB).resolve():
        raise ValueError('备份路径不能与当前数据库相同')
    with source_connection(backup) as source:
        if source.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('备份文件校验失败')
        for table in ['users', 'sessions', 'events']:
            source.execute('SELECT * FROM ' + table + ' LIMIT 1').fetchone()
        preserved = backup_database(server.DB, backup_path('before-restore')) if Path(server.DB).exists() else None
        target = sqlite3.connect(server.DB, timeout=15)
        try:
            source.backup(target)
            if not preserve_sessions:target.execute('DELETE FROM sessions')
            target.commit()
        finally:
            target.close()
    return preserved


def main():
    parser = argparse.ArgumentParser(description='净元 SQLite 运维工具')
    sub = parser.add_subparsers(dest='action', required=True)
    backup = sub.add_parser('backup')
    backup.add_argument('--output')
    reset = sub.add_parser('reset-admin')
    reset.add_argument('--password-file', default=os.environ.get('ADMIN_PASSWORD_FILE', '/run/secrets/admin_password'))
    restore = sub.add_parser('restore')
    restore.add_argument('--backup', required=True)
    restore.add_argument('--confirm-stopped', action='store_true')
    rollback = sub.add_parser('rollback-session-migration')
    rollback.add_argument('--backup', required=True)
    rollback.add_argument('--confirm-stopped', action='store_true')
    args = parser.parse_args()
    if args.action == 'backup':
        print('备份成功：' + str(backup_database(server.DB, args.output or backup_path())))
    elif args.action == 'reset-admin':
        reset_admin(args.password_file)
        print('管理员密码已更新，原管理员登录会话已失效')
    elif args.action == 'rollback-session-migration':
        if not Path(args.backup).name.startswith('before-1812-migration-'):raise ValueError('只能使用 v1.8.12 自动生成的迁移前备份')
        preserved = restore_database(args.backup, args.confirm_stopped, preserve_sessions=True)
        print('迁移前数据库已恢复，原有会话保留；恢复前副本：' + str(preserved or '原数据库不存在'))
    else:
        preserved = restore_database(args.backup, args.confirm_stopped)
        print('恢复完成；已清除旧登录会话。恢复前副本：' + str(preserved or '原数据库不存在'))


if __name__ == '__main__':
    main()
