import streamlit as st
import subprocess
import sys
import time
import os

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

def obtener_extension_segura(nombre_archivo):
    """Extrae la extensión (.mp3, .wav) y devuelve un nombre ASCII seguro"""
    try:
        if "." in nombre_archivo:
            ext = nombre_archivo.split(".")[-1].lower()
            # Lista blanca de extensiones permitidas
            if ext in ["mp3", "wav", "m4a", "mp4", "mpeg", "mpga", "webm"]:
                return f"audio_seguro.{ext}"
    except:
        pass
    return "audio_seguro.wav" # Fallback por defecto

def transcribir_audio(audio_file, api_key):
    client = openai.OpenAI(api_key=api_key)
    audio_file.seek(0)
    
    # --- CORRECCIÓN DEL ERROR ASCII ---
    # Ignoramos el nombre original con acentos y creamos uno seguro
    nombre_original = getattr(audio_file, 'name', 'desconocido.wav')
    nombre_seguro = obtener_extension_segura(nombre_original)
    
    # Enviamos a la API el archivo pero con el nombre "falso" seguro
    transcript = client.audio.transcriptions.create(
        model="whisper-1", 
        file=(nombre_seguro, audio_file), 
        language="es",
        temperature=0 # Temperatura 0 para máxima fidelidad
    )
    return transcript.text

def generar_contenido_acta(transcripcion_completa, fecha, api_key):
    client = openai.OpenAI(api_key=api_key)
    
    # --- PROMPT ANTÍ-ALUCINACIONES ---
    prompt_sistema = f"""
    Eres un redactor técnico estricto para el Departamento de Educación Física del IES Lucía de Medrano.
    
    REGLAS DE ORO (DE OBLIGADO CUMPLIMIENTO):
    1. PROHIBIDO INVENTAR: No añadas ni un solo dato, tema o nombre que no aparezca explícitamente en el texto.
    2. NOMBRES REALES: Si en el audio no se dice el nombre, usa "Un profesor" o "Un asistente". JAMÁS inventes nombres propios.
    3. FIDELIDAD: Mejora la gramática pero MANTÉN EL CONTENIDO EXACTO. No resumas excesivamente.
    4. CITA TEXTUAL: Si alguien dice "que conste en acta", transcribe literalmente: "D./Dña. [Nombre] manifestó: [Frase exacta]".
    5. CALIDAD: Si un fragmento es solo ruido, indícalo como "Fragmento ininteligible".
    
    ESTRUCTURA DE SALIDA:
    - Primero: "AUSENCIAS: [Nombres detectados]" o "AUSENCIAS: Ninguna mencionada".
    - Segundo: Desarrollo de la sesión (Narración formal y estricta de lo sucedido).
    """

    response = client.chat.completions.create(
        model="gpt-4o", 
        temperature=0.2, # Creatividad baja para evitar invenciones
        messages=[
            {"role": "system", "content": prompt_sistema},
            {"role": "user", "content": f"Fecha: {fecha}. Transcripción BRUTA (Fuente única de verdad):\n\n{transcripcion_completa}"}
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
st.caption("Modo Seguro: Se corrigen automáticamente nombres de archivo con acentos para evitar errores.")

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
                # Nombre seguro sin acentos
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
        # Mostramos el nombre real al usuario, aunque internamente usaremos uno seguro
        nombre = getattr(audio, 'name', f"Audio {i+1}.wav")
        st.text(f"{i+1}. {nombre}")

# 4. GENERAR ACTA
st.divider()
boton_finalizar = st.button(
    f"✅ PROCESAR {count} AUDIOS Y GENERAR ACTA FIEL", 
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
        errores_detectados = False
        
        try:
            # Fase 1: Transcripción
            for i, archivo in enumerate(lista_total):
                barra.progress((i / count) * 0.7, text=f"Transcribiendo audio {i+1}/{count}...")
                try:
                    texto = transcribir_audio(archivo, api_key)
                    transcripcion_total += f"\n--- Intervención {i+1} ---\n{texto}\n"
                except Exception as e:
                    errores_detectados = True
                    st.error(f"Error procesando el audio {i+1}: {str(e)}")
            
            if not transcripcion_total.strip():
                st.error("No se pudo obtener texto de los audios. Revisa que no estén vacíos o corruptos.")
            else:
                # Fase 2: Redacción Estricta
                barra.progress(0.75, text="Redactando acta sin invenciones...")
                contenido = generar_contenido_acta(transcripcion_total, fecha_sesion, api_key)
                
                # Fase 3: Documento
                barra.progress(0.95, text="Maquetando documento Word...")
                doc = crear_documento_word(contenido, fecha_sesion)
                
                barra.progress(1.0, text="¡Finalizado!")
                st.balloons()
                
                if errores_detectados:
                    st.warning("El acta se generó, pero algunos audios dieron error (ver arriba).")
                else:
                    st.success("🎉 Acta generada correctamente.")
                
                st.download_button(
                    label="📥 DESCARGAR WORD (.DOCX)",
                    data=doc.getvalue(),
                    file_name=f"Acta_EF_{fecha_sesion}.docx",
                    mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                    type="primary"
                )
        except Exception as e:
            st.error(f"Error crítico: {e}")

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
