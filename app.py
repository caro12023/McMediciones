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
    .pill-blue { background-color: #eff6ff; color: #1d4ed8; border: 1px solid #bfdbfe; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    .pill-green { background-color: #ecfdf5; color: #047857; border: 1px solid #a7f3d0; padding: 4px 12px; border-radius: 9999px; font-size: 13px; font-weight: 600; }
    [data-testid="collapsedControl"] {display: none;}
    [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

# --- MEMORIA ---
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

# Variables vivas
if 'orders' not in st.session_state: st.session_state.orders = []
if 'queues' not in st.session_state: st.session_state.queues = []
if 'stations' not in st.session_state: st.session_state.stations = []
if 'capacity' not in st.session_state: st.session_state.capacity = []
if 'events' not in st.session_state: st.session_state.events = []
if 'order_counter' not in st.session_state: st.session_state.order_counter = 1

# --- FUNCIONES DE APOYO ---
def get_safe_id(info):
    return info.get('id', info.get('id_sesion', int(time.time())))

def export_excel_maestro(session_data, session_info):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if session_data.get('orders'):
            df_ord = pd.DataFrame(session_data['orders'])
            if not df_ord.empty:
                # Demanda
                df_arr = df_ord[['Canal', 'Inicio']].copy()
                df_arr['Timestamp'] = pd.to_datetime(df_arr['Inicio'])
                dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
                resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
                resumen.index = resumen.index.astype(str)
                resumen['Total Intervalo'] = resumen.sum(axis=1)
                pd.concat([resumen, pd.DataFrame(resumen.sum()).T.rename(index={0: 'TOTAL'})]).to_excel(writer, sheet_name='Demanda_5min')
                # Pedidos
                df_ord.drop(columns=['Inicio'], errors='ignore').to_excel(writer, sheet_name='Pedidos_E2E', index=False)
        
        if session_data.get('stations'):
            pd.DataFrame(session_data['stations']).to_excel(writer, sheet_name='Estaciones', index=False)
        if session_data.get('queues'): pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas', index=False)
        if session_data.get('capacity'): pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad', index=False)
        if session_data.get('events'): pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos', index=False)
    return output.getvalue()

def render_app_view(data, mode="vivo"):
    t1, t2, t3, t4 = st.tabs(["🏃‍♂️ 1. Pedidos y Colas", "🍳 2. Estaciones", "📊 3. Capacidad y Eventos", "📈 4. Dashboard"])
    
    with t1:
        if mode == "vivo":
            st.subheader("🚨 Registrar Colas (Cada 5 min)")
            c_qc, c_qa, c_qb = st.columns([1, 1, 1])
            qc = c_qc.number_input("Caja", 0); qa = c_qa.number_input("AutoMac", 0)
            if c_qb.button("💾 Guardar Fila", use_container_width=True):
                st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Caja": qc, "AutoMac": qa}); st.rerun()
            st.divider()
            st.subheader("➕ Iniciar Nuevo Pedido")
            c1, c2, c3 = st.columns([2, 1, 1])
            n_can = c1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"], key="ncan")
            n_itm = c2.number_input("Items:", 1, key="nitm")
            if c3.button("▶ Iniciar", type="primary", use_container_width=True):
                now = datetime.now(BOGOTA_TZ)
                pid = f"P-{st.session_state.order_counter:03d}"; st.session_state.order_counter += 1
                st.session_state.orders.append({'ID': pid, 'Canal': n_can, 'Número de Items': n_itm, 'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Hora Inicio': now.strftime("%H:%M:%S"), 'Inicio': now, 'Fin Orden': "-", 'Hora Entrega': "-", 'Tiempo Total(s)': 0})
                st.rerun()
            
            st.write("### Tablero de Control")
            if st.button("🔄 Refrescar Tiempos", use_container_width=True): st.rerun()
            co1, co2 = st.columns(2)
            with co1:
                st.caption("📝 Ordering (En Caja/Speaker)")
                for p in [p for p in st.session_state.orders if p['Estado'] == 'Ordering']:
                    with st.container(border=True):
                        st.write(f"**{p['ID']}** | {p['Canal']} | ⏱️ {int(time.time()-p['Inicio_ts'])}s")
                        if st.button(f"➡️ Pasar a Espera {p['ID']}", key=f"w_{p['ID']}", use_container_width=True):
                            p['Estado'] = 'Waiting'; p['Fin Orden'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); st.rerun()
            with co2:
                st.caption("⏳ Waiting (Esperando Comida)")
                for p in [p for p in st.session_state.orders if p['Estado'] == 'Waiting']:
                    with st.container(border=True):
                        st.write(f"**{p['ID']}** | {p['Canal']} | ⏱️ {int(time.time()-p['Inicio_ts'])}s")
                        if st.button(f"✅ Entregar {p['ID']}", key=f"f_{p['ID']}", type="primary", use_container_width=True):
                            p['Estado'] = 'Completado'; p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['Tiempo Total(s)'] = int(time.time() - p['Inicio_ts']); st.rerun()

        st.divider()
        st.subheader("📋 Datos Registrados (Pedidos y Colas)")
        if data['queues']: st.write("**Colas:**"); st.dataframe(pd.DataFrame(data['queues']).iloc[::-1], use_container_width=True)
        if data['orders']:
            st.write("**Pedidos:**")
            df_ord = pd.DataFrame(data['orders'])
            comp = df_ord[df_ord['Estado'] == 'Completado']
            if not comp.empty: st.dataframe(comp[['ID', 'Hora Inicio', 'Hora Entrega', 'Canal', 'Número de Items', 'Tiempo Total(s)']].iloc[::-1], use_container_width=True)

    with t2:
        if mode == "vivo":
            st.subheader("🍳 Medición de Tiempos por Estación")
            ic1, ic2, ic3 = st.columns([2,2,1])
            s_n = ic1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
            s_e = ic2.selectbox("Estado:", ["Hecho a pedido", "Listo"])
            if ic3.button("▶ Iniciar Estación", type="primary", use_container_width=True):
                sid = f"E-{len(st.session_state.stations)+1:03d}"
                st.session_state.stations.append({'ID': sid, 'Estación': s_n, 'Estado': s_e, 'Fase': 'Corriendo', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), 'Fin': '-', 'Duración (s)': 0, 'Nota': '-'}); st.rerun()
            
            for e in [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']:
                with st.container(border=True):
                    st.write(f"**{e['ID']}** - {e['Estación']} - {int(time.time()-e['Inicio_ts'])}s")
                    nt = st.text_input("Nota breve:", key=f"n_{e['ID']}")
                    if st.button("🛑 Finalizar Estación", key=f"ef_{e['ID']}", use_container_width=True):
                        e['Fase'] = 'Completado'; e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'); e['Duración (s)'] = int(time.time()-e['Inicio_ts']); e['Nota'] = nt; st.rerun()

        st.divider()
        if data['stations']:
            st.subheader("📋 Historial de Estaciones")
            df_est = pd.DataFrame(data['stations'])
            if not df_est[df_est['Fase'] == 'Completado'].empty:
                st.dataframe(df_est[df_est['Fase'] == 'Completado'][['ID', 'Hora Inicio', 'Fin', 'Estación', 'Estado', 'Duración (s)', 'Nota']].iloc[::-1], use_container_width=True)

    with t3:
        if mode == "vivo":
            c_ca, c_ev = st.columns(2)
            with c_ca:
                st.subheader("👥 V. Capacidad Efectiva")
                mo = st.selectbox("Momento:", ["Inicio de Franja", "Pico de Congestión"])
                pe = st.number_input("Número de Personas", 0); eq = st.number_input("Equipos Activos", 0)
                if st.button("💾 Guardar Capacidad", use_container_width=True):
                    st.session_state.capacity.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": mo, "Pers": pe, "Eqps": eq}); st.success("Guardado")
            with c_ev:
                st.subheader("⚠️ VI. Registro de Eventos")
                ev = st.text_input("Descripción del evento:")
                if st.button("💾 Guardar Evento", use_container_width=True):
                    st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": ev}); st.success("Guardado")
        
        st.divider()
        st.subheader("📋 Registros de Capacidad y Eventos")
        ec1, ec2 = st.columns(2)
        with ec1: 
            if data['capacity']: st.write("**Capacidad:**"); st.dataframe(pd.DataFrame(data['capacity']), use_container_width=True)
        with ec2: 
            if data['events']: st.write("**Eventos:**"); st.dataframe(pd.DataFrame(data['events']), use_container_width=True)

    with t4:
        st.subheader("📈 Análisis de Datos (Rúbrica 3.4)")
        if data['orders']:
            df_ord = pd.DataFrame(data['orders'])
            if not df_ord.empty:
                st.write("**1. Curva de Demanda (5 min)**")
                df_arr = df_ord[['Canal', 'Inicio']].copy()
                df_arr['Timestamp'] = pd.to_datetime(df_arr['Inicio'])
                dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
                st.plotly_chart(px.line(dem_5m, x='Timestamp', y='Pedidos', color='Canal', markers=True, color_discrete_map=MC_COLORS), use_container_width=True)
                resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
                resumen.index = resumen.index.astype(str)
                st.dataframe(resumen, use_container_width=True)
        
        if data['stations']:
            st.divider()
            st.write("**2. Parámetros por Estación**")
            df_est = pd.DataFrame(data['stations'])
            comp_est = df_est[df_est['Fase'] == 'Completado']
            if not comp_est.empty:
                params = comp_est.groupby(['Estación', 'Estado']).agg(n=('Duración (s)', 'count'), mediana=('Duración (s)', 'median'), Min=('Duración (s)', 'min'), Max=('Duración (s)', 'max')).reset_index()
                st.dataframe(params.round(1), use_container_width=True)

# --- FLUJO PRINCIPAL ---

if st.session_state.selected_history:
    s = st.session_state.selected_history
    if st.button("⬅️ VOLVER AL INICIO", type="primary"):
        st.session_state.selected_history = None; st.rerun()
    st.title(f"📂 Sesión: {s['info']['franja']}")
    render_app_view(s['data'], mode="consulta")
    st.download_button("📥 Descargar Reporte Excel", export_excel_maestro(s['data'], s['info']), f"Reporte_{get_safe_id(s['info'])}.xlsx", use_container_width=True)

elif st.session_state.active_session is None:
    st.title("🍔 McMediciones Pro")
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        st.subheader("Nueva Medición")
        with st.container(border=True):
            obs_n = st.text_input("Observador")
            obs_f = st.date_input("Fecha", datetime.now(BOGOTA_TZ).date())
            franj = st.selectbox("Franja", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
            if st.button("▶ EMPEZAR", type="primary", use_container_width=True):
                if obs_n:
                    st.session_state.active_session = {"franja": f"{obs_f} | {franj}", "observer": obs_n, "id": int(time.time()), "date": str(obs_f)}
                    st.session_state.orders, st.session_state.queues, st.session_state.stations, st.session_state.capacity, st.session_state.events = [], [], [], [], []
                    st.session_state.order_counter = 1; st.rerun()
    with c2:
        st.subheader("Historial")
        if st.session_state.history:
            for s in reversed(st.session_state.history):
                with st.container(border=True):
                    st.write(f"**{s['info']['franja']}** | {s['info']['observer']}")
                    b1, b2, b3 = st.columns(3)
                    with b1: st.download_button("💾 Excel", export_excel_maestro(s['data'], s['info']), f"Data_{get_safe_id(s['info'])}.xlsx", key=f"ex_{get_safe_id(s['info'])}", use_container_width=True)
                    with b2: 
                        if st.button("📊 Ver", key=f"v_{get_safe_id(s['info'])}", use_container_width=True):
                            st.session_state.selected_history = s; st.rerun()
                    with b3:
                        if st.button("🗑️", key=f"del_{get_safe_id(s['info'])}", use_container_width=True):
                            st.session_state.history = [h for h in st.session_state.history if get_safe_id(h['info']) != get_safe_id(s['info'])]
                            save_history(); st.rerun()
        else: st.info("Sin sesiones.")

else:
    h1, h2 = st.columns([4, 1])
    h1.title("Medición en Vivo")
    if h2.button("⏹ FINALIZAR", type="primary", use_container_width=True):
        st.session_state.history.append({"info": st.session_state.active_session, "data": {'orders': list(st.session_state.orders), 'queues': list(st.session_state.queues), 'stations': list(st.session_state.stations), 'capacity': list(st.session_state.capacity), 'events': list(st.session_state.events)}})
        st.session_state.active_session = None; save_history(); st.rerun()
    
    st.caption(f"👤 {st.session_state.active_session['observer']} | ⏱️ {st.session_state.active_session['franja']}")
    render_app_view({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events})
    
    st.divider()
    st.download_button("📥 Descargar Reporte Excel", export_excel_maestro({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events}, st.session_state.active_session), "Reporte_Actual.xlsx", use_container_width=True)
