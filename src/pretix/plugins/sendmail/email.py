from pretix.base.email import MailTemplateRenderer

mail_text_sendmail = MailTemplateRenderer(
    ['expire_date', 'event', 'code', 'date', 'url', 'invoice_name', 'invoice_company']
)

