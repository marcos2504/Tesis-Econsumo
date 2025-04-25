#!/bin/bash

echo "🔧 Creando entorno virtual..."
python3 -m venv venv

echo "✅ Entorno virtual creado."

echo "📦 Activando entorno virtual..."
source venv/bin/activate

echo "📦 Instalando dependencias..."
pip install --upgrade pip
pip install -r requirements.txt

echo "✅ Listo. Entorno virtual y dependencias instaladas."