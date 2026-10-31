"""Email service for authentication-related emails."""

import smtplib
import ssl
from datetime import datetime
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional
import logging

from ..config.settings import settings

logger = logging.getLogger(__name__)


class EmailService:
    """Email service for sending authentication emails."""

    @staticmethod
    def _get_smtp_connection():
        """Create SMTP connection."""
        if not settings.smtp_host or not settings.from_email:
            raise ValueError("Email service not configured")

        context = ssl.create_default_context()

        if settings.smtp_use_tls:
            server = smtplib.SMTP(settings.smtp_host, settings.smtp_port)
            server.starttls(context=context)
        else:
            server = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, context=context)

        if settings.smtp_username and settings.smtp_password:
            server.login(settings.smtp_username, settings.smtp_password)

        return server

    @staticmethod
    async def send_verification_email(
        email: str,
        verification_token: str,
        user_name: Optional[str] = None
    ) -> bool:
        """Send email verification email."""
        try:
            # Create verification URL
            base_url = settings.frontend_url
            verification_url = f"{base_url}/verify-email?token={verification_token}"

            # Email content
            display_name = user_name if user_name else email.split('@')[0]

            subject = "Verify Your Job Portal Account"

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 10px; }}
                    .header {{ background-color: #2c3e50; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background-color: white; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .button {{ display: inline-block; background-color: #3498db; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                    .footer {{ text-align: center; margin-top: 20px; font-size: 14px; color: #7f8c8d; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Welcome to Job Portal!</h1>
                    </div>
                    <div class="content">
                        <h2>Hi {display_name},</h2>
                        <p>Thank you for signing up for Job Portal! To complete your registration and start exploring job opportunities, please verify your email address.</p>

                        <p style="text-align: center;">
                            <a href="{verification_url}" class="button">Verify Email Address</a>
                        </p>

                        <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                        <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 5px;">
                            {verification_url}
                        </p>

                        <p><strong>Note:</strong> This verification link will expire in 24 hours for security reasons.</p>

                        <p>If you didn't create an account with Job Portal, you can safely ignore this email.</p>

                        <p>Welcome aboard!<br>The Job Portal Team</p>
                    </div>
                    <div class="footer">
                        <p>This email was sent to {email}. If you have any questions, please contact our support team.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            text_content = f"""
            Hi {display_name},

            Thank you for signing up for Job Portal! To complete your registration, please verify your email address by clicking the link below:

            {verification_url}

            This verification link will expire in 24 hours for security reasons.

            If you didn't create an account with Job Portal, you can safely ignore this email.

            Welcome aboard!
            The Job Portal Team
            """

            return await EmailService._send_email(email, subject, text_content, html_content)

        except Exception as e:
            logger.error(f"Failed to send verification email to {email}: {e}")
            return False

    @staticmethod
    async def send_password_reset_email(
        email: str,
        reset_token: str,
        user_name: Optional[str] = None
    ) -> bool:
        """Send password reset email."""
        try:
            # Create reset URL
            base_url = settings.frontend_url
            reset_url = f"{base_url}/reset-password?token={reset_token}"

            # Email content
            display_name = user_name if user_name else email.split('@')[0]

            subject = "Reset Your Job Portal Password"

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 10px; }}
                    .header {{ background-color: #e74c3c; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background-color: white; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .button {{ display: inline-block; background-color: #e74c3c; color: white; padding: 12px 25px; text-decoration: none; border-radius: 5px; margin: 20px 0; }}
                    .footer {{ text-align: center; margin-top: 20px; font-size: 14px; color: #7f8c8d; }}
                    .warning {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Password Reset Request</h1>
                    </div>
                    <div class="content">
                        <h2>Hi {display_name},</h2>
                        <p>We received a request to reset your Job Portal account password.</p>

                        <p style="text-align: center;">
                            <a href="{reset_url}" class="button">Reset Password</a>
                        </p>

                        <p>If the button doesn't work, you can copy and paste this link into your browser:</p>
                        <p style="word-break: break-all; background-color: #f8f9fa; padding: 10px; border-radius: 5px;">
                            {reset_url}
                        </p>

                        <div class="warning">
                            <strong>Important:</strong>
                            <ul>
                                <li>This password reset link will expire in 1 hour for security reasons</li>
                                <li>If you didn't request this password reset, please ignore this email</li>
                                <li>Your password will remain unchanged until you create a new one</li>
                            </ul>
                        </div>

                        <p>For your security, we recommend choosing a strong password that:</p>
                        <ul>
                            <li>Is at least 8 characters long</li>
                            <li>Contains uppercase and lowercase letters</li>
                            <li>Includes numbers and special characters</li>
                            <li>Is unique to your Job Portal account</li>
                        </ul>

                        <p>Best regards,<br>The Job Portal Security Team</p>
                    </div>
                    <div class="footer">
                        <p>This email was sent to {email}. If you have security concerns, please contact our support team immediately.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            text_content = f"""
            Hi {display_name},

            We received a request to reset your Job Portal account password.

            To reset your password, please click the link below:
            {reset_url}

            IMPORTANT:
            - This password reset link will expire in 1 hour for security reasons
            - If you didn't request this password reset, please ignore this email
            - Your password will remain unchanged until you create a new one

            For your security, we recommend choosing a strong password that:
            - Is at least 8 characters long
            - Contains uppercase and lowercase letters
            - Includes numbers and special characters
            - Is unique to your Job Portal account

            Best regards,
            The Job Portal Security Team
            """

            return await EmailService._send_email(email, subject, text_content, html_content)

        except Exception as e:
            logger.error(f"Failed to send password reset email to {email}: {e}")
            return False

    @staticmethod
    async def send_password_changed_notification(
        email: str,
        user_name: Optional[str] = None,
        ip_address: Optional[str] = None
    ) -> bool:
        """Send password change notification email."""
        try:
            display_name = user_name if user_name else email.split('@')[0]

            subject = "Your Job Portal Password Has Been Changed"

            html_content = f"""
            <!DOCTYPE html>
            <html>
            <head>
                <meta charset="utf-8">
                <style>
                    body {{ font-family: Arial, sans-serif; line-height: 1.6; margin: 0; padding: 20px; }}
                    .container {{ max-width: 600px; margin: 0 auto; background-color: #f9f9f9; padding: 20px; border-radius: 10px; }}
                    .header {{ background-color: #27ae60; color: white; padding: 20px; text-align: center; border-radius: 10px 10px 0 0; }}
                    .content {{ background-color: white; padding: 30px; border-radius: 0 0 10px 10px; }}
                    .footer {{ text-align: center; margin-top: 20px; font-size: 14px; color: #7f8c8d; }}
                    .info {{ background-color: #d4edda; border: 1px solid #c3e6cb; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                    .warning {{ background-color: #fff3cd; border: 1px solid #ffeaa7; padding: 15px; border-radius: 5px; margin: 15px 0; }}
                </style>
            </head>
            <body>
                <div class="container">
                    <div class="header">
                        <h1>Password Successfully Changed</h1>
                    </div>
                    <div class="content">
                        <h2>Hi {display_name},</h2>
                        <p>This is to confirm that your Job Portal account password has been successfully changed.</p>

                        <div class="info">
                            <strong>Change Details:</strong>
                            <ul>
                                <li>Date: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}</li>
                                {f'<li>IP Address: {ip_address}</li>' if ip_address else ''}
                            </ul>
                        </div>

                        <div class="warning">
                            <strong>Didn't make this change?</strong>
                            <p>If you didn't change your password, your account may have been compromised. Please:</p>
                            <ol>
                                <li>Reset your password immediately</li>
                                <li>Review your recent account activity</li>
                                <li>Contact our support team</li>
                            </ol>
                        </div>

                        <p>Your account security is important to us. We recommend:</p>
                        <ul>
                            <li>Using a unique, strong password</li>
                            <li>Enabling two-factor authentication when available</li>
                            <li>Regularly reviewing your account activity</li>
                            <li>Not sharing your login credentials</li>
                        </ul>

                        <p>Thank you for keeping your account secure!</p>

                        <p>Best regards,<br>The Job Portal Security Team</p>
                    </div>
                    <div class="footer">
                        <p>This email was sent to {email}. If you have security concerns, please contact our support team immediately.</p>
                    </div>
                </div>
            </body>
            </html>
            """

            text_content = f"""
            Hi {display_name},

            This is to confirm that your Job Portal account password has been successfully changed.

            Change Details:
            - Date: {datetime.utcnow().strftime('%B %d, %Y at %I:%M %p UTC')}
            {f'- IP Address: {ip_address}' if ip_address else ''}

            DIDN'T MAKE THIS CHANGE?
            If you didn't change your password, your account may have been compromised. Please:
            1. Reset your password immediately
            2. Review your recent account activity
            3. Contact our support team

            Your account security is important to us. We recommend:
            - Using a unique, strong password
            - Enabling two-factor authentication when available
            - Regularly reviewing your account activity
            - Not sharing your login credentials

            Thank you for keeping your account secure!

            Best regards,
            The Job Portal Security Team
            """

            return await EmailService._send_email(email, subject, text_content, html_content)

        except Exception as e:
            logger.error(f"Failed to send password change notification to {email}: {e}")
            return False

    @staticmethod
    async def _send_email(
        to_email: str,
        subject: str,
        text_content: str,
        html_content: str
    ) -> bool:
        """Send email with both text and HTML content."""
        try:
            if not settings.from_email:
                logger.error("Email service not configured - missing from_email")
                return False

            # Create message
            message = MIMEMultipart("alternative")
            message["Subject"] = subject
            message["From"] = settings.from_email
            message["To"] = to_email

            # Add text and HTML parts
            text_part = MIMEText(text_content, "plain")
            html_part = MIMEText(html_content, "html")

            message.attach(text_part)
            message.attach(html_part)

            # Send email
            with EmailService._get_smtp_connection() as server:
                server.send_message(message)

            logger.info(f"Email sent successfully to {to_email}")
            return True

        except Exception as e:
            logger.error(f"Failed to send email to {to_email}: {e}")
            return False

    @staticmethod
    def is_email_configured() -> bool:
        """Check if email service is properly configured."""
        return bool(
            settings.smtp_host and
            settings.from_email
        )