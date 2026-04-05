import streamlit as st
import pandas as pd
import time
from datetime import datetime
import io
import pytz
import plotly.express as px
import pickle
import os

# --- CONFIGURACIÓN Y ESTÉTICA ---
st.set_page_config(page_title="McMediciones Pro", layout="wide", page_icon="🍔")
BOGOTA_TZ = pytz.timezone('America/Bogota')
HISTORY_FILE = "mcmediciones_history.pkl"
MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

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
    [data-testid="collapsedControl"] {display: none;}
    [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

# --- MANEJO DE MEMORIA ---
def load_history():
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "rb") as f: return pickle.load(f)
        except: return []
    return []

def save_history():
    with open(HISTORY_FILE, "wb") as f: pickle.dump(st.session_state.history, f)

if 'history' not in st.session_state: st.session_state.history = load_history()
if 'active_session' not in st.session_state: st.session_state.active_session = None 
if 'selected_history' not in st.session_state: st.session_state.selected_history = None

# Variables temporales
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
    
    if session_data['orders']:
        df_ord = pd.DataFrame(session_data['orders'])
        df_arr = df_ord[['Canal', 'Inicio']].copy()
        df_arr['Timestamp'] = pd.to_datetime(df_arr['Inicio'])
        dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
        resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
        resumen.index = resumen.index.astype(str)
        resumen['Total Intervalo'] = resumen.sum(axis=1)
        total_franja = pd.DataFrame(resumen.sum()).T
        total_franja.index = ['TOTAL FRANJA']
        pd.concat([resumen, total_franja]).to_excel(writer, sheet_name='Demanda_5min')
        comp = df_ord[df_ord['Estado'] == 'Completado']
        if not comp.empty:
            cols = ['ID', 'Canal', 'Número de Items', 'Hora Inicio', 'Hora Entrega', 'Tiempo Total(s)', 'Cola Salida']
            comp[cols].to_excel(writer, sheet_name='Pedidos_E2E', index=False)
            
    if session_data['stations']:
        df_est = pd.DataFrame(session_data['stations'])
        comp_est = df_est[df_est['Fase'] == 'Completado']
        if not comp_est.empty:
            params = comp_est.groupby(['Estación', 'Estado']).agg(
                n=('Duración (s)', 'count'), mediana=('Duración (s)', 'median'),
                Min=('Duración (s)', 'min'), Max=('Duración (s)', 'max'),
                P10=('Duración (s)', lambda x: x.quantile(0.10)), P90=('Duración (s)', lambda x: x.quantile(0.90))
            ).reset_index()
            params.to_excel(writer, sheet_name='Resumen_Estaciones', index=False)
            comp_est.to_excel(writer, sheet_name='Datos_Estaciones', index=False)

    if session_data['queues']: pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas_5min', index=False)
    if session_data['capacity']: pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad', index=False)
    if session_data['events']: pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos', index=False)
    writer.close()
    return output.getvalue()

def render_full_view(data, is_history=False):
    t1, t2, t3 = st.tabs(["🚶‍♂️ 1. Pedidos y Colas", "🍳 2. Operación Interna", "📊 3. Dashboard"])
    
    with t1:
        st.subheader("I. Historial de Colas Registradas")
        if data['queues']: st.dataframe(pd.DataFrame(data['queues']).iloc[::-1], use_container_width=True)
        else: st.info("No se registraron colas.")
        
        st.write("---")
        st.subheader("II. Tabla de Pedidos End-to-End")
        if data['orders']:
            df_ord = pd.DataFrame(data['orders'])
            comp = df_ord[df_ord['Estado'] == 'Completado']
            if not comp.empty:
                st.dataframe(comp[['ID', 'Hora Inicio', 'Hora Entrega', 'Canal', 'Número de Items', 'Tiempo Total(s)', 'Cola Salida']].iloc[::-1], use_container_width=True)
            else: st.info("No hay pedidos completados.")
        else: st.info("No hay pedidos.")

    with t2:
        st.subheader("IV. Tiempos por Estación")
        if data['stations']:
            df_est = pd.DataFrame(data['stations'])
            comp_est = df_est[df_est['Fase'] == 'Completado']
            if not comp_est.empty:
                st.dataframe(comp_est[['ID', 'Hora Inicio', 'Fin', 'Estación', 'Estado', 'Duración (s)', 'Nota']].iloc[::-1], use_container_width=True)
            else: st.info("No hay estaciones completadas.")
        
        c_cap, c_ev = st.columns(2)
        with c_cap:
            st.subheader("V. Capacidad Efectiva")
            if data['capacity']: st.dataframe(pd.DataFrame(data['capacity']), use_container_width=True)
            else: st.info("Sin registros de capacidad.")
        with c_ev:
            st.subheader("VI. Registro de Eventos")
            if data['events']: st.dataframe(pd.DataFrame(data['events']), use_container_width=True)
            else: st.info("Sin eventos registrados.")

    with t3:
        if data['orders']:
            df_ord = pd.DataFrame(data['orders'])
            st.subheader("Curva de Demanda por Canal (5 min)")
            df_arr = df_ord[['Canal', 'Inicio']].copy()
            df_arr['Timestamp'] = pd.to_datetime(df_arr['Inicio'])
            dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
            fig = px.line(dem_5m, x='Timestamp', y='Pedidos', color='Canal', markers=True, color_discrete_map=MC_COLORS)
            st.plotly_chart(fig, use_container_width=True)
            resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
            resumen.index = resumen.index.astype(str)
            resumen['Total Intervalo'] = resumen.sum(axis=1)
            total_franja = pd.DataFrame(resumen.sum()).T
            total_franja.index = ['TOTAL FRANJA']
            st.dataframe(pd.concat([resumen, total_franja]), use_container_width=True)
        
        if data['stations']:
            st.write("---")
            st.subheader("Parámetros Estadísticos por Estación")
            df_est = pd.DataFrame(data['stations'])
            comp_est = df_est[df_est['Fase'] == 'Completado']
            if not comp_est.empty:
                params = comp_est.groupby(['Estación', 'Estado']).agg(
                    n=('Duración (s)', 'count'), mediana=('Duración (s)', 'median'),
                    Min=('Duración (s)', 'min'), Max=('Duración (s)', 'max'),
                    P10=('Duración (s)', lambda x: x.quantile(0.10)), P90=('Duración (s)', lambda x: x.quantile(0.90))
                ).reset_index()
                st.dataframe(params.round(1), use_container_width=True)

# --- PANTALLAS ---

if st.session_state.selected_history:
    s = st.session_state.selected_history
    if st.button("⬅️ VOLVER AL INICIO", type="primary"):
        st.session_state.selected_history = None
        st.rerun()
    st.title(f"📂 Consulta de Sesión: {s['info']['franja']}")
    render_full_view(s['data'], is_history=True)
    st.download_button("📥 Descargar Excel Maestro", export_excel_maestro(s['data'], s['info']), f"Reporte_{s['info']['id']}.xlsx", use_container_width=True)

elif st.session_state.active_session is None:
    st.title("🍔 McMediciones Pro")
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        st.subheader("Nueva Medición")
        with st.container(border=True):
            obs_name = st.text_input("Observador")
            obs_date = st.date_input("Fecha", datetime.now(BOGOTA_TZ).date())
            franja = st.selectbox("Franja", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
            if st.button("▶ EMPEZAR", type="primary", use_container_width=True):
                if obs_name:
                    st.session_state.active_session = {"date": obs_date.strftime("%Y-%m-%d"), "franja": f"{obs_date} | {franja}", "observer": obs_name, "id": int(time.time())}
                    st.session_state.orders, st.session_state.queues, st.session_state.stations, st.session_state.capacity, st.session_state.events = [], [], [], [], []
                    st.session_state.order_counter = 1
                    st.rerun()
                else: st.error("Ingresa tu nombre.")
    with c2:
        st.subheader("Historial")
        if st.session_state.history:
            for s in reversed(st.session_state.history):
                with st.container(border=True):
                    st.write(f"**Franja:** {s['info']['franja']} | **Obs:** {s['info']['observer']}")
                    b1, b2, b3 = st.columns(3)
                    with b1: st.download_button("💾 Excel", export_excel_maestro(s['data'], s['info']), f"Data_{s['info']['id']}.xlsx", key=f"ex_{s['info']['id']}", use_container_width=True)
                    with b2: 
                        if st.button("📊 Ver Sesión", key=f"v_{s['info']['id']}", use_container_width=True):
                            st.session_state.selected_history = s
                            st.rerun()
                    with b3:
                        if st.button("Borrar", key=f"del_{s['info']['id']}", use_container_width=True):
                            st.session_state.history = [h for h in st.session_state.history if h['info']['id'] != s['info']['id']]
                            save_history(); st.rerun()
        else: st.info("No hay sesiones.")

else:
    h1, h2 = st.columns([4, 1])
    h1.title("Medición en Vivo")
    if h2.button("⏹ FINALIZAR", type="primary", use_container_width=True):
        st.session_state.history.append({"info": st.session_state.active_session, "data": {'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events}})
        st.session_state.active_session = None
        save_history(); st.rerun()

    st.caption(f"👤 {st.session_state.active_session['observer']} | ⏱️ {st.session_state.active_session['franja']}")
    tab_p, tab_i, tab_d = st.tabs(["🚶‍♂️ 1. Pedidos y Colas", "🍳 2. Operación Interna", "📊 3. Dashboard Vivo"])

    with tab_p:
        with st.container(border=True):
            st.subheader("🚨 Registrar Colas (5 min)")
            c_qc, c_qa, c_qb = st.columns([1, 1, 1])
            qc = c_qc.number_input("Caja", 0); qa = c_qa.number_input("AutoMac", 0)
            if c_qb.button("Guardar Fila", use_container_width=True):
                st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Caja": qc, "AutoMac": qa}); st.rerun()
            if st.session_state.queues: st.dataframe(pd.DataFrame(st.session_state.queues).iloc[::-1], height=150)
        with st.container(border=True):
            st.subheader("➕ Nuevo Pedido")
            c1, c2, c3 = st.columns([2, 1, 1])
            n_can = c1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"], label_visibility="collapsed")
            n_itm = c2.number_input("Items:", 1, label_visibility="collapsed")
            if c3.button("▶ Iniciar", type="primary", use_container_width=True):
                pid = f"P-{st.session_state.order_counter:03d}"; st.session_state.order_counter += 1
                st.session_state.orders.append({'ID': pid, 'Canal': n_can, 'Número de Items': n_itm, 'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), 'Inicio': datetime.now(BOGOTA_TZ), 'Fin_Orden_ts': None, 'Fin Orden': "-", 'Fin_Espera_ts': None, 'Hora Entrega': "-", 'T. Orden(s)': 0, 'T. Espera(s)': 0, 'Tiempo Total(s)': 0, 'Cola Salida': 0}); st.rerun()
        if st.button("🔄 Actualizar Relojes", use_container_width=True): st.rerun()
        co1, co2 = st.columns(2)
        with co1:
            st.markdown("### 📝 Tomando Pedido")
            for p in [p for p in st.session_state.orders if p['Estado'] == 'Ordering']:
                with st.container(border=True):
                    st.write(f"**{p['ID']}** | {p['Canal']} | {p['Número de Items']} ítems | ⏱️ {int(time.time() - p['Inicio_ts'])}s")
                    if st.button("Pasar a Espera", key=f"w_{p['ID']}", use_container_width=True):
                        p['Estado'] = 'Waiting'; p['Fin_Orden_ts'] = time.time(); p['Fin Orden'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['T. Orden(s)'] = int(p['Fin_Orden_ts'] - p['Inicio_ts']); st.rerun()
        with co2:
            st.markdown("### ⏳ En Espera")
            for p in [p for p in st.session_state.orders if p['Estado'] == 'Waiting']:
                with st.container(border=True):
                    st.write(f"**{p['ID']}** | {p['Canal']} | ⏱️ {int(time.time() - p['Inicio_ts'])}s")
                    cf = st.number_input("Cola Salida", 0, key=f"cf_{p['ID']}") if p['Canal'] != 'Delivery/Pickup' else 0
                    if st.button("✅ Entregar", key=f"f_{p['ID']}", type="primary", use_container_width=True):
                        p['Estado'] = 'Completado'; p['Fin_Espera_ts'] = time.time(); p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['T. Espera(s)'] = int(p['Fin_Espera_ts'] - p['Fin_Orden_ts']); p['Tiempo Total(s)'] = int(p['Fin_Espera_ts'] - p['Inicio_ts']); p['Cola Salida'] = cf; st.rerun()
        st.subheader("📋 Pedidos Finalizados")
        if st.session_state.orders:
            df_comp = pd.DataFrame([p for p in st.session_state.orders if p['Estado'] == 'Completado'])
            if not df_comp.empty: st.dataframe(df_comp[['ID', 'Hora Inicio', 'Hora Entrega', 'Canal', 'Número de Items', 'Tiempo Total(s)']].iloc[::-1], use_container_width=True)

    with tab_i:
        with st.container(border=True):
            st.subheader("🍳 IV. Tiempos por Estación")
            sc1, sc2, sc3 = st.columns([2, 2, 1])
            s_n = sc1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
            s_e = sc2.selectbox("Estado:", ["Hecho a pedido", "Listo"])
            if sc3.button("▶ Iniciar Est.", type="primary", use_container_width=True):
                sid = f"E-{len(st.session_state.stations) + 1:03d}"
                st.session_state.stations.append({'ID': sid, 'Estación': s_n, 'Estado': s_e, 'Fase': 'Corriendo', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), 'Fin': '-', 'Duración (s)': 0, 'Nota': '-'}); st.rerun()
            for e in [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']:
                with st.container(border=True):
                    st.write(f"**{e['ID']}** | {e['Estación']} | ⏱️ {int(time.time() - e['Inicio_ts'])}s")
                    n = st.text_input("Nota:", key=f"nt_{e['ID']}")
                    if st.button("🛑 Fin", key=f"fe_{e['ID']}"):
                        e['Fase'] = 'Completado'; e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'); e['Duración (s)'] = int(time.time() - e['Inicio_ts']); e['Nota'] = n; st.rerun()
            df_est_f = pd.DataFrame([e for e in st.session_state.stations if e['Fase'] == 'Completado'])
            if not df_est_f.empty: st.dataframe(df_est_f[['ID', 'Hora Inicio', 'Fin', 'Estación', 'Estado', 'Duración (s)', 'Nota']].iloc[::-1], use_container_width=True)
        c_ca, c_ev = st.columns(2)
        with c_ca:
            st.subheader("👥 V. Capacidad")
            mo = st.selectbox("Momento:", ["Inicio", "Pico"])
            pe = st.number_input("Pers", 0); eq = st.number_input("Eqps", 0)
            if st.button("Guardar Cap.", use_container_width=True): st.session_state.capacity.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": mo, "Pers": pe, "Eqps": eq}); st.rerun()
            if st.session_state.capacity: st.dataframe(pd.DataFrame(st.session_state.capacity).iloc[::-1], use_container_width=True)
        with c_ev:
            st.subheader("⚠️ VI. Eventos")
            ev = st.text_input("Evento:")
            if st.button("Guardar Evento", use_container_width=True): st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": ev}); st.rerun()
            if st.session_state.events: st.dataframe(pd.DataFrame(st.session_state.events).iloc[::-1], use_container_width=True)

    with tab_d:
        render_dashboard({'orders': st.session_state.orders, 'stations': st.session_state.stations})
        st.download_button("📥 Excel Vivo", export_excel_maestro({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events}, st.session_state.active_session), "Reporte_Vivo.xlsx", use_container_width=True)
