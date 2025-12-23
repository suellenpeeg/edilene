import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import gspread
from google.oauth2.service_account import Credentials
import uuid

# --- CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="Edilene Epilação", page_icon="🌸", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #FFF0F5; }
    .stButton>button { background-color: #FFDAB9; color: #4A4A4A; border-radius: 15px; font-weight: 600; width: 100%; }
    h1, h2, h3 { color: #BC8F8F; font-family: 'Helvetica'; }
    [data-testid="stSidebar"] { background-color: #FDF5E6; }
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO ---
def get_db_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client.open_by_key("19FiUFG7daZKCTMZ8vtDO23BPCPfnhpMaQ6UfD0KIhb0")
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return None

def load_data(sheet_name):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet(sheet_name)
            return pd.DataFrame(ws.get_all_records())
        except: return pd.DataFrame()
    return pd.DataFrame()

def save_row(sheet_name, row_data):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet(sheet_name)
            clean_row = [str(x) if not isinstance(x, (int, float)) else x for x in row_data]
            ws.append_row(clean_row)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

def update_config(dia, status, abre, fecha):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet("configuracoes")
            cell = ws.find(dia)
            ws.update_cell(cell.row, 2, status)
            ws.update_cell(cell.row, 3, str(abre))
            ws.update_cell(cell.row, 4, str(fecha))
            return True
        except: return False

# --- LÓGICA DE FILTRO ---
def check_availability(date_obj, duration_min):
    date_str = str(date_obj)
    df_ag = load_data("agendamentos")
    df_conf = load_data("configuracoes")
    
    dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    dia_nome = dias[date_obj.weekday()]
    
    conf = df_conf[df_conf['dia'] == dia_nome] if not df_conf.empty else pd.DataFrame()
    if conf.empty or conf.iloc[0]['status'] == 'Fechado': return []
    
    h_abre, h_fecha = conf.iloc[0]['abertura'], conf.iloc[0]['fechamento']
    try:
        start_work = datetime.strptime(f"{date_str} {h_abre}", "%Y-%m-%d %H:%M")
        end_work = datetime.strptime(f"{date_str} {h_fecha}", "%Y-%m-%d %H:%M")
    except: return []
    
    slots = []
    curr = start_work
    now = datetime.now()

    while curr + timedelta(minutes=duration_min) <= end_work:
        if date_obj == date.today() and curr < now:
            curr += timedelta(minutes=30); continue
        
        is_free = True
        if not df_ag.empty:
            busy = df_ag[(df_ag['data'] == date_str) & (df_ag['status'].isin(['Agendado', 'Bloqueado']))]
            for _, row in busy.iterrows():
                try:
                    b_start = datetime.strptime(f"{date_str} {row['hora_inicio']}", "%Y-%m-%d %H:%M:%S")
                    b_end = datetime.strptime(f"{date_str} {row['hora_fim']}", "%Y-%m-%d %H:%M:%S")
                    if curr < b_end and (curr + timedelta(minutes=duration_min)) > b_start:
                        is_free = False; break
                except: continue
        if is_free: slots.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=30)
    return slots

# --- INTERFACE GESTOR ---
def admin_dashboard():
    st.sidebar.title("Painel Administrativo")
    aba = st.sidebar.radio("Navegação", ["📅 Agenda", "⚙️ Gestão de Horários", "🛠️ Serviços", "💰 Financeiro"])
    
    if aba == "⚙️ Gestão de Horários":
        st.header("⚙️ Configurar Escala e Bloqueios")
        
        tab_escala, tab_bloqueio = st.tabs(["🕒 Escala Semanal", "🚫 Bloquear Horário Específico"])
        
        with tab_escala:
            st.subheader("Definir Dias e Horários de Funcionamento")
            df_conf = load_data("configuracoes")
            if not df_conf.empty:
                for _, row in df_conf.iterrows():
                    with st.expander(f"📍 {row['dia']}"):
                        new_status = st.selectbox("Status", ["Aberto", "Fechado"], index=0 if row['status']=="Aberto" else 1, key=f"s_{row['dia']}")
                        c1, c2 = st.columns(2)
                        new_abre = c1.text_input("Abertura (00:00)", value=row['abertura'], key=f"a_{row['dia']}")
                        new_fecha = c2.text_input("Fechamento (00:00)", value=row['fechamento'], key=f"f_{row['dia']}")
                        if st.button("Atualizar " + row['dia'], key=f"btn_{row['dia']}"):
                            if update_config(row['dia'], new_status, new_abre, new_fecha):
                                st.success("Escala de " + row['dia'] + " atualizada!"); st.rerun()
            else:
                st.error("Aba 'configuracoes' não encontrada ou vazia na planilha.")

        with tab_bloqueio:
            st.subheader("Bloquear um Horário no Dia")
            with st.form("f_bloq"):
                d_b = st.date_input("Data do Bloqueio", min_value=date.today())
                h_i = st.time_input("Início"); h_f = st.time_input("Fim")
                motivo = st.text_input("Motivo (ex: Almoço)")
                if st.form_submit_button("Confirmar Bloqueio"):
                    save_row("agendamentos", [str(uuid.uuid4()), f"BLOQUEIO: {motivo}", "00", "Pausa", str(d_b), h_i.strftime("%H:%M:%S"), h_f.strftime("%H:%M:%S"), 0, "Bloqueado"])
                    st.success("Bloqueado com sucesso!")

    elif aba == "📅 Agenda":
        st.header("Atendimentos")
        sel_d = st.date_input("Data:", date.today())
        df = load_data("agendamentos")
        if not df.empty:
            dia = df[df['data'] == str(sel_d)].sort_values('hora_inicio')
            st.dataframe(dia[['hora_inicio', 'cliente_nome', 'servico', 'status']], use_container_width=True)

    elif aba == "🛠️ Serviços":
        st.header("Serviços")
        df_servs = load_data("servicos")
        st.dataframe(df_servs, use_container_width=True)
        with st.form("novo_s"):
            n = st.text_input("Serviço")
            d = st.number_input("Duração (min)", 15, 120, 30)
            v = st.number_input("Preço", 0.0)
            if st.form_submit_button("Adicionar"):
                save_row("servicos", [n, d, v]); st.rerun()

    elif aba == "💰 Financeiro":
        st.header("Financeiro")
        df = load_data("agendamentos")
        if not df.empty:
            vendas = df[df['status'] == 'Agendado'].copy()
            vendas['valor'] = pd.to_numeric(vendas['valor'], errors='coerce').fillna(0)
            st.metric("Faturamento", f"R$ {vendas['valor'].sum():,.2f}")
            st.dataframe(vendas[['data', 'cliente_nome', 'servico', 'valor']], use_container_width=True)

    if st.sidebar.button("Sair/Logout"):
        st.session_state['user'] = None; st.rerun()

# --- INTERFACE CLIENTE ---
def client_dashboard():
    st.sidebar.title(f"🌸 {st.session_state['user']['name']}")
    if st.sidebar.button("Sair/Logout"):
        st.session_state['user'] = None; st.rerun()

    tab_marcar, tab_meus = st.tabs(["✨ Marcar Horário", "📅 Meus Agendamentos"])
    
    with tab_marcar:
        df_s = load_data("servicos")
        if not df_s.empty:
            serv = st.selectbox("O que deseja fazer?", df_s['nome'].tolist())
            row_s = df_s[df_s['nome'] == serv].iloc[0]
            data_sel = st.date_input("Data", min_value=date.today())
            slots = check_availability(data_sel, int(row_s['duracao_min']))
            if slots:
                hora = st.selectbox("Horários", slots)
                if st.button("Confirmar Agendamento"):
                    hf = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=int(row_s['duracao_min']))).strftime("%H:%M:%S")
                    save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], serv, str(data_sel), hora+":00", hf, row_s['valor'], "Agendado"])
                    st.success("Agendado!"); st.balloons()
            else: st.error("Agenda indisponível para este dia.")
        else: st.warning("Nenhum serviço cadastrado.")

    with tab_meus:
        df_ag = load_data("agendamentos")
        if not df_ag.empty:
            meus = df_ag[df_ag['cliente_tel'].astype(str) == st.session_state['user']['phone']]
            if meus.empty: st.info("Sem agendamentos.")
            else: st.dataframe(meus[['data', 'hora_inicio', 'servico', 'status']], use_container_width=True, hide_index=True)

# --- LOGIN ---
def login_page():
    st.markdown("<h1 style='text-align: center;'>🌸 Edilene Epilação</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        t1, t2 = st.tabs(["Sou Cliente", "Sou Gestora"])
        with t1:
            p = st.text_input("Seu Telefone")
            if p:
                cp = ''.join(filter(str.isdigit, p))
                df = load_data("clientes")
                found = df[df['telefone'].astype(str) == cp] if not df.empty else pd.DataFrame()
                if not found.empty:
                    if st.button("Entrar"):
                        st.session_state['user'] = {'role':'client', 'name': found.iloc[0]['nome'], 'phone': cp}; st.rerun()
                else:
                    n = st.text_input("Nome para cadastro")
                    if st.button("Cadastrar"):
                        save_row("clientes", [n, cp])
                        st.session_state['user'] = {'role':'client', 'name': n, 'phone': cp}; st.rerun()
        with t2:
            u = st.text_input("Usuário"); ps = st.text_input("Senha", type="password")
            if st.button("Entrar como Gestora"):
                if u == "Edilene" and ps == "senha123":
                    st.session_state['user'] = {'role':'admin', 'name':'Edilene'}; st.rerun()

if 'user' not in st.session_state: st.session_state['user'] = None
if st.session_state['user'] is None: login_page()
elif st.session_state['user']['role'] == 'admin': admin_dashboard()
else: client_dashboard()
