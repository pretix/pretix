from tests.base import SoupTest, extract_form_fields

from pretix.base.models import User


class UserSettingsTest(SoupTest):
    def setUp(self):
        super().setUp()
        self.user = User.objects.create_user('dummy@dummy.dummy', 'dummy')
        self.client.login(email='dummy@dummy.dummy', password='dummy')
        doc = self.get_doc('/control/settings')
        self.form_data = extract_form_fields(doc.select('.container-fluid form')[0])

    def save(self, data):
        form_data = self.form_data.copy()
        form_data.update(data)
        print(form_data)
        return self.post_doc('/control/settings', form_data)

    def test_set_name(self):
        doc = self.save({
            'givenname': 'Peter',
            'familyname': 'Miller'
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.givenname == 'Peter'
        assert self.user.familyname == 'Miller'

    def test_change_email_require_password(self):
        doc = self.save({
            'email': 'foo@example.com',
        })
        assert doc.select(".alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_email_success(self):
        doc = self.save({
            'email': 'foo@example.com',
            'old_pw': 'dummy'
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'foo@example.com'

    def test_change_email_no_duplicates(self):
        User.objects.create_user('foo@example.com', 'foo')
        doc = self.save({
            'email': 'foo@example.com',
            'old_pw': 'dummy'
        })
        assert doc.select(".alert-danger")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.email == 'dummy@dummy.dummy'

    def test_change_password_require_password(self):
        doc = self.save({
            'new_pw': 'foo',
            'new_pw_repeat': 'foo',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_success(self):
        doc = self.save({
            'new_pw': 'foobarbar',
            'new_pw_repeat': 'foobarbar',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-success")
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.check_password("foobarbar")

    def test_change_password_short(self):
        doc = self.save({
            'new_pw': 'foo',
            'new_pw_repeat': 'foo',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_user_attribute_similarity(self):
        doc = self.save({
            'new_pw': 'dummy123',
            'new_pw_repeat': 'dummy123',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw

    def test_change_password_require_repeat(self):
        doc = self.save({
            'new_pw': 'foooooooooooooo',
            'new_pw_repeat': 'baaaaaaaaaaaar',
            'old_pw': 'dummy',
        })
        assert doc.select(".alert-danger")
        pw = self.user.password
        self.user = User.objects.get(pk=self.user.pk)
        assert self.user.password == pw
