import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime
import io

# ==========================================
# CONFIGURACIÓN VISUAL Y DE CONEXIÓN
# ==========================================
st.set_page_config(page_title="McMediciones", layout="wide", page_icon="🍔")
MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

@st.cache_resource
def init_connection() -> Client:
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None
supabase = init_connection()

if 'pedidos_activos' not in st.session_state: st.session_state.pedidos_activos = {}
if 'estaciones_activas' not in st.session_state: st.session_state.estaciones_activas = {}

# ==========================================
# MENÚ LATERAL (Configuración)
# ==========================================
st.sidebar.image("https://upload.wikimedia.org/wikipedia/commons/thumb/3/36/McDonald%27s_Golden_Arches.svg/200px-McDonald%27s_Golden_Arches.svg.png", width=80)
st.sidebar.title("McMediciones")

observador = st.sidebar.text_input("👤 Observador:", placeholder="Nombre")
franja = st.sidebar.selectbox("⏱️ Franja:", ["10:30–12:30", "11:30–14:00", "18:00–21:00"])
st.sidebar.divider()
menu = st.sidebar.radio("Navegación:", ["1️⃣ Demanda y Tiempos", "2️⃣ Operación Interna", "📊 Salida de Datos Oficial"])

if not observador and menu != "📊 Salida de Datos Oficial":
    st.warning("⚠️ Ingresa tu nombre en el menú lateral para habilitar la captura.")
    st.stop()

# ==========================================
# PANTALLA 1: DEMANDA Y TIEMPOS
# ==========================================
if menu == "1️⃣ Demanda y Tiempos":
    st.title("📊 Control de Demanda y Front of House")

    st.subheader("I. Registro de Colas (Alarma 5 min)")
    with st.expander("🚨 Guardar Colas del Intervalo", expanded=False):
        qc1, qc2 = st.columns(2)
        cola_caja_int = qc1.number_input("Personas en fila (Caja)", min_value=0)
        cola_auto_int = qc2.number_input("Carros en Drive-Thru", min_value=0)
        if st.button("Guardar Colas"):
            if supabase:
                supabase.table("interval_queues").insert({
                    "franja": franja, "cola_caja": cola_caja_int, "cola_automac": cola_auto_int, 
                    "timestamp": datetime.now().isoformat(), "observer_name": observador
                }).execute()
            st.success("Guardado.")

    st.subheader("I. Llegadas Continuas (+1)")
    c1, c2, c3 = st.columns(3)
    def add_arrival(chan):
        if supabase: supabase.table("arrivals").insert({"franja": franja, "channel": chan, "timestamp": datetime.now().isoformat(), "observer_name": observador}).execute()
        st.toast(f"✅ Pedido en {chan}")

    with c1: st.button("👤 +1 Caja", on_click=add_arrival, args=("Caja",), use_container_width=True)
    with c2: st.button("🚗 +1 AutoMac", on_click=add_arrival, args=("AutoMac",), use_container_width=True)
    with c3: st.button("🛵 +1 Delivery/Pickup", on_click=add_arrival, args=("Delivery/Pickup",), use_container_width=True)

    st.divider()

    st.subheader("II & III. Tiempos de Pedidos End-to-End")
    with st.expander("➕ Iniciar Nuevo Pedido", expanded=False):
        t_canal = st.selectbox("Canal a medir", ["Caja", "AutoMac", "Delivery/Pickup"])
        if t_canal in ["Caja", "AutoMac"]:
            tc1, tc2, tc3 = st.columns(3)
            t_size = tc1.selectbox("Tamaño", ["Pequeño", "Mediano", "Grande"])
            t_items = tc2.number_input("Cant. Ítems", min_value=1, value=1)
            t_cola_ini = tc3.number_input("Cola Inicial", min_value=0)
        else:
            t_size = "N/A"
            t_items = 0
            t_cola_ini = 0

        if st.button("▶️ Iniciar Reloj"):
            pid = f"P-{datetime.now().strftime('%H%M%S')}"
            st.session_state.pedidos_activos[pid] = {"canal": t_canal, "size": t_size, "items": t_items, "cola_ini": t_cola_ini, "inicio": datetime.now()}
            st.rerun()

    for pid, p in list(st.session_state.pedidos_activos.items()):
        pc1, pc2 = st.columns([2, 1])
        pc1.info(f"**{p['canal']}** | Inició: {p['inicio'].strftime('%H:%M:%S')}")
        with pc2:
            if p['canal'] in ["Caja", "AutoMac"]:
                cola_fin = st.number_input("Cola Final:", min_value=0, key=f"cf_{pid}")
                obs_final = "N/A"
            else:
                cola_fin = 0
                obs_final = st.selectbox("¿Hubo espera?", ["Ninguna", "Leve", "Alta"], key=f"obs_{pid}")

            if st.button("🛑 Finalizar", key=f"btn_{pid}"):
                dur = int((datetime.now() - p['inicio']).total_seconds())
                if supabase:
                    supabase.table("tracked_orders").insert({
                        "franja": franja, "channel": p['canal'], "size": p['size'], "items_count": p['items'],
                        "cola_inicio": p['cola_ini'], "cola_fin": cola_fin, "observaciones": obs_final,
                        "duration_seconds": dur, "start_time": p['inicio'].isoformat(), "observer_name": observador
                    }).execute()
                del st.session_state.pedidos_activos[pid]
                st.rerun()

# ==========================================
# PANTALLA 2: OPERACIÓN INTERNA
# ==========================================
elif menu == "2️⃣ Operación Interna":
    st.title("🛠️ Operación Interna y Cocina")

    st.subheader("IV. Tiempos por Estación")
    with st.expander("➕ Iniciar Estación", expanded=False):
        sc1, sc2 = st.columns(2)
        s_nom = sc1.selectbox("Estación", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
        s_est = sc2.radio("Estado Componente", ["Se preparó al momento", "Ya estaba listo"])
        if st.button("▶️ Iniciar Reloj"):
            sid = f"E-{datetime.now().strftime('%H%M%S')}"
            st.session_state.estaciones_activas[sid] = {"est": s_nom, "estado": s_est, "inicio": datetime.now()}
            st.rerun()

    for sid, s in list(st.session_state.estaciones_activas.items()):
        sc1, sc2 = st.columns([2, 1])
        sc1.warning(f"**{s['est']}** ({s['estado']}) | Inició: {s['inicio'].strftime('%H:%M:%S')}")
        with sc2:
            nota_espera = st.selectbox("Espera visible:", ["Ninguna", "Leve", "Alta"], key=f"nesp_{sid}")
            if st.button("🛑 Finalizar", key=f"fbtn_{sid}"):
                dur = int((datetime.now() - s['inicio']).total_seconds())
                if supabase:
                    supabase.table("station_observations").insert({
                        "franja": franja, "station": s['est'], "component_state": s['estado'],
                        "nota_espera": nota_espera, "duration_seconds": dur, 
                        "start_time": s['inicio'].isoformat(), "observer_name": observador
                    }).execute()
                del st.session_state.estaciones_activas[sid]
                st.rerun()

    st.divider()

    st.subheader("V. Capacidad Efectiva")
    with st.expander("📋 Registrar Capacidad", expanded=False):
        momento = st.radio("Momento:", ["Inicio de Franja", "Pico de Congestión"], horizontal=True)
        zonas = ["Parrilla", "Freidoras", "Ensamble", "Bebidas", "Staging", "Entrega"]
        cap_data = {}
        for z in zonas:
            zc1, zc2 = st.columns(2)
            cap_data[f"{z}_p"] = zc1.number_input(f"Pers. {z}", min_value=0, key=f"p_{z}")
            cap_data[f"{z}_e"] = zc2.number_input(f"Equip. {z}", min_value=0, key=f"e_{z}")
        if st.button("💾 Guardar Capacidad"):
            if supabase: supabase.table("capacity").insert({"franja": franja, "momento": momento, "datos": cap_data, "timestamp": datetime.now().isoformat(), "observer_name": observador}).execute()
            st.success("Guardado.")

    st.divider()
    st.subheader("VI. Registro de Novedades")
    evento = st.text_input("Descripción libre:", placeholder="Ej: Falla en equipo, cliente molesto...")
    if st.button("📝 Guardar Evento"):
        if supabase and evento:
            supabase.table("events").insert({"franja": franja, "descripcion": evento, "timestamp": datetime.now().isoformat(), "observer_name": observador}).execute()
            st.success("Evento guardado.")

# ==========================================
# PANTALLA 3: DASHBOARDS
# ==========================================
elif menu == "📊 Salida de Datos Oficial":
    st.title("📊 Salida de Datos: McMediciones")
    
    if supabase:
        df_arr = pd.DataFrame(supabase.table('arrivals').select('*').execute().data)
        df_ord = pd.DataFrame(supabase.table('tracked_orders').select('*').execute().data)
        df_est = pd.DataFrame(supabase.table('station_observations').select('*').execute().data)

        tab1, tab2, tab3 = st.tabs(["📉 Curva de Demanda", "📋 Tabla End-to-End", "⏱️ Estaciones"])

        with tab1:
            st.subheader("Curva de Demanda por Canal (5 min)")
            if not df_arr.empty:
                df_arr['timestamp'] = pd.to_datetime(df_arr['timestamp']).dt.tz_localize(None)
                dem_5m = df_arr.groupby([pd.Grouper(key='timestamp', freq='5min'), 'channel']).size().reset_index(name='pedidos')
                fig = px.line(dem_5m, x='timestamp', y='pedidos', color='channel', markers=True, color_discrete_map=MC_COLORS)
                st.plotly_chart(fig, use_container_width=True)
                
                resumen = dem_5m.pivot(index='timestamp', columns='channel', values='pedidos').fillna(0).astype(int)
                resumen['Total Intervalo'] = resumen.sum(axis=1)
                st.dataframe(resumen, use_container_width=True)
                st.metric("Total de la Franja Observada", len(df_arr))

        with tab2:
            st.subheader("Tabla de Pedidos End-to-End")
            if not df_ord.empty:
                cols = [c for c in ['channel', 'size', 'items_count', 'duration_seconds'] if c in df_ord.columns]
                df_clean = df_ord[cols].copy()
                st.dataframe(df_clean, use_container_width=True)

        with tab3:
            st.subheader("Tabla de Parámetros por Estación")
            if not df_est.empty:
                params = df_est.groupby(['station', 'component_state']).agg(
                    n=('duration_seconds', 'count'), mediana=('duration_seconds', 'median'),
                    Mínimo=('duration_seconds', 'min'), Máximo=('duration_seconds', 'max'),
                    P10=('duration_seconds', lambda x: x.quantile(0.10)), P90=('duration_seconds', lambda x: x.quantile(0.90))
                ).reset_index()
                st.dataframe(params.round(1), use_container_width=True)

        st.divider()
        if not df_arr.empty:
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if 'resumen' in locals(): resumen.to_excel(writer, sheet_name='Demanda_5min')
                if not df_ord.empty: df_clean.to_excel(writer, sheet_name='Pedidos_E2E', index=False)
                if not df_est.empty: params.to_excel(writer, sheet_name='Estaciones', index=False)
            st.download_button("📥 Descargar Reporte Final (Excel)", output.getvalue(), "Reporte_Salida_Datos.xlsx")