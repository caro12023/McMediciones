import streamlit as st
import pandas as pd
import time
from datetime import datetime, timedelta
import io
import pytz
import plotly.express as px
import pickle
import os

# --- CONFIGURACIÓN ---
st.set_page_config(page_title="McMediciones Oficial", layout="wide", page_icon="🍔")
BOGOTA_TZ = pytz.timezone('America/Bogota')
HISTORY_FILE = "mcmediciones_history.pkl"
MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    div[data-testid="stVerticalBlock"] > div[style*="border"] { 
        border-radius: 12px; border: 1px solid #cbd5e1; background-color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.05); 
    }
    .alerta-colas { background-color: #DA291C; color: white; padding: 15px; border-radius: 8px; text-align: center; font-size: 20px; font-weight: bold; margin-bottom: 20px; border: 3px solid #FFC72C; animation: blinker 1.5s linear infinite; }
    @keyframes blinker { 50% { opacity: 0.5; } }
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

# Inicializar variables
for key in ['orders', 'queues', 'stations', 'capacity', 'events']:
    if key not in st.session_state: st.session_state[key] = []
if 'order_counter' not in st.session_state: st.session_state.order_counter = 1
if 'session_start_time' not in st.session_state: st.session_state.session_start_time = None

# --- FUNCIONES DE APOYO ---
def get_interval_label(timestamp, start_time):
    """Calcula el bloque de 5min relativo al inicio real de la toma de datos"""
    if not start_time: return "00:00 - 00:05"
    diff = timestamp - start_time
    intervals_passed = int(diff.total_seconds() // 300)
    franja_start = start_time + timedelta(minutes=intervals_passed * 5)
    franja_end = franja_start + timedelta(minutes=5)
    return f"{franja_start.strftime('%H:%M')} - {franja_end.strftime('%H:%M')}"

def clean_df(df):
    """Limpia columnas técnicas para la vista del usuario y Excel"""
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()
    for c in ['Inicio_ts', 'Inicio_dt', 'Fase']:
        if c in df.columns: df = df.drop(columns=[c])
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)
    return df

def export_excel_maestro(session_data, session_info):
    output = io.BytesIO()
    start_dt = session_info.get('start_dt')
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # Pestaña 1: Pedidos por Intervalos (Resumen)
        if session_data.get('orders'):
            df_ord = pd.DataFrame(session_data['orders'])
            df_ord['Franja'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            ped_int = df_ord.groupby(['Franja', 'Canal']).size().unstack(fill_value=0)
            ped_int['Total Intervalo'] = ped_int.sum(axis=1)
            ped_int.to_excel(writer, sheet_name='Pedidos_Intervalos')
            
            # Pestaña 2: Detalle E2E (Cada pedido individual)
            clean_df(df_ord).to_excel(writer, sheet_name='Detalle_E2E', index=False)
        
        # Pestaña 3: Colas por Intervalos
        if session_data.get('queues'):
            pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas_Intervalos', index=False)
        
        # Pestaña 4: Estaciones (Submuestra)
        if session_data.get('stations'):
            clean_df(pd.DataFrame(session_data['stations'])).to_excel(writer, sheet_name='Estaciones', index=False)
        
        # Pestaña 5: Capacidad Efectiva
        if session_data.get('capacity'):
            pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad_Franja', index=False)
            
        # Pestaña 6: Eventos
        if session_data.get('events'):
            pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos', index=False)
            
    return output.getvalue()

def render_main_view(data, mode="vivo"):
    start_dt = st.session_state.session_start_time
    
    # ALERTA DE COLA (Relativa al inicio real)
    if mode == "vivo" and start_dt:
        now = datetime.now(BOGOTA_TZ)
        current_franja = get_interval_label(now, start_dt)
        ya_registrado = any(q.get('Franja') == current_franja for q in st.session_state.queues)
        if not ya_registrado:
            st.markdown(f'<div class="alerta-colas">🚨 REGISTRA LA COLA: Franja {current_franja} 🚨</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["🏃‍♂️ 1. Pedidos y Colas", "🍳 2. Estaciones (Submuestra)", "👥 3. Capacidad / Eventos", "📊 4. Dashboard"])
    
    with t1:
        # REGISTRO COLAS
        with st.container(border=True):
            st.subheader("🚨 Registrar Colas")
            c_qc, c_qa, c_qb = st.columns([1, 1, 1])
            qc = c_qc.number_input("Fila Caja", 0); qa = c_qa.number_input("Fila AutoMac", 0)
            if c_qb.button("💾 Guardar Cola", use_container_width=True):
                franja_label = get_interval_label(datetime.now(BOGOTA_TZ), start_dt)
                st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Franja": franja_label, "Caja": qc, "AutoMac": qa})
                st.rerun()
            if data['queues']: st.dataframe(pd.DataFrame(data['queues']).iloc[::-1], use_container_width=True)

        st.divider()

        # REGISTRO PEDIDOS
        with st.container(border=True):
            st.subheader("➕ Nuevo Pedido")
            c1, c2, c3 = st.columns([2, 1, 1])
            n_can = c1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"], key="ncan")
            n_itm = c2.number_input("Items:", 1, key="nitm")
            if c3.button("▶ Iniciar", type="primary", use_container_width=True):
                now = datetime.now(BOGOTA_TZ)
                st.session_state.orders.append({'ID': f"P-{st.session_state.order_counter:03d}", 'Canal': n_can, 'Items': n_itm, 'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Inicio_dt': now, 'Hora Inicio': now.strftime("%H:%M:%S"), 'Fin Ordering': '-', 'Entrega': '-', 'Duración(s)': 0})
                st.session_state.order_counter += 1; st.rerun()
            
            k1, k2 = st.columns(2)
            with k1:
                st.caption("📝 Ordering")
                for p in [p for p in st.session_state.orders if p['Estado'] == 'Ordering']:
                    if st.button(f"➡️ Espera {p['ID']}", key=f"w_{p['ID']}", use_container_width=True):
                        p['Estado'] = 'Waiting'; p['Fin Ordering'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); st.rerun()
            with k2:
                st.caption("⏳ Waiting")
                for p in [p for p in st.session_state.orders if p['Estado'] == 'Waiting']:
                    if st.button(f"✅ Entregar {p['ID']}", key=f"f_{p['ID']}", type="primary", use_container_width=True):
                        p['Estado'] = 'Completado'; p['Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['Duración(s)'] = round(time.time() - p['Inicio_ts'], 2); st.rerun()

            if data['orders']:
                st.write("**Historial de Pedidos (End-to-End):**")
                df_o = pd.DataFrame(data['orders'])
                comp = df_o[df_o['Estado'] == 'Completado'].copy()
                if not comp.empty:
                    st.dataframe(clean_df(comp).iloc[::-1], use_container_width=True)

    with t2:
        with st.container(border=True):
            st.subheader("🍳 Estaciones (10-15 muestras)")
            st.info("Prioriza Ensamble, Bebidas y Bolseo. Marca 'Listo' si el componente ya estaba en el bin.")
            ic1, ic2, ic3 = st.columns([2,2,1])
            s_n = ic1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo"])
            s_e = ic2.selectbox("Estado:", ["Listo (En bin)", "A pedido (Esperó lote)"])
            if ic3.button("▶ Iniciar Est.", type="primary", use_container_width=True):
                st.session_state.stations.append({'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Estación': s_n, 'Estado': s_e, 'Fase': 'Corriendo', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S')})
                st.rerun()
            for e in [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']:
                with st.container(border=True):
                    st.write(f"**{e['ID']}** - {e['Estación']} - ⏱️ {time.time()-e['Inicio_ts']:.2f}s")
                    nt = st.text_input("Nota breve:", key=f"n_{e['ID']}")
                    if st.button("🛑 Terminar", key=f"ef_{e['ID']}", use_container_width=True):
                        e['Fase'] = 'Completado'; e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'); e['Duración(s)'] = round(time.time()-e['Inicio_ts'], 2); e['Nota'] = nt; st.rerun()
            if data['stations']:
                st.write("**Log de Estaciones:**")
                df_s = pd.DataFrame(data['stations'])[lambda x: x['Fase'] == 'Completado']
                if not df_s.empty: st.dataframe(clean_df(df_s).iloc[::-1], use_container_width=True)

    with t3:
        with st.container(border=True):
            st.subheader("👥 Capacidad Efectiva")
            st.info("Registrar al INICIO y en el PICO de congestión.")
            momento = st.radio("Momento:", ["Inicio de Franja", "Pico de Congestión"], horizontal=True)
            c1, c2, c3 = st.columns(3); c4, c5, c6 = st.columns(3)
            p1 = c1.number_input("Parrilla", 0); p2 = c2.number_input("Freidoras", 0); p3 = c3.number_input("Ensamble", 0)
            p4 = c4.number_input("Bebidas", 0); p5 = c5.number_input("Bolseo", 0); p6 = c6.number_input("Entrega", 0)
            eq = st.number_input("Equipos Activos (Total)", 0)
            if st.button("💾 Guardar Capacidad", use_container_width=True):
                st.session_state.capacity.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": momento, "Parrilla": p1, "Freidoras": p2, "Ensamble": p3, "Bebidas": p4, "Bolseo": p5, "Entrega": p6, "Equipos": eq})
                st.rerun()
            if data['capacity']: st.dataframe(pd.DataFrame(data['capacity']).iloc[::-1], use_container_width=True)
        
        with st.container(border=True):
            st.subheader("⚠️ Eventos")
            ev = st.text_input("¿Qué ocurrió?")
            if st.button("💾 Guardar Evento", use_container_width=True):
                st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": ev}); st.rerun()
            if data['events']: st.dataframe(pd.DataFrame(data['events']).iloc[::-1], use_container_width=True)

    with t4:
        st.subheader("📊 Dashboard (Análisis 3.4)")
        if data['orders'] and len(data['orders']) > 0:
            df_ord = pd.DataFrame(data['orders'])
            df_ord['Franja'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            resumen = df_ord.groupby(['Franja', 'Canal']).size().unstack(fill_value=0).reset_index()
            
            # Forzar canales para evitar ValueError
            for c in ['Caja', 'AutoMac', 'Delivery/Pickup']:
                if c not in resumen.columns: resumen[c] = 0
            
            try:
                fig_df = resumen.melt(id_vars='Franja', value_vars=['Caja', 'AutoMac', 'Delivery/Pickup'])
                st.plotly_chart(px.bar(fig_df, x='Franja', y='value', color='variable', color_discrete_map=MC_COLORS, barmode='stack', title="Llegadas por Canal (Intervalos de 5 min Reales)", text_auto=True), use_container_width=True)
            except: st.info("Generando gráfica...")
            
            resumen['Total'] = resumen[['Caja', 'AutoMac', 'Delivery/Pickup']].sum(axis=1)
            st.write("**Tabla de Demanda Detallada:**"); st.dataframe(resumen, use_container_width=True)
        else: st.info("Registra un pedido para ver estadísticas.")

# --- FLUJO PRINCIPAL ---
if st.session_state.active_session is None:
    st.title("🍔 McMediciones Pro")
    c1, c2 = st.columns([1, 1.2])
    with c1:
        st.subheader("Nueva Medición")
        obs_n = st.text_input("Observador")
        obs_f = st.date_input("Fecha", datetime.now(BOGOTA_TZ).date())
        franj = st.selectbox("Franja Horaria", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
        if st.button("▶ EMPEZAR TRABAJO", type="primary", use_container_width=True):
            if obs_n:
                st.session_state.session_start_time = datetime.now(BOGOTA_TZ)
                st.session_state.active_session = {"franja": franj, "observer": obs_n, "fecha": str(obs_f), "start_dt": st.session_state.session_start_time}
                st.session_state.orders, st.session_state.queues, st.session_state.stations, st.session_state.capacity, st.session_state.events = [], [], [], [], []
                st.rerun()
    with c2:
        st.subheader("Historial de Sesiones")
        if st.session_state.history:
            for i, s in enumerate(reversed(st.session_state.history)):
                with st.container(border=True):
                    st.write(f"**{s['info'].get('fecha', '')} | {s['info']['franja']}**")
                    st.download_button(f"📥 Descargar Excel Profesional {i}", export_excel_maestro(s['data'], s['info']), f"Reporte_Mc_{i}.xlsx", key=f"ex_{i}")

else:
    h1, h2 = st.columns([4, 1])
    h1.title("Medición en Vivo")
    if h2.button("⏹ FINALIZAR", type="primary"):
        st.session_state.history.append({"info": st.session_state.active_session, "data": {'orders': list(st.session_state.orders), 'queues': list(st.session_state.queues), 'stations': list(st.session_state.stations), 'capacity': list(st.session_state.capacity), 'events': list(st.session_state.events)}})
        st.session_state.active_session = None; save_history(); st.rerun()
    render_main_view({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events}, mode="vivo")
