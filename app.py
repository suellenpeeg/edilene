import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import gspread
from google.oauth2.service_account import Credentials
import uuid

# --- 1. CONFIGURAÇÃO ESTÉTICA ---
st.set_page_config(page_title="Edilene Epilação", page_icon="🌸", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #FFF0F5; }
    .stButton>button { background-color: #FFDAB9; color: #4A4A4A; border-radius: 15px; font-weight: 600; width: 100%; }
    h1, h2, h3 { color: #BC8F8F; font-family: 'Helvetica'; }
    [data-testid="stSidebar"] { background-color: #FDF5E6; }
</style>
""", unsafe_allow_html=True)

# --- 2. CONEXÃO ---
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
            data = ws.get_all_records()
            return pd.DataFrame(data)
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

def delete_row(sheet_name, column_index, value):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet(sheet_name)
            cells = ws.findall(value)
            for cell in reversed(cells):
                if cell.col == column_index:
                    ws.delete_rows(cell.row)
            return True
        except: return False

# --- 3. LÓGICA DE FILTRO ---
def check_availability(date_obj, duration_min):
    date_str = str(date_obj)
    df_ag = load_data("agendamentos")
    df_conf = load_data("configuracoes")
    
    # Horário padrão se não houver config
    h_abre, h_fecha = "08:00", "18:00"
    if not df_conf.empty:
        dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
        dia_nome = dias[date_obj.weekday()]
        conf = df_conf[df_conf['dia'] == dia_nome]
        if not conf.empty:
            if conf.iloc[0]['status'] == 'Fechado': return []
            h_abre, h_fecha = conf.iloc[0]['abertura'], conf.iloc[0]['fechamento']

    start_work = datetime.strptime(f"{date_str} {h_abre}", "%Y-%m-%d %H:%M")
    end_work = datetime.strptime(f"{date_str} {h_fecha}", "%Y-%m-%d %H:%M")
    
    slots = []
    curr = start_work
    now = datetime.now()

    while curr + timedelta(minutes=duration_min) <= end_work:
        if date_obj == date.today() and curr < now:
            curr += timedelta(minutes=30)
            continue
        
        is_free = True
        if not df_ag.empty:
            busy = df_ag[(df_ag['data'] == date_str) & (df_ag['status'].isin(['Agendado', 'Bloqueado']))]
            for _, row in busy.iterrows():
                try:
                    b_start = datetime.strptime(f"{date_str} {row['hora_inicio']}", "%Y-%m-%d %H:%M:%S")
                    b_end = datetime.strptime(f"{date_str} {row['hora_fim']}", "%Y-%m-%d %H:%M:%S")
                    if curr < b_end and (curr + timedelta(minutes=duration_min)) > b_start:
                        is_free = False
                        break
                except: continue
        
        if is_free: slots.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=30)
    return slots

# --- 4. INTERFACES ---

def admin_dashboard():
    st.sidebar.title("Painel Edilene")
    aba = st.sidebar.radio("Navegação", ["📅 Agenda e Liberação", "🚫 Criar Bloqueio", "⚙️ Serviços", "💰 Financeiro"])
    
    if aba == "📅 Agenda e Liberação":
        st.header("Gerenciar Horários")
        sel_d = st.date_input("Ver data:", date.today())
        df = load_data("agendamentos")
        if not df.empty:
            # Mostra tudo (Agendados e Bloqueados) para poder excluir
            dia = df[df['data'] == str(sel_d)].sort_values('hora_inicio')
            if dia.empty: 
                st.info("Nada consta para este dia.")
            else:
                for _, row in dia.iterrows():
                    col1, col2, col3 = st.columns([1, 3, 1])
                    col1.write(f"**{row['hora_inicio'][:5]}**")
                    col2.write(f"{row['cliente_nome']} - {row['servico']} ({row['status']})")
                    if col3.button("Liberar/Excluir", key=row['id']):
                        if delete_row("agendamentos", 1, row['id']):
                            st.success("Horário Liberado!")
                            st.rerun()

    elif aba == "🚫 Criar Bloqueio":
        st.header("Bloquear Horário")
        with st.form("f_bloq"):
            d_b = st.date_input("Data", min_value=date.today())
            h1, h2 = st.columns(2)
            hi = h1.time_input("Início")
            hf = h2.time_input("Fim")
            if st.form_submit_button("Confirmar Bloqueio"):
                save_row("agendamentos", [str(uuid.uuid4()), "BLOQUEIO", "00", "Pausa", str(d_b), hi.strftime("%H:%M:%S"), hf.strftime("%H:%M:%S"), 0, "Bloqueado"])
                st.success("Bloqueado com sucesso!")

    elif aba == "⚙️ Serviços":
        st.header("Meus Serviços")
        df_s = load_data("servicos")
        st.write("Serviços atuais na planilha:")
        st.dataframe(df_s, use_container_width=True)
        with st.form("new_s"):
            n = st.text_input("Nome do Serviço")
            d = st.number_input("Duração (minutos)", 15, 180, 30)
            v = st.number_input("Preço", 0.0)
            if st.form_submit_button("Adicionar Serviço"):
                save_row("servicos", [n, d, v])
                st.rerun()

    elif aba == "💰 Financeiro":
        st.header("Financeiro")
        df = load_data("agendamentos")
        if not df.empty:
            vendas = df[df['status'] == 'Agendado'].copy()
            vendas['valor'] = pd.to_numeric(vendas['valor'], errors='coerce').fillna(0)
            st.metric("Total Previsto", f"R$ {vendas['valor'].sum():,.2f}")
            st.dataframe(vendas[['data', 'cliente_nome', 'servico', 'valor']], use_container_width=True)

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

def client_dashboard():
    st.header(f"Olá, {st.session_state['user']['name']}! ✨")
    df_s = load_data("servicos")
    if not df_s.empty:
        serv = st.selectbox("O que vamos fazer?", df_s['nome'].tolist())
        row_s = df_s[df_s['nome'] == serv].iloc[0]
        data_sel = st.date_input("Escolha o dia", min_value=date.today())
        slots = check_availability(data_sel, int(row_s['duracao_min']))
        if slots:
            hora = st.selectbox("Horários livres", slots)
            if st.button("Agendar"):
                hf = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=int(row_s['duracao_min']))).strftime("%H:%M:%S")
                save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], serv, str(data_sel), hora+":00", hf, row_s['valor'], "Agendado"])
                st.success("Agendado! Te esperamos.")
        else: st.error("Sem horários para este dia.")
    else: st.error("Erro: Aba de serviços vazia na planilha. Verifique os nomes das colunas.")

# --- 5. LOGIN ---
def login_page():
    st.markdown("<h1 style='text-align: center;'>🌸 Edilene Epilação</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        t1, t2 = st.tabs(["Cliente", "Gestora"])
        with t1:
            p = st.text_input("Telefone")
            if p:
                cp = ''.join(filter(str.isdigit, p))
                df = load_data("clientes")
                found = df[df['telefone'].astype(str) == cp] if not df.empty else pd.DataFrame()
                if not found.empty:
                    if st.button("Entrar"):
                        st.session_state['user'] = {'role':'client', 'name': found.iloc[0]['nome'], 'phone': cp}
                        st.rerun()
                else:
                    n = st.text_input("Nome para cadastro")
                    if st.button("Cadastrar"):
                        save_row("clientes", [n, cp])
                        st.session_state['user'] = {'role':'client', 'name': n, 'phone': cp}
                        st.rerun()
        with t2:
            u = st.text_input("Usuário")
            ps = st.text_input("Senha", type="password")
            if st.button("Acesso Gestão"):
                if u == "Edilene" and ps == "senha123":
                    st.session_state['user'] = {'role':'admin', 'name':'Edilene'}
                    st.rerun()

if 'user' not in st.session_state: st.session_state['user'] = None
if st.session_state['user'] is None: login_page()
elif st.session_state['user']['role'] == 'admin': admin_dashboard()
else: client_dashboard()
