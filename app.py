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
            with open(HISTORY_FILE, "rb") as f:
                return pickle.load(f)
        except:
            return []
    return []

def save_history():
    with open(HISTORY_FILE, "wb") as f:
        pickle.dump(st.session_state.history, f)

if 'history' not in st.session_state:
    st.session_state.history = load_history()
if 'active_session' not in st.session_state:
    st.session_state.active_session = None
if 'view_session' not in st.session_state:
    st.session_state.view_session = None

# Variables para el Rastreo Secuencial (Shadowing)
if 'active_shadow' not in st.session_state:
    st.session_state.active_shadow = []
if 'shadow_counter' not in st.session_state:
    st.session_state.shadow_counter = 0

for key in ['orders', 'queues', 'stations', 'capacity', 'events']:
    if key not in st.session_state:
        st.session_state[key] = []

if 'order_counter' not in st.session_state:
    st.session_state.order_counter = 1
if 'session_start_time' not in st.session_state:
    st.session_state.session_start_time = None

# --- FUNCIONES DE CÁLCULO Y EXCEL ---
def get_franja_dt(timestamp, start_time):
    if not start_time:
        return timestamp
    diff = timestamp - start_time
    intervals = int(diff.total_seconds() // 300)
    return start_time + timedelta(minutes=intervals * 5)

def get_interval_label(timestamp, start_time):
    if not start_time:
        return "00:00 - 00:05"
    f_start = get_franja_dt(timestamp, start_time)
    f_end = f_start + timedelta(minutes=5)
    return f"{f_start.strftime('%H:%M')} - {f_end.strftime('%H:%M')}"

def clean_df_excel(df):
    if df is None or df.empty:
        return pd.DataFrame()
    df = df.copy()
    for c in ['Inicio_ts', 'Inicio_dt', 'Fase', 'Franja_dt']:
        if c in df.columns:
            df = df.drop(columns=[c])
    for col in df.columns:
        if pd.api.types.is_datetime64_any_dtype(df[col]):
            df[col] = df[col].dt.tz_localize(None)
    return df

def export_excel_pro(session_data, session_info):
    output = io.BytesIO()
    start_dt = session_info.get('start_dt')

    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        workbook = writer.book
        header_format = workbook.add_format({
            'bold': True, 'font_color': 'white', 'bg_color': '#DA291C',
            'border': 1, 'align': 'center', 'valign': 'vcenter'
        })
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
                params = df_s.groupby(['Estación'])['Duración(s)'].agg(
                    Muestra='count', Media='mean', Mediana='median',
                    Min='min', Max='max', P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()

                escribir_y_formatear(params.round(2), 'Parametros_Estaciones')
                escribir_y_formatear(clean_df_excel(df_s), 'Estaciones_Crudo')

        if session_data.get('queues'):
            escribir_y_formatear(pd.DataFrame(session_data['queues']), 'Colas_5min')
        if session_data.get('capacity'):
            escribir_y_formatear(pd.DataFrame(session_data['capacity']), 'Capacidad_Efectiva')
        if session_data.get('events'):
            escribir_y_formatear(pd.DataFrame(session_data['events']), 'Eventos_Inusuales')

    return output.getvalue()

def export_master_excel(historial):
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
        todas_ordenes = []
        todas_estaciones = []

        for s in historial:
            franja = s['info'].get('franja', 'Sin Franja')
            fecha = s['info'].get('fecha', 'Sin Fecha')

            if s['data'].get('orders'):
                df_o = pd.DataFrame(s['data']['orders']).copy()
                df_o.insert(0, 'Franja Evaluación', franja)
                df_o.insert(0, 'Fecha', fecha)
                todas_ordenes.append(df_o)
            
            if s['data'].get('stations'):
                df_e = pd.DataFrame(s['data']['stations']).copy()
                df_e = df_e[df_e['Fase'] == 'Completado']
                df_e.insert(0, 'Franja Evaluación', franja)
                df_e.insert(0, 'Fecha', fecha)
                todas_estaciones.append(df_e)

        if todas_ordenes:
            df_final_o = clean_df_excel(pd.concat(todas_ordenes, ignore_index=True))
            df_final_o.to_excel(writer, sheet_name='Master_Pedidos', index=False)
        
        if todas_estaciones:
            df_final_e = clean_df_excel(pd.concat(todas_estaciones, ignore_index=True))
            df_final_e.to_excel(writer, sheet_name='Master_Estaciones', index=False)

    return output.getvalue()

# --- LÓGICA PRINCIPAL DE LA APP ---
def render_app_logic(data, mode="vivo"):
    start_dt = st.session_state.session_start_time if mode == "vivo" else st.session_state.view_session['info']['start_dt']
    readonly = (mode == "consulta")

    if mode == "vivo" and start_dt:
        now = datetime.now(BOGOTA_TZ)
        curr_franja = get_interval_label(now, start_dt)
        ya = any(q.get('Franja') == curr_franja for q in st.session_state.queues)
        if not ya:
            st.markdown(f'<div class="alerta-colas">🚨 REGISTRA LA COLA: {curr_franja} 🚨</div>', unsafe_allow_html=True)

    t1, t2, t3, t4 = st.tabs(["🏃‍♂️ 1. Pedidos y Colas", "🍳 2. Estaciones (Shadowing)", "👥 3. Capacidad / Eventos", "📊 4. Dashboard"])

    with t1:
        c1, c2 = st.columns([1, 2])
        with c1:
            st.subheader("🚨 Colas")
            qc = st.number_input("Caja", 0, disabled=readonly)
            qa = st.number_input("AutoMac", 0, disabled=readonly)
            if not readonly and st.button("💾 Guardar Cola", use_container_width=True):
                st.session_state.queues.append({
                    "Hora": datetime.now(BOGOTA_TZ).strftime("%H:%M:%S"),
                    "Franja": get_interval_label(datetime.now(BOGOTA_TZ), start_dt), "Caja": qc, "AutoMac": qa
                })
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
                st.session_state.orders.append({
                    'ID': f"P-{st.session_state.order_counter:03d}", 'Canal': n_can, 'Items': n_itm,
                    'Estado': 'Ordering', 'Inicio_ts': time.time(), 'Inicio_dt': now,
                    'Hora Inicio': now.strftime("%H:%M:%S"), 'Fin Ordering': '-', 'Hora Entrega': '-', 'Duración Total(s)': 0
                })
                st.session_state.order_counter += 1
                st.rerun()

        k1, k2 = st.columns(2)
        with k1:
            st.markdown("### 📝 Tomando Pedido")
            for p in [p for p in st.session_state.orders if p['Estado'] == 'Ordering']:
                with st.container(border=True):
                    st.write(f"🍔 **{p['ID']}** | {p['Canal']} | {p['Items']} items")
                    if not readonly and st.button("➡️ Pasar a Espera", key=f"w_{p['ID']}", use_container_width=True):
                        p['Estado'] = 'Waiting'
                        p['Fin Ordering'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S")
                        st.rerun()
        with k2:
            st.markdown("### ⏳ Esperando Entrega")
            for p in [p for p in st.session_state.orders if p['Estado'] == 'Waiting']:
                with st.container(border=True):
                    st.write(f"🛍️ **{p['ID']}** | {p['Canal']} | {p['Items']} items")
                    if not readonly and st.button("✅ Entregar", key=f"f_{p['ID']}", type="primary", use_container_width=True):
                        p['Estado'] = 'Completado'
                        p['Hora Entrega'] = datetime.now(BOGOTA_TZ).strftime("%H:%M:%S")
                        p['Duración Total(s)'] = round(time.time() - p['Inicio_ts'], 2)
                        st.rerun()

        if data['orders']:
            st.write("### Tabla de Pedidos End-to-End")
            df_o = pd.DataFrame(data['orders'])
            comp = df_o[df_o['Estado'] == 'Completado']
            if not comp.empty:
                st.dataframe(clean_df_excel(comp[['ID', 'Canal', 'Items', 'Hora Inicio', 'Fin Ordering', 'Hora Entrega', 'Duración Total(s)']]).iloc[::-1], use_container_width=True)

    with t2:
        st.subheader("🍳 Shadowing Secuencial (Rastreo de Pedido)")
        st.info("💡 Sigue un pedido en vivo. Puedes saltar bebidas si el pedido no tiene.")

        if not readonly and st.button("➕ Iniciar Nuevo Rastreo", type="primary"):
            st.session_state.shadow_counter += 1
            new_id = f"Ticket-{st.session_state.shadow_counter:02d}"
            st.session_state.active_shadow.append({
                'id': new_id, 'fase_actual': 'Ensamble', 'inicio_global': time.time(), 'inicio_fase': time.time()
            })
            st.rerun()

        for s in st.session_state.active_shadow:
            with st.container(border=True):
                st.markdown(f"### 🍔 {s['id']} (Cocina: {time.time() - s['inicio_global']:.0f}s)")

                if s['fase_actual'] == 'Ensamble':
                    st.markdown("#### 📍 Fase 1: Ensamble")
                    nota = st.text_input("Observaciones (opcional):", key=f"n_ens_{s['id']}")
                    if st.button("Siguiente ➡️ (A Bebidas)", key=f"b_ens_{s['id']}"):
                        st.session_state.stations.append({
                            'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Ticket': s['id'], 
                            'Estación': 'Ensamble', 'Fase': 'Completado', 'Duración(s)': round(time.time() - s['inicio_fase'], 2), 'Nota': nota
                        })
                        s['fase_actual'] = 'Bebidas/Postres'
                        s['inicio_fase'] = time.time()
                        st.rerun()

                elif s['fase_actual'] == 'Bebidas/Postres':
                    st.markdown("#### 📍 Fase 2: Bebidas y Postres")
                    tiene_bebida = st.checkbox("🥤 ¿Lleva bebida, helado o postre?", value=True, key=f"chk_{s['id']}")
                    if tiene_bebida:
                        nota = st.text_input("Observaciones (opcional):", key=f"n_beb_{s['id']}")
                        if st.button("Siguiente ➡️ (A Bolseo)", key=f"b_beb_{s['id']}"):
                            st.session_state.stations.append({
                                'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Ticket': s['id'], 
                                'Estación': 'Bebidas/Postres', 'Fase': 'Completado', 'Duración(s)': round(time.time() - s['inicio_fase'], 2), 'Nota': nota
                            })
                            s['fase_actual'] = 'Staging/Bolseo'
                            s['inicio_fase'] = time.time()
                            st.rerun()
                    else:
                        st.info("⏭️ Sin bebidas. Pasa directo a bolseo.")
                        if st.button("Saltar estación ➡️", key=f"b_skip_{s['id']}"):
                            s['fase_actual'] = 'Staging/Bolseo'
                            st.rerun()

                elif s['fase_actual'] == 'Staging/Bolseo':
                    st.markdown("#### 📍 Fase 3: Staging / Bolseo")
                    nota = st.text_input("Observaciones finales:", key=f"n_bol_{s['id']}")
                    if st.button("✅ Finalizar Rastreo", type="primary", key=f"b_bol_{s['id']}"):
                        st.session_state.stations.append({
                            'ID': f"E-{len(st.session_state.stations)+1:03d}", 'Ticket': s['id'], 
                            'Estación': 'Staging/Bolseo', 'Fase': 'Completado', 'Duración(s)': round(time.time() - s['inicio_fase'], 2), 'Nota': nota
                        })
                        st.session_state.active_shadow.remove(s)
                        st.rerun()

        if data['stations']:
            st.write("### 📋 Log de Tiempos por Estación")
            df_s = pd.DataFrame(data['stations'])
            comp_s = df_s[df_s['Fase'] == 'Completado'].copy()
            if not comp_s.empty:
                if 'Ticket' not in comp_s.columns: comp_s['Ticket'] = "N/A"
                st.dataframe(comp_s[['Ticket', 'Estación', 'Duración(s)', 'Nota']].iloc[::-1], use_container_width=True)

    with t3:
        st.subheader("👥 Capacidad Efectiva")
        with st.container(border=True):
            momento = st.radio("Registro:", ["Inicio de Franja", "Pico de Congestión"], horizontal=True, disabled=readonly)
            c1, c2, c3 = st.columns(3)
            c4, c5, c6 = st.columns(3)
            p1 = c1.number_input("Parrilla", 0, disabled=readonly)
            p2 = c2.number_input("Freidoras", 0, disabled=readonly)
            p3 = c3.number_input("Ensamble", 0, disabled=readonly)
            p4 = c4.number_input("Bebidas", 0, disabled=readonly)
            p5 = c5.number_input("Bolseo", 0, disabled=readonly)
            p6 = c6.number_input("Entrega", 0, disabled=readonly)
            eq = st.number_input("Puestos Activos", 0, disabled=readonly)

            if not readonly and st.button("💾 Guardar Capacidad", use_container_width=True):
                st.session_state.capacity.append({
                    "Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Momento": momento, "Parrilla": p1, "Freidoras": p2, 
                    "Ensamble": p3, "Bebidas": p4, "Bolseo": p5, "Entrega": p6, "Equipos": eq
                })
                st.rerun()

        if data['capacity']: st.dataframe(pd.DataFrame(data['capacity']).iloc[::-1], use_container_width=True)

        st.divider()
        st.subheader("⚠️ Eventos Inusuales")
        ev_msg = st.text_input("Nota del evento:", disabled=readonly)
        if not readonly and st.button("💾 Guardar Evento"):
            st.session_state.events.append({"Hora": datetime.now(BOGOTA_TZ).strftime('%H:%M:%S'), "Evento": ev_msg})
            st.rerun()
        if data['events']: st.dataframe(pd.DataFrame(data['events']).iloc[::-1], use_container_width=True)

    with t4:
        st.subheader("📊 Análisis de Demanda")
        if data['orders'] and len(data['orders']) > 0:
            df_ord = pd.DataFrame(data['orders']).copy()
            df_ord['Franja_str'] = df_ord['Inicio_dt'].apply(lambda x: get_interval_label(x, start_dt))
            counts_str = df_ord.groupby(['Franja_str', 'Canal']).size().reset_index(name='Pedidos')

            canales_base = ['Caja', 'AutoMac', 'Delivery/Pickup']
            res_str = counts_str.pivot(index='Franja_str', columns='Canal', values='Pedidos').fillna(0).astype(int)
            res_str.columns.name = None
            for c in canales_base:
                if c not in res_str.columns: res_str[c] = 0
            res_str = res_str[canales_base]
            res_str['Total Intervalo'] = res_str.sum(axis=1)

            total_franja = pd.DataFrame(res_str.sum()).T
            total_franja.index = ["TOTAL FRANJA"]

            franjas_unicas = df_ord['Franja_str'].unique()
            grid = pd.MultiIndex.from_product([franjas_unicas, canales_base], names=['Franja_str', 'Canal']).to_frame(index=False)
            fig_df = pd.merge(grid, counts_str, on=['Franja_str', 'Canal'], how='left').fillna(0)

            try:
                fig = px.line(fig_df, x='Franja_str', y='Pedidos', color='Canal', color_discrete_map=MC_COLORS, markers=True, title="Curva de Demanda por Canal")
                fig.update_layout(xaxis_title="Franja Horaria", yaxis_title="Cantidad de Pedidos")
                st.plotly_chart(fig, use_container_width=True)
            except Exception:
                st.warning("Registra un poco más de datos para estabilizar la curva.")

            st.write("### Tabla de Conteos")
            st.dataframe(pd.concat([res_str, total_franja]), use_container_width=True)
        else:
            st.info("Registra pedidos para generar la curva de demanda.")

        st.divider()
        st.subheader("⏱️ Parámetros Estadísticos por Estación")
        if data['stations']:
            df_s = pd.DataFrame(data['stations'])
            comp_s = df_s[df_s['Fase'] == 'Completado']
            if not comp_s.empty:
                params = comp_s.groupby(['Estación'])['Duración(s)'].agg(
                    Muestra='count', Media='mean', Mediana='median', Min='min', Max='max', 
                    P10=lambda x: x.quantile(0.10), P90=lambda x: x.quantile(0.90)
                ).reset_index()
                st.dataframe(params.round(2), use_container_width=True)
            else:
                st.info("Termina al menos una medición para ver el resumen.")
        else:
            st.info("No hay registros de estaciones aún.")

# --- FLUJO PRINCIPAL ---
if st.session_state.view_session:
    s = st.session_state.view_session
    if st.button("⬅️ VOLVER AL INICIO"):
        st.session_state.view_session = None
        st.rerun()

    st.title(f"📂 Revisando: {s['info']['franja']}")
    render_app_logic(s['data'], mode="consulta")

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
                st.session_state.active_session = {
                    "franja": franj, "observer": obs_n, "fecha": str(obs_f), "start_dt": st.session_state.session_start_time
                }
                st.session_state.orders = []
                st.session_state.queues = []
                st.session_state.stations = []
                st.session_state.capacity = []
                st.session_state.events = []
                st.rerun()

    with c2:
        st.subheader("Historial de Sesiones")
        
        if st.session_state.history:
            # --- EL BOTÓN MASTER GIGANTE ---
            st.download_button(
                label="📊 DESCARGAR BASE DE DATOS MASTER (Todas las Franjas)",
                data=export_master_excel(st.session_state.history),
                file_name="Master_McMediciones.xlsx",
                type="primary",
                use_container_width=True
            )
            st.divider()
            
            for s in reversed(st.session_state.history):
                with st.container(border=True):
                    st.write(f"**{s['info'].get('fecha', '')} | {s['info']['franja']}** | {s['info']['observer']}")
                    bc1, bc2, bc3 = st.columns(3)
                    bc1.download_button("💾 Bajar Franja", export_excel_pro(s['data'], s['info']), f"Data_{s['info']['fecha']}.xlsx", key=f"ex_{s['info']['start_dt']}")
                    if bc2.button("📈 Revisar", key=f"v_{s['info']['start_dt']}", use_container_width=True):
                        st.session_state.view_session = s
                        st.rerun()
                    if bc3.button("🗑️", key=f"del_{s['info']['start_dt']}", use_container_width=True):
                        st.session_state.history = [h for h in st.session_state.history if h['info'] != s['info']]
                        save_history()
                        st.rerun()
        else:
            st.info("No hay sesiones guardadas.")

else:
    h1, h2 = st.columns([4, 1])
    h1.title("Medición en Vivo")

    if h2.button("⏹ FINALIZAR SESIÓN", type="primary"):
        st.session_state.history.append({
            "info": st.session_state.active_session,
            "data": {
                'orders': list(st.session_state.orders), 'queues': list(st.session_state.queues),
                'stations': list(st.session_state.stations), 'capacity': list(st.session_state.capacity), 'events': list(st.session_state.events)
            }
        })
        st.session_state.active_session = None
        save_history()
        st.rerun()

    render_app_logic({
        'orders': st.session_state.orders, 'queues': st.session_state.queues,
        'stations': st.session_state.stations, 'capacity': st.session_state.capacity, 'events': st.session_state.events
    }, mode="vivo")
