import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from streamlit_option_menu import option_menu
import gspread
from google.oauth2.service_account import Credentials
import uuid
import json

# --- CONFIGURAÇÃO DA PÁGINA ---
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
        # Use o nome exato ou o ID da sua planilha
        return client.open("db_edilene")
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

# FUNÇÃO CORRIGIDA PARA EVITAR O ERRO DE SERIALIZAÇÃO
def save_row(sheet_name, row_data):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet(sheet_name)
            # Converte todos os itens da lista para string ou tipos nativos do Python
            clean_row = []
            for item in row_data:
                if hasattr(item, "item"): # Converte tipos do Numpy/Pandas (int64, float64)
                    clean_row.append(item.item())
                else:
                    clean_row.append(str(item) if not isinstance(item, (int, float)) else item)
            
            ws.append_row(clean_row)
        except Exception as e: 
            st.error(f"Erro ao salvar: {e}")

# --- LÓGICA DE DISPONIBILIDADE ---
def check_availability(date_obj, duration_min):
    date_str = str(date_obj)
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    dia_nome = dias_semana[date_obj.weekday()]
    
    df_conf = load_data("configuracoes")
    if df_conf.empty:
        h_abre, h_fecha, status = "08:00", "18:00", "Aberto"
    else:
        conf = df_conf[df_conf['dia'] == dia_nome]
        if conf.empty or conf.iloc[0]['status'] == 'Fechado': return []
        h_abre, h_fecha = conf.iloc[0]['abertura'], conf.iloc[0]['fechamento']

    start_work = datetime.strptime(f"{date_str} {h_abre}", "%Y-%m-%d %H:%M")
    end_work = datetime.strptime(f"{date_str} {h_fecha}", "%Y-%m-%d %H:%M")
    
    df_ag = load_data("agendamentos")
    slots = []
    curr = start_work
    
    while curr + timedelta(minutes=duration_min) <= end_work:
        slot_end = curr + timedelta(minutes=duration_min)
        is_free = True
        if not df_ag.empty:
            busy = df_ag[(df_ag['data'] == date_str) & (df_ag['status'] != 'Cancelado')]
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

# --- LOGIN ---
def login_page():
    st.markdown("<h1 style='text-align: center;'>🌸 Edilene Epilação</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        tab_c, tab_g = st.tabs(["🙋‍♀️ Cliente", "👩‍💼 Gestora"])
        with tab_c:
            phone = st.text_input("Telefone (apenas números)")
            if phone:
                clean_p = ''.join(filter(str.isdigit, phone))
                df_cli = load_data("clientes")
                found = df_cli[df_cli['telefone'].astype(str) == clean_p] if not df_cli.empty else pd.DataFrame()
                
                if not found.empty:
                    if st.button("Entrar"):
                        st.session_state['user'] = {'role':'client', 'name': found.iloc[0]['nome'], 'phone': clean_p}
                        st.rerun()
                else:
                    st.info("Telefone não cadastrado.")
                    with st.form("reg"):
                        nome = st.text_input("Seu Nome")
                        if st.form_submit_button("Cadastrar"):
                            save_row("clientes", [nome, clean_p])
                            st.session_state['user'] = {'role':'client', 'name': nome, 'phone': clean_p}
                            st.rerun()
        with tab_g:
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            if st.button("Entrar no Painel"):
                if user == "Edilene" and pwd == "senha123":
                    st.session_state['user'] = {'role':'admin', 'name':'Edilene'}
                    st.rerun()

# --- GESTOR ---
def admin_dashboard():
    st.sidebar.title("Menu Gestão")
    aba = st.sidebar.radio("Navegação", ["Agenda", "Configurar Agenda", "Financeiro"])
    
    if aba == "Agenda":
        st.header("📅 Agenda de Atendimentos")
        hoje = st.date_input("Data:", datetime.today())
        df = load_data("agendamentos")
        if not df.empty:
            dia = df[(df['data'] == str(hoje)) & (df['status'] != 'Cancelado')].sort_values('hora_inicio')
            st.dataframe(dia[['hora_inicio', 'cliente_nome', 'servico', 'status']], use_container_width=True, hide_index=True)

    elif aba == "Configurar Agenda":
        st.header("⚙️ Gestão de Horários")
        t_hor, t_bloq, t_serv = st.tabs(["Horários Semanais", "Bloqueios/Folgas", "Serviços"])
        
        with t_hor:
            st.info("Configure o horário comercial padrão na aba 'configuracoes' da sua planilha.")
            st.write("Desta forma, o sistema saberá quando abrir e fechar a agenda.")

        with t_bloq:
            with st.form("f_bloq"):
                db = st.date_input("Data para bloquear")
                hi = st.time_input("Início")
                hf = st.time_input("Fim")
                if st.form_submit_button("Bloquear Horário"):
                    save_row("agendamentos", [str(uuid.uuid4()), "BLOQUEIO", "00", "Bloqueio", str(db), hi.strftime("%H:%M:%S"), hf.strftime("%H:%M:%S"), 0, "Bloqueado"])
                    st.success("Horário bloqueado para clientes!")

        with t_serv:
            with st.form("f_ser"):
                n = st.text_input("Nome do Serviço")
                d = st.number_input("Duração (minutos)", 15, 180, 30)
                v = st.number_input("Preço (R$)", 0.0)
                if st.form_submit_button("Adicionar"):
                    save_row("servicos", [n, d, v])
                    st.rerun()

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- CLIENTE ---
def client_dashboard():
    st.header(f"Olá, {st.session_state['user']['name']}! ✨")
    
    df_s = load_data("servicos")
    if not df_s.empty:
        serv = st.selectbox("Escolha o procedimento", df_s['nome'].tolist())
        row_s = df_s[df_s['nome'] == serv].iloc[0]
        
        data = st.date_input("Data do agendamento", min_value=datetime.today())
        slots = check_availability(data, int(row_s['duracao_min']))
        
        if slots:
            hora = st.selectbox("Horários livres", slots)
            if st.button("Agendar Agora 💖"):
                h_f = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=int(row_s['duracao_min']))).strftime("%H:%M:%S")
                save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], serv, str(data), hora+":00", h_f, row_s['valor'], "Agendado"])
                st.success("Agendamento realizado!")
                st.balloons()
        else:
            st.error("Não há horários para esta data.")
            
    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- MAIN ---
if 'user' not in st.session_state: st.session_state['user'] = None
if st.session_state['user'] is None: login_page()
elif st.session_state['user']['role'] == 'admin': admin_dashboard()
else: client_dashboard()
