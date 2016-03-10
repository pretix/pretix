from smtplib import SMTPRecipientsRefused, SMTPSenderRefused

from django.core.mail.backends.smtp import EmailBackend


class CustomSMTPBackend(EmailBackend):

    def test(self, from_addr):
        try:
            self.open()
            self.connection.ehlo_or_helo_if_needed()
            self.connection.rcpt("test@example.org")
            (code, resp) = self.connection.mail(from_addr, [])
            if code != 250:
                raise SMTPSenderRefused(code, resp, from_addr)
            senderrs = {}
            (code, resp) = self.connection.rcpt('')
            if (code != 250) and (code != 251):
                raise SMTPRecipientsRefused(senderrs)
        finally:
            self.close()
