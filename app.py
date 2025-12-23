import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import plotly.express as px
from streamlit_option_menu import option_menu
import gspread
from google.oauth2.service_account import Credentials
import uuid

# --- CONFIGURAÇÃO DA PÁGINA E ESTILO ---
st.set_page_config(page_title="Edilene Epilação", page_icon="🌸", layout="wide")

st.markdown("""
<style>
    .stApp { background-color: #FFF0F5; }
    .stButton>button { background-color: #FFDAB9; color: #4A4A4A; border-radius: 15px; font-weight: 600; }
    .stTextInput>div>div>input, .stSelectbox>div>div>div { background-color: #FDF5E6; border-radius: 10px; }
    h1, h2, h3 { color: #BC8F8F; }
    [data-testid="stSidebar"] { background-color: #FDF5E6; }
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM GOOGLE SHEETS ---
def get_db_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        # Substitua pelo seu ID real se necessário
        PLANILHA_ID = "19FiUFG7daZKCTMZ8vtD023BPCPfnhpMaQ6UfD0KIhb0"
        return client.open_by_key(PLANILHA_ID)
    except Exception as e:
        st.error(f"Erro de Conexão: {e}")
        return None

def load_data(sheet_name):
    conn = get_db_connection()
    if conn:
        try:
            return pd.DataFrame(conn.worksheet(sheet_name).get_all_records())
        except: return pd.DataFrame()
    return pd.DataFrame()

def save_row(sheet_name, row_data):
    conn = get_db_connection()
    if conn:
        try: conn.worksheet(sheet_name).append_row(row_data)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

def update_status(appointment_id, new_status):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet("agendamentos")
            cell = ws.find(str(appointment_id))
            if cell: ws.update_cell(cell.row, 9, new_status) 
        except Exception as e: st.error(f"Erro: {e}")

# --- LÓGICA DE DISPONIBILIDADE ---
def check_availability(date_obj, duration_min, current_appointments):
    date_str = str(date_obj)
    weekday_name = date_obj.strftime('%A').lower() # ex: monday
    
    # Mapeamento para tradução/busca na aba de configurações
    dias_traducao = {
        'monday': 'Segunda-feira', 'tuesday': 'Terça-feira', 'wednesday': 'Quarta-feira',
        'thursday': 'Quinta-feira', 'friday': 'Sexta-feira', 'saturday': 'Sábado', 'sunday': 'Domingo'
    }
    
    config_agenda = load_data("configuracoes") # Aba nova para horários do dia
    if config_agenda.empty:
        # Padrão caso não haja configuração
        h_abre, h_fecha = "08:00", "18:00"
    else:
        dia_config = config_agenda[config_agenda['dia'] == dias_traducao[weekday_name]]
        if dia_config.empty or dia_config.iloc[0]['status'] == 'Fechado':
            return [] # Dia não disponível
        h_abre = dia_config.iloc[0]['abertura']
        h_fecha = dia_config.iloc[0]['fechamento']

    start_work = datetime.strptime(f"{date_str} {h_abre}", "%Y-%m-%d %H:%M")
    end_work = datetime.strptime(f"{date_str} {h_fecha}", "%Y-%m-%d %H:%M")
    
    slots = []
    current_time = start_work
    
    while current_time + timedelta(minutes=duration_min) <= end_work:
        slot_end = current_time + timedelta(minutes=duration_min)
        is_free = True
        
        if not current_appointments.empty:
            daily_apps = current_appointments[(current_appointments['data'] == date_str) & (current_appointments['status'] != 'Cancelado')]
            for _, app in daily_apps.iterrows():
                try:
                    app_start = datetime.strptime(f"{app['data']} {app['hora_inicio']}", "%Y-%m-%d %H:%M:%S")
                    app_end = datetime.strptime(f"{app['data']} {app['hora_fim']}", "%Y-%m-%d %H:%M:%S")
                    if current_time < app_end and slot_end > app_start:
                        is_free = False
                        break
                except: continue
        
        if is_free: slots.append(current_time.strftime("%H:%M"))
        current_time += timedelta(minutes=30)
    return slots

# --- LOGIN ---
def login_page():
    st.markdown("<h1 style='text-align: center;'>🌸 EDILENE EPILAÇÃO</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_cli, tab_adm = st.tabs(["🙋‍♀️ Cliente", "👩‍💼 Gestora"])
        with tab_cli:
            phone = st.text_input("Telefone (com DDD)", key="login_phone")
            if phone:
                clean_phone = ''.join(filter(str.isdigit, phone))
                df_clientes = load_data("clientes")
                user_match = df_clientes[df_clientes['telefone'].astype(str) == clean_phone] if not df_clientes.empty else pd.DataFrame()
                
                if not user_match.empty:
                    if st.button("Entrar"):
                        st.session_state['user'] = {'role': 'client', 'name': user_match.iloc[0]['nome'], 'phone': clean_phone}
                        st.rerun()
                else:
                    with st.form("novo_cadastro"):
                        nome = st.text_input("Seu nome para cadastro")
                        if st.form_submit_button("Cadastrar e Entrar"):
                            if nome:
                                save_row("clientes", [nome, clean_phone])
                                st.session_state['user'] = {'role': 'client', 'name': nome, 'phone': clean_phone}
                                st.rerun()
        with tab_adm:
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            if st.button("Acessar Painel"):
                if u == "Edilene" and p == "senha123":
                    st.session_state['user'] = {'role': 'admin', 'name': 'Edilene'}
                    st.rerun()

# --- DASHBOARD GESTOR ---
def admin_dashboard():
    st.sidebar.title("Painel Administrativo")
    page = st.sidebar.radio("Navegação", ["📅 Agenda", "⚙️ Configurar Agenda", "💰 Financeiro"])
    
    if page == "📅 Agenda":
        st.header("Atendimentos do Dia")
        sel_date = st.date_input("Data:", datetime.today())
        df = load_data("agendamentos")
        if not df.empty:
            agenda = df[(df['data'] == str(sel_date)) & (df['status'] != 'Cancelado')].sort_values('hora_inicio')
            st.dataframe(agenda[['hora_inicio', 'cliente_nome', 'servico', 'status']], use_container_width=True, hide_index=True)
            
    elif page == "⚙️ Configurar Agenda":
        st.header("Configuração de Horários e Serviços")
        
        t1, t2, t3 = st.tabs(["Horários da Semana", "Bloqueios", "Serviços"])
        
        with t1:
            st.subheader("Definir Horário de Funcionamento")
            dias = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
            # Nota: Para salvar fixo, recomendamos criar a aba 'configuracoes' na planilha com colunas: dia, status, abertura, fechamento
            with st.form("config_semanal"):
                dia_sel = st.selectbox("Selecione o dia para alterar", dias)
                status_dia = st.radio("Status", ["Aberto", "Fechado"], horizontal=True)
                col_h1, col_h2 = st.columns(2)
                h_abre = col_h1.text_input("Abertura (HH:MM)", value="08:00")
                h_fecha = col_h2.text_input("Fechamento (HH:MM)", value="18:00")
                if st.form_submit_button("Salvar Configuração do Dia"):
                    # Aqui você pode implementar um overwrite na aba configuracoes
                    st.success(f"Configuração para {dia_sel} atualizada!")
        
        with t2:
            st.subheader("Bloquear Horário Específico")
            with st.form("bloqueio_form"):
                data_b = st.date_input("Data do bloqueio")
                h_i = st.text_input("Hora Início (ex: 12:00)")
                h_f = st.text_input("Hora Fim (ex: 13:00)")
                if st.form_submit_button("Confirmar Bloqueio"):
                    save_row("agendamentos", [str(uuid.uuid4()), "BLOQUEIO", "00", "Pausa", str(data_b), h_i, h_f, 0, "Bloqueado"])
                    st.warning("Horário bloqueado.")
        
        with t3:
            st.subheader("Cadastrar Novo Serviço")
            with st.form("serv_form"):
                n = st.text_input("Nome do Serviço")
                d = st.number_input("Duração (min)", value=30, step=5)
                v = st.number_input("Valor (R$)", value=0.0)
                if st.form_submit_button("Salvar Serviço"):
                    save_row("servicos", [n, d, v])
                    st.success("Serviço adicionado!")

    elif page == "💰 Financeiro":
        st.header("Resumo Financeiro")
        # Lógica de soma de valores...

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- DASHBOARD CLIENTE ---
def client_dashboard():
    st.title(f"Olá, {st.session_state['user']['name']}! 🌺")
    tab1, tab2 = st.tabs(["Novo Agendamento", "Minha Agenda"])
    
    with tab1:
        df_serv = load_data("servicos")
        if not df_serv.empty:
            servico = st.selectbox("Selecione o serviço", df_serv['nome'].tolist())
            duracao = int(df_serv[df_serv['nome'] == servico].iloc[0]['duracao_min'])
            valor = df_serv[df_serv['nome'] == servico].iloc[0]['valor']
            
            data_sel = st.date_input("Data desejada", min_value=datetime.today())
            df_ag = load_data("agendamentos")
            horarios = check_availability(data_sel, duracao, df_ag)
            
            if horarios:
                hora_sel = st.selectbox("Horários disponíveis", horarios)
                if st.button("Confirmar Agendamento"):
                    h_inicio = f"{hora_sel}:00"
                    h_fim = (datetime.strptime(hora_sel, "%H:%M") + timedelta(minutes=duracao)).strftime("%H:%M:%S")
                    save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], servico, str(data_sel), h_inicio, h_fim, valor, "Agendado"])
                    st.success("Agendado com sucesso!")
            else:
                st.error("Não há horários disponíveis para este dia.")
    
    with tab2:
        df_ag = load_data("agendamentos")
        if not df_ag.empty:
            meus = df_ag[df_ag['cliente_tel'].astype(str) == st.session_state['user']['phone']]
            st.table(meus[['data', 'hora_inicio', 'servico', 'status']])

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- MAIN ---
if 'user' not in st.session_state: st.session_state['user'] = None
if st.session_state['user'] is None: login_page()
elif st.session_state['user']['role'] == 'admin': admin_dashboard()
else: client_dashboard()
