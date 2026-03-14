# AI Invoice Processor (OCR + LLM + Automation)

Sistema automático para procesamiento inteligente de facturas usando:

- OCR (Tesseract)
- IA Generativa (LLM vía OpenRouter)
- Python
- MySQL
- Dashboard en Streamlit
- Automatización por correo electrónico
- Detección de duplicados por hash y lógica contable
- Validaciones contables automáticas
- Alertas por Telegram

---

# Arquitectura

1. Correos con facturas llegan al buzón Gmail
2. Script descarga adjuntos automáticamente
3. Archivos se guardan en carpeta `input`
4. Procesador aplica:
   - OCR para extraer texto
   - IA para estructurar datos
   - Validación contable
   - Detección de duplicados
5. Datos se guardan en MySQL
6. Dashboard muestra resultados en tiempo real
7. Notificaciones enviadas por Telegram

---

# Tecnologías

- Python
- Tesseract OCR
- OpenRouter LLM API
- MySQL
- Streamlit
- IMAP Email Automation
- Telegram Bot API

---

# IA utilizada

### Document AI
Extracción automática de datos estructurados desde facturas.

### OCR (Computer Vision)
Uso de Tesseract para convertir imágenes/PDF en texto.

### LLM (Large Language Models)
Uso de modelos GPT a través de OpenRouter para interpretar y estructurar la información.

### Automatización inteligente
Pipeline automático para procesamiento de documentos.

---

# Ejecución

Instalar dependencias

pip install -r requirements.txt

Ejecutar procesador automático

python procesador_facturas_automatico_validacion_contable.py

Ejecutar dashboard

streamlit run dashboard_facturas_tiempo_real.py

---

# Autor

Carlos Vilcatoma  
Consultor TI — Transformación Digital & IA