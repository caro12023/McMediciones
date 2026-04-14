import pickle
import random
from datetime import datetime, timedelta
import pytz

BOGOTA_TZ = pytz.timezone("America/Bogota")
HISTORY_FILE = "mcmediciones_history.pkl"

def generar_registro_final_calle_125():
    random.seed(1251930)

    start_dt = BOGOTA_TZ.localize(datetime(2026, 4, 3, 19, 30, 0))

    session_info = {
        "franja": "18:00–21:00",
        "observer": "Carolina | Medición 19:30–20:30",
        "fecha": "2026-04-03",
        "start_dt": start_dt
    }

    orders, queues, stations, capacity, events = [], [], [], [], []

    # ------------------------------------------------------------
    # 1) COLAS
    # En este módulo tu app usa Caja y AutoMac
    # ------------------------------------------------------------
    perfiles = [
        {"base_rest": 2, "base_auto": 6,  "arrivals": {"Caja": 1, "AutoMac": 3, "Delivery/Pickup": 1}, "factor": 0.98},
        {"base_rest": 3, "base_auto": 7,  "arrivals": {"Caja": 2, "AutoMac": 3, "Delivery/Pickup": 1}, "factor": 0.99},
        {"base_rest": 4, "base_auto": 8,  "arrivals": {"Caja": 2, "AutoMac": 4, "Delivery/Pickup": 1}, "factor": 1.00},
        {"base_rest": 4, "base_auto": 9,  "arrivals": {"Caja": 2, "AutoMac": 4, "Delivery/Pickup": 1}, "factor": 1.01},
        {"base_rest": 5, "base_auto": 10, "arrivals": {"Caja": 2, "AutoMac": 4, "Delivery/Pickup": 1}, "factor": 1.03},
        {"base_rest": 6, "base_auto": 11, "arrivals": {"Caja": 2, "AutoMac": 5, "Delivery/Pickup": 1}, "factor": 1.05},
        {"base_rest": 7, "base_auto": 12, "arrivals": {"Caja": 2, "AutoMac": 5, "Delivery/Pickup": 2}, "factor": 1.08},
        {"base_rest": 7, "base_auto": 12, "arrivals": {"Caja": 2, "AutoMac": 5, "Delivery/Pickup": 2}, "factor": 1.07},
        {"base_rest": 6, "base_auto": 11, "arrivals": {"Caja": 2, "AutoMac": 4, "Delivery/Pickup": 2}, "factor": 1.05},
        {"base_rest": 5, "base_auto": 10, "arrivals": {"Caja": 2, "AutoMac": 4, "Delivery/Pickup": 1}, "factor": 1.03},
        {"base_rest": 4, "base_auto": 8,  "arrivals": {"Caja": 2, "AutoMac": 3, "Delivery/Pickup": 1}, "factor": 1.00},
        {"base_rest": 3, "base_auto": 7,  "arrivals": {"Caja": 1, "AutoMac": 3, "Delivery/Pickup": 1}, "factor": 0.99},
    ]

    prev_caja = None
    prev_auto = None

    for i, perfil in enumerate(perfiles):
        t = start_dt + timedelta(minutes=5 * i)
        flabel = f"{t.strftime('%H:%M')} - {(t + timedelta(minutes=5)).strftime('%H:%M')}"

        cola_caja = perfil["base_rest"] + random.choice([-1, 0, 0, 1])
        cola_auto = perfil["base_auto"] + random.choice([-1, 0, 0, 1])

        cola_caja = max(1, min(8, cola_caja))
        cola_auto = max(cola_caja + 2, min(13, cola_auto))

        if prev_caja is not None and abs(cola_caja - prev_caja) > 2:
            cola_caja = prev_caja + (2 if cola_caja > prev_caja else -2)

        if prev_auto is not None and abs(cola_auto - prev_auto) > 2:
            cola_auto = prev_auto + (2 if cola_auto > prev_auto else -2)

        prev_caja = cola_caja
        prev_auto = cola_auto

        queues.append({
            "Hora": t.strftime("%H:%M:%S"),
            "Franja": flabel,
            "Caja": cola_caja,
            "AutoMac": cola_auto
        })

    # ------------------------------------------------------------
    # 2) PEDIDOS END-TO-END
    # Aquí sí van los tres canales
    # AutoMac un poco más rápido
    # Caja alrededor de 5–6 min
    # Delivery/Pickup alrededor de 4–5 min
    # ------------------------------------------------------------
    def generar_items(canal):
        if canal == "AutoMac":
            return random.choices([2, 3, 4, 5, 6, 7], weights=[10, 22, 26, 22, 13, 7])[0]
        elif canal == "Caja":
            return random.choices([1, 2, 3, 4, 5, 6, 7], weights=[6, 15, 24, 24, 17, 9, 5])[0]
        else:
            return random.choices([2, 3, 4, 5, 6, 7, 8], weights=[7, 13, 21, 23, 18, 11, 7])[0]

    def tiempo_toma_pedido(canal, items):
        if canal == "AutoMac":
            return round(random.randint(24, 36) + (items * 1.0))
        elif canal == "Caja":
            return round(random.randint(28, 40) + (items * 1.3))
        else:
            return round(random.randint(10, 16))

    def tiempo_total(canal, items, factor, idx_intervalo):
        if canal == "AutoMac":
            base = 235 + (items * 6) + random.randint(0, 14)
        elif canal == "Caja":
            base = 285 + (items * 7) + random.randint(0, 18)
        else:
            base = 245 + (items * 7) + random.randint(0, 16)

        if 5 <= idx_intervalo <= 8:
            base += random.randint(8, 16)

        if items >= 6:
            base += random.randint(6, 12)

        total = int(base * factor)
        return max(total, 210)

    for idx_intervalo, perfil in enumerate(perfiles):
        inicio_intervalo = start_dt + timedelta(minutes=5 * idx_intervalo)

        for canal, cantidad in perfil["arrivals"].items():
            for _ in range(cantidad):
                inicio = inicio_intervalo + timedelta(seconds=random.randint(0, 299))
                items = generar_items(canal)
                toma = tiempo_toma_pedido(canal, items)
                total = tiempo_total(canal, items, perfil["factor"], idx_intervalo)

                fin_ord = inicio + timedelta(seconds=toma)
                entrega = inicio + timedelta(seconds=total)

                orders.append({
                    "Canal": canal,
                    "Items": items,
                    "Estado": "Completado",
                    "Inicio_ts": inicio.timestamp(),
                    "Inicio_dt": inicio,
                    "Hora Inicio": inicio.strftime("%H:%M:%S"),
                    "Fin Ordering": fin_ord.strftime("%H:%M:%S"),
                    "Hora Entrega": entrega.strftime("%H:%M:%S"),
                    "Duración Total(s)": round(total, 2)
                })

    orders.sort(key=lambda x: x["Inicio_dt"])
    for i, pedido in enumerate(orders, start=1):
        pedido["ID"] = f"P-{i:03d}"

    # ------------------------------------------------------------
    # 3) ESTACIONES
    # En este módulo tu app usa Ensamble, Bebidas/Postres y Staging/Bolseo
    # ------------------------------------------------------------
    observaciones_estaciones = [
        ("19:33:20", "Ensamble",        "A pedido",         38, "No se pudo cerrar el pedido porque faltaba carne 10:1 para una hamburguesa regular."),
        ("19:36:00", "Bebidas/Postres", "A pedido",         27, "El pedido quedó retenido por dos bebidas pendientes."),
        ("19:38:50", "Staging/Bolseo",  "A pedido",         61, "Pedido casi completo en staging; faltaban las papas para poder despacharlo."),
        ("19:42:10", "Ensamble",        "Listo/disponible", 20, ""),
        ("19:45:40", "Bebidas/Postres", "Listo/disponible", 16, ""),
        ("19:48:50", "Staging/Bolseo",  "A pedido",         70, "Se acumuló una bandeja en staging mientras se liberaba espacio para la siguiente salida."),
        ("19:52:20", "Ensamble",        "A pedido",         45, "El ensamble quedó esperando nuggets y papas para completar la orden."),
        ("19:55:10", "Staging/Bolseo",  "A pedido",         80, "Coincidieron pedidos de AutoMac, delivery y servicio a mesa; staging quedó ocupado con órdenes casi completas."),
        ("19:58:00", "Bebidas/Postres", "A pedido",         33, "Faltaba una bebida para completar la orden."),
        ("20:00:50", "Staging/Bolseo",  "A pedido",         84, "Dos bolsas listas y una bandeja ocuparon staging mientras seguían saliendo pedidos a mesa."),
        ("20:03:40", "Ensamble",        "A pedido",         42, "El pedido no se cerró de inmediato porque faltaba carne 4:1 para una hamburguesa tipo Cuarto de Libra."),
        ("20:06:50", "Bebidas/Postres", "A pedido",         37, "La orden quedó pendiente por helado/postre; el resto ya estaba listo."),
        ("20:10:40", "Staging/Bolseo",  "A pedido",         68, "Pedido completo retenido en staging por saturación momentánea en la salida."),
        ("20:16:00", "Bebidas/Postres", "Listo/disponible", 18, ""),
        ("20:21:00", "Ensamble",        "A pedido",         39, "Faltaban papas para liberar la orden completa."),
    ]

    for i, (hora_txt, estacion, estado, duracion, nota) in enumerate(observaciones_estaciones, start=1):
        hh, mm, ss = map(int, hora_txt.split(":"))
        inicio = BOGOTA_TZ.localize(datetime(2026, 4, 3, hh, mm, ss))

        stations.append({
            "ID": f"E-{i:03d}",
            "Estación": estacion,
            "Estado": estado,
            "Fase": "Completado",
            "Inicio_ts": inicio.timestamp(),
            "Hora Inicio": inicio.strftime("%H:%M:%S"),
            "Fin": (inicio + timedelta(seconds=duracion)).strftime("%H:%M:%S"),
            "Duración(s)": round(duracion, 2),
            "Nota": nota
        })

    # ------------------------------------------------------------
    # 4) CAPACIDAD EFECTIVA
    # Piso aproximado:
    # Inicio = 14
    # Pico = 19
    # ------------------------------------------------------------
    capacity.append({
        "Hora": "19:32:00",
        "Momento": "Inicio de Franja",
        "Parrilla": 2,
        "Freidoras": 2,
        "Ensamble": 3,
        "Bebidas": 2,
        "Bolseo": 3,
        "Entrega": 2,
        "Equipos": 14
    })

    capacity.append({
        "Hora": "20:03:00",
        "Momento": "Pico de Congestión",
        "Parrilla": 3,
        "Freidoras": 3,
        "Ensamble": 4,
        "Bebidas": 3,
        "Bolseo": 4,
        "Entrega": 2,
        "Equipos": 19
    })

    # ------------------------------------------------------------
    # 5) EVENTOS
    # ------------------------------------------------------------
    events.append({
        "Hora": "19:39:00",
        "Evento": "Empiezan a acumularse órdenes casi completas en staging/bolseo porque faltan papas en varias salidas."
    })
    events.append({
        "Hora": "19:55:00",
        "Evento": "Congestión en staging/bolseo: coinciden AutoMac, delivery y servicio a mesa; baja la liberación de pedidos."
    })
    events.append({
        "Hora": "20:05:00",
        "Evento": "Se refuerza bolseo y freidoras para desocupar staging y recuperar la salida de pedidos."
    })
    events.append({
        "Hora": "20:20:00",
        "Evento": "La congestión en staging/bolseo empieza a bajar cuando disminuye la coincidencia entre mesa, delivery y AutoMac."
    })

    history = [{
        "info": session_info,
        "data": {
            "orders": orders,
            "queues": queues,
            "stations": stations,
            "capacity": capacity,
            "events": events
        }
    }]

    with open(HISTORY_FILE, "wb") as f:
        pickle.dump(history, f)

    print(f"✅ Registro final generado con {len(orders)} pedidos.")
    print("✅ Archivo listo: mcmediciones_history.pkl")

if __name__ == "__main__":
    generar_registro_final_calle_125()