import os
import io
import re
import csv
import base64
import fitz  # PyMuPDF
from matplotlib import pyplot as plt
import requests
import pytesseract
import cv2
import numpy as np
import pandas as pd
from PIL import Image
from playwright.sync_api import sync_playwright
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from pdf2image import convert_from_path

# === CONFIGURACIÓN ===
SCOPES = ['https://www.googleapis.com/auth/gmail.readonly']
EMAIL_QUERY = 'subject:"Factura Digital"'
CSV_FILE = "facturas_edemsa.csv"
HISTORICO_CSV = "historico_consumo_extraido.csv"

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

def extraer_info_pdf(nombre_pdf):
    doc = fitz.open(nombre_pdf)
    texto = ""
    for page in doc:
        texto += page.get_text("text")

    lineas = texto.splitlines()

    nic = ""
    direccion = ""
    fecha_lectura = ""
    consumo_kwh = ""

    for linea in lineas:
        if re.fullmatch(r"\d{6,10}", linea.strip()):
            nic = linea.strip()
            break

    for i, linea in enumerate(lineas):
        if "Domicilio suministro" in linea:
            calle = lineas[i + 1].strip()
            localidad1 = lineas[i + 2].strip()
            localidad2 = lineas[i + 3].strip()
            direccion = f"{calle}, {localidad1}, {localidad2}"
            break

    fechas = re.findall(r'\d{2}/\d{2}/\d{4}', texto)
    if len(fechas) >= 2:
        fecha_lectura = fechas[1]

    energia_activa_index = None
    for i, linea in enumerate(lineas):
        if "Energía Activa" in linea:
            energia_activa_index = i
            break

    if energia_activa_index is not None:
        for linea in lineas[energia_activa_index+1:energia_activa_index+5]:
            if re.match(r'^\d+,\d{2}$', linea.strip()):
                consumo_kwh = linea.strip().replace(",", ".")

    if not consumo_kwh:
        for i, linea in enumerate(lineas):
            if "Cargo Variable" in linea and "kWh" in linea:
                if i+1 < len(lineas):
                    match = re.search(r'(\d+,\d+)', lineas[i+1])
                    if match:
                        consumo_kwh = match.group(1).replace(",", ".")

    return {
        "nic": nic,
        "direccion": direccion,
        "fecha_lectura": fecha_lectura,
        "consumo_kwh": consumo_kwh
    }

def extraer_grafico_por_coords(nombre_pdf, output_path, dpi=200):
    try:
        pages = convert_from_path(nombre_pdf, dpi=dpi)
        if not pages:
            print("❌ No se pudo renderizar el PDF.")
            return False

        page = pages[0]
        width, height = page.size

        top = int(height * 0.455)
        bottom = int(height * 0.585)
        left = int(width * 0.05)
        right = int(width * 0.495)

        grafico = page.crop((left, top, right, bottom))
        grafico.save(output_path)
        print(f"📊 Gráfico recortado guardado en {output_path}")
        return True
    except Exception as e:
        print(f"[!] Error al extraer gráfico: {e}")
        return False

def guardar_factura(data):
    file_exists = os.path.exists(CSV_FILE)
    with open(CSV_FILE, 'a', newline='') as csvfile:
        fieldnames = ['nic', 'direccion', 'fecha_lectura', 'consumo_kwh', 'link', 'imagen']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(data)



# === DESCARGA DIRECTA DEL PDF AUTÉNTICO ===
def descargar_factura_pdf(url, index):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        try:
            print(f"🌐 Abriendo sesión para descarga directa...")
            page.goto(url, timeout=90000, wait_until="load")
            page.wait_for_timeout(5000)

            cookies = context.cookies()
            headers = {
                "User-Agent": "Mozilla/5.0",
                "Referer": url,
            }
            cookie_str = "; ".join([f"{c['name']}={c['value']}" for c in cookies])
            headers["Cookie"] = cookie_str

            pdf_url = url.replace("facturad.php", "facturad_mail.php")
            nombre_archivo = f"factura_{index + 1}.pdf"
            response = requests.get(pdf_url, headers=headers)

            if response.status_code == 200 and response.headers['Content-Type'] == 'application/pdf':
                with open(nombre_archivo, "wb") as f:
                    f.write(response.content)
                print(f"✅ PDF descargado correctamente: {nombre_archivo}")

                datos = extraer_info_pdf(nombre_archivo)
                datos["link"] = url

                nombre_imagen = f"grafico_{index + 1}.png"
                if extraer_grafico_por_coords(nombre_archivo, nombre_imagen):
                    datos["imagen"] = nombre_imagen
                else:
                    datos["imagen"] = ""

                guardar_factura(datos)
                return datos
            else:
                print(f"⚠️ Error al descargar PDF real. Status: {response.status_code}")
                return None
        except Exception as e:
            print(f"[!] Error durante la descarga del PDF: {e}")
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
        descargar_factura_pdf(link, i)

    print("\n✅ Proceso finalizado.\n")

if __name__ == '__main__':
    main()