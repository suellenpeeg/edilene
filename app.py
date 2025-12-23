import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import gspread
from google.oauth2.service_account import Credentials
import uuid

# --- 1. CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Edilene Epilação", page_icon="🌸", layout="wide")

# --- 2. CONEXÃO COM GOOGLE SHEETS ---
def get_db_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        # ID DA SUA PLANILHA (Verificado na sua imagem)
        return client.open_by_key("19FiUFG7daZKCTMZ8vtD023BPCPfnhpMaQ6UfD0KIhb0")
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
            # Converte tudo para string para evitar erro de serialização JSON (int64)
            clean_row = [str(x) if not isinstance(x, (int, float)) else x for x in row_data]
            ws.append_row(clean_row)
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

# --- 3. LÓGICA DE AGENDAMENTO ---
def check_availability(date_obj, duration_min):
    date_str = str(date_obj)
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    dia_nome = dias_semana[date_obj.weekday()]
    
    df_conf = load_data("configuracoes")
    if df_conf.empty:
        h_abre, h_fecha, status_dia = "08:00", "18:00", "Aberto"
    else:
        conf = df_conf[df_conf['dia'] == dia_nome]
        if conf.empty or conf.iloc[0]['status'] == 'Fechado': return []
        h_abre, h_fecha = conf.iloc[0]['abertura'], conf.iloc[0]['fechamento']

    start_work = datetime.strptime(f"{date_str} {h_abre}", "%Y-%m-%d %H:%M")
    end_work = datetime.strptime(f"{date_str} {h_fecha}", "%Y-%m-%d %H:%M")
    
    now = datetime.now()
    df_ag = load_data("agendamentos")
    slots = []
    curr = start_work
    
    while curr + timedelta(minutes=duration_min) <= end_work:
        slot_end = curr + timedelta(minutes=duration_min)
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
                    if curr < b_end and slot_end > b_start:
                        is_free = False
                        break
                except: continue
        
        if is_free: slots.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=30)
    return slots

# --- 4. INTERFACES ---

def login_page():
    st.title("🌸 Edilene Epilação")
    tab_c, tab_g = st.tabs(["🙋‍♀️ Cliente", "👩‍💼 Gestora"])
    
    with tab_c:
        phone = st.text_input("Telefone (DDD + Número)")
        if phone:
            clean_p = ''.join(filter(str.isdigit, phone))
            df_cli = load_data("clientes")
            found = df_cli[df_cli['telefone'].astype(str) == clean_p] if not df_cli.empty else pd.DataFrame()
            
            if not found.empty:
                if st.button("Entrar"):
                    st.session_state['user'] = {'role':'client', 'name': found.iloc[0]['nome'], 'phone': clean_p}
                    st.rerun()
            else:
                st.warning("Cadastro não encontrado.")
                with st.form("registro"):
                    nome = st.text_input("Nome Completo")
                    if st.form_submit_button("Criar Cadastro e Entrar"):
                        save_row("clientes", [nome, clean_p])
                        st.session_state['user'] = {'role':'client', 'name': nome, 'phone': clean_p}
                        st.rerun()

    with tab_g:
        user = st.text_input("Usuário")
        pwd = st.text_input("Senha", type="password")
        if st.button("Acessar Painel"):
            if user == "Edilene" and pwd == "senha123":
                st.session_state['user'] = {'role':'admin', 'name':'Edilene'}
                st.rerun()

def admin_dashboard():
    st.sidebar.title(f"Olá, {st.session_state['user']['name']}")
    aba = st.sidebar.radio("Navegação", ["Agenda", "Bloqueios", "Serviços", "💰 Financeiro"])
    
    if aba == "Agenda":
        st.header("📅 Agenda")
        hoje = st.date_input("Data:", date.today())
        df = load_data("agendamentos")
        if not df.empty:
            dia = df[(df['data'] == str(hoje)) & (df['status'] != 'Cancelado')]
            st.dataframe(dia, use_container_width=True)

    elif aba == "Bloqueios":
        st.header("🚫 Bloquear Horário")
        with st.form("bloq"):
            d = st.date_input("Data", min_value=date.today())
            h1 = st.time_input("Início")
            h2 = st.time_input("Fim")
            if st.form_submit_button("Bloquear"):
                save_row("agendamentos", [str(uuid.uuid4()), "BLOQUEIO", "00", "Bloqueio", str(d), h1.strftime("%H:%M:%S"), h2.strftime("%H:%M:%S"), 0, "Bloqueado"])
                st.success("Bloqueado!")

    elif aba == "💰 Financeiro":
        st.header("Financeiro")
        df = load_data("agendamentos")
        if not df.empty:
            df['valor'] = pd.to_numeric(df['valor'], errors='coerce').fillna(0)
            vendas = df[df['status'] == 'Agendado']
            st.metric("Total Previsto", f"R$ {vendas['valor'].sum():,.2f}")
            st.dataframe(vendas[['data', 'cliente_nome', 'servico', 'valor']])

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

def client_dashboard():
    st.header(f"Bem-vinda, {st.session_state['user']['name']}! ✨")
    df_s = load_data("servicos")
    if not df_s.empty:
        serv = st.selectbox("Escolha o serviço", df_s['nome'].tolist())
        row_s = df_s[df_s['nome'] == serv].iloc[0]
        data_sel = st.date_input("Data", min_value=date.today())
        slots = check_availability(data_sel, int(row_s['duracao_min']))
        
        if slots:
            hora = st.selectbox("Horário", slots)
            if st.button("Confirmar Agendamento"):
                hf = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=int(row_s['duracao_min']))).strftime("%H:%M:%S")
                save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], serv, str(data_sel), hora+":00", hf, row_s['valor'], "Agendado"])
                st.success("Agendado!")
        else:
            st.error("Sem horários para este dia.")

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- 5. EXECUÇÃO PRINCIPAL ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    login_page()
elif st.session_state['user']['role'] == 'admin':
    admin_dashboard()
else:
    client_dashboard()
