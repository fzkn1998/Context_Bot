import os
import smtplib
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from jose import JWTError, jwt
from passlib.context import CryptContext

SECRET_KEY = os.getenv("SECRET_KEY", "please-change-this-secret-key-in-production")
ALGORITHM = "HS256"
SESSION_EXPIRE_DAYS = 7
EMAIL_VERIFY_EXPIRE_HOURS = 1

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


def create_session_token(user_id: int, email: str) -> str:
    expire = datetime.utcnow() + timedelta(days=SESSION_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(user_id), "email": email, "exp": expire, "type": "session"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def create_verify_token(email: str) -> str:
    expire = datetime.utcnow() + timedelta(hours=EMAIL_VERIFY_EXPIRE_HOURS)
    return jwt.encode(
        {"email": email, "exp": expire, "type": "verify"},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_token(token: str) -> Optional[dict]:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        return None


def send_verification_email(to_email: str, name: str, verify_url: str) -> None:
    smtp_host = os.getenv("SMTP_HOST", "smtp.gmail.com")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER", "")
    smtp_pass = os.getenv("SMTP_PASS", "")
    from_email = os.getenv("FROM_EMAIL", smtp_user)

    msg = MIMEMultipart("alternative")
    msg["Subject"] = "Verify your ContextDesk account"
    msg["From"] = from_email
    msg["To"] = to_email

    html_body = f"""<!DOCTYPE html>
<html>
<body style="font-family:system-ui,sans-serif;background:#f8fafc;padding:40px 20px;margin:0;">
  <div style="max-width:480px;margin:0 auto;background:#fff;border-radius:12px;
              padding:36px;border:1px solid #e2e8f0;">
    <div style="margin-bottom:20px;">
      <div style="display:inline-flex;align-items:center;gap:10px;">
        <div style="width:30px;height:30px;border-radius:7px;
                    background:linear-gradient(135deg,#4f46e5,#7c3aed);"></div>
        <strong style="font-size:17px;color:#0f172a;">ContextDesk</strong>
      </div>
    </div>
    <h2 style="margin:0 0 10px;font-size:20px;color:#0f172a;">Welcome, {name}!</h2>
    <p style="color:#475569;margin:0 0 24px;line-height:1.6;">
      Please verify your email address to activate your account.
      This link expires in 1 hour.
    </p>
    <a href="{verify_url}"
       style="display:inline-block;padding:12px 28px;background:#4f46e5;color:#fff;
              text-decoration:none;border-radius:8px;font-weight:600;font-size:14px;">
      Verify Email Address
    </a>
    <p style="margin-top:24px;font-size:12px;color:#94a3b8;">
      If you did not create an account, you can safely ignore this email.
    </p>
  </div>
</body>
</html>"""

    msg.attach(MIMEText(html_body, "html"))

    with smtplib.SMTP(smtp_host, smtp_port) as server:
        server.starttls()
        server.login(smtp_user, smtp_pass)
        server.sendmail(from_email, to_email, msg.as_string())
