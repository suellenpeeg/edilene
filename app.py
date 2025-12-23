import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from streamlit_option_menu import option_menu
import gspread
from google.oauth2.service_account import Credentials
import uuid

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Edilene Epilação", page_icon="🌸", layout="wide")

# Estilo Visual
st.markdown("""
<style>
    .stApp { background-color: #FFF0F5; }
    .stButton>button { background-color: #FFDAB9; color: #4A4A4A; border-radius: 15px; font-weight: 600; width: 100%; }
    h1, h2, h3 { color: #BC8F8F; font-family: 'Helvetica'; }
    [data-testid="stSidebar"] { background-color: #FDF5E6; }
    .stTabs [data-baseweb="tab-list"] { gap: 10px; }
    .stTabs [data-baseweb="tab"] { background-color: #FDF5E6; border-radius: 5px; padding: 10px; }
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO ---
def get_db_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        # ID DA SUA PLANILHA - Verifique se este ID está 100% correto
        PLANILHA_ID = "19FiUFG7daZKCTMZ8vtD023BPCPfnhpMaQ6UfD0KIhb0"
        return client.open_by_key(PLANILHA_ID)
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
            ws.append_row(row_data)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

# --- LÓGICA DE AGENDAMENTO ---
def check_availability(date_obj, duration_min):
    date_str = str(date_obj)
    weekday_idx = date_obj.weekday() # 0=Segunda, 6=Domingo
    dias_semana = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
    dia_nome = dias_semana[weekday_idx]
    
    # Busca configurações do dia
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
    st.markdown("<h1 style='text-align: center;'>🌸 Sistema Edilene Epilação</h1>", unsafe_allow_html=True)
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        tab_c, tab_g = st.tabs(["🙋‍♀️ Área da Cliente", "👩‍💼 Gestora"])
        with tab_c:
            phone = st.text_input("Seu Telefone (DDD + Número)")
            if phone:
                clean_p = ''.join(filter(str.isdigit, phone))
                df_cli = load_data("clientes")
                found = df_cli[df_cli['telefone'].astype(str) == clean_p] if not df_cli.empty else pd.DataFrame()
                
                if not found.empty:
                    if st.button("Acessar minha conta"):
                        st.session_state['user'] = {'role':'client', 'name': found.iloc[0]['nome'], 'phone': clean_p}
                        st.rerun()
                else:
                    st.warning("Cadastro não encontrado.")
                    with st.form("reg"):
                        nome = st.text_input("Nome Completo")
                        if st.form_submit_button("Criar Cadastro"):
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
    aba = st.sidebar.radio("Ir para:", ["Agenda de Hoje", "Configurar Agenda", "Financeiro"])
    
    if aba == "Agenda de Hoje":
        st.header("📅 Compromissos")
        hoje = st.date_input("Filtrar data:", datetime.today())
        df = load_data("agendamentos")
        if not df.empty:
            dia = df[(df['data'] == str(hoje)) & (df['status'] != 'Cancelado')].sort_values('hora_inicio')
            st.dataframe(dia[['hora_inicio', 'cliente_nome', 'servico', 'status']], use_container_width=True, hide_index=True)

    elif aba == "Configurar Agenda":
        st.header("⚙️ Configurações")
        t_hor, t_bloq, t_serv = st.tabs(["Horários Semanais", "Bloquear Horário", "Meus Serviços"])
        
        with t_hor:
            st.info("Defina o horário padrão de funcionamento para cada dia.")
            dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
            with st.form("f_hor"):
                d_sel = st.selectbox("Dia", dias)
                st_sel = st.radio("Status", ["Aberto", "Fechado"], horizontal=True)
                col1, col2 = st.columns(2)
                h_a = col1.text_input("Abertura", "08:00")
                h_f = col2.text_input("Fechamento", "18:00")
                if st.form_submit_button("Salvar Horário"):
                    # Aqui você deve atualizar manualmente a aba 'configuracoes' na planilha
                    st.success(f"Configuração para {d_sel} anotada! Lembre-se de preencher na aba 'configuracoes' da planilha.")

        with t_bloq:
            with st.form("f_bloq"):
                st.subheader("Bloquear por Folga ou Almoço")
                db = st.date_input("Data")
                hi = st.text_input("Início (HH:MM)")
                hf = st.text_input("Fim (HH:MM)")
                if st.form_submit_button("Bloquear Horário"):
                    save_row("agendamentos", [str(uuid.uuid4()), "BLOQUEIO", "00", "Bloqueio/Folga", str(db), hi+":00", hf+":00", 0, "Bloqueado"])
                    st.success("Horário indisponível para clientes!")

        with t_serv:
            with st.form("f_ser"):
                n = st.text_input("Nome do Serviço")
                d = st.number_input("Minutos", 30, 180, 30)
                v = st.number_input("Preço", 0.0)
                if st.form_submit_button("Adicionar Serviço"):
                    save_row("servicos", [n, d, v])
                    st.rerun()

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- CLIENTE ---
def client_dashboard():
    st.header(f"Bem-vinda, {st.session_state['user']['name']}! ✨")
    
    df_s = load_data("servicos")
    if not df_s.empty:
        serv = st.selectbox("O que vamos fazer hoje?", df_s['nome'].tolist())
        row_s = df_s[df_s['nome'] == serv].iloc[0]
        st.write(f"⏱️ {row_s['duracao_min']} min | 💰 R$ {row_s['valor']}")
        
        data = st.date_input("Escolha a data", min_value=datetime.today())
        slots = check_availability(data, int(row_s['duracao_min']))
        
        if slots:
            hora = st.selectbox("Horários disponíveis", slots)
            if st.button("Confirmar Agendamento 💖"):
                h_f = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=int(row_s['duracao_min']))).strftime("%H:%M:%S")
                save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], serv, str(data), hora+":00", h_f, row_s['valor'], "Agendado"])
                st.success("Tudo pronto! Te esperamos.")
                st.balloons()
        else:
            st.error("Desculpe, não há horários para esta data.")
            
    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- MAIN ---
if 'user' not in st.session_state: st.session_state['user'] = None
if st.session_state['user'] is None: login_page()
elif st.session_state['user']['role'] == 'admin': admin_dashboard()
else: client_dashboard()
