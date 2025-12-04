
"""
Script Landy3.py - Aplicación Streamlit para Consulta Ambiental Geoespacial
"""

import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import Point
from streamlit_folium import st_folium
from fpdf import FPDF
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import os
import re
from datetime import datetime
import numpy as np 

# --- CONFIGURACIÓN DE PÁGINA Y CSS (MEJORA DE INTERFAZ) ---
st.set_page_config(
    page_title="Geolandy - Consulta Ambiental",
    layout="wide",
    initial_sidebar_state="expanded"
)

# CSS Personalizado para un mejor estilo
st.markdown("""
    <style>
    /* Estilo para el fondo del sidebar (Color institucional) */
    [data-testid="stSidebar"] {
        background-color: #2d5016;
    }
    /* Estilo para el texto del sidebar */
    [data-testid="stSidebar"] * {
        color: #ffffff;
    }
    /* Estilo para el título principal */
    h1 {
        color: #4a7c2c;
        border-bottom: 2px solid #4a7c2c;
        padding-bottom: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# --- INICIALIZACIÓN DEL ESTADO DE SESIÓN (SOLUCIÓN AL REINICIO) ---
if 'resultado_consulta' not in st.session_state:
    st.session_state.resultado_consulta = None

# --- CONFIGURACIÓN DE COLORES POR CATEGORÍA ---
COLORES_CATEGORIA = {
    'Zona de Preservacion': '#006400',           # Verde oscuro
    'Zona de Restauracion': '#FFA500',           # Naranja
    'Zona de uso Sostenible': '#FFFF00',         # Amarillo
    'Zona general de uso Publico': '#FF69B4',    # Rosado
    'Zona de Recuperacion Ambiental': '#D3D3D3'  # Gris claro
}



# --- FUNCIONES AUXILIARES ---

def formatear_area(area_m2, formato_reporte=False):
    """
    Formatea el área. Si es para el reporte (formato_reporte=True),
    muestra ha (m²). De lo contrario, usa la unidad más grande.
    """
    area_m2 = float(area_m2)
    area_ha = area_m2 / 10000

    if formato_reporte:
        # Formato para el reporte: ha (m²)
        return f"{area_ha:,.2f} ha ({area_m2:,.2f} m²)"
    
    # Lógica para Streamlit: unidad más grande
    if area_m2 < 10000:
        return f"{area_m2:,.2f} m²"
    else:
        return f"{area_ha:,.2f} ha"

@st.cache_data
def cargar_datos():
    """
    Carga los archivos geoespaciales, los reproyecta a EPSG:9377
    y aplica el mapeo de nombres a la columna ZONIFICACI.
    """
    try:
        # Cargar y reproyectar a EPSG:9377 
        predios = gpd.read_file("PREDIOS_RFPBOB_2025.shp").to_crs(epsg=9377)
        zonas = gpd.read_file("Zonificacion_Ambiental_RFP_Bosque_Oriental_de_Bogota2.shp").to_crs(epsg=9377)
        

        return predios, zonas
    except Exception as e:
        st.error(f"Error al cargar datos geoespaciales. Asegúrate de que los archivos .shp y sus complementos estén en el mismo directorio: {e}")
        return None, None


# --- GENERACIÓN DE PDF MEJORADA ---

def generar_pdf(chip, consulta, interseccion, area_predio, area_afectada, porcentaje_afectado):
    

    chip_limpio = re.sub(r'[^\w]', '', chip)
    archivo_mapa = f"mapa_temp_{chip_limpio}.png"

    # === 1. Generar mapa estático optimizado ===
    try:
        fig, ax = plt.subplots(1, 1, figsize=(8, 8))
        ax.set_title(f"Afectación Ambiental - CHIP: {chip}", fontsize=13)

        # Dibujar el polígono del predio
        consulta.plot(ax=ax, facecolor='none', edgecolor='blue', linewidth=2, label='Límite Predio')

        # Dibujar intersecciones con color ya precalculado
        interseccion.plot(ax=ax, color=interseccion['color'], edgecolor='black', linewidth=0.5)

        # Leyenda simplificada
        handles = [mpatches.Patch(color=COLORES_CATEGORIA[c], label=c)
                   for c in interseccion['ZONIFICACI'].unique()]
        handles.append(mpatches.Patch(edgecolor='blue', facecolor='none', linewidth=2, label='Límite Predio'))
        ax.legend(handles=handles, title="Zonificación", loc='lower left', fontsize=8)

        ax.set_axis_off()
        plt.tight_layout()
        plt.savefig(archivo_mapa, dpi=200, bbox_inches='tight')
        plt.close(fig)

    except Exception as e:
        st.error(f"Error al generar el mapa: {e}")
        return

    # === 2. Clase PDF ===
    class PDF(FPDF):
        def header(self):
            self.set_fill_color(45, 80, 22)
            self.rect(0, 0, 210, 20, 'F')
            self.set_font('Arial', 'B', 16)
            self.set_text_color(255, 255, 255)
            self.cell(0, 15, 'REPORTE GEOLANDY - Consulta Ambiental de Predios', 0, 1, 'C')
            self.set_font('Arial', '', 10)
            self.set_text_color(0, 0, 0)
            self.set_y(20)
            self.cell(0, 5, f'Generado el: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}', 0, 1, 'R')
            self.ln(5)

        def footer(self):
            self.set_y(-15)
            self.set_font('Arial', 'I', 8)
            self.cell(0, 10, f'Página {self.page_no()}/{{nb}}', 0, 0, 'C')

    pdf = PDF()
    pdf.alias_nb_pages()
    pdf.add_page()
    pdf.set_auto_page_break(auto=True, margin=15)

    # === 3. Sección: Resumen ===
    pdf.set_font('Arial', 'B', 12)
    pdf.set_fill_color(220, 230, 240)
    pdf.cell(0, 8, '1. Resumen de la Consulta y Propiedad', 1, 1, 'L', 1)

    pdf.set_font('Arial', '', 10)
    pdf.set_fill_color(240, 240, 240)
    pdf.cell(50, 8, "CHIP/Referencia:", 1, 0, 'L', 1)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(140, 8, f"{chip}", 1, 1, 'L', 0)
    pdf.set_font('Arial', '', 10)

    pdf.cell(50, 8, "Área Total del Predio:", 1, 0, 'L', 1)
    pdf.cell(140, 8, f"{formatear_area(area_predio, True)}", 1, 1, 'L', 0)

    pdf.cell(50, 8, "Área Afectada por Reserva:", 1, 0, 'L', 1)
    fill_color = (255, 230, 230) if porcentaje_afectado > 0 else (230, 255, 230)
    estado = "AFECTADO" if porcentaje_afectado > 0 else "NO AFECTADO"
    pdf.set_fill_color(*fill_color)
    pdf.set_font('Arial', 'B', 10)
    pdf.cell(140, 8, f"{formatear_area(area_afectada, True)} ({porcentaje_afectado:.2f}%)", 1, 1, 'L', 1)

    pdf.cell(50, 8, "Estado del Predio:", 1, 0, 'L', 1)
    pdf.set_fill_color(*fill_color)
    pdf.cell(140, 8, estado, 1, 1, 'C', 1)
    pdf.ln(5)

    # === 4. Sección: Mapa ===
    pdf.set_font('Arial', 'B', 12)
    pdf.set_fill_color(220, 230, 240)
    pdf.cell(0, 8, '2. Mapa de Afectación', 1, 1, 'L', 1)

    if os.path.exists(archivo_mapa):
        pdf.image(archivo_mapa, x=30, y=pdf.get_y(), w=150)
        pdf.set_y(pdf.get_y() + 150)
        pdf.set_font('Arial', 'I', 8)
        pdf.cell(0, 4, 'Mapa: superposición del predio (azul) y las zonas intersectadas.', 0, 1, 'C')
    pdf.ln(5)

    # === 5. Sección: Detalle de Zonas ===
    if not interseccion.empty:
        pdf.set_font('Arial', 'B', 12)
        pdf.set_fill_color(220, 230, 240)
        pdf.cell(0, 8, '3. Detalle de Zonas Afectadas', 1, 1, 'L', 1)
        pdf.set_font('Arial', '', 10)

        for row in interseccion.itertuples(index=False):
            pdf.set_fill_color(230, 230, 230)
            pdf.set_font('Arial', 'B', 10)
            pdf.cell(0, 8, f"ZONA: {row.ZONIFICACI} (Afectación: {formatear_area(row.geometry.area, True)})", ln=True, fill=True)
            
            pdf.set_font('Arial', 'U', 9)
            pdf.cell(0, 6, "Descripción:", 0, 1)
            pdf.set_font('Arial', '', 9)
            pdf.multi_cell(0, 5, str(row.DESCRIPCI or ""), align='J')

            pdf.set_font('Arial', 'U', 9)
            pdf.cell(0, 6, "Actividades Permitidas:", 0, 1)
            pdf.set_font('Arial', '', 9)
            if isinstance(row.ACT_PERMIT, str):
                for act in [a.strip() for a in row.ACT_PERMIT.split('.') if a.strip()]:
                    pdf.cell(5)
                    pdf.multi_cell(0, 4, f"- {act}", 0, 'J')

            pdf.set_font('Arial', 'U', 9)
            pdf.cell(0, 6, "Actividades Prohibidas:", 0, 1)
            pdf.set_font('Arial', 'B', 9)
            if isinstance(row.ACT_PROHIB, str):
                for act in [a.strip() for a in row.ACT_PROHIB.split('.') if a.strip()]:
                    pdf.cell(5)
                    pdf.multi_cell(0, 4, f"- {act}", 0, 'J')

            pdf.ln(3)

    # === 6. Guardar y ofrecer descarga ===
    archivo_pdf = f"reporte_{chip_limpio}.pdf"
    pdf.output(archivo_pdf)

    with open(archivo_pdf, "rb") as f:
        st.download_button(
            label="⬇️ Descargar Reporte PDF",
            data=f,
            file_name=archivo_pdf,
            mime="application/pdf"
        )

    if os.path.exists(archivo_mapa):
        os.remove(archivo_mapa)


# --- CARGA INICIAL DE DATOS ---
predios, zonas = cargar_datos()

if predios is None or zonas is None:
    st.stop() 


# =========================================================================
# === BARRA LATERAL (SIDEBAR) - LÓGICA DE ENTRADA ===
# =========================================================================

st.sidebar.header("🔎 Consulta GEOLandy")
modo = st.sidebar.radio("Modo de búsqueda:", ["Por CHIP", "Por coordenadas"])

if modo == "Por CHIP":
    chip = st.sidebar.text_input("Ingrese el código CHIP (Ej: AAA0143FTRS):")
    
    if st.sidebar.button("🔍 Buscar por CHIP"):
        if chip.strip() == "":
            st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': "Por favor, ingrese un código CHIP."}
            st.rerun()
            
        patron_chip = r"^[A-Za-z]{3}\d{4}[A-Za-z]{4}$"
        if not re.match(patron_chip, chip):
            st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': "Formato de CHIP inválido. Debe ser 3 letras + 4 números + 4 letras."}
            st.rerun()

        try:
            # Uso de 'CHIP' para filtrar
            consulta = predios[predios['CHIP'] == chip]
            
            if len(consulta) > 0:
                # Almacena la información
                st.session_state.resultado_consulta = {
                    'tipo': 'chip',
                    'referencia': chip,
                    'consulta_gdf': consulta.copy() 
                }
            else:
                st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': f"Predio con CHIP {chip} no encontrado en la base de datos."}
                
                                
        except Exception as e:
            st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': f"Error al buscar el CHIP: {e}"}
            
    # Botón para limpiar si ya hay un resultado
    if st.session_state.resultado_consulta is not None:
        if st.sidebar.button("↩️ Limpiar Búsqueda"):
            st.session_state.resultado_consulta = None
            st.rerun()

elif modo == "Por coordenadas":
    st.sidebar.markdown("**Sistema de Referencia: EPSG:9377**")
    
    # Ejemplo para evitar errores de digitación
    st.sidebar.info("💡 **Ejemplo (EPSG:9377):**\n- X (Este): 4884290.02 \n- Y (Norte): 2065679.52")
    
    x = st.sidebar.number_input("Coordenada X (Este):", value=5000000.0, format="%.2f")
    y = st.sidebar.number_input("Coordenada Y (Norte):", value=2000000.0, format="%.2f") 
    
    if st.sidebar.button("🔍 Buscar por coordenadas"):
        try:
            # Crear un punto GeoDataFrame en EPSG:9377
            punto = gpd.GeoDataFrame(geometry=[Point(x, y)], crs="EPSG:9377") 
            
            # Operación de intersección espacial 
            consulta = predios[predios.intersects(punto.iloc[0].geometry)]
            
            if len(consulta) > 0:
                # Uso de 'CHIP' para obtener el identificador
                predio_chip = consulta.iloc[0]['CHIP']
                st.session_state.resultado_consulta = {
                    'tipo': 'coordenadas',
                    'referencia': predio_chip,
                    'consulta_gdf': consulta.copy()
                }
            else:
                st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': "Predio no encontrado en la base de datos en esas coordenadas."}

        except Exception as e:
            st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': f"Error al buscar por coordenadas: {e}"}
            
    # Botón para limpiar si ya hay un resultado
    if st.session_state.resultado_consulta is not None:
        if st.sidebar.button("↩️ Limpiar Búsqueda"):
            st.session_state.resultado_consulta = None
            st.rerun()


# =========================================================================
# === CUERPO PRINCIPAL - LÓGICA DE PRESENTACIÓN DE RESULTADOS ===
# =========================================================================

st.title("🏡 Geolandy: Consulta Ambiental de Predios")
st.markdown("Aplicacion para determinar la afectación por zonificación de la Reserva Forestal Protectora Bosque Oriental de Bogota.")

st.markdown("---")

if st.session_state.resultado_consulta is not None:
    resultado = st.session_state.resultado_consulta

    if resultado['tipo'] == 'error':
        st.error(f"❌ Error en la consulta: {resultado['mensaje']}")
        
    else:
        # Se encontró un predio, procesar y mostrar resultados
        try:
            consulta = resultado['consulta_gdf']
            referencia = resultado['referencia'] # Contiene el CHIP
            
            # --- CÁLCULOS DE INTERSECCIÓN Y ÁREAS ---
            
            interseccion = gpd.overlay(consulta, zonas, how="intersection", keep_geom_type=False)
            area_predio = consulta.iloc[0].geometry.area
            
            
            if not interseccion.empty:
                # Predio Afectado
                area_afectada = interseccion.geometry.union_all().area
                area_no_afectada = area_predio - area_afectada
                porcentaje_afectado = (area_afectada / area_predio) * 100
                porcentaje_no_afectado = 100 - porcentaje_afectado
                
                # --- VISUALIZACIÓN DE RESULTADOS (Interfaz Mejorada) ---
                
                st.success(f"✅ Predio encontrado. CHIP: **{referencia}** | Afectación Total: **{porcentaje_afectado:.2f}%**")
                
                # 1. FILA DE MAPAS
                # Se utiliza st.columns([1, 2]) para dar más espacio al mapa de detalle
                col_mapa_general, col_mapa_detalle = st.columns([1, 2]) 

                # 2. Generación de los Mapas Folium
                consulta_wgs = consulta.to_crs(epsg=4326)
                interseccion_wgs = interseccion.to_crs(epsg=4326)
                centroid = consulta_wgs.geometry.iloc[0].centroid
                
                # Calcular bounds para zoom dinámico
                bounds = consulta_wgs.total_bounds
                folium_bounds = [[bounds[1], bounds[0]], [bounds[3], bounds[2]]] # Folium format: [[lat_min, lon_min], [lat_max, lon_max]]
                
                
                # MAPA 1: UBICACIÓN GENERAL (Zoom Dinámico)
                with col_mapa_general:
                    st.subheader("🗺️ Ubicación General")
                    mapa_general = folium.Map(location=[centroid.y, centroid.x], zoom_start=12) 
                    # 🛑 AJUSTE: Aplicar fit_bounds para ver el predio completo
                    mapa_general.fit_bounds(folium_bounds)
                    
                    folium.GeoJson(
                        consulta_wgs.to_json(),
                        style_function=lambda x: {'fillColor': 'none', 'color': 'blue', 'weight': 3},
                        tooltip=folium.Tooltip(f"Predio: {referencia}")
                    ).add_to(mapa_general)
                    st_folium(mapa_general, height=500, key="mapa_general")


                # MAPA 2: MAPA DETALLADO DE AFECTACIÓN (Zoom Fijo para detalle)
                with col_mapa_detalle:
                    st.subheader("🌐 Detalle de Afectación")
                    mapa_detalle = folium.Map(location=[centroid.y, centroid.x], zoom_start=14) 
                    
                    folium.GeoJson(
                        consulta_wgs.to_json(),
                        style_function=lambda x: {'fillColor': 'none', 'color': 'blue', 'weight': 3, 'fillOpacity': 0.5},
                        tooltip=folium.Tooltip(f"Predio: {referencia}")
                    ).add_to(mapa_detalle)
                    
                    folium.GeoJson(
                        interseccion_wgs.to_json(),
                        style_function=lambda x: {
                            'fillColor': COLORES_CATEGORIA.get(x['properties']['ZONIFICACI'], '#808080'),
                            'color': 'black',
                            'weight': 1,
                            'fillOpacity': 0.7
                        },
                        tooltip=folium.GeoJsonTooltip(fields=['ZONIFICACI', 'ACTO_ZONIF'], aliases=['Zona:', 'Norma:'])
                    ).add_to(mapa_detalle)
                    
                    st_folium(mapa_detalle, height=500, key="mapa_afectacion")

                # 3. FILA DE RESUMEN Y DETALLE (Debajo de los mapas)
                st.markdown("---")
                col_resumen, col_detalle = st.columns([1, 2])
                
                with col_resumen:
                    st.subheader("📊 Resumen de Áreas")
                    
                    # 1.1 Métricas para el resumen
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(label="Área Total Predio", value=formatear_area(area_predio))
                    with col2:
                        st.metric(label="Área No Afectada", value=formatear_area(area_no_afectada), delta=f"{porcentaje_no_afectado:.2f}%")
                        
                        st.metric(label="Área Afectada por Reserva", value=formatear_area(area_afectada), delta=f"-{porcentaje_afectado:.2f}%", delta_color="inverse")
                    
                    st.subheader("🛠️ Acciones")

                    # Botón para el PDF
                    
                    if st.button("📄 Generar Reporte PDF", key="btn_pdf"):
                        interseccion_vis = interseccion.to_crs(epsg=4326).copy()
                        interseccion_vis["color"] = interseccion_vis["ZONIFICACI"].map(COLORES_CATEGORIA).fillna("#808080")
                        consulta_vis = consulta.to_crs(epsg=4326).copy()
                        generar_pdf(referencia, consulta_vis, interseccion_vis, area_predio, area_afectada, porcentaje_afectado)

                    
                    
                    #if st.button("📄 Generar Reporte PDF", key="btn_pdf"):
                        #generar_pdf(referencia, consulta, interseccion, area_predio, area_afectada, porcentaje_afectado)

                with col_detalle:
                    st.subheader("📝 Detalle de Zonificación Afectada")
                    
                    # Expander para detalles de la tabla
                    with st.expander("Ver Tabla Completa de Zonas Afectadas"):
                        interseccion['Area_m2'] = interseccion.geometry.area
                        interseccion_detallada = interseccion[['ZONIFICACI', 'DESCRIPCI', 'ACTO_ZONIF', 'ACT_PERMIT', 'ACT_PROHIB', 'Area_m2']].copy()
                        interseccion_detallada['Área'] = interseccion_detallada['Area_m2'].apply(formatear_area)
                        interseccion_detallada.drop(columns=['Area_m2'], inplace=True)
                        st.dataframe(interseccion_detallada, width="stretch", hide_index=True)
                
            # Si NO hay afectación
            else:
                area_predio = consulta.iloc[0].geometry.area
                st.success(f"✅ Predio encontrado. CHIP: **{referencia}**")
                st.warning("⚠️ **¡NO AFECTADO!** El predio no intersecta con la zonificación de la Reserva Forestal Protectora.")
                st.metric(label="Área Total Predio", value=formatear_area(area_predio))
                
            st.markdown("---")
            if st.button("↩️ **Iniciar Nueva Consulta**", key="btn_nueva_consulta"):
                st.session_state.resultado_consulta = None 
                st.rerun() 
                
        except Exception as e:
            st.error(f"Error desconocido durante el procesamiento de resultados. Intente de nuevo: {e}")
            st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': f"Error en el procesamiento: {e}"}
            st.rerun()