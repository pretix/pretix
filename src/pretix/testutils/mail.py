import smtplib

from django.core.mail.backends.locmem import EmailBackend


class FailingEmailBackend(EmailBackend):
    def send_messages(self, email_messages):
        raise smtplib.SMTPRecipientsRefused({
            'recipient@example.org': (450, b'Recipient unknown')
        })
