import os
import time
import imaplib
import email
from email.header import decode_header
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

EMAIL_IMAP_HOST = os.getenv("EMAIL_IMAP_HOST", "imap.gmail.com").strip()
EMAIL_IMAP_PORT = int(os.getenv("EMAIL_IMAP_PORT", "993"))
EMAIL_USER = os.getenv("EMAIL_USER", "").strip()
EMAIL_PASS = os.getenv("EMAIL_PASS", "").strip()
EMAIL_FOLDER = os.getenv("EMAIL_FOLDER", "INBOX").strip()
EMAIL_CHECK_INTERVAL_SECONDS = int(os.getenv("EMAIL_CHECK_INTERVAL_SECONDS", "30"))

BASE_DIR = Path(__file__).resolve().parent
INPUT_DIR = BASE_DIR / "input"
LOGS_DIR = BASE_DIR / "logs"

ALLOWED_EXTENSIONS = {".pdf", ".jpg", ".jpeg", ".png"}


def asegurar_carpetas():
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    LOGS_DIR.mkdir(parents=True, exist_ok=True)


def log(msg: str):
    marca = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{marca}] {msg}")


def decodificar_texto(valor):
    if not valor:
        return ""
    partes = decode_header(valor)
    texto_final = []
    for parte, encoding in partes:
        if isinstance(parte, bytes):
            texto_final.append(parte.decode(encoding or "utf-8", errors="ignore"))
        else:
            texto_final.append(str(parte))
    return "".join(texto_final).strip()


def nombre_archivo_unico(carpeta: Path, nombre: str) -> Path:
    destino = carpeta / nombre
    if not destino.exists():
        return destino

    stem = destino.stem
    suffix = destino.suffix
    contador = 1
    while True:
        candidato = carpeta / f"{stem}_{contador}{suffix}"
        if not candidato.exists():
            return candidato
        contador += 1


def extension_permitida(nombre_archivo: str) -> bool:
    return Path(nombre_archivo).suffix.lower() in ALLOWED_EXTENSIONS


def validar_configuracion():
    faltantes = []
    if not EMAIL_USER:
        faltantes.append("EMAIL_USER")
    if not EMAIL_PASS:
        faltantes.append("EMAIL_PASS")
    if not EMAIL_IMAP_HOST:
        faltantes.append("EMAIL_IMAP_HOST")

    if faltantes:
        raise RuntimeError("Faltan variables para correo en .env: " + ", ".join(faltantes))

    log("Configuración de correo OK")
    log(f"Servidor IMAP: {EMAIL_IMAP_HOST}:{EMAIL_IMAP_PORT}")
    log(f"Buzón: {EMAIL_FOLDER}")
    log(f"Intervalo revisión: {EMAIL_CHECK_INTERVAL_SECONDS} segundos")
    log(f"Carpeta input: {INPUT_DIR}")


def conectar_imap():
    mail = imaplib.IMAP4_SSL(EMAIL_IMAP_HOST, EMAIL_IMAP_PORT)
    mail.login(EMAIL_USER, EMAIL_PASS)
    return mail


def descargar_adjuntos_no_leidos():
    descargados = 0

    mail = conectar_imap()
    try:
        status, _ = mail.select(EMAIL_FOLDER)
        if status != "OK":
            raise RuntimeError(f"No se pudo abrir el buzón {EMAIL_FOLDER}")

        status, data = mail.search(None, "UNSEEN")
        if status != "OK":
            raise RuntimeError("No se pudieron buscar correos no leídos")

        ids = data[0].split()

        if not ids:
            log("No hay correos nuevos con adjuntos.")
            return 0

        log(f"Correos no leídos encontrados: {len(ids)}")

        for correo_id in ids:
            status, msg_data = mail.fetch(correo_id, "(RFC822)")
            if status != "OK":
                log(f"No se pudo leer el correo ID {correo_id.decode()}")
                continue

            raw_email = msg_data[0][1]
            mensaje = email.message_from_bytes(raw_email)

            asunto = decodificar_texto(mensaje.get("Subject", ""))
            remitente = decodificar_texto(mensaje.get("From", ""))

            log("-" * 70)
            log(f"Procesando correo -> Asunto: {asunto}")
            log(f"Remitente: {remitente}")

            tuvo_adjunto = False

            for part in mensaje.walk():
                content_disposition = str(part.get("Content-Disposition", ""))
                if "attachment" not in content_disposition.lower():
                    continue

                nombre = part.get_filename()
                nombre = decodificar_texto(nombre)

                if not nombre:
                    continue

                if not extension_permitida(nombre):
                    log(f"Adjunto omitido por extensión no permitida: {nombre}")
                    continue

                tuvo_adjunto = True
                ruta_destino = nombre_archivo_unico(INPUT_DIR, nombre)

                with open(ruta_destino, "wb") as f:
                    f.write(part.get_payload(decode=True))

                descargados += 1
                log(f"Adjunto guardado en input: {ruta_destino}")

            mail.store(correo_id, "+FLAGS", "\Seen")

            if not tuvo_adjunto:
                log("El correo no tenía adjuntos válidos para el sistema.")

        return descargados

    finally:
        try:
            mail.close()
        except Exception:
            pass
        mail.logout()


def ejecutar_modo_automatico():
    log("=" * 70)
    log("DESCARGADOR AUTOMATICO DE ADJUNTOS DE CORREO")
    log("Los adjuntos válidos irán a la carpeta input/")
    log("Presiona Ctrl + C para detener.")
    log("=" * 70)

    while True:
        try:
            total = descargar_adjuntos_no_leidos()
            log(f"Ciclo finalizado. Adjuntos descargados: {total}")
        except Exception as e:
            log(f"ERROR en ciclo de correo: {e}")

        time.sleep(EMAIL_CHECK_INTERVAL_SECONDS)


if __name__ == "__main__":
    asegurar_carpetas()
    validar_configuracion()

    try:
        ejecutar_modo_automatico()
    except KeyboardInterrupt:
        print("\nProceso detenido por el usuario.")
