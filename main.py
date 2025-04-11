from mail_utils.fetch_emails import descargar_facturas
from mail_utils.pdf_parser import extraer_consumo

EMAIL = "tu_email@gmail.com"
PASSWORD = "tu_app_password"
CARPETA_FACTURAS = "data"

# Paso 1: Descargar facturas de Ecogas
descargar_facturas(EMAIL, PASSWORD, carpeta=CARPETA_FACTURAS)

# Paso 2: Extraer datos de consumo desde los PDFs
datos = extraer_consumo(CARPETA_FACTURAS)

print("\n📊 Datos extraídos:")
print(datos.head())