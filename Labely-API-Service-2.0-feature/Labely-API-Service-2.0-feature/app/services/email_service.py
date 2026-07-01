import logging
import smtplib
import ssl
import time
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Any, Dict

from app.core.config import settings
from app.services.template_service import template_service

logger = logging.getLogger(__name__)

class EmailService:
    """Email service for sending emails."""

    def __init__(self):
        self.smtp_server = settings.SMTP_SERVER
        self.smtp_port = settings.SMTP_PORT
        self.smtp_username = settings.SMTP_USERNAME
        self.smtp_password = settings.SMTP_PASSWORD
        self.from_email = settings.FROM_EMAIL

    def send_password_reset_email(self, to_email: str, reset_token: str, user_name: str) -> Dict[str, Any]:
        """
        Send password reset email using template.
        """
        max_retries = 3
        retry_delay = 2

        for attempt in range(max_retries):
            try:
                logger.info(f"Attempting to send password reset email to {to_email}")

                # Render template
                template_data = template_service.render_email_template(
                    "password_reset",
                    {
                        "user_name": user_name,
                        "reset_token": reset_token,
                        "reset_url": f"{settings.FRONTEND_URL}/reset-password?token={reset_token}"
                    }
                )

                # Create email message
                subject = f"Password Reset Request - {settings.APP_NAME}"
                msg = MIMEMultipart('alternative')
                msg['Subject'] = subject
                msg['From'] = f"{settings.APP_NAME} <{self.from_email}>"
                msg['To'] = to_email
                msg['Reply-To'] = self.from_email

                # Add headers
                msg['X-Mailer'] = f"{settings.APP_NAME} Mailer"
                msg['X-Priority'] = '1'
                msg['X-Auto-Response-Suppress'] = 'OOF, AutoReply'

                # Attach both HTML and plain text
                msg.attach(MIMEText(template_data["text"], 'plain', 'utf-8'))
                msg.attach(MIMEText(template_data["html"], 'html', 'utf-8'))

                # Send email
                context = ssl.create_default_context()

                with smtplib.SMTP(self.smtp_server, self.smtp_port, timeout=30) as server:
                    server.ehlo()

                    if server.has_extn('STARTTLS'):
                        server.starttls(context=context)
                        server.ehlo()

                    server.login(self.smtp_username, self.smtp_password)
                    server.send_message(msg)

                logger.info(f"  Password reset email sent successfully to {to_email}")

                return {
                    "success": True,
                    "message": "Password reset email sent successfully",
                    "to_email": to_email
                }

            except Exception as e:
                logger.error(f"Failed to send email (attempt {attempt + 1}): {e}")
                if attempt == max_retries - 1:
                    return {
                        "success": False,
                        "error": "Failed to send email",
                        "details": str(e),
                        "to_email": to_email
                    }

                # Wait before retry
                time.sleep(retry_delay * (attempt + 1))

        return {
            "success": False,
            "error": "Max retries exceeded",
            "to_email": to_email
        }

email_service = EmailService()
