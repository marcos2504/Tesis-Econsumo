import imaplib
import email
import os

def descargar_facturas(email_user, email_pass, carpeta="data"):
    if not os.path.exists(carpeta):
        os.makedirs(carpeta)

    print("📬 Conectando a Gmail...")
    mail = imaplib.IMAP4_SSL("imap.gmail.com")
    mail.login(email_user, email_pass)
    mail.select("inbox")

    print("🔍 Buscando facturas de Ecogas...")
    result, data = mail.search(None, '(SUBJECT "ecogas")')
    email_ids = data[0].split()

    print(f"📥 Se encontraron {len(email_ids)} mails con el asunto 'ecogas'")

    for e_id in email_ids:
        result, msg_data = mail.fetch(e_id, "(RFC822)")
        raw_email = msg_data[0][1]
        msg = email.message_from_bytes(raw_email)

        for part in msg.walk():
            if part.get_content_maintype() == 'multipart':
                continue
            if part.get('Content-Disposition') is None:
                continue
            filename = part.get_filename()
            if filename and filename.endswith(".pdf"):
                filepath = os.path.join(carpeta, filename)
                if not os.path.exists(filepath):
                    with open(filepath, 'wb') as f:
                        f.write(part.get_payload(decode=True))
                    print(f"✅ Descargado: {filename}")
    mail.logout()