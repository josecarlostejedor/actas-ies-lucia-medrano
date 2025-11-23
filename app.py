import streamlit as st
import subprocess
import sys
import time

# --- BLOQUE DE AUTO-INSTALACIÓN ---
def instalar(package):
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
    except:
        pass 

try:
    import openai
    from docx import Document
    from fpdf import FPDF
    # Verificamos versión de streamlit
    ver = st.__version__.split('.')
    if int(ver[0]) < 1 or (int(ver[0]) == 1 and int(ver[1]) < 40):
        raise ImportError("Versión vieja")

except ImportError:
    st.warning("Actualizando sistema... espera un momento.")
    instalar("streamlit>=1.40.0")
    instalar("openai")
    instalar("python-docx")
    instalar("fpdf")
    st.rerun() 

import openai
from docx import Document
from docx.shared import Pt
from docx.enum.text import WD_ALIGN_PARAGRAPH
from datetime import date
import io

# --- CONFIGURACIÓN DE PÁGINA ---
st.set_page_config(page_title="Actas EF - IES Lucía de Medrano", page_icon="📝")

# --- GESTIÓN DE MEMORIA (SESSION STATE) ---
# Aquí guardamos las grabaciones para que no se borren al recargar
if 'grabaciones_guardadas' not in st.session_state:
    st.session_state.grabaciones_guardadas = []
if 'contador_micro' not in st.session_state:
    st.session_state.contador_micro = 0

# --- FUNCIONES DE LÓGICA ---
def transcribir_audio(audio_file, api_key):
    client = openai.OpenAI(api_key=api_key)
    # Importante: Resetear el puntero del archivo al inicio
    audio_file.seek(0)
    # Intentamos detectar si tiene atributo name, si no (grabacion) inventamos uno
    nombre = getattr(audio_file, 'name', 'grabacion.wav')
    
    transcript = client.audio.transcriptions.create(
        model="whisper-1", 
        file=(nombre, audio_file), # Pasamos tupla (nombre, bytes) para asegurar compatibilidad
        language="es"
    )
    return transcript.text

def generar_contenido_acta(transcripcion_completa, fecha, api_key):
    client = openai.OpenAI(api_key=api_key)
    
    prompt_sistema = f"""
    Eres el secretario experto del Departamento de Educación Física del IES Lucía de Medrano.
    Tu tarea es convertir una transcripción de reunión (que puede venir de varios audios unidos) en un ACTA FORMAL.
    
    REGLAS DE REDACCIÓN:
    1. Estilo general: Impersonal, formal y administrativo.
    2. EXCEPCIÓN CRÍTICA: Si en el texto alguien dice explícitamente "que conste en acta" o similar, transcribe EXACTAMENTE lo que dice a continuación y atribúyelo a la persona: "D. [Nombre] manifestó lo siguiente: [Cita textual]".
    3. ASISTENTES: Si se menciona que alguien faltó, extráelo. Si no, asume que están todos.
    
    ESTRUCTURA DE TU RESPUESTA (Solo devuelve el contenido del cuerpo y ausencias):
    - Primero: "AUSENCIAS: [Nombres]" o "AUSENCIAS: Ninguna".
    - Segundo: Redacta los puntos tratados en párrafos numerados.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"La reunión fue el {fecha}. Transcripción completa: {transcripcion_completa}"}
        ]
    )
    return response.choices[0].message.content

def crear_documento_word(contenido_ai, fecha):
    doc = Document()
    style = doc.styles['Normal']
    font = style.font
    font.name = 'Arial'
    font.size = Pt(11)

    # Encabezado
    header = doc.add_paragraph()
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    run = header.add_run("Acta del Departamento de Educación Física del IES Lucía de Medrano")
    run.bold = True
    run.font.size = Pt(14)
    doc.add_paragraph("") 

    # Fecha
    p_fecha = doc.add_paragraph()
    p_fecha.add_run("Fecha de la sesión: ").bold = True
    p_fecha.add_run(str(fecha))

    # Procesar texto
    lineas = contenido_ai.split('\n')
    texto_cuerpo = ""
    texto_asistentes = "Todos los componentes del Departamento de EF"
    
    for linea in lineas:
        if "AUSENCIAS:" in linea:
            if "Ninguna" not in linea:
                ausentes = linea.replace("AUSENCIAS:", "").strip()
                texto_asistentes += f", excepto {ausentes}"
        else:
            texto_cuerpo += linea + "\n"

    # Asistentes
    p_asist = doc.add_paragraph()
    p_asist.add_run("Asistentes: ").bold = True
    p_asist.add_run(texto_asistentes)
    doc.add_paragraph("") 
    
    # Cuerpo
    doc.add_heading('Desarrollo de la sesión:', level=2)
    doc.add_paragraph(texto_cuerpo.strip())
    doc.add_paragraph("") 

    # Cierre y Firma
    p_cierre = doc.add_paragraph()
    p_cierre.add_run("Y para que conste en acta y surta los efectos oportunos donde proceda firmo la siguiente.\n")
    p_cierre.add_run(f"En Salamanca a {fecha}")
    doc.add_paragraph("") 
    doc.add_paragraph("") 
    
    p_firma = doc.add_paragraph("EL JEFE DEL DEPARTAMENTO DE EDUCACIÓN FÍSICA")
    p_firma.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_firma.runs[0].bold = True

    bio = io.BytesIO()
    doc.save(bio)
    return bio

# --- INTERFAZ VISUAL ---
st.title("📝 Generador de Actas - Dpto. Educación Física")
st.markdown("**IES Lucía de Medrano**")

# 1. API KEY
with st.expander("🔐 Configuración", expanded=not st.session_state.get('api_ok', False)):
    api_key = st.text_input("Introduce tu API Key de OpenAI:", type="password")
    if api_key: st.session_state['api_ok'] = True

st.divider()
fecha_sesion = st.date_input("📅 Fecha de la sesión", date.today())

# 2. ZONA DE CARGA (PESTAÑAS)
st.write("### 🎙️ Gestión de Audios")
st.info("Puedes combinar archivos subidos y múltiples grabaciones. Se procesarán en el orden que aparecen abajo.")

tab1, tab2 = st.tabs(["📂 1. Subir Archivos", "🎤 2. Grabar (Multi-toma)"])

# --- PESTAÑA 1: ARCHIVOS ---
with tab1:
    archivos_subidos = st.file_uploader(
        "Arrastra archivos aquí", 
        type=["mp3", "m4a", "wav"], 
        accept_multiple_files=True
    )

# --- PESTAÑA 2: GRABADORA CON MEMORIA ---
with tab2:
    st.write("Graba tus intervenciones una a una. Al terminar una, pulsa 'Guardar' para archivarla y grabar la siguiente.")
    
    # Usamos una key dinámica para resetear el widget después de guardar
    key_micro = f"micro_input_{st.session_state.contador_micro}"
    audio_temporal = st.audio_input("Microfono", key=key_micro)

    if audio_temporal is not None:
        st.success("✅ Audio capturado")
        col_a, col_b = st.columns(2)
        with col_a:
            st.audio(audio_temporal)
        with col_b:
            if st.button("💾 GUARDAR ESTA GRABACIÓN Y LIMPIAR", type="primary"):
                # Guardamos en la lista de sesión
                timestamp = date.today().strftime("%H:%M:%S")
                audio_temporal.name = f"Grabación en directo {timestamp}"
                st.session_state.grabaciones_guardadas.append(audio_temporal)
                
                # Incrementamos contador para forzar que el widget del micro se reinicie
                st.session_state.contador_micro += 1
                st.rerun()

# 3. RESUMEN DE AUDIOS (LISTA TOTAL)
st.divider()
st.subheader("🎧 Audios listos para procesar")

lista_total = []
# Primero añadimos los subidos
if archivos_subidos:
    lista_total.extend(archivos_subidos)
# Después añadimos los grabados
lista_total.extend(st.session_state.grabaciones_guardadas)

count = len(lista_total)

if count == 0:
    st.markdown("*La lista está vacía.*")
else:
    for i, audio in enumerate(lista_total):
        # Intentamos obtener nombre, si no tiene usamos uno genérico
        nombre_audio = getattr(audio, 'name', f"Audio {i+1}")
        st.text(f"{i+1}. {nombre_audio} ({len(audio.getvalue())/1024:.1f} KB)")
    
    # Botón para limpiar grabaciones si te equivocas
    if st.session_state.grabaciones_guardadas:
        if st.button("🗑️ Borrar grabaciones del micro"):
            st.session_state.grabaciones_guardadas = []
            st.rerun()

# 4. FINALIZAR
st.divider()
boton_finalizar = st.button(
    f"✅ PROCESAR {count} AUDIOS Y GENERAR ACTA", 
    type="primary", 
    use_container_width=True,
    disabled=(count == 0)
)

if boton_finalizar:
    if not api_key:
        st.error("⚠️ Falta la API Key.")
    elif count > 20:
        st.error(f"⚠️ Has superado el límite de 20 archivos (Tienes {count}).")
    else:
        transcripcion_total = ""
        barra = st.progress(0, text="Iniciando...")
        
        try:
            for i, archivo in enumerate(lista_total):
                barra.progress((i / count) * 0.8, text=f"Transcribiendo audio {i+1}/{count}...")
                texto = transcribir_audio(archivo, api_key)
                transcripcion_total += f"\n--- Audio {i+1} ---\n{texto}\n"
            
            barra.progress(0.85, text="Redactando acta oficial...")
            contenido_acta = generar_contenido_acta(transcripcion_total, fecha_sesion, api_key)
            
            barra.progress(0.95, text="Creando Word...")
            doc_final = crear_documento_word(contenido_acta, fecha_sesion)
            
            barra.progress(1.0, text="¡Hecho!")
            st.balloons()
            st.success("🎉 Acta generada.")
            
            st.download_button(
                label="📥 DESCARGAR ACTA (.DOCX)",
                data=doc_final.getvalue(),
                file_name=f"Acta_EF_{fecha_sesion}.docx",
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                type="primary"
            )
            
        except Exception as e:
            st.error(f"Error: {str(e)}")
