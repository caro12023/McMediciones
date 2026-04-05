import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import io
import pytz
import plotly.express as px
import pickle
import os

# --- CONFIGURACIÓN Y ESTÉTICA ---
st.set_page_config(page_title="McMediciones Sabana Final", layout="wide", page_icon="🍔")
BOGOTA_TZ = pytz.timezone('America/Bogota')
HISTORY_FILE = "mcmediciones_history.pkl"
MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    div[data-testid="stVerticalBlock"] > div[style*="border"] { 
        border-radius: 12px; border: 1px solid #cbd5e1; background-color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.05); 
    }
    .alerta-colas { background-color: #DA291C; color: white; padding: 15px; border-radius: 8px; text-align: center; font-size: 22px; font-weight: bold; margin-bottom: 20px; animation: blinker 1.5s linear infinite; border: 3px solid #FFC72C; }
    @keyframes blinker { 50% { opacity: 0.3; } }
    .stTabs button p { font-size: 17px !important; font-weight: bold !important; }
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
if 'last_alert_check' not in st.session_state: st.session_state.last_alert_check = ""

# --- FUNCIONES DE APOYO ---
def get_safe_id(info):
    return info.get('id', info.get('id_sesion', int(time.time())))

def export_excel_maestro(session_data, session_info):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if session_data.get('orders'):
            df_ord = pd.DataFrame(session_data['orders'])
            if not df_ord.empty:
                df_arr = df_ord[['Canal', 'Inicio']].copy()
                df_arr['Timestamp'] = pd.to_datetime(df_arr['Inicio'])
                dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
                resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
                resumen.index = [f"{t.strftime('%H:%M')} - {(t + timedelta(minutes=5)).strftime('%H:%M')}" for t in resumen.index]
                resumen['Total Intervalo'] = resumen.sum(axis=1)
                pd.concat([resumen, pd.DataFrame(resumen.sum()).T.rename(index={0: 'TOTAL FRANJA'})]).to_excel(writer, sheet_name='Demanda')
                df_ord.drop(columns=['Inicio', 'Inicio_ts'], errors='ignore').to_excel(writer, sheet_name='Pedidos_E2E', index=False)
        
        if session_data.get('stations'):
            pd.DataFrame(session_data['stations']).drop(columns=['Inicio_ts'], errors='ignore').to_excel(writer, sheet_name='Estaciones', index=False)
        if session_data.get('queues'): pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas', index=False)
        if session_data.get('capacity'): pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad', index=False)
        if session_data.get('events'): pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos', index=False)
    return output.getvalue()

def render_full_view(data, mode="vivo"):
    # --- ALERTA INTELIGENTE ---
    if mode == "vivo":
        now = datetime.now(BOGOTA_TZ)
        current_interval = f"{now.hour}:{now.minute // 5 * 5}"
        
        # Si estamos en un minuto múltiplo de 5 y aún no hemos registrado para este intervalo
        if now.minute % 5 == 0 and st.session_state.last_alert_check != current_interval:
            st.markdown(f'<div class="alerta-colas">🚨 HORA DE COLA: Son las {now.strftime("%H:%M")}. ¡ANOTA YA! 🚨</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["🏃‍♂️ Pedidos y Colas", "🍳 Estaciones", "👥 Capacidad/Eventos", "📊 Dashboard"])
    
    with t1:
        # REGISTRO COLAS
        with st.container(border=True):
            st.subheader("🚨 Registrar Colas (Cada 5 min)")
            c_qc, c_qa, c_qb = st.columns([1, 1, 1])
            qc = c_qc.number_input("Fila Caja", 0)
            qa = c_qa.number_input("Fila AutoMac", 0)
            if c_qb.button("💾 Guardar y Quitar Alerta", use_container_width=True):
                st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Caja": qc, "AutoMac": qa})
                st.session_state.last_alert_check = f"{datetime.now(BOGOTA_TZ).hour}:{datetime.now(BOGOTA_TZ).minute // 5 * 5}"
                st.rerun()
            if data['queues']:
                st.write("**Log de Colas:**")
                st.dataframe(pd.DataFrame(data['queues']).iloc[::-1], use_container_width=True)

        st.divider()

        # REGISTRO PEDIDOS
        with st.container(border=True):
            st.subheader("➕ Iniciar Pedido")
            c1, c2, c3 = st.columns([2, 1, 1])
            n_can = c1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"], key="ncan")
            n_itm = c2.number_input("Items:", 1, key="nitm")
            if c3.button("▶ Iniciar Pedido", type="primary", use_container_width=True):
                now = datetime.now(BOGOTA_TZ)
                st.session_state.orders.append({'ID': f"P-{st.session_state.order_counter:03d}", 'Canal': n_can, 'Número de Items': n_itm, 'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Hora Inicio': now.strftime("%H:%M:%S"), 'Inicio': now})
                st.session_state.order_counter += 1; st.rerun()
            
            k1, k2 = st.columns(2)
            with k1:
                st.caption("📝 Ordering (En proceso)")
                for p in [p for p in st.session_state.orders if p['Estado'] == 'Ordering']:
                    with st.container(border=True):
                        st.write(f"**{p['ID']}** | {p['Canal']} | ⏱️ {time.time()-p['Inicio_ts']:.2f}s")
                        if st.button(f"➡️ Espera {p['ID']}", key=f"w_{p['ID']}", use_container_width=True):
                            p['Estado'] = 'Waiting'; p['Fin Orden'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); st.rerun()
            with k2:
                st.caption("⏳ Waiting (Esperando)")
                for p in [p for p in st.session_state.orders if p['Estado'] == 'Waiting']:
                    with st.container(border=True):
                        st.write(f"**{p['ID']}** | ⏱️ {time.time()-p['Inicio_ts']:.2f}s")
                        if st.button(f"✅ Entregar {p['ID']}", key=f"f_{p['ID']}", type="primary", use_container_width=True):
                            p['Estado'] = 'Completado'; p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['Tiempo Total(s)'] = round(time.time() - p['Inicio_ts'], 2); st.rerun()

            if data['orders']:
                st.write("**Log de Pedidos Finalizados:**")
                df_o = pd.DataFrame(data['orders'])
                comp = df_o[df_o['Estado'] == 'Completado']
                if not comp.empty: st.dataframe(comp[['ID', 'Hora Inicio', 'Hora Entrega', 'Canal', 'Número de Items', 'Tiempo Total(s)']].iloc[::-1], use_container_width=True)

    with t2:
        with st.container(border=True):
            st.subheader("🍳 Estaciones (Lotes)")
            ic1, ic2, ic3 = st.columns([2,2,1])
            s_n = ic1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
            s_e = ic2.selectbox("Estado:", ["Listo (En bin)", "A pedido (Esperando lote)"])
            if ic3.button("▶ Iniciar Estación", type="primary", use_container_width=True):
                st.session_state.stations.append({'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Estación': s_n, 'Estado': s_e, 'Fase': 'Corriendo', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S')})
                st.rerun()
            
            for e in [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']:
                with st.container(border=True):
                    st.write(f"**{e['ID']}** - {e['Estación']} - ⏱️ {time.time()-e['Inicio_ts']:.2f}s")
                    nt = st.text_input("Observación:", key=f"n_{e['ID']}")
                    if st.button("🛑 Terminar Medición", key=f"ef_{e['ID']}", use_container_width=True):
                        e['Fase'] = 'Completado'; e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'); e['Duración (s)'] = round(time.time()-e['Inicio_ts'], 2); e['Nota'] = nt; st.rerun()

            if data['stations']:
                st.write("**Log de Estaciones:**")
                df_s = pd.DataFrame(data['stations'])
                ce = df_s[df_s['Fase'] == 'Completado']
                if not ce.empty: st.dataframe(ce[['ID', 'Hora Inicio', 'Fin', 'Estación', 'Estado', 'Duración (s)', 'Nota']].iloc[::-1], use_container_width=True)

    with t3:
        c_cap, c_ev = st.columns(2)
        with c_cap:
            with st.container(border=True):
                st.subheader("👥 Capacidad")
                mo = st.selectbox("Momento:", ["Inicio", "Pico"]); pe = st.number_input("Pers", 0); eq = st.number_input("Eqps", 0)
                if st.button("💾 Guardar Capacidad", use_container_width=True):
                    st.session_state.capacity.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": mo, "Pers": pe, "Eqps": eq}); st.rerun()
                if data['capacity']: st.dataframe(pd.DataFrame(data['capacity']), use_container_width=True)
        with c_ev:
            with st.container(border=True):
                st.subheader("⚠️ Eventos")
                ev = st.text_input("Nota del evento:")
                if st.button("💾 Guardar Evento", use_container_width=True):
                    st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": ev}); st.rerun()
                if data['events']: st.dataframe(pd.DataFrame(data['events']), use_container_width=True)

    with t4:
        st.subheader("📊 Dashboard de Resultados")
        if data['orders']:
            df_ord = pd.DataFrame(data['orders'])
            if not df_ord.empty:
                st.write("### 1. Cubetas de Demanda (5 min)")
                df_arr = df_ord[['Canal', 'Inicio']].copy()
                df_arr['Timestamp'] = pd.to_datetime(df_arr['Inicio'])
                dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
                
                resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
                
                # --- GRÁFICA CON SEGURO ---
                fig_df = resumen.reset_index()
                fig_df['Franja'] = fig_df['Timestamp'].apply(lambda t: f"{t.strftime('%H:%M')} - {(t + timedelta(minutes=5)).strftime('%H:%M')}")
                
                # Seleccionar solo canales que existen en los datos para evitar el ValueError
                canales_presentes = [c for c in ['Caja', 'AutoMac', 'Delivery/Pickup'] if c in resumen.columns]
                
                if canales_presentes:
                    fig = px.bar(fig_df.melt(id_vars='Franja', value_vars=canales_presentes), 
                                 x='Franja', y='value', color='variable', 
                                 color_discrete_map=MC_COLORS, barmode='stack', text_auto=True)
                    st.plotly_chart(fig, use_container_width=True)
                
                # --- TABLA CON TOTALES ---
                resumen['Total Intervalo'] = resumen.sum(axis=1)
                total_franja = pd.DataFrame(resumen.sum()).T; total_franja.index = ["TOTAL FRANJA"]
                resumen.index = [f"{t.strftime('%H:%M')} - {(t + timedelta(minutes=5)).strftime('%H:%M')}" for t in resumen.index]
                st.write("**Tabla de Demanda Consolidada:**")
                st.dataframe(pd.concat([resumen, total_franja]), use_container_width=True)
        else: st.info("Inicia pedidos para ver la demanda.")
        
        if data['stations']:
            st.divider()
            st.write("### 2. Estadísticas de Estaciones")
            df_s = pd.DataFrame(data['stations'])
            cs = df_s[df_s['Fase'] == 'Completado']
            if not cs.empty:
                params = cs.groupby(['Estación', 'Estado']).agg(n=('Duración (s)', 'count'), mediana=('Duración (s)', 'median'), P10=('Duración (s)', lambda x: x.quantile(0.10)), P90=('Duración (s)', lambda x: x.quantile(0.90))).reset_index()
                st.dataframe(params.round(2), use_container_width=True)

# --- FLUJO PRINCIPAL ---

if st.session_state.selected_history:
    s = st.session_state.selected_history
    if st.button("⬅️ VOLVER AL INICIO", type="primary"): st.session_state.selected_history = None; st.rerun()
    st.title(f"📂 Sesión: {s['info']['franja']}")
    render_full_view(s['data'], mode="consulta")
    st.download_button("📥 Descargar Reporte Excel", export_excel_maestro(s['data'], s['info']), f"Reporte_{get_safe_id(s['info'])}.xlsx", use_container_width=True)

elif st.session_state.active_session is None:
    st.title("🍔 McMediciones Sabana Final")
    c1, c2 = st.columns([1, 1.2], gap="large")
    with c1:
        st.subheader("Nueva Medición")
        with st.container(border=True):
            obs_n = st.text_input("Observador")
            obs_f = st.date_input("Fecha", datetime.now(BOGOTA_TZ).date())
            franj = st.selectbox("Franja", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
            if st.button("▶ EMPEZAR TRABAJO", type="primary", use_container_width=True):
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
                        if st.button("📊 Ver", key=f"v_{get_safe_id(s['info'])}", use_container_width=True): st.session_state.selected_history = s; st.rerun()
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
    
    render_full_view({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events})
    
    st.divider()
    st.download_button("📥 Descargar Reporte Excel", export_excel_maestro({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events}, st.session_state.active_session), "Reporte_Actual.xlsx", use_container_width=True)
