import streamlit as st
import pandas as pd
import time
from datetime import datetime
import io
import pytz
import plotly.express as px
import pickle
import os

# --- ZONA HORARIA Y CONFIGURACIÓN ---
st.set_page_config(page_title="McMediciones Pro", layout="wide", page_icon="🍔")
BOGOTA_TZ = pytz.timezone('America/Bogota')
HISTORY_FILE = "mcmediciones_history.pkl"
MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

# --- MEMORIA PERSISTENTE ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "rb") as f: return pickle.load(f)
        except Exception: return []
    return []

def save_history():
    with open(HISTORY_FILE, "wb") as f: pickle.dump(st.session_state.history, f)

# --- DISEÑO ESTÉTICO (ESTILO SABANA) ---
st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    div[data-testid="stVerticalBlock"] > div[style*="border"] { 
        border-radius: 12px; border: 1px solid #cbd5e1; background-color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.05); 
    }
    .stTabs button p { font-size: 18px !important; font-weight: bold !important; color: #1e293b !important; }
    
    .pill-red { background-color: #fee2e2; color: #b91c1c; border: 1px solid #fca5a5; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    .pill-yellow { background-color: #fef3c7; color: #b45309; border: 1px solid #fde68a; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    .pill-black { background-color: #f1f5f9; color: #0f172a; border: 1px solid #cbd5e1; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    .pill-blue { background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    .pill-green { background-color: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    
    .table-head-cell { text-align: center; font-weight: bold; color: #334155; font-size: 14px; border-bottom: 2px solid #cbd5e1; padding-bottom: 8px; margin-bottom: 4px; }
    .table-data-cell { text-align: center; color: #475569; font-size: 14px; padding: 6px 0px; border-bottom: 1px solid #f1f5f9; }
    [data-testid="collapsedControl"] {display: none;}
    [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

# --- INICIALIZACIÓN DE VARIABLES ---
if 'history' not in st.session_state: st.session_state.history = load_history()
if 'active_session' not in st.session_state: st.session_state.active_session = None 
if 'selected_history' not in st.session_state: st.session_state.selected_history = None

if 'arrivals' not in st.session_state: st.session_state.arrivals = []
if 'orders' not in st.session_state: st.session_state.orders = []
if 'queues' not in st.session_state: st.session_state.queues = []
if 'stations' not in st.session_state: st.session_state.stations = []
if 'capacity' not in st.session_state: st.session_state.capacity = []
if 'events' not in st.session_state: st.session_state.events = []
if 'order_counter' not in st.session_state: st.session_state.order_counter = 1

# --- FUNCIONES DE EXPORTACIÓN Y DASHBOARD ---
def export_excel_maestro(session_data, session_info):
    output = io.BytesIO()
    writer = pd.ExcelWriter(output, engine='xlsxwriter')
    
    # 1. Demanda
    if session_data['arrivals']:
        df_arr = pd.DataFrame(session_data['arrivals'])
        df_arr['Timestamp'] = pd.to_datetime(df_arr['Timestamp'])
        dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
        resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
        resumen['Total Intervalo'] = resumen.sum(axis=1)
        total_franja = resumen.sum().to_frame().T
        total_franja.index = ['TOTAL FRANJA']
        pd.concat([resumen, total_franja]).to_excel(writer, sheet_name='Demanda_5min')
    
    # 2. End to End
    if session_data['orders']:
        df_ord = pd.DataFrame(session_data['orders'])
        comp = df_ord[df_ord['Estado'] == 'Completado']
        if not comp.empty:
            cols = ['ID', 'Canal', 'Número de Items', 'Hora Inicio', 'Fin Orden', 'Hora Entrega', 'T. Orden(s)', 'T. Espera(s)', 'Tiempo Total(s)', 'Cola Salida', 'Obs']
            comp[cols].to_excel(writer, sheet_name='Pedidos_E2E', index=False)
            
    # 3. Estaciones
    if session_data['stations']:
        df_est = pd.DataFrame(session_data['stations'])
        comp_est = df_est[df_est['Fase'] == 'Completado']
        if not comp_est.empty:
            params = comp_est.groupby(['Estación', 'Estado']).agg(
                n=('Duración (s)', 'count'), mediana=('Duración (s)', 'median'),
                Mínimo=('Duración (s)', 'min'), Máximo=('Duración (s)', 'max'),
                P10=('Duración (s)', lambda x: x.quantile(0.10)), P90=('Duración (s)', lambda x: x.quantile(0.90))
            ).reset_index()
            params.to_excel(writer, sheet_name='Parametros_Estacion', index=False)
            comp_est[['ID', 'Estación', 'Estado', 'Inicio', 'Fin', 'Duración (s)', 'Nota']].to_excel(writer, sheet_name='Estaciones_Data_Cruda', index=False)

    if session_data['queues']: pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas', index=False)
    if session_data['capacity']: pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad', index=False)
    if session_data['events']: pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos', index=False)
    
    writer.close()
    return output.getvalue()

def render_dashboard(data):
    st.header("📈 Dashboard (Rúbrica 3.4)")
    
    # Curva de Demanda
    st.subheader("1. Curva de Demanda por Canal (5 min)")
    if data['arrivals']:
        df_arr = pd.DataFrame(data['arrivals'])
        df_arr['Timestamp'] = pd.to_datetime(df_arr['Timestamp'])
        dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
        fig = px.line(dem_5m, x='Timestamp', y='Pedidos', color='Canal', markers=True, color_discrete_map=MC_COLORS)
        st.plotly_chart(fig, use_container_width=True)
        
        resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
        resumen['Total Intervalo'] = resumen.sum(axis=1)
        total_franja = resumen.sum().to_frame().T
        total_franja.index = ['TOTAL FRANJA']
        st.dataframe(pd.concat([resumen, total_franja]), use_container_width=True)
    else: st.info("No hay datos de demanda registrados.")

    st.write("---")
    
    # Tabla E2E
    st.subheader("2. Tabla de Pedidos End-to-End")
    if data['orders']:
        df_ord = pd.DataFrame(data['orders'])
        comp = df_ord[df_ord['Estado'] == 'Completado']
        if not comp.empty:
            cols = ['ID', 'Canal', 'Número de Items', 'Hora Inicio', 'Hora Entrega', 'Tiempo Total(s)', 'Cola Salida', 'Obs']
            st.dataframe(comp[cols].iloc[::-1], use_container_width=True)
        else: st.info("No hay pedidos completados.")
    else: st.info("No hay datos de pedidos.")

    st.write("---")

    # Tabla Estaciones
    st.subheader("3. Tabla de Parámetros por Estación")
    if data['stations']:
        df_est = pd.DataFrame(data['stations'])
        comp_est = df_est[df_est['Fase'] == 'Completado']
        if not comp_est.empty:
            params = comp_est.groupby(['Estación', 'Estado']).agg(
                n=('Duración (s)', 'count'), mediana=('Duración (s)', 'median'),
                Mínimo=('Duración (s)', 'min'), Máximo=('Duración (s)', 'max'),
                P10=('Duración (s)', lambda x: x.quantile(0.10)), P90=('Duración (s)', lambda x: x.quantile(0.90))
            ).reset_index()
            st.dataframe(params.round(1), use_container_width=True)
        else: st.info("No hay estaciones completadas.")
    else: st.info("No hay datos de estaciones.")


# ==========================================
# RUTEO DE PANTALLAS
# ==========================================

# --- MODO HISTORIAL (SOLO LECTURA) ---
if st.session_state.selected_history:
    s = st.session_state.selected_history
    st.markdown(f"## 📂 Historial: {s['info']['franja']}")
    st.caption(f"Observador: {s['info']['observer']}")
    
    if st.button("⬅️ VOLVER AL INICIO", type="primary"):
        st.session_state.selected_history = None
        st.rerun()
        
    st.write("---")
    render_dashboard(s['data'])
    
    st.write("---")
    st.download_button("📥 Descargar Excel Maestro de esta Sesión", export_excel_maestro(s['data'], s['info']), f"Reporte_{s['info']['date']}.xlsx")

# --- PANTALLA PRINCIPAL (LOGIN Y SESIONES PASADAS) ---
elif st.session_state.active_session is None:
    st.title("🍔 McMediciones Pro")
    st.write("Sistema de rastreo operativo. Selecciona o inicia una sesión.")
    st.write("---")
    
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        st.subheader("Iniciar Nueva Medición")
        with st.container(border=True):
            obs_name = st.text_input("Nombre del Observador")
            obs_date = st.date_input("Fecha de Medición", datetime.now(BOGOTA_TZ).date())
            franja = st.selectbox("Franja", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
            
            if st.button("▶ INICIAR TRABAJO DE CAMPO", type="primary", use_container_width=True):
                if obs_name:
                    st.session_state.active_session = {
                        "date": obs_date.strftime("%Y-%m-%d"), 
                        "franja": f"{obs_date.strftime('%Y-%m-%d')} | {franja}",
                        "start_time": datetime.now(BOGOTA_TZ), 
                        "observer": obs_name, 
                        "id_sesion": int(time.time())
                    }
                    st.session_state.arrivals, st.session_state.orders, st.session_state.queues = [], [], []
                    st.session_state.stations, st.session_state.capacity, st.session_state.events = [], [], []
                    st.session_state.order_counter = 1
                    st.rerun()
                else: st.error("Ingresa tu nombre.")
                    
    with c2:
        st.subheader("Historial de Sesiones")
        if st.session_state.history:
            for s in reversed(st.session_state.history):
                with st.container(border=True):
                    st.write(f"**Franja:** {s['info']['franja']} | **Obs:** {s['info']['observer']}")
                    b1, b2, b3 = st.columns(3)
                    with b1: st.download_button("💾 Excel", export_excel_maestro(s['data'], s['info']), f"Data_{s['info']['date']}.xlsx", key=f"ex_{s['info']['id_sesion']}", use_container_width=True)
                    with b2: 
                        if st.button("📊 Ver Tablas", key=f"v_{s['info']['id_sesion']}", use_container_width=True):
                            st.session_state.selected_history = s
                            st.rerun()
                    with b3:
                        if st.button("Eliminar", key=f"del_{s['info']['id_sesion']}", use_container_width=True):
                            st.session_state.history = [h for h in st.session_state.history if h['info']['id_sesion'] != s['info']['id_sesion']]
                            save_history()
                            st.rerun()
        else:
            st.info("No hay sesiones guardadas.")

# --- MODO EN VIVO (TRABAJO DE CAMPO) ---
else:
    h1, h2 = st.columns([4, 1])
    h1.title("Medición en Tiempo Real")
    if h2.button("⏹ FINALIZAR SESIÓN", type="primary", use_container_width=True):
        session_data = {
            'arrivals': st.session_state.arrivals, 'orders': st.session_state.orders, 'queues': st.session_state.queues,
            'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events
        }
        st.session_state.history.append({"info": st.session_state.active_session, "data": session_data})
        st.session_state.active_session = None
        save_history()
        st.rerun()

    st.caption(f"👤 {st.session_state.active_session['observer']} | ⏱️ {st.session_state.active_session['franja']}")
    tab_fo, tab_int, tab_dash = st.tabs(["🚶‍♂️ 1. Control de Demanda y Pedidos", "🛠️ 2. Operación Interna", "📊 3. Dashboard"])

    # ---------------------------------------------------------
    # TAB 1: FRONT OF HOUSE
    # ---------------------------------------------------------
    with tab_fo:
        
        # 1. Colas y Llegadas Integradas
        with st.container(border=True):
            st.subheader("🚨 Llegadas Rápidas y Colas (Intervalo 5 min)")
            c1, c2, c3, c4 = st.columns([1, 1, 1, 2])
            if c1.button("🚶‍♂️ +1 Caja", use_container_width=True): st.session_state.arrivals.append({"Canal": "Caja", "Timestamp": datetime.now(BOGOTA_TZ)})
            if c2.button("🚗 +1 AutoMac", use_container_width=True): st.session_state.arrivals.append({"Canal": "AutoMac", "Timestamp": datetime.now(BOGOTA_TZ)})
            if c3.button("🛵 +1 Delivery", use_container_width=True): st.session_state.arrivals.append({"Canal": "Delivery/Pickup", "Timestamp": datetime.now(BOGOTA_TZ)})
            
            with c4.popover("📝 Registrar Colas"):
                qc = st.number_input("Fila Caja", 0)
                qa = st.number_input("Fila AutoMac", 0)
                if st.button("Guardar", use_container_width=True):
                    st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Caja": qc, "AutoMac": qa})
                    st.rerun()
                    
        if st.session_state.queues:
            with st.expander("Ver tabla de Colas Registradas"):
                st.dataframe(pd.DataFrame(st.session_state.queues).iloc[::-1], use_container_width=True)

        # 2. Medición End to End (Ordering -> Waiting)
        st.write("---")
        with st.container(border=True):
            st.subheader("➕ Nuevo Pedido (End-to-End)")
            c1, c2, c3 = st.columns([2, 1, 1])
            n_canal = c1.selectbox("Canal a medir:", ["Caja", "AutoMac", "Delivery/Pickup"], label_visibility="collapsed")
            n_items = c2.number_input("Número de items:", min_value=1, value=1, label_visibility="collapsed")
            if c3.button("▶ Iniciar Pedido", type="primary", use_container_width=True):
                pid = f"P-{st.session_state.order_counter:03d}"
                st.session_state.order_counter += 1
                st.session_state.orders.append({
                    'ID': pid, 'Canal': n_canal, 'Número de Items': n_items, 'Estado': 'Ordering',
                    'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"),
                    'Fin_Orden_ts': None, 'Fin Orden': "-", 'Fin_Espera_ts': None, 'Hora Entrega': "-",
                    'T. Orden(s)': 0, 'T. Espera(s)': 0, 'Tiempo Total(s)': 0, 'Cola Salida': 0, 'Obs': "-"
                })
                st.rerun()

        # Tableros en Vivo
        pedidos_ord = [p for p in st.session_state.orders if p['Estado'] == 'Ordering']
        pedidos_wait = [p for p in st.session_state.orders if p['Estado'] == 'Waiting']
        
        col_ord, col_wait = st.columns(2)
        
        with col_ord:
            st.markdown("### 📝 Tomando Pedido")
            if not pedidos_ord: st.info("No hay pedidos en caja/speaker.")
            for p in pedidos_ord:
                with st.container(border=True):
                    t_trans = int(time.time() - p['Inicio_ts'])
                    pill = "pill-red" if p['Canal'] == "Caja" else "pill-yellow" if p['Canal'] == "AutoMac" else "pill-black"
                    st.markdown(f"**{p['ID']}** | <span class='{pill}'>{p['Canal']}</span>", unsafe_allow_html=True)
                    st.write(f"⏱️ Tiempo: **{t_trans}s** | {p['Número de Items']} items")
                    
                    if st.button("Pasar a Espera", key=f"mw_{p['ID']}", use_container_width=True):
                        p['Estado'] = 'Waiting'
                        p['Fin_Orden_ts'] = time.time()
                        p['Fin Orden'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S")
                        p['T. Orden(s)'] = int(p['Fin_Orden_ts'] - p['Inicio_ts'])
                        st.rerun()

        with col_wait:
            st.markdown("### ⏳ En Espera")
            if not pedidos_wait: st.info("No hay clientes esperando entrega.")
            for p in pedidos_wait:
                with st.container(border=True):
                    t_tot = int(time.time() - p['Inicio_ts'])
                    pill = "pill-blue"
                    st.markdown(f"**{p['ID']}** | <span class='{pill}'>Esperando</span>", unsafe_allow_html=True)
                    st.write(f"⏱️ Total: **{t_tot}s** | {p['Canal']}")
                    
                    c_in1, c_in2 = st.columns(2)
                    if p['Canal'] in ["Caja", "AutoMac"]:
                        cola_f = c_in1.number_input("Cola Salida", 0, key=f"cf_{p['ID']}")
                        obs = "-"
                    else:
                        cola_f = 0
                        obs = c_in1.selectbox("Obs", ["Ninguna", "Domiciliario tarde", "Congestión"], key=f"ob_{p['ID']}")

                    if c_in2.button("✅ Entregar", key=f"mf_{p['ID']}", type="primary", use_container_width=True):
                        p['Estado'] = 'Completado'
                        p['Fin_Espera_ts'] = time.time()
                        p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S")
                        p['T. Espera(s)'] = int(p['Fin_Espera_ts'] - p['Fin_Orden_ts'])
                        p['Tiempo Total(s)'] = int(p['Fin_Espera_ts'] - p['Inicio_ts'])
                        p['Cola Salida'] = cola_f
                        p['Obs'] = obs
                        st.rerun()

        # Tabla Completa
        st.write("---")
        st.subheader("📋 Tabla de Pedidos")
        if st.session_state.orders:
            df_ord = pd.DataFrame(st.session_state.orders)
            cols = ['ID', 'Hora Inicio', 'Fin Orden', 'Hora Entrega', 'Canal', 'Número de Items', 'T. Orden(s)', 'T. Espera(s)', 'Tiempo Total(s)', 'Estado']
            st.dataframe(df_ord[cols].iloc[::-1], use_container_width=True)

    # ---------------------------------------------------------
    # TAB 2: OPERACIÓN INTERNA
    # ---------------------------------------------------------
    with tab_int:
        with st.container(border=True):
            st.subheader("🍳 IV. Tiempos por Estación")
            sc1, sc2, sc3 = st.columns([2, 2, 1])
            s_nom = sc1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
            s_est = sc2.selectbox("Estado:", ["Hecho a pedido", "Listo (Ya preparado)"])
            if sc3.button("▶ Iniciar", type="primary", use_container_width=True):
                sid = f"E-{len(st.session_state.stations) + 1:03d}"
                st.session_state.stations.append({
                    'ID': sid, 'Estación': s_nom, 'Estado': s_est, 'Fase': 'Corriendo', 
                    'Inicio_ts': time.time(), 'Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'),
                    'Fin': '-', 'Duración (s)': 0, 'Nota': '-'
                })
                st.rerun()

            est_act = [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']
            for e in est_act:
                with st.container(border=True):
                    ec1, ec2, ec3 = st.columns([2, 2, 1])
                    t_seg = int(time.time() - e['Inicio_ts'])
                    ec1.markdown(f"**{e['ID']}** | {e['Estación']} | <span class='pill-green'>Corriendo: {t_seg}s</span>", unsafe_allow_html=True)
                    nota = ec2.text_input("Nota breve:", key=f"nt_{e['ID']}")
                    if ec3.button("🛑 Fin", key=f"fb_{e['ID']}"):
                        e['Fase'] = 'Completado'
                        e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S')
                        e['Duración (s)'] = int(time.time() - e['Inicio_ts'])
                        e['Nota'] = nota
                        st.rerun()

            if st.session_state.stations:
                df_est = pd.DataFrame(st.session_state.stations)
                st.dataframe(df_est[['ID', 'Inicio', 'Fin', 'Estación', 'Estado', 'Duración (s)', 'Nota']].iloc[::-1], use_container_width=True)

        c_cap, c_ev = st.columns(2)
        with c_cap:
            with st.container(border=True):
                st.subheader("👥 V. Capacidad")
                momento = st.selectbox("Momento:", ["Inicio de Franja", "Pico de Congestión"])
                z_p, z_e = st.columns(2)
                p_val = z_p.number_input("Personas", 0)
                e_val = z_e.number_input("Equipos", 0)
                if st.button("Guardar Cap.", use_container_width=True):
                    st.session_state.capacity.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": momento, "Pers": p_val, "Eqps": e_val})
                    st.rerun()
                if st.session_state.capacity: st.dataframe(pd.DataFrame(st.session_state.capacity).iloc[::-1])

        with c_ev:
            with st.container(border=True):
                st.subheader("⚠️ VI. Eventos")
                evento = st.text_input("Descripción:")
                if st.button("Guardar Evento", use_container_width=True):
                    st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": evento})
                    st.rerun()
                if st.session_state.events: st.dataframe(pd.DataFrame(st.session_state.events).iloc[::-1])

    # ---------------------------------------------------------
    # TAB 3: DASHBOARD EN VIVO
    # ---------------------------------------------------------
    with tab_dash:
        session_data = {
            'arrivals': st.session_state.arrivals, 'orders': st.session_state.orders, 'queues': st.session_state.queues,
            'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events
        }
        render_dashboard(session_data)
