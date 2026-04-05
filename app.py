import streamlit as st
import pandas as pd
import plotly.express as px
from supabase import create_client, Client
from datetime import datetime, timedelta
import io

# ==========================================
# CONFIGURACIÓN Y ELIMINACIÓN DE BARRA LATERAL
# ==========================================
st.set_page_config(page_title="McMediciones", layout="wide", page_icon="🍔")

st.markdown("""
    <style>
        [data-testid="collapsedControl"] {display: none;}
        [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

@st.cache_resource
def init_connection() -> Client:
    try: return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
    except: return None
supabase = init_connection()

if 'configurado' not in st.session_state: st.session_state.configurado = False
if 'cronos_e2e' not in st.session_state: st.session_state.cronos_e2e = {}
if 'cronos_est' not in st.session_state: st.session_state.cronos_est = {}

# ==========================================
# 1. PANTALLA DE INICIO (LIMPIA)
# ==========================================
if not st.session_state.configurado:
    st.title("🍔 McMediciones")
    st.markdown("### Configuración de Turno")
    
    with st.container(border=True):
        obs = st.text_input("👤 Tu Nombre (Observador)", placeholder="Ej: Caro")
        dia = st.date_input("📅 Fecha")
        franja = st.selectbox("⏱️ Franja de Medición", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
        
        if st.button("🚀 Iniciar Trabajo de Campo", use_container_width=True):
            if obs:
                st.session_state.obs = obs
                st.session_state.franja_oficial = f"{dia} | {franja}"
                st.session_state.configurado = True
                st.rerun()
            else:
                st.error("⚠️ Falta tu nombre.")
    st.stop()

# ==========================================
# 2. MENÚ PRINCIPAL (TABS SUPERIORES)
# ==========================================
c_info, c_salir = st.columns([3, 1])
c_info.caption(f"👤 **{st.session_state.obs}** | ⏱️ {st.session_state.franja_oficial}")
if c_salir.button("Cerrar Sesión", size="small"):
    st.session_state.configurado = False
    st.rerun()

tab_fo, tab_int, tab_dash = st.tabs([
    "🚶‍♂️ Registro de Pedidos", 
    "🛠️ Operación Interna", 
    "📊 Dashboard y Exportar"
])

# ---------------------------------------------------------
# TAB 1: REGISTRO DE PEDIDOS (E2E + Delivery)
# ---------------------------------------------------------
with tab_fo:
    st.header("Control de Demanda y Tiempos")
    
    with st.container(border=True):
        st.subheader("🚨 I. Colas (Alarma 5 min)")
        qc1, qc2 = st.columns(2)
        cola_caja_int = qc1.number_input("Fila Caja (Personas)", min_value=0, key="qcaja")
        cola_auto_int = qc2.number_input("Fila AutoMac (Carros)", min_value=0, key="qauto")
        if st.button("💾 Guardar Colas", use_container_width=True):
            if supabase: supabase.table("interval_queues").insert({"franja": st.session_state.franja_oficial, "cola_caja": cola_caja_int, "cola_automac": cola_auto_int, "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
            st.success("¡Colas registradas!")

    with st.container(border=True):
        st.subheader("👥 II. Llegadas Rápidas (+1)")
        lc1, lc2, lc3 = st.columns(3)
        if lc1.button("🚶‍♂️ +1 Caja", use_container_width=True):
            if supabase: supabase.table("arrivals").insert({"franja": st.session_state.franja_oficial, "channel": "Caja", "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
        if lc2.button("🚗 +1 AutoMac", use_container_width=True):
            if supabase: supabase.table("arrivals").insert({"franja": st.session_state.franja_oficial, "channel": "AutoMac", "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
        if lc3.button("🛵 +1 Delivery", use_container_width=True):
            if supabase: supabase.table("arrivals").insert({"franja": st.session_state.franja_oficial, "channel": "Delivery/Pickup", "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()

    with st.container(border=True):
        st.subheader("⏱️ III. Medir Tiempo de Pedido")
        c1, c2 = st.columns(2)
        nuevo_canal = c1.selectbox("Canal a medir:", ["Caja", "AutoMac", "Delivery/Pickup"])
        nuevo_items = c2.number_input("Cantidad de Ítems (Tamaño):", min_value=1, value=1)
        
        if st.button("▶️ Iniciar Reloj", use_container_width=True, type="primary"):
            pid = f"ORD-{datetime.now().strftime('%H%M%S')}"
            st.session_state.cronos_e2e[pid] = {"canal": nuevo_canal, "items": nuevo_items, "inicio": datetime.now()}
            st.rerun()

        st.divider()
        if st.button("🔄 Actualizar Relojes Activos", use_container_width=True): st.rerun()
        
        for pid, p in list(st.session_state.cronos_e2e.items()):
            with st.expander(f"⏳ {p['canal']} ({p['items']} ítems) - Inició: {p['inicio'].strftime('%H:%M:%S')}", expanded=True):
                t_trans = int((datetime.now() - p['inicio']).total_seconds())
                st.write(f"Tiempo corriendo: **{t_trans} segundos**")
                
                if p['canal'] in ["Caja", "AutoMac"]:
                    cola_fin = st.number_input("Cola al salir:", min_value=0, key=f"cf_{pid}")
                    obs_final = "N/A"
                else:
                    cola_fin = 0
                    obs_final = st.selectbox("Observación de espera:", ["Ninguna", "Domiciliario tarde", "Congestión local"], key=f"ob_{pid}")

                if st.button("🛑 Finalizar Pedido", key=f"btn_{pid}"):
                    dur = int((datetime.now() - p['inicio']).total_seconds())
                    if supabase: supabase.table("tracked_orders").insert({"franja": st.session_state.franja_oficial, "channel": p['canal'], "size": "N/A", "items_count": p['items'], "cola_inicio": 0, "cola_fin": cola_fin, "observaciones": obs_final, "duration_seconds": dur, "start_time": p['inicio'].isoformat(), "observer_name": st.session_state.obs}).execute()
                    del st.session_state.cronos_e2e[pid]
                    st.rerun()

    st.divider()
    st.subheader("📋 Registro en Vivo (Pedidos)")
    if supabase:
        df_live = pd.DataFrame(supabase.table('tracked_orders').select('*').eq('franja', st.session_state.franja_oficial).execute().data)
        if not df_live.empty:
            df_live['Hora Inicio'] = pd.to_datetime(df_live['start_time']).dt.strftime('%H:%M:%S')
            df_live['Hora Fin'] = (pd.to_datetime(df_live['start_time']) + pd.to_timedelta(df_live['duration_seconds'], unit='s')).dt.strftime('%H:%M:%S')
            df_live['Duración (seg)'] = df_live['duration_seconds']
            df_live['Canal'] = df_live['channel']
            df_live['Items'] = df_live['items_count']
            
            columnas_mostrar = ['Hora Inicio', 'Hora Fin', 'Canal', 'Items', 'Duración (seg)']
            st.dataframe(df_live[columnas_mostrar].sort_index(ascending=False), use_container_width=True)
        else:
            st.info("Aún no hay pedidos guardados en esta sesión.")

# ---------------------------------------------------------
# TAB 2: OPERACIÓN INTERNA (ACTUALIZADO A RÚBRICA)
# ---------------------------------------------------------
with tab_int:
    st.header("🛠️ Operación Interna")
    
    # IV. ESTACIONES
    with st.container(border=True):
        st.subheader("IV. Tiempos por Estación (Submuestra)")
        sc1, sc2 = st.columns(2)
        s_nom = sc1.selectbox("Estación observada:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
        s_est = sc2.selectbox("Estado del componente:", ["Hecho a pedido", "Listo (Ya preparado)"])
        
        if st.button("▶️ Iniciar Reloj Estación", use_container_width=True):
            sid = f"EST-{datetime.now().strftime('%H%M%S')}"
            st.session_state.cronos_est[sid] = {"est": s_nom, "estado": s_est, "inicio": datetime.now()}
            st.rerun()

        for sid, s in list(st.session_state.cronos_est.items()):
            with st.expander(f"🍳 {s['est']} ({s['estado']})", expanded=True):
                nota_espera = st.text_input("Nota breve si hay espera visible:", key=f"nesp_{sid}")
                if st.button("🛑 Finalizar Estación", key=f"fbtn_{sid}"):
                    dur = int((datetime.now() - s['inicio']).total_seconds())
                    if supabase: supabase.table("station_observations").insert({"franja": st.session_state.franja_oficial, "station": s['est'], "component_state": s['estado'], "nota_espera": nota_espera, "duration_seconds": dur, "start_time": s['inicio'].isoformat(), "observer_name": st.session_state.obs}).execute()
                    del st.session_state.cronos_est[sid]
                    st.rerun()
        
        # TABLA EN VIVO: ESTACIONES
        if supabase:
            df_est_live = pd.DataFrame(supabase.table('station_observations').select('*').eq('franja', st.session_state.franja_oficial).execute().data)
            if not df_est_live.empty:
                st.markdown("**📋 Registros guardados:**")
                df_est_live['Inicio'] = pd.to_datetime(df_est_live['start_time']).dt.strftime('%H:%M:%S')
                df_est_live.rename(columns={'station': 'Estación', 'component_state': 'Estado', 'duration_seconds': 'Duración(s)', 'nota_espera': 'Nota'}, inplace=True)
                st.dataframe(df_est_live[['Inicio', 'Estación', 'Estado', 'Duración(s)', 'Nota']].sort_index(ascending=False), use_container_width=True)

    # V. CAPACIDAD EFECTIVA
    with st.container(border=True):
        st.subheader("👥 V. Capacidad Efectiva")
        momento = st.selectbox("Momento del registro:", ["Inicio de Franja", "Pico de Congestión"])
        zonas = ["Parrilla", "Freidoras", "Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Entrega"]
        cap_data = {}
        for z in zonas:
            zc1, zc2 = st.columns(2)
            cap_data[f"{z}_p"] = zc1.number_input(f"Pers. en {z}", min_value=0, key=f"p_{z}")
            cap_data[f"{z}_e"] = zc2.number_input(f"Equipos {z}", min_value=0, key=f"e_{z}")
        if st.button("💾 Guardar Capacidad", use_container_width=True):
            if supabase: supabase.table("capacity").insert({"franja": st.session_state.franja_oficial, "momento": momento, "datos": cap_data, "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
            st.success("¡Capacidad guardada!")

        # TABLA EN VIVO: CAPACIDAD
        if supabase:
            df_cap_live = pd.DataFrame(supabase.table('capacity').select('*').eq('franja', st.session_state.franja_oficial).execute().data)
            if not df_cap_live.empty:
                st.markdown("**📋 Registros guardados:**")
                df_cap_live['Hora'] = pd.to_datetime(df_cap_live['timestamp']).dt.strftime('%H:%M:%S')
                df_cap_live.rename(columns={'momento': 'Momento'}, inplace=True)
                st.dataframe(df_cap_live[['Hora', 'Momento']].sort_index(ascending=False), use_container_width=True)

    # VI. REGISTRO DE EVENTOS
    with st.container(border=True):
        st.subheader("⚠️ VI. Registro de Eventos")
        st.caption("Ej: Reposición de insumos, limpieza rápida, cambios de dotación, fallas.")
        evento = st.text_input("Tipo de evento y descripción:")
        if st.button("📝 Guardar Evento", use_container_width=True):
            if supabase and evento: supabase.table("events").insert({"franja": st.session_state.franja_oficial, "descripcion": evento, "timestamp": datetime.now().isoformat(), "observer_name": st.session_state.obs}).execute()
            st.success("Evento guardado.")

        # TABLA EN VIVO: EVENTOS
        if supabase:
            df_ev_live = pd.DataFrame(supabase.table('events').select('*').eq('franja', st.session_state.franja_oficial).execute().data)
            if not df_ev_live.empty:
                st.markdown("**📋 Registros guardados:**")
                df_ev_live['Hora'] = pd.to_datetime(df_ev_live['timestamp']).dt.strftime('%H:%M:%S')
                df_ev_live.rename(columns={'descripcion': 'Evento'}, inplace=True)
                st.dataframe(df_ev_live[['Hora', 'Evento']].sort_index(ascending=False), use_container_width=True)

# ---------------------------------------------------------
# TAB 3: DASHBOARD Y REPORTES OFICIALES
# ---------------------------------------------------------
with tab_dash:
    st.header("📈 Centro de Análisis y Reportes")
    
    if st.button("🔄 Traer Datos Nuevos de la Nube", type="primary", use_container_width=True):
        st.rerun()

    if supabase:
        df_arr = pd.DataFrame(supabase.table('arrivals').select('*').eq('franja', st.session_state.franja_oficial).execute().data)
        df_ord = pd.DataFrame(supabase.table('tracked_orders').select('*').eq('franja', st.session_state.franja_oficial).execute().data)
        df_est = pd.DataFrame(supabase.table('station_observations').select('*').eq('franja', st.session_state.franja_oficial).execute().data)

        if df_arr.empty and df_ord.empty:
            st.warning("Aún no hay datos para procesar las gráficas.")
        else:
            st.subheader("Curva de Demanda por Canal (Intervalos 5 min)")
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

            st.divider()
            st.subheader("📂 Reporte Completo de la Sesión")
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
                if 'resumen_final' in locals(): resumen_final.to_excel(writer, sheet_name='Demanda_Curva')
                if not df_ord.empty: df_ord.to_excel(writer, sheet_name='Pedidos_E2E_Delivery', index=False)
                if not params.empty: params.to_excel(writer, sheet_name='Estaciones_Resumen', index=False)
            st.download_button("📥 Descargar Reporte Completo (Excel Maestro)", output.getvalue(), "McMediciones_Reporte_Maestro.xlsx", use_container_width=True, type="primary")
