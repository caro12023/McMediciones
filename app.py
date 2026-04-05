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
    .alerta-colas { background-color: #DA291C; color: white; padding: 15px; border-radius: 8px; text-align: center; font-size: 20px; font-weight: bold; margin-bottom: 20px; border: 3px solid #FFC72C; }
    .stTabs button p { font-size: 17px !important; font-weight: bold !important; }
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
if 'view_session' not in st.session_state: st.session_state.view_session = None

# Inicializar variables
for key in ['orders', 'queues', 'stations', 'capacity', 'events']:
    if key not in st.session_state: st.session_state[key] = []
if 'order_counter' not in st.session_state: st.session_state.order_counter = 1
if 'session_start_time' not in st.session_state: st.session_state.session_start_time = None

# --- FUNCIONES DE CÁLCULO ---
def get_interval_label(timestamp, start_time):
    if not start_time: return "00:00 - 00:05"
    diff = timestamp - start_time
    intervals = int(diff.total_seconds() // 300)
    f_start = start_time + timedelta(minutes=intervals * 5)
    f_end = f_start + timedelta(minutes=5)
    return f"{f_start.strftime('%H:%M')} - {f_end.strftime('%H:%M')}"

def clean_df_excel(df):
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()
    for c in ['Inicio_ts', 'Inicio_dt', 'Fase']:
        if c in df.columns: df = df.drop(columns=[c])
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)
    return df

def export_excel_pro(session_data, session_info):
    output = io.BytesIO()
    start_dt = session_info.get('start_dt')
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        # 1. Demanda por Intervalos
        if session_data.get('orders'):
            df_ord = pd.DataFrame(session_data['orders'])
            df_ord['Franja'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            ped_int = df_ord.groupby(['Franja', 'Canal']).size().unstack(fill_value=0)
            ped_int['Total Intervalo'] = ped_int.sum(axis=1)
            # Agregar fila de totales
            total_row = pd.DataFrame(ped_int.sum()).T
            total_row.index = ["TOTAL FRANJA"]
            pd.concat([ped_int, total_row]).to_excel(writer, sheet_name='Demanda_Intervalos')
            
            # 2. Detalle End-to-End
            clean_df_excel(df_ord).to_excel(writer, sheet_name='Detalle_E2E', index=False)

        # 3. Parámetros Estaciones
        if session_data.get('stations'):
            df_s = pd.DataFrame(session_data['stations'])
            df_s = df_s[df_s['Fase'] == 'Completado']
            if not df_s.empty:
                params = df_s.groupby(['Estación', 'Estado'])['Duración(s)'].agg(
                    n='count', Mediana='median', Min='min', Max='max', 
                    P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()
                params.round(2).to_excel(writer, sheet_name='Parametros_Estaciones', index=False)
                clean_df_excel(df_s).to_excel(writer, sheet_name='Estaciones_Crudo', index=False)

        # 4. Colas y Capacidad
        if session_data.get('queues'): pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas_5min', index=False)
        if session_data.get('capacity'): pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad_Efectiva', index=False)
        if session_data.get('events'): pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos_Inusuales', index=False)

    return output.getvalue()

def render_app_logic(data, mode="vivo"):
    start_dt = st.session_state.session_start_time if mode == "vivo" else st.session_state.view_session['info']['start_dt']
    readonly = (mode == "consulta")

    # ALERTA DE COLAS
    if mode == "vivo" and start_dt:
        now = datetime.now(BOGOTA_TZ)
        curr_franja = get_interval_label(now, start_dt)
        ya = any(q.get('Franja') == curr_franja for q in st.session_state.queues)
        if not ya:
            st.markdown(f'<div class="alerta-colas">🚨 REGISTRA COLA: Franja {curr_franja} 🚨</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["🏃‍♂️ 1. Pedidos y Colas", "🍳 2. Estaciones", "👥 3. Capacidad / Eventos", "📊 4. Dashboard Oficial"])

    with t1:
        # COLAS
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("🚨 Colas")
            qc = st.number_input("Caja", 0, disabled=readonly)
            qa = st.number_input("AutoMac", 0, disabled=readonly)
            if not readonly and st.button("💾 Guardar Cola", use_container_width=True):
                flabel = get_interval_label(datetime.now(BOGOTA_TZ), start_dt)
                st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Franja": flabel, "Caja": qc, "AutoMac": qa})
                st.rerun()
            if not readonly and data['queues']:
                if st.button("🗑️ Borrar Última Cola"): st.session_state.queues.pop(); st.rerun()
        with c2:
            if data['queues']: st.dataframe(pd.DataFrame(data['queues']).iloc[::-1], use_container_width=True)

        st.divider()

        # PEDIDOS END-TO-END
        st.subheader("➕ Pedidos End-to-End")
        if not readonly:
            cp1, cp2, cp3 = st.columns([2, 1, 1])
            n_can = cp1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"])
            n_itm = cp2.number_input("Tamaño (Items):", 1)
            if cp3.button("▶ Iniciar Pedido", type="primary", use_container_width=True):
                now = datetime.now(BOGOTA_TZ)
                st.session_state.orders.append({'ID': f"P-{st.session_state.order_counter:03d}", 'Canal': n_can, 'Tamaño': n_itm, 'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Inicio_dt': now, 'Hora Inicio': now.strftime("%H:%M:%S"), 'Fin Ordering': '-', 'Hora Entrega': '-', 'Duración Total(s)': 0})
                st.session_state.order_counter += 1; st.rerun()

        k1, k2 = st.columns(2)
        with k1:
            st.caption("📝 Tomando Pedido (Ordering)")
            for p in [p for p in st.session_state.orders if p['Estado'] == 'Ordering']:
                with st.container(border=True):
                    st.write(f"**{p['ID']}** | {p['Canal']} | {time.time()-p['Inicio_ts']:.1f}s")
                    if not readonly and st.button(f"➡️ A Espera {p['ID']}", key=f"w_{p['ID']}"):
                        p['Estado'] = 'Waiting'; p['Fin Ordering'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); st.rerun()
        with k2:
            st.caption("⏳ Esperando Entrega")
            for p in [p for p in st.session_state.orders if p['Estado'] == 'Waiting']:
                with st.container(border=True):
                    st.write(f"**{p['ID']}** | {time.time()-p['Inicio_ts']:.1f}s")
                    if not readonly and st.button(f"✅ Entregar {p['ID']}", key=f"f_{p['ID']}", type="primary"):
                        p['Estado'] = 'Completado'; p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['Duración Total(s)'] = round(time.time() - p['Inicio_ts'], 2); st.rerun()

        # TABLA END TO END EN VIVO
        if data['orders']:
            st.write("### Tabla de Pedidos End-to-End")
            df_o = pd.DataFrame(data['orders'])
            comp = df_o[df_o['Estado'] == 'Completado'].copy()
            if not comp.empty:
                st.dataframe(clean_df_excel(comp[['ID', 'Canal', 'Tamaño', 'Hora Inicio', 'Hora Entrega', 'Duración Total(s)']]).iloc[::-1], use_container_width=True)
                if not readonly and st.button("🗑️ Borrar Último Pedido"): st.session_state.orders.pop(); st.rerun()

    with t2:
        st.subheader("🍳 Parámetros por Estación")
        if not readonly:
            ic1, ic2, ic3 = st.columns([2, 2, 1])
            s_n = ic1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo"])
            s_e = ic2.selectbox("Estado componente:", ["Listo (En bin)", "A pedido (Esperó)"])
            if ic3.button("▶ Iniciar", type="primary", use_container_width=True):
                st.session_state.stations.append({'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Estación': s_n, 'Estado': s_e, 'Fase': 'Corriendo', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S')})
                st.rerun()
        
        for e in [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']:
            with st.container(border=True):
                st.write(f"**{e['ID']}** - {e['Estación']} - {time.time()-e['Inicio_ts']:.1f}s")
                nt = st.text_input("Nota:", key=f"n_{e['ID']}")
                if st.button("🛑 Terminar", key=f"ef_{e['ID']}"):
                    e['Fase'] = 'Completado'; e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'); e['Duración(s)'] = round(time.time()-e['Inicio_ts'], 2); e['Nota'] = nt; st.rerun()

        # TABLA DE PARÁMETROS EN VIVO (RÚBRICA)
        if data['stations']:
            df_s = pd.DataFrame(data['stations'])
            comp_s = df_s[df_s['Fase'] == 'Completado']
            if not comp_s.empty:
                st.write("### Resumen de Parámetros (Estadísticas)")
                params = comp_s.groupby(['Estación', 'Estado'])['Duración(s)'].agg(
                    n='count', Mediana='median', Min='min', Max='max', 
                    P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()
                st.dataframe(params.round(2), use_container_width=True)
                
                with st.expander("Ver registros individuales"):
                    st.dataframe(clean_df_excel(comp_s).iloc[::-1], use_container_width=True)
                    if not readonly and st.button("🗑️ Borrar Última Estación"): st.session_state.stations.pop(); st.rerun()

    with t3:
        st.subheader("👥 Capacidad Efectiva")
        with st.container(border=True):
            momento = st.radio("Momento:", ["Inicio de Franja", "Pico de Congestión"], horizontal=True, disabled=readonly)
            c1, c2, c3 = st.columns(3); c4, c5, c6 = st.columns(3)
            p1 = c1.number_input("Parrilla", 0, disabled=readonly); p2 = c2.number_input("Freidoras", 0, disabled=readonly); p3 = c3.number_input("Ensamble", 0, disabled=readonly)
            p4 = c4.number_input("Bebidas", 0, disabled=readonly); p5 = c5.number_input("Bolseo", 0, disabled=readonly); p6 = c6.number_input("Entrega", 0, disabled=readonly)
            eq = st.number_input("Puestos Activos", 0, disabled=readonly)
            if not readonly and st.button("💾 Guardar Capacidad", use_container_width=True):
                st.session_state.capacity.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": momento, "Parrilla": p1, "Freidoras": p2, "Ensamble": p3, "Bebidas": p4, "Bolseo": p5, "Entrega": p6, "Equipos": eq})
                st.rerun()
            if data['capacity']: st.dataframe(pd.DataFrame(data['capacity']).iloc[::-1], use_container_width=True)
        
        st.divider()
        st.subheader("⚠️ Eventos Inusuales")
        ev_msg = st.text_input("Nota del evento:", disabled=readonly)
        if not readonly and st.button("💾 Guardar Evento"):
            st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": ev_msg}); st.rerun()
        if data['events']: st.dataframe(pd.DataFrame(data['events']).iloc[::-1], use_container_width=True)

    with t4:
        st.subheader("📊 Análisis de Demanda")
        if data['orders']:
            df_ord = pd.DataFrame(data['orders'])
            df_ord['Franja'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            
            # Crear base consolidada
            res = df_ord.groupby(['Franja', 'Canal']).size().unstack(fill_value=0).reset_index()
            for c in ['Caja', 'AutoMac', 'Delivery/Pickup']:
                if c not in res.columns: res[c] = 0
            
            # 1. GRÁFICA EN VIVO
            fig_df = res.melt(id_vars='Franja', value_vars=['Caja', 'AutoMac', 'Delivery/Pickup'])
            st.plotly_chart(px.line(fig_df, x='Franja', y='value', color='variable', color_discrete_map=MC_COLORS, markers=True, title="Curva de Demanda por Canal"), use_container_width=True)
            
            # 2. TABLA CON TOTALES (RÚBRICA)
            res.set_index('Franja', inplace=True)
            res['Total Intervalo'] = res.sum(axis=1)
            total_franja = pd.DataFrame(res.sum()).T
            total_franja.index = ["TOTAL FRANJA"]
            st.write("### Tabla de Demanda (Conteos cada 5 min)")
            st.dataframe(pd.concat([res, total_franja]), use_container_width=True)
        else: st.info("Registra pedidos para generar la curva de demanda.")

# --- FLUJO PRINCIPAL ---

if st.session_state.view_session:
    s = st.session_state.view_session
    if st.button("⬅️ VOLVER AL INICIO"): st.session_state.view_session = None; st.rerun()
    st.title(f"📂 Revisando: {s['info']['franja']}")
    render_app_logic(s['data'], mode="consulta")
    st.download_button("📥 Descargar Excel del Reporte", export_excel_pro(s['data'], s['info']), f"Reporte_{s['info']['fecha']}.xlsx", use_container_width=True)

elif st.session_state.active_session is None:
    st.title("🍔 McMediciones Pro (Consultoría)")
    c1, c2 = st.columns([1, 1.2])
    with c1:
        st.subheader("Nueva Medición")
        obs_n = st.text_input("Observador")
        obs_f = st.date_input("Fecha", datetime.now(BOGOTA_TZ).date())
        franj = st.selectbox("Franja Horaria", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
        if st.button("▶ INICIAR TRABAJO", type="primary", use_container_width=True):
            if obs_n:
                st.session_state.session_start_time = datetime.now(BOGOTA_TZ)
                st.session_state.active_session = {"franja": franj, "observer": obs_n, "fecha": str(obs_f), "start_dt": st.session_state.session_start_time}
                st.session_state.orders, st.session_state.queues, st.session_state.stations, st.session_state.capacity, st.session_state.events = [], [], [], [], []
                st.rerun()
    with c2:
        st.subheader("Historial de Sesiones")
        if st.session_state.history:
            for s in reversed(st.session_state.history):
                with st.container(border=True):
                    st.write(f"**{s['info'].get('fecha', '')} | {s['info']['franja']}**")
                    bc1, bc2, bc3 = st.columns(3)
                    bc1.download_button("💾 Bajar Excel", export_excel_pro(s['data'], s['info']), f"Data_{s['info']['fecha']}.xlsx", key=f"ex_{s['info']['start_dt']}")
                    if bc2.button("📊 Revisar", key=f"v_{s['info']['start_dt']}", use_container_width=True): st.session_state.view_session = s; st.rerun()
                    if bc3.button("🗑️", key=f"del_{s['info']['start_dt']}", use_container_width=True):
                        st.session_state.history = [h for h in st.session_state.history if h['info'] != s['info']]; save_history(); st.rerun()
        else: st.info("No hay sesiones guardadas.")

else:
    h1, h2 = st.columns([4, 1])
    h1.title("Medición en Vivo")
    if h2.button("⏹ FINALIZAR SESIÓN", type="primary"):
        st.session_state.history.append({"info": st.session_state.active_session, "data": {'orders': list(st.session_state.orders), 'queues': list(st.session_state.queues), 'stations': list(st.session_state.stations), 'capacity': list(st.session_state.capacity), 'events': list(st.session_state.events)}})
        st.session_state.active_session = None; save_history(); st.rerun()
    render_app_logic({'orders': st.session_state.orders, 'queues': st.session_state.queues, 'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events}, mode="vivo")
