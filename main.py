import os
import re
import csv
import base64
from datetime import datetime

import pandas as pd

from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

from playwright.sync_api import sync_playwright

# === CONFIGURACIÓN ===
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
EMAIL_QUERY = 'subject:"Factura Digital"'
CSV_FILE = "facturas_edemsa.csv"

# === GMAIL API ===
def get_service():
    if os.path.exists("token.json"):
        creds = Credentials.from_authorized_user_file("token.json", SCOPES)
    else:
        flow = InstalledAppFlow.from_client_secrets_file("credentials.json", SCOPES)
        creds = flow.run_local_server(port=0)
        with open("token.json", "w") as token:
            token.write(creds.to_json())
    return build('gmail', 'v1', credentials=creds)

def get_html_part(payload):
    if 'parts' in payload:
        for part in payload['parts']:
            if part.get('mimeType') == 'text/html':
                return part['body'].get('data')
            elif part.get('parts'):
                return get_html_part(part)
    elif payload.get('mimeType') == 'text/html':
        return payload['body'].get('data')
    return None

def get_edemsa_links(service):
    results = service.users().messages().list(userId='me', q=EMAIL_QUERY).execute()
    messages = results.get('messages', [])
    links = []

    for msg in messages:
        msg_data = service.users().messages().get(userId='me', id=msg['id'], format='full').execute()
        html_data = get_html_part(msg_data['payload'])
        if not html_data:
            continue
        html = base64.urlsafe_b64decode(html_data + '===').decode('utf-8', errors='ignore')
        encontrados = re.findall(r'https://oficinavirtual\.edemsa\.com/facturad\.php\?conf=[^"]+', html)
        links.extend(encontrados)

    return list(set(links))

# === FUNCIONES PARA GUARDADO Y CSV ===
def cargar_facturas_existentes():
    if os.path.exists(CSV_FILE):
        df = pd.read_csv(CSV_FILE)
        return set(df['link'].values)
    return set()

def guardar_factura(data):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as csvfile:
        fieldnames = ['fecha_vencimiento', 'importe_total', 'consumo_kwh', 'link']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)

# === AUTOMATIZACIÓN CON PLAYWRIGHT ===
def extraer_datos_playwright(url, index):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 3000},
            locale="es-ES"
        )
        page = context.new_page()

        try:
            print(f"\n📄 Abriendo link de factura:\n{url}")
            page.goto(url, timeout=60000, wait_until="domcontentloaded")
            page.wait_for_timeout(5000)

            nombre_archivo = f"factura_{index + 1}.pdf"

            page.set_viewport_size({"width": 1280, "height": 3000})
            page.pdf(
                path=nombre_archivo,
                print_background=True,
                margin={"top": "10mm", "bottom": "10mm", "left": "10mm", "right": "10mm"},
                scale=1.0,
                width="1280px",
                height="3000px"
            )

            print(f"✅ PDF generado: {nombre_archivo}")

            return {"fecha_vencimiento": "", "importe_total": "", "consumo_kwh": "", "link": url}

        except Exception as e:
            print(f"[!] Falló al navegar: {e}")
            try:
                page.screenshot(path=f"error_{index + 1}.png", full_page=True)
                print(f"📸 Captura guardada: error_{index + 1}.png")
            except Exception as e2:
                print(f"⚠️ No se pudo tomar screenshot: {e2}")
            return None
        finally:
            browser.close()

# === MAIN ===
def main():
    print("🔍 Buscando facturas...")
    service = get_service()
    links = get_edemsa_links(service)
    if not links:
        print("No se encontraron facturas nuevas.")
        return

    existentes = cargar_facturas_existentes()
    nuevos = [l for l in links if l not in existentes]

    print(f"🆕 Se encontraron {len(nuevos)} nuevas facturas.")

    for i, link in enumerate(nuevos):
        data = extraer_datos_playwright(link, i)
        if data:
            guardar_factura(data)

    print("\n✅ Proceso finalizado.\n")

if __name__ == '__main__':
    main()
