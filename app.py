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

# --- GESTIÓN DE MEMORIA (SESSION STATE) ---
if 'grabaciones_guardadas' not in st.session_state:
    st.session_state.grabaciones_guardadas = []
if 'contador_micro' not in st.session_state:
    st.session_state.contador_micro = 0
# Esta clave sirve para resetear el cargador de archivos
if 'uploader_key' not in st.session_state:
    st.session_state.uploader_key = 0

# --- FUNCIONES DE LÓGICA ---
def transcribir_audio(audio_file, api_key):
    client = openai.OpenAI(api_key=api_key)
    audio_file.seek(0)
    
    # FIX IPAD/IPHONE: Forzar nombre con extensión si no la tiene
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
    
    prompt_sistema = f"""
    Eres el secretario experto del Departamento de Educación Física del IES Lucía de Medrano.
    Tu tarea es convertir una transcripción de reunión en un ACTA FORMAL.
    
    REGLAS:
    1. Estilo: Impersonal, formal y administrativo.
    2. EXCEPCIÓN: Si alguien dice "que conste en acta", transcribe EXACTAMENTE: "D. [Nombre] manifestó lo siguiente: [Cita textual]".
    3. ASISTENTES: Si se menciona que alguien faltó, extráelo. Si no, asume que están todos.
    
    ESTRUCTURA (Solo cuerpo):
    - "AUSENCIAS: [Nombres]" o "AUSENCIAS: Ninguna".
    - Puntos tratados numerados.
    """

    response = client.chat.completions.create(
        model="gpt-4o",
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"Fecha: {fecha}. Transcripción: {transcripcion_completa}"}
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

tab1, tab2 = st.tabs(["📂 1. Subir Archivos", "🎤 2. Grabar (Multi-toma)"])

with tab1:
    # Usamos una key dinámica. Al cambiar 'uploader_key', este widget se resetea.
    key_dinamica = f"uploader_{st.session_state.uploader_key}"
    archivos_subidos = st.file_uploader(
        "Arrastra archivos aquí (mp3, m4a, wav)", 
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
    f"✅ PROCESAR {count} AUDIOS Y GENERAR ACTA", 
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
        # ... (PROCESO DE GENERACIÓN) ...
        transcripcion_total = ""
        barra = st.progress(0, text="Iniciando...")
        try:
            for i, archivo in enumerate(lista_total):
                barra.progress((i / count) * 0.8, text=f"Transcribiendo {i+1}/{count}...")
                try:
                    texto = transcribir_audio(archivo, api_key)
                    transcripcion_total += f"\n--- Audio {i+1} ---\n{texto}\n"
                except Exception as e:
                    st.error(f"Error en audio {i+1}: {e}")
            
            if transcripcion_total.strip():
                barra.progress(0.85, text="Redactando...")
                contenido = generar_contenido_acta(transcripcion_total, fecha_sesion, api_key)
                doc = crear_documento_word(contenido, fecha_sesion)
                barra.progress(1.0, text="¡Listo!")
                st.balloons()
                
                st.success("🎉 Acta generada correctamente. Descárgala abajo.")
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

# 5. ZONA DE LIMPIEZA Y BORRADO (NUEVO)
st.write("---")
st.write("### 🗑️ Gestión de Privacidad")

# Variable de estado para controlar si se muestra la confirmación
if 'mostrar_confirmacion' not in st.session_state:
    st.session_state.mostrar_confirmacion = False

col_clean1, col_clean2 = st.columns([3, 1])

with col_clean1:
    st.caption("Una vez descargada el acta, se recomienda borrar los audios del servidor para liberar espacio y mantener la privacidad.")

with col_clean2:
    if st.button("Borrar Archivos", type="secondary"):
        st.session_state.mostrar_confirmacion = True

# Lógica de confirmación
if st.session_state.mostrar_confirmacion:
    st.warning("⚠️ **¿Estás seguro?** Esta acción no se puede deshacer. Se eliminarán todos los archivos subidos y grabados.")
    
    col_conf1, col_conf2 = st.columns(2)
    with col_conf1:
        if st.button("❌ Cancelar"):
            st.session_state.mostrar_confirmacion = False
            st.rerun()
            
    with col_conf2:
        if st.button("✅ SÍ, BORRAR TODO"):
            # 1. Vaciar lista de grabaciones
            st.session_state.grabaciones_guardadas = []
            # 2. Resetear contadores
            st.session_state.contador_micro = 0
            # 3. Truco: Cambiar la clave del uploader fuerza a Streamlit a reiniciarlo vacío
            st.session_state.uploader_key += 1
            # 4. Ocultar confirmación
            st.session_state.mostrar_confirmacion = False
            # 5. Recargar la página
            st.rerun()
