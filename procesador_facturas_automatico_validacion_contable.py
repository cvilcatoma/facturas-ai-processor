import os
import json
import time
import shutil
import hashlib
from datetime import datetime

import fitz  # PyMuPDF
import pytesseract
import requests
import mysql.connector
from dotenv import load_dotenv
from PIL import Image
from pdf2image import convert_from_path

load_dotenv()

OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY", "").strip()
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN", "").strip()
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "").strip()
MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost").strip()
MYSQL_USER = os.getenv("MYSQL_USER", "root").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "").strip()
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "demo_facturas").strip()

PROCESS_INTERVAL_SECONDS = int(os.getenv("PROCESS_INTERVAL_SECONDS", "10"))

TESSERACT_CMD = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
TESSDATA_DIR = r"C:\Program Files\Tesseract-OCR\tessdata"

pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
os.environ["TESSDATA_PREFIX"] = TESSDATA_DIR

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
INPUT_DIR = os.path.join(BASE_DIR, "input")
PROCESADAS_DIR = os.path.join(BASE_DIR, "procesadas")
ERROR_DIR = os.path.join(BASE_DIR, "error")
DUPLICADOS_DIR = os.path.join(BASE_DIR, "duplicados")
OBSERVADAS_DIR = os.path.join(BASE_DIR, "observadas")
LOGS_DIR = os.path.join(BASE_DIR, "logs")

EXTENSIONES_SOPORTADAS = {".pdf", ".jpg", ".jpeg", ".png"}


def asegurar_carpetas():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(PROCESADAS_DIR, exist_ok=True)
    os.makedirs(ERROR_DIR, exist_ok=True)
    os.makedirs(DUPLICADOS_DIR, exist_ok=True)
    os.makedirs(OBSERVADAS_DIR, exist_ok=True)
    os.makedirs(LOGS_DIR, exist_ok=True)


def log(msg):
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{marca}] {msg}")


def limpiar_texto(valor):
    if valor is None:
        return ""
    return str(valor).strip()


def parse_numero(valor):
    texto = limpiar_texto(valor)
    if not texto:
        return None

    texto = texto.replace("S/", "").replace("$", "").replace("US$", "")
    texto = texto.replace(" ", "")

    if "," in texto and "." in texto:
        if texto.rfind(",") > texto.rfind("."):
            texto = texto.replace(".", "").replace(",", ".")
        else:
            texto = texto.replace(",", "")
    else:
        if "," in texto:
            texto = texto.replace(",", ".")

    try:
        return float(texto)
    except Exception:
        return None


def validar_configuracion():
    print("\nDIAGNOSTICO DE VARIABLES:")
    print(f"OPENROUTER_API_KEY cargada: {bool(OPENROUTER_API_KEY)}")
    print(f"TELEGRAM_TOKEN cargado: {bool(TELEGRAM_TOKEN)}")
    print(f"TELEGRAM_CHAT_ID cargado: {bool(TELEGRAM_CHAT_ID)}")
    print(f"MYSQL_HOST: {MYSQL_HOST}")
    print(f"MYSQL_USER: {MYSQL_USER}")
    print(f"MYSQL_PASSWORD cargado: {bool(MYSQL_PASSWORD)}")
    print(f"MYSQL_DATABASE: {MYSQL_DATABASE}")
    print(f"PROCESS_INTERVAL_SECONDS: {PROCESS_INTERVAL_SECONDS}")
    print(f"TESSERACT_CMD: {TESSERACT_CMD}")
    print(f"TESSDATA_PREFIX: {os.environ.get('TESSDATA_PREFIX', '')}")

    faltantes = []
    if not OPENROUTER_API_KEY:
        faltantes.append("OPENROUTER_API_KEY")
    if not TELEGRAM_TOKEN:
        faltantes.append("TELEGRAM_TOKEN")
    if not TELEGRAM_CHAT_ID:
        faltantes.append("TELEGRAM_CHAT_ID")
    if not MYSQL_HOST:
        faltantes.append("MYSQL_HOST")
    if not MYSQL_USER:
        faltantes.append("MYSQL_USER")
    if MYSQL_PASSWORD == "":
        faltantes.append("MYSQL_PASSWORD")
    if not MYSQL_DATABASE:
        faltantes.append("MYSQL_DATABASE")

    if faltantes:
        raise RuntimeError("Faltan variables en el archivo .env: " + ", ".join(faltantes))


def asegurar_columna(cursor, tabla, columna, definicion_sql):
    cursor.execute(f"SHOW COLUMNS FROM {tabla} LIKE %s", (columna,))
    existe = cursor.fetchone()
    if not existe:
        cursor.execute(f"ALTER TABLE {tabla} ADD COLUMN {columna} {definicion_sql}")
        log(f"Columna agregada: {tabla}.{columna}")


def crear_base_de_datos():
    log("Preparando MySQL...")
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
    )
    cursor = conn.cursor()
    cursor.execute(f"CREATE DATABASE IF NOT EXISTS {MYSQL_DATABASE}")
    cursor.execute(f"USE {MYSQL_DATABASE}")
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS facturas (
            id INT AUTO_INCREMENT PRIMARY KEY,
            archivo_origen VARCHAR(255),
            hash_archivo VARCHAR(64),
            numero_factura VARCHAR(50),
            fecha_emision VARCHAR(20),
            fecha_vencimiento VARCHAR(20),
            proveedor VARCHAR(200),
            ruc_proveedor VARCHAR(20),
            cliente VARCHAR(200),
            subtotal VARCHAR(30),
            igv VARCHAR(30),
            total VARCHAR(30),
            forma_pago VARCHAR(100),
            json_ia LONGTEXT,
            estado VARCHAR(30) DEFAULT 'PROCESADA',
            observacion VARCHAR(255),
            fecha_registro DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    asegurar_columna(cursor, "facturas", "archivo_origen", "VARCHAR(255) NULL")
    asegurar_columna(cursor, "facturas", "hash_archivo", "VARCHAR(64) NULL")
    asegurar_columna(cursor, "facturas", "numero_factura", "VARCHAR(50) NULL")
    asegurar_columna(cursor, "facturas", "fecha_emision", "VARCHAR(20) NULL")
    asegurar_columna(cursor, "facturas", "fecha_vencimiento", "VARCHAR(20) NULL")
    asegurar_columna(cursor, "facturas", "proveedor", "VARCHAR(200) NULL")
    asegurar_columna(cursor, "facturas", "ruc_proveedor", "VARCHAR(20) NULL")
    asegurar_columna(cursor, "facturas", "cliente", "VARCHAR(200) NULL")
    asegurar_columna(cursor, "facturas", "subtotal", "VARCHAR(30) NULL")
    asegurar_columna(cursor, "facturas", "igv", "VARCHAR(30) NULL")
    asegurar_columna(cursor, "facturas", "total", "VARCHAR(30) NULL")
    asegurar_columna(cursor, "facturas", "forma_pago", "VARCHAR(100) NULL")
    asegurar_columna(cursor, "facturas", "json_ia", "LONGTEXT NULL")
    asegurar_columna(cursor, "facturas", "estado", "VARCHAR(30) NULL DEFAULT 'PROCESADA'")
    asegurar_columna(cursor, "facturas", "observacion", "VARCHAR(255) NULL")

    try:
        cursor.execute("CREATE INDEX idx_facturas_hash_archivo ON facturas(hash_archivo)")
    except Exception:
        pass

    try:
        cursor.execute("CREATE INDEX idx_facturas_ruc_numero ON facturas(ruc_proveedor, numero_factura)")
    except Exception:
        pass

    conn.commit()
    cursor.close()
    conn.close()
    log("MySQL listo")


def calcular_hash_archivo(ruta_archivo):
    sha256 = hashlib.sha256()
    with open(ruta_archivo, "rb") as f:
        for bloque in iter(lambda: f.read(8192), b""):
            sha256.update(bloque)
    return sha256.hexdigest()


def buscar_duplicado_por_hash(hash_archivo):
    conn = mysql.connector.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE
    )
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        "SELECT id, archivo_origen, numero_factura, ruc_proveedor FROM facturas WHERE hash_archivo = %s LIMIT 1",
        (hash_archivo,)
    )
    fila = cursor.fetchone()
    cursor.close()
    conn.close()
    return fila


def buscar_duplicado_logico(numero_factura, ruc_proveedor):
    if not numero_factura or not ruc_proveedor:
        return None

    conn = mysql.connector.connect(
        host=MYSQL_HOST, user=MYSQL_USER, password=MYSQL_PASSWORD, database=MYSQL_DATABASE
    )
    cursor = conn.cursor(dictionary=True)
    cursor.execute(
        """SELECT id, archivo_origen, numero_factura, ruc_proveedor
           FROM facturas
           WHERE numero_factura = %s AND ruc_proveedor = %s
           LIMIT 1""",
        (str(numero_factura).strip(), str(ruc_proveedor).strip())
    )
    fila = cursor.fetchone()
    cursor.close()
    conn.close()
    return fila


def idiomas_tesseract():
    try:
        return pytesseract.get_languages(config="")
    except Exception:
        return []


def ocr_con_fallback(imagen):
    langs = [x.lower() for x in idiomas_tesseract()]
    if "spa" in langs:
        return pytesseract.image_to_string(imagen, lang="spa").strip()
    if "eng" in langs:
        return pytesseract.image_to_string(imagen, lang="eng").strip()
    return pytesseract.image_to_string(imagen).strip()


def extraer_texto_pdf(ruta_pdf):
    doc = fitz.open(ruta_pdf)
    paginas = []
    for pagina in doc:
        paginas.append(pagina.get_text("text"))
    doc.close()

    texto = "\n".join(paginas).strip()

    if len(texto) > 30:
        log("PDF con texto detectable")
        return texto

    log("PDF sin texto suficiente. Aplicando OCR...")
    return aplicar_ocr_a_pdf(ruta_pdf)


def aplicar_ocr_a_pdf(ruta_pdf):
    try:
        imagenes = convert_from_path(ruta_pdf)
    except Exception as e:
        raise RuntimeError(
            "No se pudo convertir el PDF a imagen para OCR. "
            "Verifica que Poppler esté instalado. "
            f"Detalle: {e}"
        )

    textos = []
    for img in imagenes:
        texto_pagina = ocr_con_fallback(img)
        textos.append(texto_pagina)

    texto_final = "\n".join(textos).strip()
    if not texto_final:
        raise RuntimeError("OCR no devolvió texto del PDF escaneado.")
    return texto_final


def extraer_texto_imagen(ruta_imagen):
    log("Aplicando OCR a imagen...")
    try:
        img = Image.open(ruta_imagen)
    except Exception as e:
        raise RuntimeError(f"No se pudo abrir la imagen: {e}")

    texto = ocr_con_fallback(img)
    if not texto:
        log("OCR no devolvió texto para la imagen. Se escalará a IA directamente.")
        return ""   # vacío → ocr_extrajo_datos_suficientes() → False → IA
    return texto


def ocr_extrajo_datos_suficientes(texto):
    """
    Evalúa si el texto extraído por OCR contiene los campos clave
    de una factura peruana. Retorna True si el OCR fue suficiente
    y no es necesario llamar a la IA.
    """
    if not texto or len(texto.strip()) < 30:
        log("OCR: texto insuficiente (muy corto). Se usará IA.")
        return False

    texto_lower = texto.lower()

    # Detectar número de factura (formato peruano: F001-000123, E001-1, etc.)
    import re
    tiene_numero_factura = bool(re.search(r'[fFbBeE]\d{3}[-\s]\d+', texto))

    # Detectar RUC (11 dígitos, a veces precedido por "RUC")
    tiene_ruc = bool(re.search(r'\b\d{11}\b', texto))

    # Detectar monto total (S/ o número con decimales)
    tiene_monto = bool(re.search(r'(s/\.?\s*\d+[\.,]\d{2}|\b\d{1,8}[\.,]\d{2}\b)', texto_lower))

    campos_encontrados = sum([tiene_numero_factura, tiene_ruc, tiene_monto])

    log(
        f"OCR evaluación -> Nº factura: {tiene_numero_factura} | "
        f"RUC: {tiene_ruc} | Monto: {tiene_monto} | "
        f"Campos encontrados: {campos_encontrados}/3"
    )

    if campos_encontrados >= 2:
        log("OCR suficiente. Se intentará extraer datos sin IA.")
        return True

    log("OCR insuficiente. Se escalará a IA.")
    return False


def extraer_datos_con_ocr(texto):
    """
    Intenta estructurar los datos de la factura usando solo expresiones
    regulares sobre el texto extraído por OCR, sin llamar a la IA.
    Retorna un dict con los campos o None si no pudo estructurarlos.
    """
    import re

    datos = {
        "numero_factura": "",
        "fecha_emision": "",
        "fecha_vencimiento": "",
        "proveedor": "",
        "ruc_proveedor": "",
        "cliente": "",
        "subtotal": "",
        "igv": "",
        "total": "",
        "forma_pago": "",
    }

    # Número de factura
    m = re.search(r'([fFbBeE]\d{3}[-\s]\d+)', texto)
    if m:
        datos["numero_factura"] = m.group(1).strip()

    # RUC (11 dígitos)
    ruc_matches = re.findall(r'\b(\d{11})\b', texto)
    if ruc_matches:
        datos["ruc_proveedor"] = ruc_matches[0]

    # Fecha emisión
    m = re.search(
        r'(?:fecha\s*(?:de\s*)?emisi[oó]n|emitido|fecha)[:\s]+(\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4})',
        texto, re.IGNORECASE
    )
    if m:
        datos["fecha_emision"] = m.group(1).strip()
    else:
        # Buscar cualquier fecha dd/mm/yyyy
        m = re.search(r'\b(\d{1,2}[/\-]\d{1,2}[/\-]\d{4})\b', texto)
        if m:
            datos["fecha_emision"] = m.group(1).strip()

    # Total
    m = re.search(
        r'(?:total\s*(?:a\s*pagar)?|importe\s*total)[:\s]*(s/\.?\s*)?(\d{1,8}[.,]\d{2})',
        texto, re.IGNORECASE
    )
    if m:
        datos["total"] = m.group(2).replace(",", ".")

    # IGV
    m = re.search(
        r'(?:igv|i\.g\.v)[:\s]*(s/\.?\s*)?(\d{1,8}[.,]\d{2})',
        texto, re.IGNORECASE
    )
    if m:
        datos["igv"] = m.group(2).replace(",", ".")

    # Subtotal
    m = re.search(
        r'(?:subtotal|sub\s*total|valor\s*venta)[:\s]*(s/\.?\s*)?(\d{1,8}[.,]\d{2})',
        texto, re.IGNORECASE
    )
    if m:
        datos["subtotal"] = m.group(2).replace(",", ".")

    # Forma de pago
    m = re.search(
        r'(?:forma\s*de\s*pago|condici[oó]n\s*de\s*pago)[:\s]+([^\n]+)',
        texto, re.IGNORECASE
    )
    if m:
        datos["forma_pago"] = m.group(1).strip()[:100]

    # Validar campos críticos de identificación
    campos_criticos = [datos["numero_factura"], datos["ruc_proveedor"]]
    if not all(campos_criticos):
        log("OCR: faltan número de factura o RUC. Escalando a IA...")
        return None

    # Validar campos financieros obligatorios
    # Si falta cualquiera de los montos → escalar a IA para datos completos
    campos_financieros = [datos["subtotal"], datos["igv"], datos["total"]]
    if not all(campos_financieros):
        log(
            f"OCR: campos financieros incompletos "
            f"(subtotal='{datos['subtotal']}' | igv='{datos['igv']}' | total='{datos['total']}'). "
            f"Escalando a IA para garantizar datos completos..."
        )
        return None

    log("Datos estructurados por OCR OK (sin IA).")
    return datos


def extraer_json_de_texto(texto):
    texto = texto.replace("```json", "").replace("```", "").strip()
    inicio = texto.find("{")
    fin = texto.rfind("}")
    if inicio != -1 and fin != -1 and fin > inicio:
        texto = texto[inicio:fin + 1]
    return json.loads(texto)


def extraer_datos_con_ia(texto_factura, ruta_archivo=None):
    import base64

    log("Enviando factura a IA...")

    prompt_base = """Extrae estos datos de la factura y responde SOLO con JSON valido, sin texto extra ni backticks:
{
  "numero_factura":"",
  "fecha_emision":"",
  "fecha_vencimiento":"",
  "proveedor":"",
  "ruc_proveedor":"",
  "cliente":"",
  "subtotal":"",
  "igv":"",
  "total":"",
  "forma_pago":""
}

Reglas:
- Devuelve exactamente un objeto JSON.
- Mantén los valores como texto.
- Si no encuentras un dato, deja una cadena vacia.
- No agregues explicaciones.
- subtotal, igv y total deben ser SOLO el valor numerico (ejemplo: 1234.56). NUNCA el texto en letras como "mil doscientos".
- Si ves "Son: DOCE MIL..." u otra expresion en letras, ignorala. Usa solo el numero que aparece junto a S/, IGV o TOTAL.
- Para fecha_emision busca el formato dd/mm/yyyy o similar cerca de palabras como Fecha, Emision, Emitido."""

    # Si no hay texto (OCR falló totalmente) → enviar imagen directamente al modelo de visión
    texto_vacio = not texto_factura or not texto_factura.strip()
    if texto_vacio and ruta_archivo:
        ext = os.path.splitext(ruta_archivo)[1].lower()
        mime = "image/jpeg" if ext in {".jpg", ".jpeg"} else "image/png"
        log("Texto OCR vacío — enviando imagen directamente a la IA (modo visión)...")
        with open(ruta_archivo, "rb") as f:
            img_b64 = base64.b64encode(f.read()).decode("utf-8")

        messages_payload = [
            {"role": "system", "content": "Eres un extractor de datos de facturas. Devuelve unicamente JSON valido."},
            {"role": "user", "content": [
                {"type": "text",  "text": prompt_base},
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{img_b64}"}},
            ]},
        ]
        modelo = "openai/gpt-4o-mini"
    else:
        prompt = f"{prompt_base}\n\nFACTURA:\n{texto_factura}"
        messages_payload = [
            {"role": "system", "content": "Eres un extractor de datos de facturas. Devuelve unicamente JSON valido."},
            {"role": "user",   "content": prompt},
        ]
        modelo = "openai/gpt-4o-mini"

    response = requests.post(
        url="https://openrouter.ai/api/v1/chat/completions",
        headers={
            "Authorization": f"Bearer {OPENROUTER_API_KEY}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://localhost",
            "X-Title": "Procesador Automatico Facturas",
        },
        json={
            "model": modelo,
            "messages": messages_payload,
            "temperature": 0,
        },
        timeout=60,
    )

    try:
        resultado = response.json()
    except Exception:
        raise RuntimeError(f"La API no devolvió JSON válido: {response.text}")

    if response.status_code != 200:
        detalle = resultado.get("error", resultado)
        raise RuntimeError(f"Error OpenRouter HTTP {response.status_code}: {detalle}")

    if "choices" not in resultado or not resultado["choices"]:
        raise RuntimeError(f"La respuesta no contiene 'choices': {resultado}")

    texto = resultado["choices"][0]["message"]["content"]
    if isinstance(texto, list):
        partes = []
        for item in texto:
            if isinstance(item, dict) and item.get("type") == "text":
                partes.append(item.get("text", ""))
        texto = "\n".join(partes)

    datos = extraer_json_de_texto(texto)
    log("Datos extraídos por IA OK")
    return datos


def validar_contabilidad(datos):
    observaciones = []

    subtotal = parse_numero(datos.get("subtotal"))
    igv = parse_numero(datos.get("igv"))
    total = parse_numero(datos.get("total"))

    if subtotal is None:
        observaciones.append("Subtotal no numérico o vacío.")
    if igv is None:
        observaciones.append("IGV no numérico o vacío.")
    if total is None:
        observaciones.append("Total no numérico o vacío.")

    if subtotal is not None and igv is not None and total is not None:
        esperado = round(subtotal + igv, 2)
        diferencia = abs(round(total - esperado, 2))
        if diferencia > 0.05:
            observaciones.append(
                f"Inconsistencia contable: subtotal + igv = {esperado:.2f}, pero total = {total:.2f}."
            )

    numero_factura = limpiar_texto(datos.get("numero_factura"))
    ruc_proveedor = limpiar_texto(datos.get("ruc_proveedor"))
    fecha_emision = limpiar_texto(datos.get("fecha_emision"))

    if not numero_factura:
        observaciones.append("Número de factura vacío.")
    if not ruc_proveedor:
        observaciones.append("RUC proveedor vacío.")
    elif not ruc_proveedor.isdigit() or len(ruc_proveedor) != 11:
        observaciones.append("RUC proveedor inválido: debe tener 11 dígitos.")
    if not fecha_emision:
        observaciones.append("Fecha de emisión vacía.")

    if observaciones:
        estado = "OBSERVADA_CONTABLE"
        observacion = " | ".join(observaciones)
    else:
        estado = "PROCESADA"
        observacion = None

    return estado, observacion, observaciones


def guardar_en_mysql(datos, archivo_origen, hash_archivo, estado="PROCESADA", observacion=None):
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
    cursor = conn.cursor()

    json_ia = json.dumps(datos, ensure_ascii=False)

    sql = """INSERT INTO facturas (
        archivo_origen, hash_archivo, numero_factura, fecha_emision, fecha_vencimiento,
        proveedor, ruc_proveedor, cliente,
        subtotal, igv, total, forma_pago, json_ia, estado, observacion
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    valores = (
        archivo_origen,
        hash_archivo,
        datos.get("numero_factura"),
        datos.get("fecha_emision"),
        datos.get("fecha_vencimiento"),
        datos.get("proveedor"),
        datos.get("ruc_proveedor"),
        datos.get("cliente"),
        datos.get("subtotal"),
        datos.get("igv"),
        datos.get("total"),
        datos.get("forma_pago"),
        json_ia,
        estado,
        observacion,
    )
    cursor.execute(sql, valores)
    conn.commit()
    nuevo_id = cursor.lastrowid
    cursor.close()
    conn.close()
    log(f"Guardado en MySQL con ID #{nuevo_id}")
    return nuevo_id


def guardar_error_en_mysql(archivo_origen, hash_archivo, mensaje_error):
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )
    cursor = conn.cursor()

    datos_stub = {
        "numero_factura": "",
        "fecha_emision": "",
        "fecha_vencimiento": "",
        "proveedor": "",
        "ruc_proveedor": "",
        "cliente": "",
        "subtotal": "",
        "igv": "",
        "total": "",
        "forma_pago": "",
        "error": mensaje_error,
    }

    json_ia = json.dumps(datos_stub, ensure_ascii=False)

    sql = """INSERT INTO facturas (
        archivo_origen, hash_archivo, numero_factura, fecha_emision, fecha_vencimiento,
        proveedor, ruc_proveedor, cliente,
        subtotal, igv, total, forma_pago, json_ia, estado, observacion
    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)"""
    valores = (
        archivo_origen,
        hash_archivo,
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        json_ia,
        "ERROR",
        mensaje_error[:255],
    )
    cursor.execute(sql, valores)
    conn.commit()
    nuevo_id = cursor.lastrowid
    cursor.close()
    conn.close()
    log(f"Error registrado en MySQL con ID #{nuevo_id}")
    return nuevo_id


def enviar_telegram(datos, id_registro, archivo_origen, tipo="PROCESADA", detalle_extra=""):
    if tipo == "PROCESADA":
        titulo = "NUEVA FACTURA PROCESADA"
    elif tipo == "DUPLICADA":
        titulo = "FACTURA DUPLICADA DETECTADA"
    elif tipo == "OBSERVADA":
        titulo = "FACTURA OBSERVADA CONTABLEMENTE"
    else:
        titulo = "ERROR PROCESANDO FACTURA"

    mensaje = (
        f"{titulo}\n"
        "========================\n"
        f"Archivo: {archivo_origen}\n"
        f"N: {datos.get('numero_factura')}\n"
        f"Proveedor: {datos.get('proveedor')}\n"
        f"RUC: {datos.get('ruc_proveedor')}\n"
        f"Cliente: {datos.get('cliente')}\n"
        f"Emision: {datos.get('fecha_emision')}\n"
        f"Vence: {datos.get('fecha_vencimiento')}\n"
        f"Subtotal: {datos.get('subtotal')}\n"
        f"IGV: {datos.get('igv')}\n"
        f"TOTAL: {datos.get('total')}\n"
        f"Pago: {datos.get('forma_pago')}\n"
        f"ID MySQL: {id_registro}\n"
        f"Fecha: {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}\n"
    )
    if detalle_extra:
        mensaje += f"Detalle: {detalle_extra}\n"

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": mensaje}, timeout=30)
    if r.status_code != 200:
        raise RuntimeError(f"ERROR Telegram HTTP {r.status_code}: {r.text}")


def mover_archivo(ruta_origen, carpeta_destino):
    nombre = os.path.basename(ruta_origen)
    marca = datetime.now().strftime("%Y%m%d_%H%M%S")
    destino = os.path.join(carpeta_destino, f"{marca}_{nombre}")
    shutil.move(ruta_origen, destino)
    return destino


def obtener_texto_archivo(ruta_archivo):
    ext = os.path.splitext(ruta_archivo)[1].lower()

    if ext == ".pdf":
        return extraer_texto_pdf(ruta_archivo)
    if ext in {".jpg", ".jpeg", ".png"}:
        return extraer_texto_imagen(ruta_archivo)

    raise RuntimeError(f"Extensión no soportada: {ext}")


def procesar_archivo(ruta_archivo):
    nombre = os.path.basename(ruta_archivo)
    log("=" * 70)
    log(f"Procesando archivo: {nombre}")

    hash_archivo = calcular_hash_archivo(ruta_archivo)
    log(f"Hash archivo: {hash_archivo}")

    duplicado_hash = buscar_duplicado_por_hash(hash_archivo)
    if duplicado_hash:
        detalle = f"Duplicado exacto por hash. Ya existe ID #{duplicado_hash['id']} ({duplicado_hash['archivo_origen']})."
        log(detalle)

        datos_stub = {
            "numero_factura": duplicado_hash.get("numero_factura", ""),
            "fecha_emision": "",
            "fecha_vencimiento": "",
            "proveedor": "",
            "ruc_proveedor": duplicado_hash.get("ruc_proveedor", ""),
            "cliente": "",
            "subtotal": "",
            "igv": "",
            "total": "",
            "forma_pago": ""
        }

        id_registro = guardar_en_mysql(
            datos_stub, nombre, hash_archivo,
            estado="DUPLICADO_HASH",
            observacion=detalle
        )
        enviar_telegram(datos_stub, id_registro, nombre, tipo="DUPLICADA", detalle_extra=detalle)
        destino = mover_archivo(ruta_archivo, DUPLICADOS_DIR)
        log(f"Archivo duplicado movido a: {destino}")
        return "duplicado"

    texto = obtener_texto_archivo(ruta_archivo)

    # ── FLUJO CASCADA: OCR primero, IA solo si OCR no es suficiente ──────────
    datos = None
    if ocr_extrajo_datos_suficientes(texto):
        datos = extraer_datos_con_ocr(texto)
        if datos is None:
            log("OCR no pudo estructurar los campos clave. Escalando a IA...")

    if datos is None:
        log("Llamando a IA para extraer datos...")
        datos = extraer_datos_con_ia(texto, ruta_archivo)
    # ─────────────────────────────────────────────────────────────────────────

    numero_factura = str(datos.get("numero_factura", "")).strip()
    ruc_proveedor = str(datos.get("ruc_proveedor", "")).strip()

    duplicado_logico = buscar_duplicado_logico(numero_factura, ruc_proveedor)
    if duplicado_logico:
        detalle = (
            f"Duplicado lógico por número de factura + RUC. "
            f"Ya existe ID #{duplicado_logico['id']} ({duplicado_logico['archivo_origen']})."
        )
        log(detalle)

        id_registro = guardar_en_mysql(
            datos, nombre, hash_archivo,
            estado="DUPLICADO_LOGICO",
            observacion=detalle
        )
        enviar_telegram(datos, id_registro, nombre, tipo="DUPLICADA", detalle_extra=detalle)
        destino = mover_archivo(ruta_archivo, DUPLICADOS_DIR)
        log(f"Archivo duplicado movido a: {destino}")
        return "duplicado"

    estado_contable, observacion_contable, _ = validar_contabilidad(datos)
    log(f"Validación contable: {estado_contable}")

    nuevo_id = guardar_en_mysql(
        datos,
        nombre,
        hash_archivo,
        estado=estado_contable,
        observacion=observacion_contable
    )

    if estado_contable == "OBSERVADA_CONTABLE":
        enviar_telegram(datos, nuevo_id, nombre, tipo="OBSERVADA", detalle_extra=observacion_contable)
        destino = mover_archivo(ruta_archivo, OBSERVADAS_DIR)
        log(f"Archivo movido a observadas: {destino}")
        return "observada"

    enviar_telegram(datos, nuevo_id, nombre, tipo="PROCESADA")
    destino = mover_archivo(ruta_archivo, PROCESADAS_DIR)
    log(f"Archivo movido a procesadas: {destino}")
    return "procesado"


def listar_archivos_input():
    archivos = []
    for nombre in os.listdir(INPUT_DIR):
        ruta = os.path.join(INPUT_DIR, nombre)
        if os.path.isfile(ruta):
            ext = os.path.splitext(nombre)[1].lower()
            if ext in EXTENSIONES_SOPORTADAS:
                archivos.append(ruta)
    return archivos


def procesar_carpeta_una_vez():
    archivos = listar_archivos_input()

    if not archivos:
        log("No hay archivos nuevos en input.")
        return

    procesados = 0
    duplicados = 0
    observadas = 0
    errores = 0

    for ruta in archivos:
        nombre = os.path.basename(ruta)
        hash_archivo = ""
        try:
            try:
                hash_archivo = calcular_hash_archivo(ruta)
            except Exception:
                hash_archivo = ""
            resultado = procesar_archivo(ruta)
            if resultado == "duplicado":
                duplicados += 1
            elif resultado == "observada":
                observadas += 1
            else:
                procesados += 1
        except Exception as e:
            errores += 1
            mensaje_error = str(e)
            log(f"ERROR procesando {nombre}: {mensaje_error}")
            try:
                id_error = guardar_error_en_mysql(nombre, hash_archivo, mensaje_error)
                datos_error = {
                    "numero_factura": "",
                    "fecha_emision": "",
                    "fecha_vencimiento": "",
                    "proveedor": "",
                    "ruc_proveedor": "",
                    "cliente": "",
                    "subtotal": "",
                    "igv": "",
                    "total": "",
                    "forma_pago": ""
                }
                enviar_telegram(datos_error, id_error, nombre, tipo="ERROR", detalle_extra=mensaje_error)
            except Exception as e_db:
                log(f"No se pudo registrar el error en MySQL/Telegram: {e_db}")

            try:
                destino = mover_archivo(ruta, ERROR_DIR)
                log(f"Archivo movido a error: {destino}")
            except Exception as e2:
                log(f"No se pudo mover a carpeta error: {e2}")

    log(
        f"Ciclo finalizado -> Procesados: {procesados} | Observadas: {observadas} | "
        f"Duplicados: {duplicados} | Errores: {errores}"
    )


def ejecutar_modo_automatico():
    log("=" * 70)
    log("MODO AUTOMATICO ACTIVADO")
    log(f"Monitoreando carpeta: {INPUT_DIR}")
    log(f"Intervalo de revisión: {PROCESS_INTERVAL_SECONDS} segundos")
    log("Presiona Ctrl + C para detener el proceso.")
    log("=" * 70)

    while True:
        try:
            procesar_carpeta_una_vez()
        except Exception as e:
            log(f"ERROR general del ciclo: {e}")

        time.sleep(PROCESS_INTERVAL_SECONDS)


if __name__ == "__main__":
    print("=" * 70)
    print("PROCESADOR AUTOMATICO DE FACTURAS")
    print("IA + OCR + DUPLICADOS + AUDITORIA + VALIDACION CONTABLE")
    print("=" * 70)

    asegurar_carpetas()
    validar_configuracion()
    crear_base_de_datos()

    try:
        ejecutar_modo_automatico()
    except KeyboardInterrupt:
        print("\nProceso detenido por el usuario.")
