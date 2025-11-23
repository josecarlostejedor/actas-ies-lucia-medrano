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

# --- GESTIÓN DE MEMORIA ---
if 'grabaciones_guardadas' not in st.session_state:
    st.session_state.grabaciones_guardadas = []
if 'contador_micro' not in st.session_state:
    st.session_state.contador_micro = 0
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- FUNCIONES DE LÓGICA ---
def transcribir_audio(audio_file, api_key):
    client = openai.OpenAI(api_key=api_key)
    audio_file.seek(0)
    
    if hasattr(audio_file, 'name') and audio_file.name:
        nombre_archivo = audio_file.name
    else:
        nombre_archivo = "audio_ipad.wav"

    transcript = client.audio.transcriptions.create(
        model="whisper-1", 
        file=(nombre_archivo, audio_file),
        language="es"
    )
    return transcript.text

def generar_contenido_acta(transcripcion_completa, fecha, api_key):
    client = openai.OpenAI(api_key=api_key)
    
    # --- AQUÍ ESTÁ EL CAMBIO CLAVE: PROMPT EXHAUSTIVO ---
    prompt_sistema = f"""
    Eres el secretario del Departamento de Educación Física del IES Lucía de Medrano.
    Tu tarea es redactar un ACTA DE REUNIÓN EXHAUSTIVA Y FIEL A LA REALIDAD.
    
    INSTRUCCIONES DE REDACCIÓN (IMPORTANTE):
    1. NO HAGAS UN RESUMEN CORTO. Necesito un registro detallado de todo lo hablado.
    2. Cuando se narren hechos generales o acuerdos conjuntos, usa estilo impersonal ("Se debatió sobre...", "Se procedió a...").
    3. INTERVENCIONES PERSONALES (CRÍTICO): Cuando una persona concreta intervenga o dé una opinión, DEBES TRANSCRIBIR SUS PALABRAS TEXTUALMENTE (o lo más fielmente posible) y ponerlas entre comillas.
       - Formato: D./Dña. [Nombre] manifestó: "[Sus palabras exactas]".
       - No simplifiques sus argumentos. Si alguien se queja o argumenta extensamente, refléjalo todo.
    4. "QUE CONSTE EN ACTA": Si alguien usa esta frase explícita, dale máxima prioridad y exactitud literal.
    5. Solo elimina: Repeticiones exactas (tartamudeos), saludos triviales ("hola, qué tal") o ruidos. El resto del contenido DEBE aparecer.
    
    ESTRUCTURA DE SALIDA:
    - Primero: "AUSENCIAS: [Nombres]" o "AUSENCIAS: Ninguna". (Deducir del contexto).
    - Segundo: Desarrollo de la sesión (No uses viñetas simples, usa párrafos completos y detallados, citando a los intervinientes).
    """

    response = client.chat.completions.create(
        model="gpt-4o", # Usamos el modelo más potente para captar matices
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"Fecha de la reunión: {fecha}. Aquí tienes la transcripción bruta completa:\n\n{transcripcion_completa}"}
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

    # Cierre
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

# 2. ZONA DE CARGA
st.write("### 🎙️ Gestión de Audios")
st.caption("Modo Exhaustivo: Se transcribirán literalmente las intervenciones personales.")

tab1, tab2 = st.tabs(["📂 1. Subir Archivos", "🎤 2. Grabar (Multi-toma)"])

with tab1:
    key_dinamica = f"uploader_{st.session_state.uploader_key}"
    archivos_subidos = st.file_uploader(
        "Arrastra archivos aquí", 
        type=["mp3", "m4a", "wav"], 
        accept_multiple_files=True,
        key=key_dinamica
    )

with tab2:
    st.write("Graba y pulsa 'Guardar'.")
    key_micro = f"micro_input_{st.session_state.contador_micro}"
    audio_temporal = st.audio_input("Microfono", key=key_micro)

    if audio_temporal is not None:
        st.success("✅ Audio capturado")
        col_a, col_b = st.columns(2)
        with col_a:
            st.audio(audio_temporal)
        with col_b:
            if st.button("💾 GUARDAR Y LIMPIAR", type="primary"):
                timestamp = date.today().strftime("%H-%M-%S")
                audio_temporal.name = f"Grabacion_directo_{timestamp}.wav"
                st.session_state.grabaciones_guardadas.append(audio_temporal)
                st.session_state.contador_micro += 1
                st.rerun()

# 3. RESUMEN
st.divider()
st.subheader("🎧 Audios listos para procesar")

lista_total = []
if archivos_subidos:
    lista_total.extend(archivos_subidos)
lista_total.extend(st.session_state.grabaciones_guardadas)

count = len(lista_total)

if count == 0:
    st.markdown("*La lista está vacía.*")
else:
    for i, audio in enumerate(lista_total):
        nombre = getattr(audio, 'name', f"Audio {i+1}.wav")
        st.text(f"{i+1}. {nombre}")

# 4. GENERAR ACTA
st.divider()
boton_finalizar = st.button(
    f"✅ PROCESAR {count} AUDIOS Y GENERAR ACTA DETALLADA", 
    type="primary", 
    use_container_width=True,
    disabled=(count == 0)
)

if boton_finalizar:
    if not api_key:
        st.error("⚠️ Falta la API Key.")
    elif count > 20:
        st.error(f"⚠️ Has superado el límite de 20 archivos.")
    else:
        transcripcion_total = ""
        barra = st.progress(0, text="Iniciando...")
        try:
            # Fase 1: Transcripción
            for i, archivo in enumerate(lista_total):
                barra.progress((i / count) * 0.7, text=f"Transcribiendo audio {i+1}/{count}...")
                try:
                    texto = transcribir_audio(archivo, api_key)
                    transcripcion_total += f"\n--- Audio {i+1} ---\n{texto}\n"
                except Exception as e:
                    st.error(f"Error en audio {i+1}: {e}")
            
            if transcripcion_total.strip():
                # Fase 2: Redacción Exhaustiva
                barra.progress(0.75, text="Analizando intervenciones y redactando al detalle (esto puede tardar un poco más)...")
                contenido = generar_contenido_acta(transcripcion_total, fecha_sesion, api_key)
                
                # Fase 3: Documento
                barra.progress(0.95, text="Maquetando documento Word...")
                doc = crear_documento_word(contenido, fecha_sesion)
                
                barra.progress(1.0, text="¡Finalizado!")
                st.balloons()
                
                st.success("🎉 Acta detallada generada.")
                st.download_button(
                    label="📥 DESCARGAR WORD (.DOCX)",
                    data=doc.getvalue(),
                    file_name=f"Acta_EF_{fecha_sesion}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary"
                )
            else:
                st.error("No se detectó voz en los archivos.")
        except Exception as e:
            st.error(f"Error: {e}")

# 5. BORRADO
st.write("---")
st.write("### 🗑️ Privacidad")

if 'mostrar_confirmacion' not in st.session_state:
    st.session_state.mostrar_confirmacion = False

col_clean1, col_clean2 = st.columns([3, 1])
with col_clean1:
    st.caption("Una vez descargada el acta, borra los archivos por seguridad.")

with col_clean2:
    if st.button("Borrar Archivos", type="secondary"):
        st.session_state.mostrar_confirmacion = True

if st.session_state.mostrar_confirmacion:
    st.warning("⚠️ ¿Borrar todos los audios subidos y grabados?")
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1:
        if st.button("❌ Cancelar"):
            st.session_state.mostrar_confirmacion = False
            st.rerun()
    with col_conf2:
        if st.button("✅ SÍ, BORRAR TODO"):
            st.session_state.grabaciones_guardadas = []
            st.session_state.contador_micro = 0
            st.session_state.uploader_key += 1
            st.session_state.mostrar_confirmacion = False
            st.rerun()
