import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime
import io
import time

# ==========================================
# CONFIGURACIÓN INICIAL
# ==========================================
st.set_page_config(page_title="McMediciones", layout="wide", page_icon="🍔")
MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

@st.cache_resource
def init_connection() -> Client:
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None
supabase = init_connection()

if 'configurado' not in st.session_state: st.session_state.configurado = False
if 'pedidos_activos' not in st.session_state: st.session_state.pedidos_activos = {}
if 'estaciones_activas' not in st.session_state: st.session_state.estaciones_activas = {}

# ==========================================
# 1. PANTALLA DE INICIO (LOGIN AISLADO)
# ==========================================
if not st.session_state.configurado:
    st.markdown("""<style>[data-testid="stSidebar"] {display: none;}</style>""", unsafe_allow_html=True)
    
    st.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/McDonald%27s_Golden_Arches.svg/100px-McDonald%27s_Golden_Arches.svg.png")
    st.title("Bienvenido a McMediciones 🍔")
    st.markdown("Por favor, configura tu sesión antes de empezar el trabajo de campo.")
    
    with st.form("login_form"):
        col1, col2 = st.columns(2)
        obs = col1.text_input("👤 Nombre del Observador", placeholder="Ej: Tu Nombre")
        dia = col2.date_input("📅 Fecha de Medición")
        franja = st.selectbox("⏱️ Franja de Medición", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
        
        if st.form_submit_button("Empezar Mediciones 🚀", use_container_width=True):
            if obs:
                st.session_state.obs = obs
                st.session_state.franja_oficial = f"{dia} | {franja}"
                st.session_state.configurado = True
                st.rerun()
            else:
                st.error("⚠️ Debes ingresar tu nombre para continuar.")
    st.stop()

# ==========================================
# 2. BARRA LATERAL (NAVEGACIÓN)
# ==========================================
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/McDonald%27s_Golden_Arches.svg/100px-McDonald%27s_Golden_Arches.svg.png")
st.sidebar.title("Menú")
menu = st.sidebar.radio("Ir a:", ["📊 Dashboard y Reportes", "1️⃣ Pedidos y Tiempos", "2️⃣ Operación Interna"])

st.sidebar.divider()
st.sidebar.caption("Datos de la sesión:")
st.sidebar.info(f"👤 **{st.session_state.obs}**\n\n⏱️ {st.session_state.franja_oficial}")

if st.sidebar.button("Cerrar Sesión"):
    st.session_state.configurado = False
    st.session_state.pedidos_activos = {}
    st.rerun()

# ==========================================
# MÓDULO 1: DASHBOARD Y REPORTES (VIVO E HISTORIAL)
# ==========================================
if menu == "📊 Dashboard y Reportes":
    st.title("📈 Centro de Análisis y Reportes")
    
    if supabase:
        # Obtener todas las franjas históricas para el filtro
        fechas_data = supabase.table('arrivals').select('franja').execute().data
        todas_franjas = list(set([f['franja'] for f in fechas_data])) if fechas_data else []
        if st.session_state.franja_oficial not in todas_franjas:
            todas_franjas.insert(0, st.session_state.franja_oficial)
        
        col_filtro, col_auto = st.columns([3, 1])
        franja_seleccionada = col_filtro.selectbox("🔎 Filtrar por Sesión / Historial:", sorted(todas_franjas, reverse=True))
        auto_refresh = col_auto.toggle("🔄 Auto-Actualizar (Vivo)")

        # Descargar datos de la base de datos (filtrados)
        df_arr = pd.DataFrame(supabase.table('arrivals').select('*').eq('franja', franja_seleccionada).execute().data)
        df_ord = pd.DataFrame(supabase.table('tracked_orders').select('*').eq('franja', franja_seleccionada).execute().data)
        df_est = pd.DataFrame(supabase.table('station_observations').select('*').eq('franja', franja_seleccionada).execute().data)

        tab1, tab2, tab3, tab_pdf = st.tabs(["📉 1. Demanda (5 min)", "📋 2. End-to-End", "⏱️ 3. Estaciones", "📄 Generar Reporte"])

        with tab1:
            st.subheader(f"Curva de Demanda - {franja_seleccionada}")
            if not df_arr.empty:
                df_arr['timestamp'] = pd.to_datetime(df_arr['timestamp']).dt.tz_localize(None)
                dem_5m = df_arr.groupby([pd.Grouper(key='timestamp', freq='5min'), 'channel']).size().reset_index(name='pedidos')
                fig = px.line(dem_5m, x='timestamp', y='pedidos', color='channel', markers=True, color_discrete_map=MC_COLORS)
                st.plotly_chart(fig, use_container_width=True)
                
                resumen = dem_5m.pivot(index='timestamp', columns='channel', values='pedidos').fillna(0).astype(int)
                resumen['Total Intervalo'] = resumen.sum(axis=1)
                total_franja = resumen.sum().to_frame().T
                total_franja.index = ['TOTAL FRANJA']
                resumen_final = pd.concat([resumen, total_franja])
                st.dataframe(resumen_final, use_container_width=True)
            else:
                st.info("No hay datos de llegadas en esta sesión.")

        with tab2:
            st.subheader("Tabla de Pedidos End-to-End")
            df_clean = pd.DataFrame()
            if not df_ord.empty:
                cols = [c for c in ['channel', 'items_count', 'duration_seconds', 'cola_fin', 'observaciones'] if c in df_ord.columns]
                df_clean = df_ord[cols].copy()
                df_clean.rename(columns={'channel': 'Canal', 'items_count': 'Tamaño (Items)', 'duration_seconds': 'Tiempo Total (seg)', 'cola_fin': 'Cola Final', 'observaciones': 'Observaciones'}, inplace=True)
                st.dataframe(df_clean.sort_index(ascending=False), use_container_width=True)
            else:
                st.info("No hay pedidos registrados.")

        with tab3:
            st.subheader("Parámetros Estadísticos por Estación")
            params = pd.DataFrame()
            if not df_est.empty:
                params = df_est.groupby(['station', 'component_state']).agg(
                    n=('duration_seconds', 'count'), mediana=('duration_seconds', 'median'),
                    Mínimo=('duration_seconds', 'min'), Máximo=('duration_seconds', 'max'),
                    P10=('duration_seconds', lambda x: x.quantile(0.10)), P90=('duration_seconds', lambda x: x.quantile(0.90))
                ).reset_index()
                params.rename(columns={'station': 'Estación', 'component_state': 'Estado/Tipo'}, inplace=True)
                st.dataframe(params.round(1), use_container_width=True)
            else:
                st.info("No hay mediciones de estaciones.")

        with tab_pdf:
            st.subheader("📄 Reporte Ejecutivo para Exportar")
            st.markdown(f"**Sesión:** {franja_seleccionada}")
            st.markdown("---")
            st.markdown("### Resumen Rápido")
            col_a, col_b, col_c = st.columns(3)
            col_a.metric("Total Pedidos Atendidos", len(df_ord))
            col_b.metric("Llegadas Registradas", len(df_arr))
            if not df_ord.empty: col_c.metric("Tiempo Promedio (seg)", int(df_ord['duration_seconds'].mean()))
            st.markdown("---")
            st.markdown("> 💡 **Para guardar como PDF:** Presiona `Ctrl + P` (o Comando + P en Mac), elige 'Guardar como PDF' y tendrás este documento listo para enviar.")
            st.divider()

        if not df_arr.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if 'resumen_final' in locals(): resumen_final.to_excel(writer, sheet_name='Demanda')
                if not df_clean.empty: df_clean.to_excel(writer, sheet_name='End_to_End', index=False)
                if not params.empty: params.to_excel(writer, sheet_name='Estaciones', index=False)
            st.download_button("📥 Descargar Todo a Excel (Data Cruda)", output.getvalue(), f"Reporte_{franja_seleccionada}.xlsx", use_container_width=True)

        # Lógica de auto-refresh
        if auto_refresh:
            time.sleep(5)
            st.rerun()

# ==========================================
# MÓDULO 2: PEDIDOS Y TIEMPOS (CAPTURA)
# ==========================================
elif menu == "1️⃣ Pedidos y Tiempos":
    st.title("📊 Registro de Pedidos Multitarea")

    with st.expander("🚨 Registrar Colas Globales (Cada 5 min)", expanded=False):
        qc1, qc2 = st.columns(2)
        cola_caja_int = qc1.number_input("Personas en fila (Caja)", min_value=0, key="qcaja")
        cola_auto_int = qc2.number_input("Carros en Drive-Thru", min_value=0, key="qauto")
        if st.button("Guardar Colas Actuales"):
            if supabase: supabase.table("interval_queues").insert({"franja": st.session_state.franja_oficial, "cola_caja": cola_caja_int, "cola_automac": cola_auto_int, "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
            st.success("Colas guardadas exitosamente.")

    st.divider()
    st.subheader("➕ Nuevo Pedido")
    with st.container():
        c1, c2, c3 = st.columns([2, 1, 1])
        nuevo_canal = c1.selectbox("Canal del Pedido", ["Caja", "AutoMac", "Delivery/Pickup"], label_visibility="collapsed")
        nuevo_items = c2.number_input("Cantidad de Ítems", min_value=1, value=1, label_visibility="collapsed")
        
        if c3.button("▶️ Iniciar Reloj", use_container_width=True):
            pid = f"P-{datetime.now().strftime('%H%M%S')}"
            st.session_state.pedidos_activos[pid] = {"canal": nuevo_canal, "items": nuevo_items, "inicio": datetime.now()}
            if supabase: supabase.table("arrivals").insert({"franja": st.session_state.franja_oficial, "channel": nuevo_canal, "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
            st.rerun()

    st.divider()
    c_tit, c_btn = st.columns([3, 1])
    c_tit.subheader(f"⏱️ Pedidos en curso ({len(st.session_state.pedidos_activos)})")
    if c_btn.button("🔄 Actualizar Cronómetros", use_container_width=True): st.rerun()
    
    if not st.session_state.pedidos_activos:
        st.info("No hay pedidos en curso.")
    
    for pid, p in list(st.session_state.pedidos_activos.items()):
        with st.container():
            pc1, pc2, pc3 = st.columns([3, 2, 2])
            t_trans = int((datetime.now() - p['inicio']).total_seconds())
            mins, segs = divmod(t_trans, 60)
            
            pc1.info(f"**{p['canal']}** ({p['items']} ítems) | Inició: {p['inicio'].strftime('%H:%M:%S')} | ⏳ {mins}m {segs}s")
            
            with pc2:
                if p['canal'] in ["Caja", "AutoMac"]:
                    cola_fin = st.number_input("Cola al salir:", min_value=0, key=f"cf_{pid}", label_visibility="collapsed")
                    obs_final = "N/A"
                else:
                    cola_fin = 0
                    obs_final = st.selectbox("Espera:", ["Ninguna", "Leve", "Alta"], key=f"ob_{pid}", label_visibility="collapsed")

            if pc3.button("🛑 Finalizar", key=f"btn_{pid}", use_container_width=True):
                dur = int((datetime.now() - p['inicio']).total_seconds())
                if supabase:
                    supabase.table("tracked_orders").insert({"franja": st.session_state.franja_oficial, "channel": p['canal'], "size": "N/A", "items_count": p['items'], "cola_inicio": 0, "cola_fin": cola_fin, "observaciones": obs_final, "duration_seconds": dur, "start_time": p['inicio'].isoformat(), "observer_name": st.session_state.obs}).execute()
                del st.session_state.pedidos_activos[pid]
                st.rerun()

# ==========================================
# MÓDULO 3: OPERACIÓN INTERNA
# ==========================================
elif menu == "2️⃣ Operación Interna":
    st.title("🛠️ Operación Interna y Cocina")

    c_tit_est, c_btn_est = st.columns([3, 1])
    c_tit_est.subheader("Tiempos por Estación")
    if c_btn_est.button("🔄 Actualizar Tiempos"): st.rerun()

    with st.expander("➕ Iniciar Estación", expanded=False):
        sc1, sc2 = st.columns(2)
        s_nom = sc1.selectbox("Estación", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
        s_est = sc2.radio("Estado Componente", ["Se preparó al momento", "Ya estaba listo"])
        if st.button("▶️ Iniciar Reloj Estación"):
            sid = f"E-{datetime.now().strftime('%H%M%S')}"
            st.session_state.estaciones_activas[sid] = {"est": s_nom, "estado": s_est, "inicio": datetime.now()}
            st.rerun()

    for sid, s in list(st.session_state.estaciones_activas.items()):
        sc1, sc2 = st.columns([2, 1])
        t_trans = int((datetime.now() - s['inicio']).total_seconds())
        m_est, s_est_time = divmod(t_trans, 60)
        
        sc1.warning(f"**{s['est']}** ({s['estado']}) | Inició: {s['inicio'].strftime('%H:%M:%S')} | ⏳ {m_est}m {s_est_time}s")
        with sc2:
            nota_espera = st.selectbox("Espera visible:", ["Ninguna", "Leve", "Alta"], key=f"nesp_{sid}")
            if st.button("🛑 Finalizar", key=f"fbtn_{sid}"):
                dur = int((datetime.now() - s['inicio']).total_seconds())
                if supabase: supabase.table("station_observations").insert({"franja": st.session_state.franja_oficial, "station": s['est'], "component_state": s['estado'], "nota_espera": nota_espera, "duration_seconds": dur, "start_time": s['inicio'].isoformat(), "observer_name": st.session_state.obs}).execute()
                del st.session_state.estaciones_activas[sid]
                st.rerun()
