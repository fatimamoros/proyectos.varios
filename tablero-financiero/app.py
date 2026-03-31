import streamlit as st
import requests
import pandas as pd
import json
import os
from datetime import datetime

st.set_page_config(page_title="Tablero Financiero", page_icon="📊", layout="wide")

# ── Credenciales IOL ──────────────────────────────────────────────────────────
try:
    from config import IOL_USUARIO, IOL_PASSWORD
except ImportError:
    st.error("No se encontró config.py con tus credenciales de IOL.")
    st.stop()

# ── Archivos locales ──────────────────────────────────────────────────────────
FAVORITOS_FILE  = "favoritos.json"
PORTAFOLIO_FILE = "portafolio.json"

def cargar_json(path, default):
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return default

def guardar_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

# ── Data912 ───────────────────────────────────────────────────────────────────
BASE = "https://data912.com/live"

@st.cache_data(ttl=30)
def get_data912(endpoint):
    try:
        r = requests.get(f"{BASE}/{endpoint}", timeout=10)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return []

def get_acciones(): return get_data912("arg_stocks")
def get_cedears():  return get_data912("arg_cedears")
def get_bonos():    return get_data912("arg_bonds")
def get_letras():   return get_data912("arg_notes")

@st.cache_data(ttl=30)
def get_tipos_cambio():
    mep_val, ccl_val = None, None
    try:
        mep_data = get_data912("mep")
        if mep_data:
            marks = sorted([d["mark"] for d in mep_data if d.get("mark") and d["mark"] > 100])
            if marks:
                mep_val = marks[len(marks)//2]
    except:
        pass
    try:
        ccl_data = get_data912("ccl")
        if ccl_data:
            marks = sorted([d["CCL_mark"] for d in ccl_data if d.get("CCL_mark") and d["CCL_mark"] > 100])
            if marks:
                ccl_val = marks[len(marks)//2]
    except:
        pass
    return mep_val, ccl_val

# ── IOL ───────────────────────────────────────────────────────────────────────
@st.cache_data(ttl=3300)
def get_token():
    try:
        r = requests.post(
            "https://api.invertironline.com/token",
            data={"username": IOL_USUARIO, "password": IOL_PASSWORD, "grant_type": "password"},
            timeout=10
        )
        if r.status_code == 200:
            return r.json()["access_token"]
    except:
        pass
    return None

def get_headers():
    token = get_token()
    if not token:
        st.error("No se pudo autenticar con IOL.")
        st.stop()
    return {"Authorization": f"Bearer {token}"}

@st.cache_data(ttl=30)
def get_cotizacion_iol(simbolo, mercado="bCBA"):
    url = f"https://api.invertironline.com/api/v2/{mercado}/Titulos/{simbolo}/Cotizacion"
    try:
        r = requests.get(url, headers=get_headers(), timeout=8)
        if r.status_code == 200:
            return r.json()
    except:
        pass
    return None

# ── Clasificación ─────────────────────────────────────────────────────────────
def tipo_bono(symbol):
    """Devuelve (base, sufijo) — base es el ticker sin C/D, sufijo es '', 'C' o 'D'."""
    s = symbol.upper()
    if s.endswith("C"):
        return s[:-1], "C"
    if s.endswith("D"):
        return s[:-1], "D"
    return s, ""

def serie_bono(symbol):
    s = symbol.upper().rstrip("CD")
    if s.startswith("GD"):
        return "Ley Extranjera"
    return "Ley Local"

def serie_letra(symbol):
    s = symbol.upper()
    if s.startswith("D"):
        return "Dólar Linked"
    if s.startswith("LBA") or s.startswith("LBE") or s.startswith("LBC") or s.startswith("S"):
        return "LECAP / Bontes"
    if s.startswith("BNA") or s.startswith("BU") or s.startswith("T"):
        return "CER / Ajustables"
    return "Otras"

# ── Formateo ──────────────────────────────────────────────────────────────────
def fmt_precio(v):
    try:
        f = float(v)
        return f"${f:,.0f}" if f >= 10 else f"${f:,.4f}"
    except:
        return "-"

def fmt_var(v):
    try:
        return f"{float(v):+.2f}%"
    except:
        return "-"

def color_var(v):
    try:
        val = float(v)
        return "green" if val > 0 else "red" if val < 0 else "gray"
    except:
        return "gray"

def fmt_moneda(v, moneda, mep, ccl):
    try:
        v = float(v)
        if moneda == "ARS":
            return f"${v:,.0f}"
        elif moneda == "USD MEP":
            return f"USD {v/mep:,.0f}" if mep else "-"
        elif moneda == "USD CCL":
            return f"USD {v/ccl:,.0f}" if ccl else "-"
    except:
        return "-"

def metrica(col, label, valor, delta=None):
    delta_color = "green" if delta and delta >= 0 else "red"
    delta_str = f"<div style='font-size:12px;color:{delta_color}'>{delta:+.2f}%</div>" if delta is not None else ""
    col.markdown(f"""
    <div style='padding:12px;border-radius:8px;border:1px solid #e0e0e0;margin-bottom:8px'>
        <div style='font-size:12px;color:gray;margin-bottom:4px'>{label}</div>
        <div style='font-size:17px;font-weight:600'>{valor}</div>
        {delta_str}
    </div>
    """, unsafe_allow_html=True)

# ── Estado de sesión ──────────────────────────────────────────────────────────
if "favoritos" not in st.session_state:
    st.session_state.favoritos = cargar_json(FAVORITOS_FILE, [])
if "portafolio" not in st.session_state:
    st.session_state.portafolio = cargar_json(PORTAFOLIO_FILE, [])

def toggle_favorito(simbolo, fuente):
    favs = st.session_state.favoritos
    if any(f["simbolo"] == simbolo for f in favs):
        st.session_state.favoritos = [f for f in favs if f["simbolo"] != simbolo]
    else:
        st.session_state.favoritos.append({"simbolo": simbolo, "fuente": fuente})
    guardar_json(FAVORITOS_FILE, st.session_state.favoritos)

def es_favorito(simbolo):
    return any(f["simbolo"] == simbolo for f in st.session_state.favoritos)

# ── Tabla de mercado ──────────────────────────────────────────────────────────
def mostrar_tabla_mercado(datos, fuente, busqueda=""):
    if not datos:
        st.info("No hay datos para esta categoría.")
        return

    if busqueda:
        datos = [d for d in datos if busqueda.upper() in d.get("symbol", "").upper()]

    datos = sorted(datos, key=lambda x: x.get("pct_change", 0) or 0, reverse=True)

    anchos  = [0.4, 1.2, 1.4, 1.4, 1.4, 1.4, 1.6, 1.2]
    headers = ["⭐", "Símbolo", "Último", "Variación", "Bid", "Ask", "Volumen", "Operaciones"]
    cols = st.columns(anchos)
    for col, h in zip(cols, headers):
        col.markdown(f"**{h}**")
    st.divider()

    for d in datos:
        s = d.get("symbol", "")
        cols = st.columns(anchos)
        estrella = "⭐" if es_favorito(s) else "☆"
        if cols[0].button(estrella, key=f"fav_{fuente}_{s}"):
            toggle_favorito(s, fuente)
            st.rerun()
        cols[1].write(s)
        cols[2].write(fmt_precio(d.get("c")))
        var = d.get("pct_change")
        cols[3].markdown(f"<span style='color:{color_var(var)};font-weight:500'>{fmt_var(var)}</span>", unsafe_allow_html=True)
        cols[4].write(fmt_precio(d.get("px_bid")))
        cols[5].write(fmt_precio(d.get("px_ask")))
        try:
            cols[6].write(f"{int(float(d.get('v', 0))):,}")
        except:
            cols[6].write("-")
        try:
            cols[7].write(f"{int(float(d.get('q_op', 0))):,}")
        except:
            cols[7].write("-")

# ── Tipos de cambio ───────────────────────────────────────────────────────────
mep_val, ccl_val = get_tipos_cambio()

# ── Sidebar ───────────────────────────────────────────────────────────────────
st.sidebar.title("📊 Tablero Financiero")
st.sidebar.caption(f"Actualizado: {datetime.now().strftime('%H:%M:%S')}")
st.sidebar.metric("💵 Dólar MEP", f"${mep_val:,.0f}" if mep_val else "Sin datos")
st.sidebar.metric("💵 Dólar CCL", f"${ccl_val:,.0f}" if ccl_val else "Sin datos")
st.sidebar.markdown("---")

seccion = st.sidebar.radio(
    "Ir a",
    ["⭐ Favoritos", "📈 Mercado", "💼 Portafolio"],
    label_visibility="collapsed"
)

if st.sidebar.button("🔄 Actualizar datos"):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("Mercado: Data912 · Portafolio: IOL")

# ══════════════════════════════════════════════════════════════════════════════
# FAVORITOS
# ══════════════════════════════════════════════════════════════════════════════
if seccion == "⭐ Favoritos":
    st.title("⭐ Favoritos")

    favs = st.session_state.favoritos
    if not favs:
        st.info("Todavía no tenés favoritos. Agregá desde 📈 Mercado tocando la ☆.")
    else:
        indice = {}
        for lista in [get_acciones(), get_cedears(), get_bonos(), get_letras()]:
            for item in lista:
                indice[item["symbol"]] = item

        anchos  = [0.4, 1.2, 1.4, 1.4, 1.4, 1.4, 1.6, 1.2]
        headers = ["⭐", "Símbolo", "Último", "Variación", "Bid", "Ask", "Volumen", "Operaciones"]
        cols = st.columns(anchos)
        for col, h in zip(cols, headers):
            col.markdown(f"**{h}**")
        st.divider()

        for fav in favs:
            s = fav["simbolo"]
            d = indice.get(s)
            cols = st.columns(anchos)
            if cols[0].button("⭐", key=f"unfav_{s}"):
                toggle_favorito(s, fav.get("fuente", ""))
                st.rerun()
            cols[1].write(s)
            if d:
                cols[2].write(fmt_precio(d.get("c")))
                var = d.get("pct_change")
                cols[3].markdown(f"<span style='color:{color_var(var)};font-weight:500'>{fmt_var(var)}</span>", unsafe_allow_html=True)
                cols[4].write(fmt_precio(d.get("px_bid")))
                cols[5].write(fmt_precio(d.get("px_ask")))
                try:
                    cols[6].write(f"{int(float(d.get('v', 0))):,}")
                except:
                    cols[6].write("-")
                try:
                    cols[7].write(f"{int(float(d.get('q_op', 0))):,}")
                except:
                    cols[7].write("-")
            else:
                for c in cols[2:]:
                    c.write("-")

# ══════════════════════════════════════════════════════════════════════════════
# MERCADO
# ══════════════════════════════════════════════════════════════════════════════
elif seccion == "📈 Mercado":
    st.title("📈 Mercado en tiempo real")

    tabs = st.tabs(["🏢 Acciones", "🌎 CEDEARs", "📜 Bonos", "💵 Letras"])

    # ── Acciones ──────────────────────────────────────────────────────────────
    with tabs[0]:
        busqueda = st.text_input("🔍 Buscar", placeholder="Ej: GGAL", key="bus_acc")
        with st.spinner("Cargando..."):
            datos = get_acciones()
        st.caption(f"{len(datos)} acciones · tiempo real")
        mostrar_tabla_mercado(datos, "acc", busqueda)

    # ── CEDEARs ───────────────────────────────────────────────────────────────
    with tabs[1]:
        busqueda = st.text_input("🔍 Buscar", placeholder="Ej: AAPL", key="bus_ced")
        with st.spinner("Cargando..."):
            datos = get_cedears()
        st.caption(f"{len(datos)} CEDEARs · tiempo real")
        mostrar_tabla_mercado(datos, "ced", busqueda)

    # ── Bonos ─────────────────────────────────────────────────────────────────
    with tabs[2]:
        with st.spinner("Cargando bonos..."):
            todos_bonos = get_bonos()

        # Selector de cotización
        cotiz_bono = st.radio(
            "Cotización",
            ["ARS (pesos)", "C (cable)", "D (dólar)"],
            horizontal=True,
            key="cotiz_bono"
        )
        sufijo_map = {"ARS (pesos)": "", "C (cable)": "C", "D (dólar)": "D"}
        sufijo = sufijo_map[cotiz_bono]

        # Filtrar por sufijo elegido
        bonos_filtrados = [d for d in todos_bonos if tipo_bono(d["symbol"])[1] == sufijo]

        # Separar por serie
        ley_local     = [d for d in bonos_filtrados if serie_bono(d["symbol"]) == "Ley Local"]
        ley_extranjera = [d for d in bonos_filtrados if serie_bono(d["symbol"]) == "Ley Extranjera"]

        busqueda_bon = st.text_input("🔍 Buscar bono", placeholder="Ej: AL30", key="bus_bon")

        st.subheader(f"🏛 Ley Local ({len(ley_local)})")
        mostrar_tabla_mercado(ley_local, "bon_local", busqueda_bon)

        st.markdown("<br>", unsafe_allow_html=True)
        st.subheader(f"🌐 Ley Extranjera ({len(ley_extranjera)})")
        mostrar_tabla_mercado(ley_extranjera, "bon_ext", busqueda_bon)

    # ── Letras ────────────────────────────────────────────────────────────────
    with tabs[3]:
        with st.spinner("Cargando letras..."):
            todos_letras = get_letras()

        # Selector de cotización
        cotiz_letra = st.radio(
            "Cotización",
            ["ARS (pesos)", "C (cable)", "D (dólar)"],
            horizontal=True,
            key="cotiz_letra"
        )
        sufijo_letra = sufijo_map[cotiz_letra]
        letras_filtradas = [d for d in todos_letras if tipo_bono(d["symbol"])[1] == sufijo_letra]

        # Separar por tipo
        lecap   = [d for d in letras_filtradas if serie_letra(d["symbol"]) == "LECAP / Bontes"]
        cer     = [d for d in letras_filtradas if serie_letra(d["symbol"]) == "CER / Ajustables"]
        dl      = [d for d in letras_filtradas if serie_letra(d["symbol"]) == "Dólar Linked"]
        otras   = [d for d in letras_filtradas if serie_letra(d["symbol"]) == "Otras"]

        busqueda_let = st.text_input("🔍 Buscar letra", placeholder="Ej: LECAP", key="bus_let")

        if lecap:
            st.subheader(f"📄 LECAP / Bontes ({len(lecap)})")
            mostrar_tabla_mercado(lecap, "let_lecap", busqueda_let)
            st.markdown("<br>", unsafe_allow_html=True)

        if cer:
            st.subheader(f"📈 CER / Ajustables ({len(cer)})")
            mostrar_tabla_mercado(cer, "let_cer", busqueda_let)
            st.markdown("<br>", unsafe_allow_html=True)

        if dl:
            st.subheader(f"💵 Dólar Linked ({len(dl)})")
            mostrar_tabla_mercado(dl, "let_dl", busqueda_let)
            st.markdown("<br>", unsafe_allow_html=True)

        if otras:
            st.subheader(f"📋 Otras ({len(otras)})")
            mostrar_tabla_mercado(otras, "let_otras", busqueda_let)

# ══════════════════════════════════════════════════════════════════════════════
# PORTAFOLIO
# ══════════════════════════════════════════════════════════════════════════════
elif seccion == "💼 Portafolio":
    st.title("💼 Mi portafolio")

    # Selector de moneda
    moneda = st.radio(
        "Ver en",
        ["ARS", "USD MEP", "USD CCL"],
        horizontal=True,
        label_visibility="collapsed"
    )

    with st.expander("➕ Agregar posición", expanded=len(st.session_state.portafolio) == 0):
        c1, c2, c3, c4, c5 = st.columns(5)
        nuevo_simbolo  = c1.text_input("Símbolo", placeholder="Ej: GGAL").upper().strip()
        nuevo_mercado  = c2.selectbox("Mercado", ["bCBA", "rFX"])
        nuevo_broker   = c3.selectbox("Broker", ["Balanz", "IEB+", "Eco Valores", "Otro"])
        nueva_cantidad = c4.number_input("Cantidad", min_value=0.0, step=1.0)
        nuevo_costo    = c5.number_input("Costo promedio ($)", min_value=0.0, step=0.01)

        if st.button("Agregar posición"):
            if nuevo_simbolo and nueva_cantidad > 0 and nuevo_costo > 0:
                st.session_state.portafolio.append({
                    "simbolo": nuevo_simbolo,
                    "mercado": nuevo_mercado,
                    "broker": nuevo_broker,
                    "cantidad": nueva_cantidad,
                    "costo_promedio": nuevo_costo,
                })
                guardar_json(PORTAFOLIO_FILE, st.session_state.portafolio)
                st.success(f"✅ {nuevo_simbolo} agregado.")
                st.rerun()
            else:
                st.warning("Completá todos los campos.")

    portafolio = st.session_state.portafolio
    if not portafolio:
        st.info("Agregá tus posiciones usando el formulario de arriba.")
    else:
        # Índice de precios
        todos_precios = {}
        for lista in [get_acciones(), get_cedears(), get_bonos(), get_letras()]:
            for item in lista:
                todos_precios[item["symbol"]] = item.get("c")

        total_ars       = 0.0
        total_invertido = 0.0
        filas = []
        por_broker = {}

        for i, pos in enumerate(portafolio):
            s = pos["simbolo"]
            precio_ars = todos_precios.get(s)
            if precio_ars is None:
                cotiz = get_cotizacion_iol(s, pos["mercado"])
                if cotiz:
                    precio_ars = cotiz.get("ultimoPrecio")

            try:
                pa     = float(precio_ars) if precio_ars else None
                cant   = float(pos["cantidad"])
                costo  = float(pos["costo_promedio"])
                valuar = pa * cant if pa else None
                invert = costo * cant
                result = (valuar - invert) if valuar else None
                pct    = (result / invert * 100) if (result is not None and invert > 0) else None
                if valuar:
                    total_ars += valuar
                    broker = pos["broker"]
                    por_broker[broker] = por_broker.get(broker, 0.0) + valuar
                total_invertido += invert
            except:
                pa = valuar = result = pct = None
                invert = 0.0

            filas.append({
                "idx": i,
                "Símbolo": s,
                "Broker": pos["broker"],
                "Cantidad": int(pos["cantidad"]),
                "_costo_ars": pos["costo_promedio"],
                "_precio_ars": pa,
                "_valuar_ars": valuar,
                "_result_ars": result,
                "Resultado %": f"{pct:+.2f}%" if pct is not None else "-",
                "_pct": pct or 0,
            })

        resultado_total = total_ars - total_invertido
        pct_total = (resultado_total / total_invertido * 100) if total_invertido > 0 else 0

        # ── Métricas resumen ──────────────────────────────────────────────────
        m1, m2, m3, m4, m5 = st.columns(5)
        metrica(m1, f"Valor total ({moneda})", fmt_moneda(total_ars, moneda, mep_val, ccl_val), pct_total)
        metrica(m2, f"Invertido ({moneda})", fmt_moneda(total_invertido, moneda, mep_val, ccl_val))
        metrica(m3, f"Resultado ({moneda})", fmt_moneda(resultado_total, moneda, mep_val, ccl_val))
        metrica(m4, "Dólar MEP", f"${mep_val:,.0f}" if mep_val else "Sin datos")
        metrica(m5, "Dólar CCL", f"${ccl_val:,.0f}" if ccl_val else "Sin datos")

        st.markdown("<br>", unsafe_allow_html=True)

        # ── Distribución por ALYC ─────────────────────────────────────────────
        st.subheader("Distribución por ALYC")
        if por_broker:
            cols_alyc = st.columns(len(por_broker))
            for col, (broker, valor_ars) in zip(cols_alyc, por_broker.items()):
                pct_broker = (valor_ars / total_ars * 100) if total_ars > 0 else 0
                valor_mostrar = fmt_moneda(valor_ars, moneda, mep_val, ccl_val)
                metrica(col, f"🏦 {broker}", valor_mostrar, None)
                col.markdown(f"<div style='text-align:center;font-size:13px;color:gray;margin-top:-8px'>{pct_broker:.1f}% del total</div>", unsafe_allow_html=True)

        st.divider()

        # ── Tabla de posiciones ───────────────────────────────────────────────
        anchos  = [1.5, 1.5, 0.8, 1.5, 1.5, 1.5, 1.5, 1.2, 0.5]
        headers = ["Símbolo", "Broker", "Cant.", f"Costo ({moneda})", f"Precio ({moneda})", f"Valuación ({moneda})", f"Resultado ({moneda})", "Result. %", "🗑"]
        cols = st.columns(anchos)
        for col, h in zip(cols, headers):
            col.markdown(f"**{h}**")
        st.divider()

        for row in filas:
            cols = st.columns(anchos)
            cols[0].write(row["Símbolo"])
            cols[1].write(row["Broker"])
            cols[2].write(row["Cantidad"])
            cols[3].write(fmt_moneda(row["_costo_ars"], moneda, mep_val, ccl_val))
            cols[4].write(fmt_moneda(row["_precio_ars"], moneda, mep_val, ccl_val) if row["_precio_ars"] else "-")
            cols[5].write(fmt_moneda(row["_valuar_ars"], moneda, mep_val, ccl_val) if row["_valuar_ars"] else "-")
            cols[6].write(fmt_moneda(row["_result_ars"], moneda, mep_val, ccl_val) if row["_result_ars"] else "-")
            color = color_var(row["_pct"])
            cols[7].markdown(f"<span style='color:{color};font-weight:500'>{row['Resultado %']}</span>", unsafe_allow_html=True)
            if cols[8].button("🗑", key=f"del_{row['idx']}"):
                st.session_state.portafolio.pop(row["idx"])
                guardar_json(PORTAFOLIO_FILE, st.session_state.portafolio)
                st.rerun()
