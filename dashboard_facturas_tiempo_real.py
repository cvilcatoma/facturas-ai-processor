import os
import json
import pandas as pd
import mysql.connector
import streamlit as st
from dotenv import load_dotenv

load_dotenv()

MYSQL_HOST = os.getenv("MYSQL_HOST", "localhost").strip()
MYSQL_USER = os.getenv("MYSQL_USER", "root").strip()
MYSQL_PASSWORD = os.getenv("MYSQL_PASSWORD", "").strip()
MYSQL_DATABASE = os.getenv("MYSQL_DATABASE", "demo_facturas").strip()

st.set_page_config(page_title="Dashboard de Facturas IA", layout="wide")

st.title("Dashboard de Facturas IA")
st.caption("Monitoreo en tiempo real de facturas procesadas, observadas, duplicados, errores y auditoría JSON.")

if st.button("Actualizar ahora"):
    st.cache_data.clear()
    st.rerun()

auto_refresh = st.sidebar.checkbox("Auto-actualizar cada 30 segundos", value=True)
if auto_refresh:
    st.markdown(
        """
        <script>
        setTimeout(function() {
            window.location.reload();
        }, 30000);
        </script>
        """,
        unsafe_allow_html=True,
    )


@st.cache_data(ttl=15)
def cargar_facturas():
    conn = mysql.connector.connect(
        host=MYSQL_HOST,
        user=MYSQL_USER,
        password=MYSQL_PASSWORD,
        database=MYSQL_DATABASE,
    )

    query = """
    SELECT
        id,
        archivo_origen,
        hash_archivo,
        numero_factura,
        fecha_emision,
        fecha_vencimiento,
        proveedor,
        ruc_proveedor,
        cliente,
        subtotal,
        igv,
        total,
        forma_pago,
        json_ia,
        estado,
        observacion,
        fecha_registro
    FROM facturas
    ORDER BY id DESC
    """

    df = pd.read_sql(query, conn)
    conn.close()

    for col in ["subtotal", "igv", "total"]:
        if col in df.columns:
            df[col + "_num"] = pd.to_numeric(df[col], errors="coerce")

    return df


def mostrar_metricas(df):
    col1, col2, col3, col4, col5 = st.columns(5)

    total_facturas = len(df)
    total_procesadas = len(df[df["estado"] == "PROCESADA"]) if "estado" in df.columns else 0
    total_observadas = len(df[df["estado"].astype(str).str.contains("OBSERVADA", na=False)]) if "estado" in df.columns else 0
    total_duplicados = len(df[df["estado"].astype(str).str.contains("DUPLICADO", na=False)]) if "estado" in df.columns else 0
    total_errores = len(df[df["estado"].astype(str).str.contains("ERROR", na=False)]) if "estado" in df.columns else 0

    col1.metric("Total registros", f"{total_facturas}")
    col2.metric("Procesadas", f"{total_procesadas}")
    col3.metric("Observadas", f"{total_observadas}")
    col4.metric("Duplicados", f"{total_duplicados}")
    col5.metric("Errores", f"{total_errores}")


def filtros_sidebar(df):
    st.sidebar.header("Filtros")

    estados = ["Todos"] + sorted([x for x in df["estado"].dropna().astype(str).unique().tolist()])
    estado_sel = st.sidebar.selectbox("Estado", estados)

    proveedores = ["Todos"] + sorted([x for x in df["proveedor"].dropna().astype(str).unique().tolist()])
    proveedor_sel = st.sidebar.selectbox("Proveedor", proveedores)

    texto = st.sidebar.text_input("Buscar", placeholder="Factura, RUC, cliente, archivo...")

    df_filtrado = df.copy()

    if estado_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["estado"].astype(str) == estado_sel]

    if proveedor_sel != "Todos":
        df_filtrado = df_filtrado[df_filtrado["proveedor"].astype(str) == proveedor_sel]

    if texto:
        texto = texto.lower().strip()
        mascara = (
            df_filtrado["numero_factura"].astype(str).str.lower().str.contains(texto, na=False) |
            df_filtrado["ruc_proveedor"].astype(str).str.lower().str.contains(texto, na=False) |
            df_filtrado["cliente"].astype(str).str.lower().str.contains(texto, na=False) |
            df_filtrado["proveedor"].astype(str).str.lower().str.contains(texto, na=False) |
            df_filtrado["archivo_origen"].astype(str).str.lower().str.contains(texto, na=False)
        )
        df_filtrado = df_filtrado[mascara]

    return df_filtrado


def panel_tiempo_real(df):
    st.subheader("Monitoreo en tiempo real")

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.write("**Últimos procesados**")
        proc = df[df["estado"].astype(str) == "PROCESADA"].head(10)
        if proc.empty:
            st.info("No hay procesadas recientes.")
        else:
            st.dataframe(
                proc[["id", "archivo_origen", "numero_factura", "proveedor", "total", "fecha_registro"]],
                use_container_width=True,
                height=300
            )

    with col2:
        st.write("**Últimas observadas contables**")
        obs = df[df["estado"].astype(str).str.contains("OBSERVADA", na=False)].head(10)
        if obs.empty:
            st.info("No hay observadas recientes.")
        else:
            st.dataframe(
                obs[["id", "archivo_origen", "numero_factura", "ruc_proveedor", "observacion", "fecha_registro"]],
                use_container_width=True,
                height=300
            )

    with col3:
        st.write("**Últimos duplicados**")
        dup = df[df["estado"].astype(str).str.contains("DUPLICADO", na=False)].head(10)
        if dup.empty:
            st.info("No hay duplicados recientes.")
        else:
            st.dataframe(
                dup[["id", "archivo_origen", "numero_factura", "ruc_proveedor", "estado", "observacion", "fecha_registro"]],
                use_container_width=True,
                height=300
            )

    with col4:
        st.write("**Últimos errores**")
        err = df[df["estado"].astype(str).str.contains("ERROR", na=False)].head(10)
        if err.empty:
            st.info("No hay errores registrados.")
        else:
            st.dataframe(
                err[["id", "archivo_origen", "estado", "observacion", "fecha_registro"]],
                use_container_width=True,
                height=300
            )


def tabla_principal(df):
    columnas = [
        "id",
        "archivo_origen",
        "numero_factura",
        "fecha_emision",
        "proveedor",
        "ruc_proveedor",
        "cliente",
        "subtotal",
        "igv",
        "total",
        "forma_pago",
        "estado",
        "observacion",
        "fecha_registro",
    ]
    columnas = [c for c in columnas if c in df.columns]

    st.subheader("Facturas")
    st.dataframe(df[columnas], use_container_width=True, height=420)


def detalle_factura(df):
    st.subheader("Detalle y auditoría")

    if df.empty:
        st.info("No hay registros para mostrar.")
        return

    opciones = df["id"].astype(str).tolist()
    id_sel = st.selectbox("Selecciona un ID de factura", opciones)
    fila = df[df["id"].astype(str) == id_sel].iloc[0]

    col1, col2 = st.columns(2)

    with col1:
        st.write("**Datos principales**")
        campos = [
            "id", "archivo_origen", "numero_factura", "fecha_emision",
            "fecha_vencimiento", "proveedor", "ruc_proveedor", "cliente",
            "subtotal", "igv", "total", "forma_pago", "estado", "observacion",
            "fecha_registro", "hash_archivo"
        ]
        for campo in campos:
            if campo in fila.index:
                st.write(f"**{campo}:** {fila[campo]}")

    with col2:
        st.write("**JSON IA**")
        json_raw = fila.get("json_ia", "")
        if json_raw:
            try:
                st.json(json.loads(json_raw))
            except Exception:
                st.text_area("json_ia", str(json_raw), height=320)
        else:
            st.info("Este registro no tiene json_ia guardado.")


def graficos(df):
    st.subheader("Resumen visual")

    col1, col2 = st.columns(2)

    with col1:
        if "estado" in df.columns and not df.empty:
            resumen_estado = df["estado"].fillna("SIN_ESTADO").value_counts().reset_index()
            resumen_estado.columns = ["estado", "cantidad"]
            st.write("**Facturas por estado**")
            st.bar_chart(resumen_estado.set_index("estado"))

    with col2:
        if "proveedor" in df.columns and "total_num" in df.columns and not df.empty:
            resumen_proveedor = (
                df.groupby("proveedor", dropna=False)["total_num"]
                .sum()
                .sort_values(ascending=False)
                .head(10)
            )
            st.write("**Top 10 proveedores por monto**")
            st.bar_chart(resumen_proveedor)


def exportacion(df):
    st.subheader("Exportación")
    csv_data = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label="Descargar CSV",
        data=csv_data,
        file_name="facturas_dashboard.csv",
        mime="text/csv"
    )


def main():
    try:
        df = cargar_facturas()
    except Exception as e:
        st.error(f"No se pudo conectar o leer MySQL: {e}")
        st.stop()

    mostrar_metricas(df)
    panel_tiempo_real(df)
    df_filtrado = filtros_sidebar(df)
    tabla_principal(df_filtrado)
    graficos(df_filtrado)
    detalle_factura(df_filtrado)
    exportacion(df_filtrado)


if __name__ == "__main__":
    main()
