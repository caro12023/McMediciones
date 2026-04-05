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
    if not start_time: return timestamp
    diff = timestamp - start_time
    intervals = int(diff.total_seconds() // 300)
    return start_time + timedelta(minutes=intervals * 5)

def get_interval_label(timestamp, start_time):
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
        workbook = writer.book
        header_format = workbook.add_format({'bold': True, 'font_color': 'white', 'bg_color': '#DA291C', 'border': 1, 'align': 'center', 'valign': 'vcenter'})
        cell_format = workbook.add_format({'border': 1, 'align': 'center'})
        
        def escribir_y_formatear(df, nombre_hoja):
            if df.empty: return
            df.to_excel(writer, sheet_name=nombre_hoja, index=False)
            worksheet = writer.sheets[nombre_hoja]
            for col_num, value in enumerate(df.columns.values):
                worksheet.write(0, col_num, value, header_format)
                ancho_columna = max(len(str(value)), df[df.columns[col_num]].astype(str).map(len).max()) + 2
                worksheet.set_column(col_num, col_num, ancho_columna, cell_format)

        if session_data.get('orders'):
            df_ord = pd.DataFrame(session_data['orders']).copy()
            df_ord['Franja'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            
            counts_str = df_ord.groupby(['Franja', 'Canal']).size().reset_index(name='Pedidos')
            ped_int = counts_str.pivot(index='Franja', columns='Canal', values='Pedidos').fillna(0).astype(int)
            ped_int.columns.name = None
            for c in ['Caja', 'AutoMac', 'Delivery/Pickup']:
                if c not in ped_int.columns: ped_int[c] = 0
            ped_int = ped_int[['Caja', 'AutoMac', 'Delivery/Pickup']]
            ped_int['Total Intervalo'] = ped_int.sum(axis=1)
            
            ped_int_reset = ped_int.reset_index()
            tot_row = pd.DataFrame(ped_int.sum()).T.reset_index(drop=True)
            tot_row.insert(0, 'Franja', 'TOTAL FRANJA')
            
            escribir_y_formatear(pd.concat([ped_int_reset, tot_row]), 'Demanda_Intervalos')
            escribir_y_formatear(clean_df_excel(df_ord), 'Detalle_E2E')

        if session_data.get('stations'):
            df_s = pd.DataFrame(session_data['stations'])
            df_s = df_s[df_s['Fase'] == 'Completado']
            if not df_s.empty:
                params = df_s.groupby(['Estación', 'Estado'])['Duración(s)'].agg(
                    n='count', Mediana='median', Min='min', Max='max', 
                    P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()
                escribir_y_formatear(params.round(2), 'Parametros_Estaciones')
                escribir_y_formatear(clean_df_excel(df_s), 'Estaciones_Crudo')

        if session_data.get('queues'): escribir_y_formatear(pd.DataFrame(session_data['queues']), 'Colas_5min')
        if session_data.get('capacity'): escribir_y_formatear(pd.DataFrame(session_data['capacity']), 'Capacidad_Efectiva')
        if session_data.get('events'): escribir_y_formatear(pd.DataFrame(session_data['events']), 'Eventos_Inusuales')

    return output.getvalue()

def render_app_logic(data, mode="vivo"):
    start_dt = st.session_state.session_start_time if mode == "vivo" else st.session_state.view_session['info']['start_dt']
    readonly = (mode == "consulta")

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
        st.subheader("🍳 Registro de Estaciones (Submuestra)")
        if not readonly:
            ic1, ic2, ic3 = st.columns([2, 2, 1])
            s_n = ic1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo"])
            s_e = ic2.selectbox("Estado componente:", ["Listo (En bin)", "A pedido (Esperó)"])
            if ic3.button("▶ Iniciar Medición", type="primary", use_container_width=True):
                st.session_state.stations.append({'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Estación': s_n, 'Estado': s_e, 'Fase': 'Corriendo', 'Inicio_ts': time.time(), 'Hora Inicio': datetime.now(BOGOTA_TZ).strftime('%H:%M:%S')})
                st.rerun()
        
        for e in [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']:
            with st.container(border=True):
                st.write(f"**{e['ID']}** - {e['Estación']} - {time.time()-e['Inicio_ts']:.1f}s")
                nt = st.text_input("Nota:", key=f"n_{e['ID']}")
                if st.button("🛑 Terminar", key=f"ef_{e['ID']}"):
                    e['Fase'] = 'Completado'; e['Fin'] = datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'); e['Duración(s)'] = round(time.time()-e['Inicio_ts'], 2); e['Nota'] = nt; st.rerun()

        if data['stations']:
            st.write("### Log de Estaciones (Crudo)")
            df_s = pd.DataFrame(data['stations'])
            comp_s = df_s[df_s['Fase'] == 'Completado']
            if not comp_s.empty:
                st.dataframe(clean_df_excel(comp_s[['ID', 'Estación', 'Estado', 'Hora Inicio', 'Fin', 'Duración(s)', 'Nota']]).iloc[::-1], use_container_width=True)

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
            df_ord = pd.DataFrame(data['orders']).copy()
            
            # Gráfica de línea
            df_ord['Franja_dt'] = df_ord['Inicio_dt'].apply(lambda x: get_franja_dt(x, start_dt))
            counts = df_ord.groupby(['Franja_dt', 'Canal']).size().reset_index(name='Pedidos')
            
            franjas_unicas = df_ord['Franja_dt'].unique()
            canales_base = ['Caja', 'AutoMac', 'Delivery/Pickup']
            
            grid = pd.MultiIndex.from_product([franjas_unicas, canales_base], names=['Franja_dt', 'Canal']).to_frame(index=False)
            fig_df = pd.merge(grid, counts, on=['Franja_dt', 'Canal'], how='left').fillna(0)
            
            try:
                fig = px.line(fig_df, x='Franja_dt', y='Pedidos', color='Canal', color_discrete_map=MC_COLORS, markers=True, title="Curva de Demanda por Canal")
                fig.update_layout(xaxis_title="Hora de Inicio del Bloque", yaxis_title="Cantidad de Pedidos")
                st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.warning("Registra un poco más de datos para estabilizar la curva.")
            
            # Tabla de Rúbrica
            df_ord['Franja_str'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            counts_str = df_ord.groupby(['Franja_str', 'Canal']).size().reset_index(name='Pedidos')
            res_str = counts_str.pivot(index='Franja_str', columns='Canal', values='Pedidos').fillna(0).astype(int)
            res_str.columns.name = None
            
            for c in canales_base:
                if c not in res_str.columns: res_str[c] = 0
            res_str = res_str[canales_base]
            res_str['Total Intervalo'] = res_str.sum(axis=1)
            
            total_franja = pd.DataFrame(res_str.sum()).T
            total_franja.index = ["TOTAL FRANJA"]
            
            st.write("### Tabla de Conteos (Rúbrica)")
            st.dataframe(pd.concat([res_str, total_franja]), use_container_width=True)
        else: st.info("Registra pedidos para generar la curva de demanda.")

        st.divider()
        st.subheader("⏱️ Parámetros Estadísticos por Estación")
        if data['stations']:
            df_s = pd.DataFrame(data['stations'])
            comp_s = df_s[df_s['Fase'] == 'Completado']
            if not comp_s.empty:
                params = comp_s.groupby(['Estación', 'Estado'])['Duración(s)'].agg(
                    n='count', Mediana='median', Min='min', Max='max', 
                    P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()
                st.dataframe(params.round(2), use_container_width=True)
            else: st.info("Termina al menos una medición de estación para ver el resumen.")
        else: st.info("No hay registros de estaciones aún.")

# --- FLUJO PRINCIPAL ---
if st.session_state.view_session:
    s = st.session_state.view_session
    if st.button("⬅️ VOLVER AL INICIO"): st.session_state.view_session = None; st.rerun()
    st.title(f"📂 Revisando: {s['info']['franja']}")
    render_app_logic(s['data'], mode="consulta")
    st.download_button("📥 Descargar Excel del Reporte", export_excel_pro(s['data'], s['info']), f"Reporte_{s['info']['fecha']}.xlsx", use_container_width=True)

elif st.session_state.active_session is None:
    st.title("🍔 McMediciones Pro")
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
                    st.write(f"**{s['info'].get('fecha', '')} | {s['info']['franja']}** | {s['info']['observer']}")
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
