import re
from werkzeug.security import generate_password_hash

def password_valid(password):
    if not 12<=len(password)<=256:
        raise ValueError('Passwords must contain 12–256 characters.')

def lock_accounts(d):
    if d.pg:d.execute('SELECT pg_advisory_xact_lock(7241016)')

def require_admin(d,username,version):
    lock_accounts(d)
    row=d.execute('SELECT * FROM users WHERE username=?'+(' FOR UPDATE' if d.pg else ''),(username,)).fetchone()
    if not row or row['disabled'] or row['role']!='admin' or row['auth_version']!=version:
        raise PermissionError('Administrator access required.')

def create_user(d,username,password,role='staff',temporary=True):
    username=username.strip().lower()
    if not re.fullmatch(r'[a-z0-9_.-]{3,64}',username):
        raise ValueError('Use 3–64 letters, numbers, dots, underscores or hyphens for the username.')
    if role not in ['admin','staff']:raise ValueError('Choose Admin or Staff.')
    password_valid(password)
    if d.execute('SELECT username FROM users WHERE LOWER(username)=?',(username,)).fetchone():
        raise ValueError('That username is already in use.')
    from datetime import datetime,timezone
    d.execute('INSERT INTO users(username,password_hash,role,must_change_password,created_at) VALUES (?,?,?,?,?)',
      (username,generate_password_hash(password),role,int(temporary),datetime.now(timezone.utc).isoformat(timespec='seconds')))
    return username

def change_user(d,actor,username,action,role=None,password=None):
    target=d.execute('SELECT * FROM users WHERE username=?',(username,)).fetchone()
    if not target:raise ValueError('User not found.')
    if action=='reset':
        if actor==username:raise ValueError('Use Account settings to change your own password.')
        password_valid(password or '')
        d.execute('UPDATE users SET password_hash=?,auth_version=auth_version+1,must_change_password=1,failures=0,locked_until=0 WHERE username=?',(generate_password_hash(password),username))
    elif action in ['role','disable','enable']:
        if action=='role' and role not in ['admin','staff']:raise ValueError('Choose Admin or Staff.')
        if action=='disable' and actor==username:raise ValueError('You cannot disable your own account.')
        if action=='role' and target['role']==role:return
        if action in ['disable','enable'] and target['disabled']==int(action=='disable'):return
        removes_admin=not target['disabled'] and target['role']=='admin' and (action=='disable' or action=='role' and role!='admin')
        if removes_admin and d.execute("SELECT COUNT(*) AS n FROM users WHERE role='admin' AND disabled=0").fetchone()['n']<=1:
            raise ValueError('Keep at least one enabled administrator.')
        if action=='role':d.execute('UPDATE users SET role=?,auth_version=auth_version+1 WHERE username=?',(role,username))
        else:d.execute('UPDATE users SET disabled=?,auth_version=auth_version+1 WHERE username=?',(int(action=='disable'),username))
    elif action=='unlock':
        d.execute('UPDATE users SET failures=0,locked_until=0 WHERE username=?',(username,))
    else:raise ValueError('Choose a valid user action.')
