import streamlit as st
import geopandas as gpd
import pandas as pd
import folium
from shapely.geometry import Point
from streamlit_folium import st_folium
from fpdf import FPDF
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyArrowPatch
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
        
        # Crear límite de la reserva (unión de todas las zonas)
        limite_reserva = zonas.geometry.union_all()
        reserva_gdf = gpd.GeoDataFrame(geometry=[limite_reserva], crs=zonas.crs)

        return predios, zonas, reserva_gdf
    except Exception as e:
        st.error(f"Error al cargar datos geoespaciales. Asegúrate de que los archivos .shp y sus complementos estén en el mismo directorio: {e}")
        return None, None, None


# --- GENERACIÓN DE PDF MEJORADA ---

def generar_pdf(chip, consulta, interseccion, area_predio, area_afectada, porcentaje_afectado, reserva_gdf):
    
    chip_limpio = re.sub(r'[^\w]', '', chip)
    archivo_mapa = f"mapa_temp_{chip_limpio}.png"

    # === 1. Generar mapa estático optimizado ===
    try:
        # Calcular aspect ratio del predio para tamaño adaptativo
        bounds = consulta.total_bounds
        width = bounds[2] - bounds[0]
        height = bounds[3] - bounds[1]
        aspect_ratio = width / height
        
        # Determinar tamaño de figura según aspect ratio
        if aspect_ratio > 1.5:  # Predio ancho
            figsize = (10, 6)
        elif aspect_ratio < 0.67:  # Predio alto
            figsize = (6, 10)
        else:  # Predio cuadrado
            figsize = (8, 8)
        
        # Crear figura con subplots para mapa principal e inset
        fig = plt.figure(figsize=figsize)
        
        # Eje principal (mapa de detalle)
        ax_main = fig.add_axes([0.1, 0.25, 0.8, 0.65])  # [left, bottom, width, height]
        ax_main.set_title(f"Afectación Ambiental - CHIP: {chip}", fontsize=13, pad=10)

        # Dibujar el polígono del predio
        consulta.plot(ax=ax_main, facecolor='none', edgecolor='blue', linewidth=2.5, label='Límite Predio')

        # Dibujar intersecciones con color ya precalculado
        if not interseccion.empty:
            interseccion.plot(ax=ax_main, color=interseccion['color'], edgecolor='black', linewidth=0.5)

        # Ajustar límites con margen
        minx, miny, maxx, maxy = consulta.total_bounds
        margin_x = (maxx - minx) * 0.1
        margin_y = (maxy - miny) * 0.1
        ax_main.set_xlim(minx - margin_x, maxx + margin_x)
        ax_main.set_ylim(miny - margin_y, maxy + margin_y)
        
        # Añadir flecha norte (simple)
        arrow_x = maxx - margin_x * 0.5
        arrow_y = maxy - margin_y * 0.5
        arrow_length = min(margin_x, margin_y) * 0.8
        
        arrow = FancyArrowPatch((arrow_x, arrow_y - arrow_length), (arrow_x, arrow_y),
                               arrowstyle='->', mutation_scale=20, linewidth=2, color='black')
        ax_main.add_patch(arrow)
        ax_main.text(arrow_x, arrow_y + arrow_length * 0.2, 'N', fontsize=12, 
                    weight='bold', ha='center', va='bottom')

        ax_main.set_axis_off()
        
        # === Mini-mapa de contexto (inset) ===
        ax_inset = fig.add_axes([0.65, 0.27, 0.23, 0.23])  # Posición esquina superior derecha
        
        # Dibujar límite de la reserva
        reserva_gdf.plot(ax=ax_inset, facecolor='lightgreen', edgecolor='darkgreen', 
                        linewidth=1, alpha=0.3)
        
        # Dibujar predio como punto rojo
        centroid = consulta.geometry.centroid.iloc[0]
        ax_inset.plot(centroid.x, centroid.y, 'ro', markersize=8, markeredgecolor='darkred', 
                     markeredgewidth=1.5)
        
        # Ajustar límites al extent de la reserva
        res_bounds = reserva_gdf.total_bounds
        ax_inset.set_xlim(res_bounds[0], res_bounds[2])
        ax_inset.set_ylim(res_bounds[1], res_bounds[3])
        ax_inset.set_title('Ubicación en Reserva', fontsize=8)
        ax_inset.set_axis_off()
        
        # === Leyenda fuera del mapa (abajo) ===
        ax_legend = fig.add_axes([0.1, 0.05, 0.8, 0.15])
        ax_legend.set_axis_off()
        
        # Crear handles para la leyenda
        handles = []
        if not interseccion.empty:
            for categoria in interseccion['ZONIFICACI'].unique():
                handles.append(mpatches.Patch(color=COLORES_CATEGORIA.get(categoria, '#808080'), 
                                             label=categoria))
        handles.append(mpatches.Patch(edgecolor='blue', facecolor='none', 
                                     linewidth=2, label='Límite Predio'))
        
        # Posicionar leyenda
        legend = ax_legend.legend(handles=handles, title="Zonificación", 
                                 loc='upper center', ncol=min(3, len(handles)),
                                 fontsize=8, title_fontsize=9, frameon=True)
        
        # Añadir información del sistema de referencia
        ax_legend.text(0.5, 0.05, 'Sistema de Referencia: EPSG:9377 (MAGNA-SIRGAS / Colombia Bogotá)', 
                      ha='center', va='bottom', fontsize=7, style='italic',
                      transform=ax_legend.transAxes)

        plt.savefig(archivo_mapa, dpi=200, bbox_inches='tight', facecolor='white')
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
        # Calcular dimensiones para centrar el mapa
        img_width = 170  # Ancho máximo
        pdf.image(archivo_mapa, x=20, y=pdf.get_y() + 5, w=img_width)
        
        # Ajustar posición Y según altura de imagen
        from PIL import Image
        with Image.open(archivo_mapa) as img:
            img_height = (img.height / img.width) * img_width
        pdf.set_y(pdf.get_y() + img_height + 10)
        
        pdf.set_font('Arial', 'I', 8)
        pdf.cell(0, 4, 'Mapa: superposición del predio (azul) y las zonas intersectadas con mini-mapa de contexto.', 0, 1, 'C')
    pdf.ln(5)

    # === 5. Sección: Detalle de Zonas ===
    if not interseccion.empty and porcentaje_afectado > 0:
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

    # Esperar un momento antes de eliminar el archivo (solución para Windows)
    import time
    time.sleep(0.5)
    
    # Intentar eliminar el archivo temporal de manera segura
    if os.path.exists(archivo_mapa):
        try:
            os.remove(archivo_mapa)
        except PermissionError:
            # Si no se puede eliminar inmediatamente, programar eliminación
            import atexit
            atexit.register(lambda: os.remove(archivo_mapa) if os.path.exists(archivo_mapa) else None)


# --- CARGA INICIAL DE DATOS ---
predios, zonas, reserva_gdf = cargar_datos()

if predios is None or zonas is None or reserva_gdf is None:
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
                # CORREGIDO: Mensaje para predios no encontrados
                st.session_state.resultado_consulta = {
                    'tipo': 'no_afectado',
                    'mensaje': f"El predio consultado (CHIP: {chip}) no presenta afectación por la Reserva Forestal Protectora Bosque Oriental de Bogotá."
                }
                                
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
                # CORREGIDO: Mensaje para coordenadas no encontradas
                st.session_state.resultado_consulta = {
                    'tipo': 'no_afectado',
                    'mensaje': f"El predio consultado en las coordenadas (X: {x}, Y: {y}) no presenta afectación por la Reserva Forestal Protectora Bosque Oriental de Bogotá."
                }

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
st.markdown("Aplicación para determinar la afectación por zonificación de la Reserva Forestal Protectora Bosque Oriental de Bogotá.")

st.markdown("---")

if st.session_state.resultado_consulta is not None:
    resultado = st.session_state.resultado_consulta

    if resultado['tipo'] == 'error':
        st.error(f"❌ Error en la consulta: {resultado['mensaje']}")
    
    elif resultado['tipo'] == 'no_afectado':
        # NUEVO: Manejo de predios no afectados
        st.success("✅ Consulta realizada exitosamente")
        st.info(f"ℹ️ {resultado['mensaje']}")
        
        st.markdown("---")
        if st.button("↩️ **Iniciar Nueva Consulta**", key="btn_nueva_consulta_na"):
            st.session_state.resultado_consulta = None 
            st.rerun()
        
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
                area_afectada = interseccion.geometry.area.sum()  # CORREGIDO: sum() en lugar de union_all().area
                area_no_afectada = area_predio - area_afectada
                porcentaje_afectado = (area_afectada / area_predio) * 100
                porcentaje_no_afectado = 100 - porcentaje_afectado
                
                # --- VISUALIZACIÓN DE RESULTADOS (Interfaz Mejorada) ---
                
                st.success(f"✅ Predio encontrado. CHIP: **{referencia}** | Afectación Total: **{porcentaje_afectado:.2f}%**")
                
                # 1. FILA DE MAPAS
                col_mapa_general, col_mapa_detalle = st.columns([1, 2]) 

                # 2. Generación de los Mapas Folium
                consulta_wgs = consulta.to_crs(epsg=4326)
                interseccion_wgs = interseccion.to_crs(epsg=4326)
                reserva_wgs = reserva_gdf.to_crs(epsg=4326)
                centroid = consulta_wgs.geometry.iloc[0].centroid
                
                # Calcular bounds
                bounds_predio = consulta_wgs.total_bounds
                bounds_reserva = reserva_wgs.total_bounds
                
                # MAPA 1: UBICACIÓN GENERAL (Contexto de la Reserva)
                with col_mapa_general:
                    st.subheader("🗺️ Ubicación General")
                    mapa_general = folium.Map(
                        location=[(bounds_reserva[1] + bounds_reserva[3])/2, 
                                 (bounds_reserva[0] + bounds_reserva[2])/2],
                        zoom_start=11
                    )
                    
                    # Añadir límite de la reserva
                    folium.GeoJson(
                        reserva_wgs.to_json(),
                        style_function=lambda x: {'fillColor': 'lightgreen', 
                                                 'color': 'darkgreen', 
                                                 'weight': 2,
                                                 'fillOpacity': 0.2},
                        tooltip=folium.Tooltip("Reserva Forestal Protectora")
                    ).add_to(mapa_general)
                    
                    # Añadir predio
                    folium.GeoJson(
                        consulta_wgs.to_json(),
                        style_function=lambda x: {'fillColor': 'blue', 
                                                 'color': 'darkblue', 
                                                 'weight': 3,
                                                 'fillOpacity': 0.6},
                        tooltip=folium.Tooltip(f"Predio: {referencia}")
                    ).add_to(mapa_general)
                    
                    # Ajustar vista a la reserva
                    mapa_general.fit_bounds([
                        [bounds_reserva[1], bounds_reserva[0]], 
                        [bounds_reserva[3], bounds_reserva[2]]
                    ])
                    
                    st_folium(mapa_general, height=500, key="mapa_general")


                # MAPA 2: MAPA DETALLADO DE AFECTACIÓN (Ajuste automático)
                with col_mapa_detalle:
                    st.subheader("🌿 Detalle de Afectación")
                    mapa_detalle = folium.Map(
                        location=[centroid.y, centroid.x],
                        zoom_start=15
                    ) 
                    
                    # Añadir límite del predio
                    folium.GeoJson(
                        consulta_wgs.to_json(),
                        style_function=lambda x: {'fillColor': 'none', 
                                                 'color': 'blue', 
                                                 'weight': 3, 
                                                 'fillOpacity': 0.1},
                        tooltip=folium.Tooltip(f"Predio: {referencia}")
                    ).add_to(mapa_detalle)
                    
                    # Añadir zonas de afectación
                    folium.GeoJson(
                        interseccion_wgs.to_json(),
                        style_function=lambda x: {
                            'fillColor': COLORES_CATEGORIA.get(x['properties']['ZONIFICACI'], '#808080'),
                            'color': 'black',
                            'weight': 1,
                            'fillOpacity': 0.7
                        },
                        tooltip=folium.GeoJsonTooltip(
                            fields=['ZONIFICACI', 'ACTO_ZONIF'], 
                            aliases=['Zona:', 'Norma:']
                        )
                    ).add_to(mapa_detalle)
                    
                    # CORREGIDO: Ajustar vista automáticamente al predio
                    mapa_detalle.fit_bounds([
                        [bounds_predio[1], bounds_predio[0]], 
                        [bounds_predio[3], bounds_predio[2]]
                    ])
                    
                    st_folium(mapa_detalle, height=500, key="mapa_afectacion")

                # 3. FILA DE RESUMEN Y DETALLE (Debajo de los mapas)
                st.markdown("---")
                col_resumen, col_detalle = st.columns([1, 2])
                
                with col_resumen:
                    st.subheader("📊 Resumen de Áreas")
                    
                    # CORREGIDO: Métricas sin valores negativos
                    col1, col2 = st.columns(2)
                    with col1:
                        st.metric(label="Área Total Predio", value=formatear_area(area_predio))
                    with col2:
                        st.metric(
                            label="Área No Afectada", 
                            value=formatear_area(area_no_afectada), 
                            delta=f"{porcentaje_no_afectado:.2f}%"
                        )
                        
                        st.metric(
                            label="Área Afectada por Reserva", 
                            value=formatear_area(area_afectada), 
                            delta=f"{porcentaje_afectado:.2f}%", 
                            delta_color="inverse"
                        )
                    
                    st.subheader("🛠️ Acciones")

                    # Botón para el PDF
                    if st.button("📄 Generar Reporte PDF", key="btn_pdf"):
                        # Preparar datos para el PDF con colores
                        interseccion_pdf = interseccion.copy()
                        interseccion_pdf["color"] = interseccion_pdf["ZONIFICACI"].map(COLORES_CATEGORIA).fillna("#808080")
                        
                        generar_pdf(referencia, consulta, interseccion_pdf, 
                                  area_predio, area_afectada, porcentaje_afectado, 
                                  reserva_gdf)

                with col_detalle:
                    st.subheader("🔍 Detalle de Zonificación Afectada")
                    
                    # Expander para detalles de la tabla
                    with st.expander("Ver Tabla Completa de Zonas Afectadas"):
                        interseccion['Area_m2'] = interseccion.geometry.area
                        interseccion_detallada = interseccion[['ZONIFICACI', 'DESCRIPCI', 'ACTO_ZONIF', 'ACT_PERMIT', 'ACT_PROHIB', 'Area_m2']].copy()
                        interseccion_detallada['Área'] = interseccion_detallada['Area_m2'].apply(formatear_area)
                        interseccion_detallada.drop(columns=['Area_m2'], inplace=True)
                        st.dataframe(interseccion_detallada, width="stretch", hide_index=True)
                
            # Si NO hay afectación
            else:
                st.success(f"✅ Predio encontrado. CHIP: **{referencia}**")
                st.info("ℹ️ **El predio no presenta afectación.** No intersecta con la zonificación de la Reserva Forestal Protectora.")
                st.metric(label="Área Total Predio", value=formatear_area(area_predio))
                
            st.markdown("---")
            if st.button("↩️ **Iniciar Nueva Consulta**", key="btn_nueva_consulta"):
                st.session_state.resultado_consulta = None 
                st.rerun() 
                
        except Exception as e:
            st.error(f"Error desconocido durante el procesamiento de resultados. Intente de nuevo: {e}")
            st.session_state.resultado_consulta = {'tipo': 'error', 'mensaje': f"Error en el procesamiento: {e}"}
            st.rerun()