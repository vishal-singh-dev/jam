"""Email notification service sending transactional emails via Mailpit SMTP."""

import logging
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from src.config import Settings, get_settings

logger = logging.getLogger("api.auth.email")


def send_smtp_email(
    to_email: str,
    subject: str,
    html_content: str,
    text_content: str,
    settings: Settings | None = None,
) -> bool:
    """Send an email using SMTP (Mailpit in local/test environments)."""
    cfg = settings or get_settings()

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"{cfg.mail_from_name} <{cfg.mail_from_email}>"
    msg["To"] = to_email

    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    try:
        with smtplib.SMTP(cfg.mailpit_smtp_host, cfg.mailpit_smtp_port, timeout=5.0) as server:
            server.send_message(msg)
        logger.info("Sent email '%s' to %s via Mailpit SMTP", subject, to_email)
        return True
    except Exception as exc:
        logger.warning(
            "Failed to deliver email to %s via SMTP (%s:%s): %s",
            to_email,
            cfg.mailpit_smtp_host,
            cfg.mailpit_smtp_port,
            exc,
        )
        return False


def send_verification_email(
    to_email: str,
    display_name: str,
    raw_token: str,
    settings: Settings | None = None,
) -> bool:
    """Send an email containing a verification link with raw single-use token."""
    cfg = settings or get_settings()
    frontend_origin = cfg.cors_origins[0] if cfg.cors_origins else "http://localhost:5173"
    verify_url = f"{frontend_origin}/verify-email?token={raw_token}"

    subject = "Verify your email - Collaborative Whiteboard"
    text_content = (
        f"Hello {display_name},\n\n"
        f"Thank you for registering. Please verify your email by clicking the link below:\n"
        f"{verify_url}\n\n"
        f"Or use this verification token directly: {raw_token}\n\n"
        f"This token expires in {cfg.verification_token_expire_hours} hours."
    )
    html_content = f"""
    <html>
      <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
        <h2>Welcome to Collaborative Whiteboard, {display_name}!</h2>
        <p>Please confirm your email address by clicking the link below:</p>
        <p>
          <a href="{verify_url}"
             style="display: inline-block; padding: 10px 20px; background-color: #2563eb;
                    color: #ffffff; text-decoration: none; border-radius: 5px;">
            Verify Email Address
          </a>
        </p>
        <p>Alternatively, copy and paste this verification token: <code>{raw_token}</code></p>
        <p><small>This token will expire in {cfg.verification_token_expire_hours} hours.</small></p>
      </body>
    </html>
    """
    return send_smtp_email(to_email, subject, html_content, text_content, cfg)


def send_password_reset_email(
    to_email: str,
    display_name: str,
    raw_token: str,
    settings: Settings | None = None,
) -> bool:
    """Send an email containing a single-use password reset link."""
    cfg = settings or get_settings()
    frontend_origin = cfg.cors_origins[0] if cfg.cors_origins else "http://localhost:5173"
    reset_url = f"{frontend_origin}/reset-password?token={raw_token}"

    subject = "Password Reset Request - Collaborative Whiteboard"
    text_content = (
        f"Hello {display_name},\n\n"
        "A password reset was requested for your account. "
        "You can reset your password using the link below:\n"
        f"{reset_url}\n\n"
        f"Or use this reset token directly: {raw_token}\n\n"
        f"This token expires in {cfg.password_reset_token_expire_hours} hour(s). "
        "If you did not request this, please ignore this email."
    )
    html_content = f"""
    <html>
      <body style="font-family: sans-serif; line-height: 1.6; color: #333;">
        <h2>Password Reset Request</h2>
        <p>Hello {display_name},</p>
        <p>Click the button below to choose a new password:</p>
        <p>
          <a href="{reset_url}"
             style="display: inline-block; padding: 10px 20px; background-color: #dc2626;
                    color: #ffffff; text-decoration: none; border-radius: 5px;">
            Reset Password
          </a>
        </p>
        <p>Or copy and paste this token: <code>{raw_token}</code></p>
        <p>
          <small>
            This single-use link expires in {cfg.password_reset_token_expire_hours} hour(s).
          </small>
        </p>
      </body>
    </html>
    """
    return send_smtp_email(to_email, subject, html_content, text_content, cfg)
