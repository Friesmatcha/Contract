from dataclasses import dataclass
from email.message import EmailMessage
from smtplib import SMTP

from backend.app.config import Settings


class MailerUnavailableError(RuntimeError):
    pass


class Mailer:
    def send_password_reset(self, *, recipient: str, reset_url: str) -> None:
        raise NotImplementedError

    def send_invitation(self, *, recipient: str, invitation_url: str) -> None:
        raise NotImplementedError


@dataclass(frozen=True, slots=True)
class SmtpMailer(Mailer):
    host: str
    port: int
    sender: str

    def _send(self, *, recipient: str, subject: str, body: str) -> None:
        message = EmailMessage()
        message["From"] = self.sender
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)
        with SMTP(self.host, self.port, timeout=10) as connection:
            connection.send_message(message)

    def send_password_reset(self, *, recipient: str, reset_url: str) -> None:
        self._send(recipient=recipient, subject="重置合同审核系统密码", body=reset_url)

    def send_invitation(self, *, recipient: str, invitation_url: str) -> None:
        self._send(recipient=recipient, subject="合同审核系统邀请", body=invitation_url)


class UnavailableMailer(Mailer):
    def _raise(self) -> None:
        raise MailerUnavailableError("SMTP is not configured")

    def send_password_reset(self, *, recipient: str, reset_url: str) -> None:
        self._raise()

    def send_invitation(self, *, recipient: str, invitation_url: str) -> None:
        self._raise()


def create_mailer(settings: Settings) -> Mailer:
    if settings.smtp_host and settings.smtp_from:
        return SmtpMailer(settings.smtp_host, settings.smtp_port, settings.smtp_from)
    return UnavailableMailer()
