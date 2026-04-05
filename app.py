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
if 'view_session' not in st.session_state: st.session_state.view_session = None

for key in ['orders', 'queues', 'stations', 'capacity', 'events']:
    if key not in st.session_state: st.session_state[key] = []
if 'order_counter' not in st.session_state: st.session_state.order_counter = 1
if 'session_start_time' not in st.session_state: st.session_state.session_start_time = None

# --- FUNCIONES DE CÁLCULO DE FRANJAS ---
def get_franja_dt(timestamp, start_time):
    """Devuelve la hora exacta de inicio del bloque (Para la Gráfica)"""
    if not start_time: return timestamp
    diff = timestamp - start_time
    intervals = int(diff.total_seconds() // 300)
    return start_time + timedelta(minutes=intervals * 5)

def get_interval_label(timestamp, start_time):
    """Devuelve el texto del bloque (Para la Tabla)"""
    if not start_time: return "00:00 - 00:05"
    f_start = get_franja_dt(timestamp, start_time)
    f_end = f_start + timedelta(minutes=5)
    return f"{f_start.strftime('%H:%M')} - {f_end.strftime('%H:%M')}"

def clean_df_excel(df):
    if df is None or df.empty: return pd.DataFrame()
    df = df.copy()
    for c in ['Inicio_ts', 'Inicio_dt', 'Fase', 'Franja_dt']:
        if c in df.columns: df = df.drop(columns=[c])
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)
    return df

def export_excel_pro(session_data, session_info):
    output = io.BytesIO()
    start_dt = session_info.get('start_dt')
    
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        if session_data.get('orders'):
            df_ord = pd.DataFrame(session_data['orders'])
            df_ord['Franja'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            ped_int = df_ord.groupby(['Franja', 'Canal']).size().unstack(fill_value=0)
            ped_int['Total Intervalo'] = ped_int.sum(axis=1)
            pd.concat([ped_int, pd.DataFrame(ped_int.sum()).T.rename(index={0: 'TOTAL'})]).to_excel(writer, sheet_name='Demanda_Intervalos')
            clean_df_excel(df_ord).to_excel(writer, sheet_name='Detalle_E2E', index=False)

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

        if session_data.get('queues'): pd.DataFrame(session_data['queues']).to_excel(writer, sheet_name='Colas_5min', index=False)
        if session_data.get('capacity'): pd.DataFrame(session_data['capacity']).to_excel(writer, sheet_name='Capacidad_Efectiva', index=False)
        if session_data.get('events'): pd.DataFrame(session_data['events']).to_excel(writer, sheet_name='Eventos_Inusuales', index=False)

    return output.getvalue()

def render_app_logic(data, mode="vivo"):
    start_dt = st.session_state.session_start_time if mode == "vivo" else st.session_state.view_session['info']['start_dt']
    readonly = (mode == "consulta")

    # ALERTA DE COLAS INTELIGENTE
    if mode == "vivo" and start_dt:
        now = datetime.now(BOGOTA_TZ)
        curr_franja = get_interval_label(now, start_dt)
        ya = any(q.get('Franja') == curr_franja for q in st.session_state.queues)
        if not ya:
            st.markdown(f'<div class="alerta-colas">🚨 REGISTRA LA COLA: {curr_franja} 🚨</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["🏃‍♂️ 1. Pedidos y Colas", "🍳 2. Estaciones", "👥 3. Capacidad / Eventos", "📊 4. Dashboard Oficial"])

    with t1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("🚨 Colas")
            qc = st.number_input("Caja", 0, disabled=readonly)
            qa = st.number_input("AutoMac", 0, disabled=readonly)
            if not readonly and st.button("💾 Guardar Cola", use_container_width=True):
                flabel = get_interval_label(datetime.now(BOGOTA_TZ), start_dt)
                st.session_state.queues.append({"Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"), "Franja": flabel, "Caja": qc, "AutoMac": qa})
                st.rerun()
        with c2:
            if data['queues']: st.dataframe(pd.DataFrame(data['queues']).iloc[::-1], use_container_width=True)

        st.divider()

        st.subheader("➕ Pedidos End-to-End")
        if not readonly:
            cp1, cp2, cp3 = st.columns([2, 1, 1])
            n_can = cp1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"])
            n_itm = cp2.number_input("Tamaño (Items):", 1)
            if cp3.button("▶ Iniciar Pedido", type="primary", use_container_width=True):
                now = datetime.now(BOGOTA_TZ)
                st.session_state.orders.append({'ID': f"P-{st.session_state.order_counter:03d}", 'Canal': n_can, 'Items': n_itm, 'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Inicio_dt': now, 'Hora Inicio': now.strftime("%H:%M:%S"), 'Fin Ordering': '-', 'Hora Entrega': '-', 'Duración Total(s)': 0})
                st.session_state.order_counter += 1; st.rerun()

        k1, k2 = st.columns(2)
        with k1:
            st.markdown("### 📝 Tomando Pedido (Ordering)")
            for i, p in enumerate([p for p in st.session_state.orders if p['Estado'] == 'Ordering']):
                with st.container(border=True):
                    st.markdown(f"**Posición #{i+1}** | 🍔 **{p['ID']}**")
                    st.write(f"Canal: **{p['Canal']}** | Items: {p['Items']}")
                    st.info(f"⏱️ Tiempo activo: **{time.time()-p['Inicio_ts']:.1f}s**")
                    if not readonly and st.button(f"➡️ Pasar a Espera", key=f"w_{p['ID']}", use_container_width=True):
                        p['Estado'] = 'Waiting'; p['Fin Ordering'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); st.rerun()
        with k2:
            st.markdown("### ⏳ Esperando Entrega")
            for i, p in enumerate([p for p in st.session_state.orders if p['Estado'] == 'Waiting']):
                with st.container(border=True):
                    st.markdown(f"**Posición #{i+1}** | 🛍️ **{p['ID']}**")
                    st.write(f"Canal: **{p['Canal']}** | Items: {p['Items']}")
                    st.warning(f"⏱️ Tiempo total: **{time.time()-p['Inicio_ts']:.1f}s**")
                    if not readonly and st.button(f"✅ Entregar Pedido", key=f"f_{p['ID']}", type="primary", use_container_width=True):
                        p['Estado'] = 'Completado'; p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"); p['Duración Total(s)'] = round(time.time() - p['Inicio_ts'], 2); st.rerun()

        if data['orders']:
            st.write("### Tabla de Pedidos End-to-End")
            df_o = pd.DataFrame(data['orders'])
            comp = df_o[df_o['Estado'] == 'Completado'].copy()
            if not comp.empty: st.dataframe(clean_df_excel(comp[['ID', 'Canal', 'Items', 'Hora Inicio', 'Fin Ordering', 'Hora Entrega', 'Duración Total(s)']]).iloc[::-1], use_container_width=True)

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

        if data['stations']:
            df_s = pd.DataFrame(data['stations'])
            comp_s = df_s[df_s['Fase'] == 'Completado']
            if not comp_s.empty:
                st.write("### Tabla de Parámetros (Rúbrica)")
                params = comp_s.groupby(['Estación', 'Estado'])['Duración(s)'].agg(
                    n='count', Mediana='median', Min='min', Max='max', 
                    P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()
                st.dataframe(params.round(2), use_container_width=True)

    with t3:
        st.subheader("👥 Capacidad Efectiva")
        with st.container(border=True):
            momento = st.radio("Registro:", ["Inicio de Franja", "Pico de Congestión"], horizontal=True, disabled=readonly)
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
        if data['orders'] and len(data['orders']) > 0:
            df_ord = pd.DataFrame(data['orders'])
            
            # --- SOLUCIÓN DE LA GRÁFICA (EJE X COMO HORA EXACTA) ---
            df_ord['Franja_dt'] = df_ord['Inicio_dt'].apply(lambda x: get_franja_dt(x, start_dt))
            res_dt = df_ord.groupby(['Franja_dt', 'Canal']).size().unstack(fill_value=0).reset_index()
            for c in ['Caja', 'AutoMac', 'Delivery/Pickup']:
                if c not in res_dt.columns: res_dt[c] = 0
            
            fig_df = res_dt.melt(id_vars='Franja_dt', value_vars=['Caja', 'AutoMac', 'Delivery/Pickup'])
            fig = px.line(fig_df, x='Franja_dt', y='value', color='variable', color_discrete_map=MC_COLORS, markers=True, title="Curva de Demanda por Canal")
            fig.update_layout(xaxis_title="Hora de Inicio del Bloque", yaxis_title="Pedidos")
            st.plotly_chart(fig, use_container_width=True)
            
            # --- TABLA CON FRANJAS EN TEXTO (COMO PIDE LA RÚBRICA) ---
            df_ord['Franja_str'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            res_str = df_ord.groupby(['Franja_str', 'Canal']).size().unstack(fill_value=0)
            for c in ['Caja', 'AutoMac', 'Delivery/Pickup']:
                if c not in res_str.columns: res_str[c] = 0
            
            res_str['Total Intervalo'] = res_str.sum(axis=1)
            total_franja = pd.DataFrame(res_str.sum()).T
            total_franja.index = ["TOTAL FRANJA"]
            
            st.write("### Tabla de Conteos (Rúbrica)")
            st.dataframe(pd.concat([res_str, total_franja]), use_container_width=True)
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
