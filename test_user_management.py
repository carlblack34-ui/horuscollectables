import unittest
import test_app as support
from db import Database,migrate
from werkzeug.security import check_password_hash,generate_password_hash

class UserManagementTests(unittest.TestCase):
    setUp=support.PortalTests.setUp
    tearDown=support.PortalTests.tearDown
    post=support.PortalTests.post
    scalar=support.PortalTests.scalar
    def admin(self):
        with Database(self.path) as d:d.execute("UPDATE users SET role='admin' WHERE username='owner'")
    def create(self,username='alex',role='staff'):
        return self.post('/admin/users',username=username,role=role,password='temporary-password',confirm_password='temporary-password')
    def other_client(self):
        c=self.app.test_client();c.get('/login')
        with c.session_transaction() as s:token=s['csrf']
        result=c.post('/login',data=dict(csrf=token,username='alex',password='temporary-password'))
        return c,result
    def action(self,action,username='alex',**data):return self.post('/admin/users/action',username=username,action=action,**data)

    def test_staff_cannot_manage_users_or_read_admin_audit(self):
        self.assertEqual(self.client.get('/admin/users').status_code,403)
        self.assertEqual(self.create().status_code,403)
        self.assertEqual(self.action('disable',username='owner').status_code,403)
        self.assertEqual(self.client.get('/export/audit').status_code,403)
        self.assertEqual(self.client.get('/stock').status_code,200)

    def test_admin_creates_user_hashes_password_never_echoes_it(self):
        self.admin();self.assertEqual(self.create().status_code,302)
        self.assertTrue(check_password_hash(self.scalar("SELECT password_hash FROM users WHERE username='alex'"),'temporary-password'))
        self.assertEqual(self.scalar("SELECT must_change_password FROM users WHERE username='alex'"),1)
        html=self.client.get('/admin/users').get_data(as_text=True)
        self.assertIn('alex',html);self.assertNotIn('temporary-password',html)
        self.assertNotIn('scrypt:',html)

    def test_invalid_duplicate_and_role_validation(self):
        self.admin();self.create()
        self.assertEqual(self.create().status_code,200)
        self.assertEqual(self.create('OWNER').status_code,200)
        self.assertEqual(self.create('newperson','superuser').status_code,200)
        self.assertEqual(self.create('<script>').status_code,200)
        self.assertEqual(self.scalar('SELECT COUNT(*) FROM users'),2)

    def test_temporary_password_must_change_before_inventory(self):
        self.admin();self.create();c,result=self.other_client()
        self.assertEqual(result.location,'/password')
        self.assertEqual(c.get('/stock').location,'/password')
        with c.session_transaction() as s:token=s['csrf']
        changed=c.post('/password',data=dict(csrf=token,current_password='temporary-password',new_password='private-user-password',confirm_password='private-user-password'))
        self.assertEqual(changed.location,'/')
        self.assertEqual(c.get('/stock').status_code,200)
        self.assertEqual(self.scalar("SELECT must_change_password FROM users WHERE username='alex'"),0)

    def test_reset_invalidates_existing_sessions_and_clears_lockout(self):
        self.admin();self.create();c,_=self.other_client()
        with Database(self.path) as d:d.execute("UPDATE users SET failures=7,locked_until=99999999999 WHERE username='alex'")
        self.assertEqual(self.action('reset',password='new-temp-password',confirm_password='new-temp-password').status_code,302)
        self.assertEqual(c.get('/stock').location,'/login')
        self.assertEqual(self.scalar("SELECT failures FROM users WHERE username='alex'"),0)
        self.assertEqual(self.scalar("SELECT locked_until FROM users WHERE username='alex'"),0)
        self.assertTrue(check_password_hash(self.scalar("SELECT password_hash FROM users WHERE username='alex'"),'new-temp-password'))

    def test_disabled_accounts_cannot_login_or_keep_sessions(self):
        self.admin();self.create();c,_=self.other_client()
        self.action('disable');self.assertEqual(c.get('/stock').location,'/login')
        c.get('/login')
        with c.session_transaction() as s:token=s['csrf']
        self.assertEqual(c.post('/login',data=dict(csrf=token,username='alex',password='temporary-password')).status_code,200)
        self.action('enable');self.assertEqual(self.scalar("SELECT disabled FROM users WHERE username='alex'"),0)

    def test_cannot_remove_last_admin_or_disable_self(self):
        self.admin();self.action('role',username='owner',role='staff');self.action('disable',username='owner')
        self.assertEqual(self.scalar("SELECT role FROM users WHERE username='owner'"),'admin')
        self.assertEqual(self.scalar("SELECT disabled FROM users WHERE username='owner'"),0)
        self.assertEqual(self.client.get('/admin/users').status_code,200)

    def test_role_change_revokes_session_and_records_audit(self):
        self.admin();self.create();c,_=self.other_client();self.action('role',role='admin')
        self.assertEqual(c.get('/password').location,'/login')
        self.assertEqual(self.scalar("SELECT role FROM users WHERE username='alex'"),'admin')
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM audit WHERE action='user role'"),1)
        self.assertEqual(self.client.get('/export/audit').status_code,200)

    def test_password_confirmation_and_admin_csrf_required(self):
        self.admin();self.create()
        self.assertEqual(self.client.post('/admin/users/action',data=dict(username='alex',action='disable')).status_code,400)
        self.action('reset',password='new-temp-password',confirm_password='different-password')
        self.assertTrue(check_password_hash(self.scalar("SELECT password_hash FROM users WHERE username='alex'"),'temporary-password'))

    def test_cli_promotes_known_account_and_revokes_old_session(self):
        result=self.app.test_cli_runner().invoke(args=['promote-admin','owner'])
        self.assertEqual(result.exit_code,0,result.output)
        self.assertEqual(self.scalar("SELECT role FROM users WHERE username='owner'"),'admin')
        self.assertEqual(self.client.get('/stock').location,'/login')
        result=self.app.test_cli_runner().invoke(args=['promote-admin','unknown'])
        self.assertNotEqual(result.exit_code,0)

    def test_self_password_change_revokes_other_sessions(self):
        second=self.app.test_client()
        with second.session_transaction() as s:s.update(user='owner',csrf='token')
        response=self.post('/password',current_password='long-test-password',new_password='new-private-password',confirm_password='new-private-password')
        self.assertEqual(response.status_code,302)
        self.assertEqual(self.client.get('/stock').status_code,200)
        self.assertEqual(second.get('/stock').location,'/login')

    def test_migration_preserves_existing_user_privileges_and_password(self):
        self.admin();before=self.scalar("SELECT password_hash FROM users WHERE username='owner'")
        migrate(self.path);migrate(self.path)
        self.assertEqual(self.scalar("SELECT password_hash FROM users WHERE username='owner'"),before)
        self.assertEqual(self.scalar("SELECT role FROM users WHERE username='owner'"),'admin')

    def test_cli_creates_admin_with_hidden_password_prompt(self):
        result=self.app.test_cli_runner().invoke(args=['create-user','newadmin','--admin'],input='new-admin-password\nnew-admin-password\n')
        self.assertEqual(result.exit_code,0,result.output)
        self.assertEqual(self.scalar("SELECT role FROM users WHERE username='newadmin'"),'admin')
        self.assertNotIn('new-admin-password',result.output)

if __name__=='__main__':unittest.main(verbosity=2)
