"""Envío del informe por email (SMTP genérico: Gmail, Outlook, Brevo...)."""
import os
import smtplib
import ssl
from email.mime.image import MIMEImage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def enviar(asunto: str, html: str, texto: str, imagenes: dict[str, Path], log=print) -> bool:
    # los secretos vacíos llegan como "", por eso se usa `or` para los valores por defecto
    host = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
    port = int(os.environ.get("SMTP_PORT") or "465")
    user = os.environ.get("SMTP_USER")
    pwd = os.environ.get("SMTP_PASSWORD")
    to = os.environ.get("EMAIL_TO") or user
    if not user or not pwd:
        log("SMTP_USER / SMTP_PASSWORD no configurados: no se envía email (el informe queda guardado).")
        return False

    msg = MIMEMultipart("related")
    msg["Subject"], msg["From"], msg["To"] = asunto, user, to
    alt = MIMEMultipart("alternative")
    alt.attach(MIMEText(texto, "plain", "utf-8"))
    alt.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(alt)
    for cid, ruta in imagenes.items():
        img = MIMEImage(Path(ruta).read_bytes(), _subtype="png")
        img.add_header("Content-ID", f"<{cid}>")
        img.add_header("Content-Disposition", "inline", filename=Path(ruta).name)
        msg.attach(img)

    ctx = ssl.create_default_context()
    destinatarios = [d.strip() for d in to.split(",")]
    if port == 465:
        with smtplib.SMTP_SSL(host, port, context=ctx, timeout=60) as s:
            s.login(user, pwd)
            s.sendmail(user, destinatarios, msg.as_string())
    else:
        with smtplib.SMTP(host, port, timeout=60) as s:
            s.starttls(context=ctx)
            s.login(user, pwd)
            s.sendmail(user, destinatarios, msg.as_string())
    log(f"Email enviado a {to}")
    return True
