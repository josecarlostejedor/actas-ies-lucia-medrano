import streamlit as st
import subprocess
import sys

# --- BLOQUE DE AUTO-INSTALACIÓN DE EMERGENCIA ---
# Esto instalará las librerías si el servidor no las encuentra
def instalar(package):
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])

try:
    import openai
    from docx import Document
    from fpdf import FPDF
except ImportError:
    st.warning("Instalando librerías necesarias... espera unos segundos y recarga la página si es necesario.")
    instalar("openai")
    instalar("python-docx")
    instalar("fpdf")
    import openai
    from docx import Document
    from fpdf import FPDF
# ------------------------------------------------

from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import date
import io

# --- CONFIGURACIÓN ---
api_key = st.text_input("Introduce tu API Key de OpenAI:", type="password")

def transcribir_audio(audio_file, api_key):
    client = openai.OpenAI(api_key=api_key)
    transcript = client.audio.transcriptions.create(
        model="whisper-1", 
        file=audio_file,
        language="es"
    )
    return transcript.text

def generar_contenido_acta(transcripcion, fecha, api_key):
    client = openai.OpenAI(api_key=api_key)
    
    prompt_sistema = f"""
    Eres el secretario experto del Departamento de Educación Física del IES Lucía de Medrano.
    Tu tarea es convertir una transcripción de reunión en un ACTA FORMAL.
    
    REGLAS DE REDACCIÓN:
    1. Estilo general: Impersonal, formal y administrativo (ej: "Se debatió sobre...", "Se acordó realizar...").
    2. EXCEPCIÓN CRÍTICA: Si en el texto alguien dice explícitamente "que conste en acta" o similar, debes transcribir EXACTAMENTE lo que dice a continuación y atribuirlo a la persona, usando el formato: "D. [Nombre] manifestó lo siguiente: [Cita textual]".
    3. ASISTENTES: Analiza el texto. Si se menciona que alguien faltó, extráelo. Si no se menciona ninguna ausencia, asume que están todos.
    
    ESTRUCTURA DE TU RESPUESTA (Solo devuelve el contenido del cuerpo y la lista de ausentes si la hay, no saludes):
    - Primero: Indica si hubo ausencias con el formato "AUSENCIAS: [Nombres]" o "AUSENCIAS: Ninguna".
    - Segundo: Redacta los puntos tratados en párrafos numerados o viñetas claras.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"La reunión fue el {fecha}. Aquí tienes la transcripción: {transcripcion}"}
        ]
    )
    return response.choices[0].message.content

def crear_documento_word(contenido_ai, fecha):
    doc = Document()
    
    # Estilos
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(11)

    # 1. Encabezado
    header = doc.add_paragraph()
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = header.add_run("Acta del Departamento de Educación Física del IES Lucía de Medrano")
    run.bold = True
    run.font.size = Pt(14)
    
    doc.add_paragraph("") # Espacio

    # 2. Fecha
    p_fecha = doc.add_paragraph()
    p_fecha.add_run("Fecha de la sesión: ").bold = True
    p_fecha.add_run(str(fecha))

    # Procesar respuesta de la IA para separar Ausencias del Cuerpo
    lineas = contenido_ai.split('\n')
    texto_cuerpo = ""
    texto_asistentes = "Todos los componentes del Departamento de EF"
    
    modo_cuerpo = False
    for linea in lineas:
        if "AUSENCIAS:" in linea:
            if "Ninguna" not in linea:
                ausentes = linea.replace("AUSENCIAS:", "").strip()
                texto_asistentes += f", excepto {ausentes}"
        else:
            texto_cuerpo += linea + "\n"

    # 3. Asistentes
    p_asist = doc.add_paragraph()
    p_asist.add_run("Asistentes: ").bold = True
    p_asist.add_run(texto_asistentes)
    
    doc.add_paragraph("") # Espacio
    
    # 4. Cuerpo del Acta
    doc.add_heading('Desarrollo de la sesión:', level=2)
    doc.add_paragraph(texto_cuerpo.strip())

    doc.add_paragraph("") # Espacio grande
    doc.add_paragraph("") 

    # 5. Cierre y Firma
    p_cierre = doc.add_paragraph()
    p_cierre.add_run("Y para que conste en acta y surta los efectos oportunos donde proceda firmo la siguiente.\n")
    p_cierre.add_run(f"En Salamanca a {fecha}")
    
    doc.add_paragraph("") 
    doc.add_paragraph("") 
    
    p_firma = doc.add_paragraph("EL JEFE DEL DEPARTAMENTO DE EDUCACIÓN FÍSICA")
    p_firma.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_firma.runs[0].bold = True

    # Guardar en memoria
    bio = io.BytesIO()
    doc.save(bio)
    return bio

# --- INTERFAZ DE USUARIO ---
st.title("📝 Generador de Actas - Dpto. Educación Física")
st.subheader("IES Lucía de Medrano")

fecha_sesion = st.date_input("Fecha de la sesión", date.today())
archivo_audio = st.file_uploader("Sube la grabación de la reunión", type=["mp3", "m4a", "wav"])

if st.button("Generar Acta") and archivo_audio and api_key:
    with st.spinner("Escuchando y transcribiendo la reunión..."):
        transcripcion = transcribir_audio(archivo_audio, api_key)
        st.success("Audio transcrito correctamente.")
        
    with st.spinner("Redactando el acta y detectando intervenciones formales..."):
        contenido = generar_contenido_acta(transcripcion, fecha_sesion, api_key)
        
    # Generar Word
    doc_file = crear_documento_word(contenido, fecha_sesion)
    
    st.write("### Vista previa del contenido procesado:")
    st.write(contenido)
    
    st.download_button(
        label="📥 Descargar Acta en Word (.docx)",
        data=doc_file.getvalue(),
        file_name=f"Acta_EF_{fecha_sesion}.docx",
        mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    
    st.info("Nota: Puedes guardar el archivo Word como PDF directamente desde Microsoft Word.")

elif not api_key:
    st.warning("Por favor, introduce tu API Key para comenzar.")
