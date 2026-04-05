import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime
import io

# ==========================================
# 1. CONFIGURACIÓN Y ESTÉTICA
# ==========================================
st.set_page_config(page_title="McMediciones Pro", layout="wide", page_icon="🍔")

st.markdown("""
    <style>
    .stApp { background-color: #f8fafc; }
    div[data-testid="stVerticalBlock"] > div[style*="border"] { 
        border-radius: 12px; border: 1px solid #cbd5e1; background-color: white; box-shadow: 0 1px 2px rgba(0,0,0,0.05); 
    }
    .pill-red { background-color: #fee2e2; color: #b91c1c; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; }
    .pill-yellow { background-color: #fef3c7; color: #b45309; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; }
    .pill-black { background-color: #e2e8f0; color: #0f172a; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; }
    .pill-blue { background-color: #eff6ff; color: #1d4ed8; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; }
    .pill-green { background-color: #ecfdf5; color: #047857; padding: 4px 12px; border-radius: 9999px; font-size: 12px; font-weight: bold; }
    [data-testid="collapsedControl"] {display: none;}
    [data-testid="stSidebar"] {display: none;}
    </style>
""", unsafe_allow_html=True)

MC_COLORS = {'Caja': '#DA291C', 'AutoMac': '#FFC72C', 'Delivery/Pickup': '#27251F'}

# ==========================================
# 2. MEMORIA DEL SISTEMA (TODO EN TIEMPO REAL)
# ==========================================
if 'configurado' not in st.session_state: st.session_state.configurado = False
if 'orders' not in st.session_state: st.session_state.orders = []
if 'stations' not in st.session_state: st.session_state.stations = []
if 'arrivals' not in st.session_state: st.session_state.arrivals = []
if 'capacity' not in st.session_state: st.session_state.capacity = []
if 'events' not in st.session_state: st.session_state.events = []
if 'queues' not in st.session_state: st.session_state.queues = []

# ==========================================
# 3. PANTALLA DE INICIO
# ==========================================
if not st.session_state.configurado:
    st.title("🍔 McMediciones Pro")
    st.write("Sistema de Medición en Tiempo Real.")
    
    with st.container(border=True):
        obs = st.text_input("👤 Tu Nombre (Observador)")
        dia = st.date_input("📅 Fecha de Medición")
        franja = st.selectbox("⏱️ Franja de Medición", ["10:30–12:30", "11:30–14:00", "18:00–21:00", "Otra"])
        
        if st.button("▶ INICIAR TRABAJO DE CAMPO", type="primary", use_container_width=True):
            if obs:
                st.session_state.obs = obs
                st.session_state.franja = f"{dia} | {franja}"
                st.session_state.configurado = True
                st.rerun()
            else:
                st.error("⚠️ Ingresa tu nombre.")
    st.stop()

# ==========================================
# 4. NAVEGACIÓN Y TABS
# ==========================================
c_info, c_salir = st.columns([4, 1])
c_info.markdown(f"**Observador:** {st.session_state.obs} | **Franja:** {st.session_state.franja}")
if c_salir.button("🛑 Cerrar Sesión", use_container_width=True):
    st.session_state.clear()
    st.rerun()

tab_pedidos, tab_interna, tab_dash = st.tabs(["🚶‍♂️ 1. Registro de Pedidos", "🛠️ 2. Operación Interna", "📊 3. Dashboard y Exportar"])

# ---------------------------------------------------------
# TAB 1: PEDIDOS (EL NUEVO FLUJO MULTITAREA)
# ---------------------------------------------------------
with tab_pedidos:
    
    # 1. Registro Rápido (Llegadas y Colas 5m)
    with st.container(border=True):
        st.subheader("🚨 Controles Rápidos (Colas y Llegadas)")
        c1, c2, c3, c4 = st.columns(4)
        if c1.button("🚶‍♂️ +1 Caja (Llegada)", use_container_width=True): st.session_state.arrivals.append({"Canal": "Caja", "Timestamp": datetime.now()})
        if c2.button("🚗 +1 AutoMac (Llegada)", use_container_width=True): st.session_state.arrivals.append({"Canal": "AutoMac", "Timestamp": datetime.now()})
        if c3.button("🛵 +1 Delivery (Llegada)", use_container_width=True): st.session_state.arrivals.append({"Canal": "Delivery/Pickup", "Timestamp": datetime.now()})
        
        with c4.popover("📝 Registrar Colas (5min)"):
            qc = st.number_input("Fila Caja", 0)
            qa = st.number_input("Fila AutoMac", 0)
            if st.button("Guardar"):
                st.session_state.queues.append({"Hora": datetime.now().strftime("%H:%M:%S"), "Caja": qc, "AutoMac": qa})
                st.rerun()

    # 2. Creación de Pedido
    with st.container(border=True):
        st.subheader("➕ Nuevo Pedido a Medir")
        c1, c2, c3 = st.columns([2, 1, 1])
        n_canal = c1.selectbox("Canal:", ["Caja", "AutoMac", "Delivery/Pickup"], label_visibility="collapsed")
        n_items = c2.number_input("Items (Tamaño):", min_value=1, value=1, label_visibility="collapsed")
        if c3.button("▶ Iniciar Pedido", type="primary", use_container_width=True):
            pid = f"P-{len(st.session_state.orders) + 1:03d}"
            st.session_state.orders.append({
                'ID': pid, 'Canal': n_canal, 'Items': n_items, 'Estado': 'Ordering',
                'Inicio': datetime.now(), 'Fin_Orden': None, 'Fin_Espera': None,
                'Cola_Salida': None, 'Obs': None
            })
            st.rerun()

    st.write("---")
    if st.button("🔄 Actualizar Relojes", use_container_width=True): st.rerun()

    # 3. TABLEROS EN VIVO (Ordering -> Waiting)
    col_ord, col_wait = st.columns(2)
    
    # Columna 1: TOMANDO PEDIDO
    with col_ord:
        st.markdown("### 📝 Tomando Pedido (Ordering)")
        pedidos_ordering = [p for p in st.session_state.orders if p['Estado'] == 'Ordering']
        if not pedidos_ordering: st.info("No hay pedidos en esta fase.")
        
        for p in pedidos_ordering:
            with st.container(border=True):
                t_ord = int((datetime.now() - p['Inicio']).total_seconds())
                pill = "pill-red" if p['Canal'] == "Caja" else "pill-yellow" if p['Canal'] == "AutoMac" else "pill-black"
                st.markdown(f"**{p['ID']}** | <span class='{pill}'>{p['Canal']}</span> ({p['Items']} items)", unsafe_allow_html=True)
                st.write(f"⏱️ Tiempo pidiendo: **{t_ord}s**")
                
                if st.button("▶ Pasar a Espera", key=f"mw_{p['ID']}", use_container_width=True):
                    p['Estado'] = 'Waiting'
                    p['Fin_Orden'] = datetime.now()
                    st.rerun()

    # Columna 2: EN ESPERA
    with col_wait:
        st.markdown("### ⏳ En Espera (Waiting)")
        pedidos_waiting = [p for p in st.session_state.orders if p['Estado'] == 'Waiting']
        if not pedidos_waiting: st.info("No hay pedidos esperando.")
        
        for p in pedidos_waiting:
            with st.container(border=True):
                t_tot = int((datetime.now() - p['Inicio']).total_seconds())
                t_wait = int((datetime.now() - p['Fin_Orden']).total_seconds())
                pill = "pill-red" if p['Canal'] == "Caja" else "pill-yellow" if p['Canal'] == "AutoMac" else "pill-black"
                
                st.markdown(f"**{p['ID']}** | <span class='{pill}'>{p['Canal']}</span> ({p['Items']} items)", unsafe_allow_html=True)
                st.write(f"⏱️ Total: **{t_tot}s** | Esperando: **{t_wait}s**")
                
                if p['Canal'] in ["Caja", "AutoMac"]:
                    cola_fin = st.number_input("Cola al salir:", 0, key=f"cf_{p['ID']}")
                    obs = "N/A"
                else:
                    cola_fin = 0
                    obs = st.selectbox("Obs:", ["Ninguna", "Domiciliario tarde", "Congestión"], key=f"ob_{p['ID']}")

                if st.button("✅ Entregar y Finalizar", key=f"mf_{p['ID']}", type="primary", use_container_width=True):
                    p['Estado'] = 'Completed'
                    p['Fin_Espera'] = datetime.now()
                    p['Cola_Salida'] = cola_fin
                    p['Obs'] = obs
                    st.rerun()

    # 4. TABLA EN VIVO DE PEDIDOS
    st.write("---")
    st.subheader("📋 Pedidos Finalizados")
    pedidos_completos = [p for p in st.session_state.orders if p['Estado'] == 'Completed']
    if pedidos_completos:
        datos_tabla = []
        for p in pedidos_completos:
            t_ord = int((p['Fin_Orden'] - p['Inicio']).total_seconds())
            t_wait = int((p['Fin_Espera'] - p['Fin_Orden']).total_seconds())
            t_tot = int((p['Fin_Espera'] - p['Inicio']).total_seconds())
            datos_tabla.append({
                "ID": p['ID'], "Canal": p['Canal'], "Items": p['Items'],
                "T. Orden(s)": t_ord, "T. Espera(s)": t_wait, "T. Total(s)": t_tot,
                "Cola Salida": p['Cola_Salida'], "Obs": p['Obs']
            })
        st.dataframe(pd.DataFrame(datos_tabla).iloc[::-1], use_container_width=True)
    else:
        st.info("Aún no has finalizado ningún pedido.")

# ---------------------------------------------------------
# TAB 2: OPERACIÓN INTERNA
# ---------------------------------------------------------
with tab_interna:
    
    # 1. Estaciones
    with st.container(border=True):
        st.subheader("🍳 IV. Tiempos por Estación")
        sc1, sc2, sc3 = st.columns([2, 2, 1])
        s_nom = sc1.selectbox("Estación:", ["Ensamble", "Bebidas/Postres", "Staging/Bolseo", "Parrilla", "Freidoras"])
        s_est = sc2.selectbox("Estado:", ["Hecho a pedido", "Listo (Ya preparado)"])
        if sc3.button("▶ Iniciar", type="primary", use_container_width=True):
            sid = f"E-{len(st.session_state.stations) + 1:03d}"
            st.session_state.stations.append({'ID': sid, 'Estación': s_nom, 'Estado': s_est, 'Fase': 'Corriendo', 'Inicio': datetime.now()})
            st.rerun()

        est_activas = [e for e in st.session_state.stations if e['Fase'] == 'Corriendo']
        for e in est_activas:
            with st.container(border=True):
                ec1, ec2, ec3 = st.columns([2, 2, 1])
                t_seg = int((datetime.now() - e['Inicio']).total_seconds())
                ec1.markdown(f"**{e['ID']}** | {e['Estación']} | <span class='pill-blue'>Corriendo: {t_seg}s</span>", unsafe_allow_html=True)
                nota = ec2.text_input("Nota breve:", key=f"nt_{e['ID']}")
                if ec3.button("🛑 Fin", key=f"fb_{e['ID']}"):
                    e['Fase'] = 'Completed'
                    e['Fin'] = datetime.now()
                    e['Duración (s)'] = int((e['Fin'] - e['Inicio']).total_seconds())
                    e['Nota'] = nota
                    st.rerun()

        est_fin = [e for e in st.session_state.stations if e['Fase'] == 'Completed']
        if est_fin:
            st.markdown("**📋 Estaciones Finalizadas:**")
            df_e = pd.DataFrame(est_fin)[['Estación', 'Estado', 'Duración (s)', 'Nota']]
            st.dataframe(df_e.iloc[::-1], use_container_width=True)

    # 2. Capacidad y Eventos
    c_cap, c_ev = st.columns(2)
    with c_cap:
        with st.container(border=True):
            st.subheader("👥 V. Capacidad Efectiva")
            momento = st.selectbox("Momento:", ["Inicio de Franja", "Pico de Congestión"])
            z_p, z_e = st.columns(2)
            p_val = z_p.number_input("Personas Activas", 0)
            e_val = z_e.number_input("Equipos Activos", 0)
            if st.button("Guardar Capacidad", use_container_width=True):
                st.session_state.capacity.append({"Hora": datetime.now().strftime('%H:%M:%S'), "Momento": momento, "Pers": p_val, "Eqps": e_val})
                st.rerun()
            if st.session_state.capacity: st.dataframe(pd.DataFrame(st.session_state.capacity).iloc[::-1], use_container_width=True)

    with c_ev:
        with st.container(border=True):
            st.subheader("⚠️ VI. Registro de Eventos")
            evento = st.text_input("Descripción (falla, reposición...):")
            if st.button("Guardar Evento", use_container_width=True):
                st.session_state.events.append({"Hora": datetime.now().strftime('%H:%M:%S'), "Evento": evento})
                st.rerun()
            if st.session_state.events: st.dataframe(pd.DataFrame(st.session_state.events).iloc[::-1], use_container_width=True)

# ---------------------------------------------------------
# TAB 3: DASHBOARD Y EXPORTAR (TODO INTEGRADO)
# ---------------------------------------------------------
with tab_dash:
    st.header("📈 Dashboard y Exportación")
    
    # Demanda 5 min
    if st.session_state.arrivals:
        df_arr = pd.DataFrame(st.session_state.arrivals)
        dem_5m = df_arr.groupby([pd.Grouper(key='Timestamp', freq='5min'), 'Canal']).size().reset_index(name='Pedidos')
        
        st.subheader("Curva de Demanda (Intervalos 5 min)")
        fig = px.line(dem_5m, x='Timestamp', y='Pedidos', color='Canal', markers=True, color_discrete_map=MC_COLORS)
        st.plotly_chart(fig, use_container_width=True)
        
        resumen = dem_5m.pivot(index='Timestamp', columns='Canal', values='Pedidos').fillna(0).astype(int)
        resumen['Total Intervalo'] = resumen.sum(axis=1)
        total_franja = resumen.sum().to_frame().T
        total_franja.index = ['TOTAL FRANJA']
        resumen_final = pd.concat([resumen, total_franja])
        st.dataframe(resumen_final, use_container_width=True)
    else:
        st.info("Registra llegadas (+1) en la pestaña 1 para ver la curva de demanda.")

    st.write("---")
    
    # BOTÓN MAESTRO DE EXCEL
    st.subheader("📂 Descargar Toda la Sesión")
    
    if st.button("Preparar Excel Maestro", type="primary"):
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            # 1. Llegadas
            if st.session_state.arrivals:
                resumen_final.to_excel(writer, sheet_name='Demanda_5min')
                pd.DataFrame(st.session_state.arrivals).to_excel(writer, sheet_name='Llegadas_Crudas', index=False)
            
            # 2. Pedidos End-to-End
            if pedidos_completos: pd.DataFrame(datos_tabla).to_excel(writer, sheet_name='Pedidos_E2E', index=False)
            
            # 3. Estaciones
            est_fin = [e for e in st.session_state.stations if e['Fase'] == 'Completed']
            if est_fin: pd.DataFrame(est_fin).drop(columns=['Fase', 'Inicio', 'Fin']).to_excel(writer, sheet_name='Estaciones', index=False)
            
            # 4. Extras
            if st.session_state.capacity: pd.DataFrame(st.session_state.capacity).to_excel(writer, sheet_name='Capacidad', index=False)
            if st.session_state.events: pd.DataFrame(st.session_state.events).to_excel(writer, sheet_name='Eventos', index=False)
            if st.session_state.queues: pd.DataFrame(st.session_state.queues).to_excel(writer, sheet_name='Colas_Globales', index=False)
            
        st.download_button(
            label="📥 HAZ CLIC AQUÍ PARA DESCARGAR EL REPORTE FINAL (EXCEL)", 
            data=output.getvalue(), 
            file_name=f"McMediciones_Final_{datetime.now().strftime('%H%M')}.xlsx", 
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
