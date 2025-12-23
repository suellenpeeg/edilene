import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, time
import plotly.express as px
from streamlit_option_menu import option_menu
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import uuid

# --- CONFIGURAÇÃO DA PÁGINA E ESTILO ---
st.set_page_config(page_title="Edilene Epilação", page_icon="🌸", layout="wide")

# Paleta de Cores: Rosa Bebê (#FCE1E4), Bege (#F5F5DC), Laranja Claro (#FFDAB9), Texto Escuro (#4A4A4A)
st.markdown("""
<style>
    /* Fundo Geral */
    .stApp {
        background-color: #FFF0F5;
    }
    
    /* Botões */
    .stButton>button {
        background-color: #FFDAB9;
        color: #4A4A4A;
        border-radius: 12px;
        border: 1px solid #E6E6FA;
        font-weight: bold;
    }
    .stButton>button:hover {
        background-color: #FAC898;
        border-color: #F08080;
    }

    /* Inputs */
    .stTextInput>div>div>input, .stSelectbox>div>div>div {
        background-color: #FDF5E6;
        color: #4A4A4A;
        border-radius: 10px;
    }

    /* Títulos */
    h1, h2, h3 {
        color: #BC8F8F;
        font-family: 'Helvetica', sans-serif;
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #FDF5E6;
    }
    
    /* Metrics */
    [data-testid="stMetricValue"] {
        color: #DB7093;
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM GOOGLE SHEETS ---
# Nota: Em produção, use st.secrets. Aqui simulamos a estrutura.
def get_db_connection():
    # Tente conectar via Secrets do Streamlit Cloud
    try:
        scope = ["https://spreadsheets.google.com/feeds", "https://www.googleapis.com/auth/drive"]
        # Convertendo st.secrets para dict normal para autenticação
        creds_dict = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(creds_dict, scope)
        client = gspread.authorize(creds)
        # Abre a planilha pelo nome
        sheet = client.open("db_edilene")
        return sheet
    except Exception as e:
        st.error(f"Erro na conexão com Banco de Dados: {e}")
        return None

# --- FUNÇÕES DE DADOS (CRUD) ---
def load_data(sheet_name):
    conn = get_db_connection()
    if conn:
        try:
            worksheet = conn.worksheet(sheet_name)
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except:
            return pd.DataFrame() # Retorna vazio se a aba não existir ou estiver vazia
    return pd.DataFrame()

def save_row(sheet_name, row_data):
    conn = get_db_connection()
    if conn:
        worksheet = conn.worksheet(sheet_name)
        worksheet.append_row(row_data)

def update_status(appointment_id, new_status):
    conn = get_db_connection()
    if conn:
        ws = conn.worksheet("agendamentos")
        # Localizar a célula e atualizar (lógica simplificada)
        cells = ws.findall(str(appointment_id))
        if cells:
            row = cells[0].row
            # Assume que status é a coluna 9 (I)
            ws.update_cell(row, 9, new_status) 

# --- LÓGICA DE AGENDAMENTO ---
def check_availability(date_str, duration_min, current_appointments):
    # Horário de funcionamento: 08:00 às 18:00
    start_work = datetime.strptime(f"{date_str} 08:00", "%Y-%m-%d %H:%M")
    end_work = datetime.strptime(f"{date_str} 18:00", "%Y-%m-%d %H:%M")
    
    # Gerar slots a cada 30 min
    slots = []
    current_time = start_work
    while current_time + timedelta(minutes=duration_min) <= end_work:
        slot_end = current_time + timedelta(minutes=duration_min)
        
        # Verificar conflito
        is_free = True
        if not current_appointments.empty:
            # Filtra agendamentos ativos do dia
            daily_apps = current_appointments[
                (current_appointments['data'] == date_str) & 
                (current_appointments['status'] != 'Cancelado')
            ]
            
            for _, app in daily_apps.iterrows():
                app_start = datetime.strptime(f"{app['data']} {app['hora_inicio']}", "%Y-%m-%d %H:%M:%S")
                app_end = datetime.strptime(f"{app['data']} {app['hora_fim']}", "%Y-%m-%d %H:%M:%S")
                
                # Lógica de sobreposição
                if not (slot_end <= app_start or current_time >= app_end):
                    is_free = False
                    break
        
        if is_free:
            slots.append(current_time.strftime("%H:%M"))
        
        current_time += timedelta(minutes=30) # Passo de 30 min
        
    return slots

# --- INTERFACE: LOGIN ---
def login_page():
    st.markdown("<h1 style='text-align: center; color: #DB7093;'>🌸 EDILENE EPILAÇÃO 🌸</h1>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        tab1, tab2 = st.tabs(["Cliente", "Gestor"])
        
        # --- LOGIN CLIENTE ---
        with tab1:
            st.subheader("Acesso do Cliente")
            phone = st.text_input("Seu Telefone (apenas números)", key="cli_phone")
            
            if st.button("Entrar / Cadastrar"):
                df_clientes = load_data("clientes")
                # Limpeza simples do telefone
                clean_phone = ''.join(filter(str.isdigit, phone))
                
                if clean_phone:
                    if not df_clientes.empty and clean_phone in df_clientes['telefone'].astype(str).values:
                        user_data = df_clientes[df_clientes['telefone'].astype(str) == clean_phone].iloc[0]
                        st.session_state['user'] = {'role': 'client', 'name': user_data['nome'], 'phone': clean_phone}
                        st.rerun()
                    else:
                        st.warning("Primeiro acesso detectado. Por favor, digite seu nome.")
                        name = st.text_input("Seu Nome Completo")
                        if name and st.button("Confirmar Cadastro"):
                            save_row("clientes", [name, clean_phone])
                            st.session_state['user'] = {'role': 'client', 'name': name, 'phone': clean_phone}
                            st.rerun()

        # --- LOGIN GESTOR ---
        with tab2:
            st.subheader("Área Restrita")
            user = st.text_input("Usuário")
            pwd = st.text_input("Senha", type="password")
            if st.button("Acessar Gerência"):
                if user == "Edilene" and pwd == "senha123":
                    st.session_state['user'] = {'role': 'admin', 'name': 'Edilene'}
                    st.rerun()
                else:
                    st.error("Dados incorretos.")

# --- INTERFACE: CLIENTE ---
def client_dashboard():
    st.sidebar.markdown(f"## Olá, {st.session_state['user']['name']}! 🌸")
    menu = option_menu(None, ["Agendar", "Meus Agendamentos"], 
        icons=['calendar-plus', 'list-check'], 
        menu_icon="cast", default_index=0, orientation="horizontal",
        styles={"nav-link-selected": {"background-color": "#FFDAB9", "color": "black"}})

    df_servicos = load_data("servicos")
    df_agendamentos = load_data("agendamentos")

    if menu == "Agendar":
        st.markdown("### ✨ Novo Agendamento")
        with st.container(border=True):
            if df_servicos.empty:
                st.info("Nenhum serviço cadastrado pelo gestor ainda.")
            else:
                s_options = df_servicos['nome'].tolist()
                servico_selecionado = st.selectbox("Escolha o Procedimento", s_options)
                
                servico_info = df_servicos[df_servicos['nome'] == servico_selecionado].iloc[0]
                duracao = int(servico_info['duracao_min'])
                valor = float(servico_info['valor'])
                
                st.caption(f"⏱️ Duração: {duracao} min | 💲 Valor: R$ {valor:.2f}")
                
                d_date = st.date_input("Escolha a Data", min_value=datetime.today())
                
                # Buscar horários
                if d_date:
                    slots = check_availability(str(d_date), duracao, df_agendamentos)
                    if slots:
                        time_slot = st.selectbox("Horários Disponíveis", slots)
                        
                        if st.button("Confirmar Agendamento 💖"):
                            # Calcular hora fim
                            start_dt = datetime.strptime(f"{d_date} {time_slot}", "%Y-%m-%d %H:%M")
                            end_dt = start_dt + timedelta(minutes=duracao)
                            
                            new_app = [
                                str(uuid.uuid4()), # ID
                                st.session_state['user']['name'],
                                st.session_state['user']['phone'],
                                servico_selecionado,
                                str(d_date),
                                time_slot + ":00",
                                end_dt.strftime("%H:%M:%S"),
                                valor,
                                "Agendado"
                            ]
                            save_row("agendamentos", new_app)
                            st.success("Agendamento realizado com sucesso!")
                            st.cache_data.clear() # Limpar cache para recarregar dados
                    else:
                        st.error("Não há horários disponíveis para este serviço nesta data. Tente outro dia.")

    elif menu == "Meus Agendamentos":
        st.markdown("### 📅 Minha Agenda")
        if not df_agendamentos.empty:
            my_apps = df_agendamentos[
                (df_agendamentos['cliente_tel'].astype(str) == st.session_state['user']['phone']) &
                (df_agendamentos['status'] != 'Cancelado')
            ]
            
            if not my_apps.empty:
                for idx, row in my_apps.iterrows():
                    with st.container(border=True):
                        col_a, col_b = st.columns([3, 1])
                        with col_a:
                            st.markdown(f"**{row['servico']}**")
                            st.write(f"🗓️ {row['data']} às {row['hora_inicio']}")
                            st.caption(f"Valor: R$ {row['valor']}")
                        with col_b:
                            if st.button("Cancelar", key=f"cancel_{row['id']}"):
                                update_status(row['id'], "Cancelado")
                                st.warning("Agendamento cancelado.")
                                st.rerun()
            else:
                st.info("Você não tem agendamentos futuros.")
        else:
            st.info("Nenhum agendamento encontrado.")
            
    if st.sidebar.button("Sair / Logout"):
        st.session_state['user'] = None
        st.rerun()

# --- INTERFACE: GESTOR ---
def admin_dashboard():
    st.sidebar.title("Painel da Edilene 👩‍💼")
    
    page = st.sidebar.radio("Navegação", ["Agenda", "Serviços & Config", "Financeiro"])
    
    df_agendamentos = load_data("agendamentos")
    
    if page == "Agenda":
        st.header("📖 Agenda Semanal")
        
        # Filtro de Data
        sel_date = st.date_input("Filtrar por data", datetime.today())
        
        if not df_agendamentos.empty:
            day_apps = df_agendamentos[
                (df_agendamentos['data'] == str(sel_date)) &
                (df_agendamentos['status'] != 'Cancelado')
            ].sort_values(by='hora_inicio')
            
            if not day_apps.empty:
                st.table(day_apps[['hora_inicio', 'cliente_nome', 'servico', 'status']])
                
                st.subheader("Gerenciar Agendamento Específico")
                app_to_edit = st.selectbox("Selecione para alterar", day_apps['id'].astype(str) + " - " + day_apps['cliente_nome'])
                app_id = app_to_edit.split(" - ")[0]
                
                col1, col2 = st.columns(2)
                if col1.button("❌ Cancelar Agendamento"):
                    update_status(app_id, "Cancelado")
                    st.success("Cancelado!")
                    st.rerun()
            else:
                st.info("Agenda livre para este dia.")
        else:
            st.info("Sem dados.")

    elif page == "Serviços & Config":
        st.header("⚙️ Cadastro de Serviços")
        
        with st.form("new_service"):
            st.write("Adicionar Novo Serviço")
            name = st.text_input("Nome do Serviço")
            duration = st.number_input("Duração (minutos)", min_value=15, step=15)
            price = st.number_input("Valor (R$)", min_value=0.0)
            submitted = st.form_submit_button("Salvar Serviço")
            
            if submitted and name:
                save_row("servicos", [name, duration, price])
                st.success(f"Serviço {name} cadastrado!")
        
        st.divider()
        st.subheader("Lista de Serviços Atuais")
        df_servicos = load_data("servicos")
        if not df_servicos.empty:
            st.dataframe(df_servicos)

    elif page == "Financeiro":
        st.header("💰 Gestão Financeira")
        
        # Calcular Receita
        receita_total = 0
        if not df_agendamentos.empty:
            valid_apps = df_agendamentos[df_agendamentos['status'] == 'Concluido'] # Idealmente 'Concluido', aqui usando 'Agendado' para demo se nao tiver concluido
            # Para simplificar, vamos somar todos que não estão cancelados
            valid_apps = df_agendamentos[df_agendamentos['status'] != 'Cancelado']
            receita_total = valid_apps['valor'].sum()

        # Calcular Despesas
        df_despesas = load_data("despesas")
        despesa_total = 0
        if not df_despesas.empty:
            # Garante que é numérico
            despesa_total = pd.to_numeric(df_despesas['valor']).sum()

        lucro = receita_total - despesa_total

        # KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("Receita (Estimada)", f"R$ {receita_total:,.2f}")
        c2.metric("Despesas", f"R$ {despesa_total:,.2f}")
        c3.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta_color="normal")
        
        st.divider()
        
        # Cadastro de Despesa
        with st.expander("Cadastrar Nova Despesa"):
            with st.form("add_expense"):
                desc = st.text_input("Descrição")
                val = st.number_input("Valor", min_value=0.0)
                d_date = st.date_input("Data")
                if st.form_submit_button("Lançar"):
                    save_row("despesas", [str(d_date), desc, val])
                    st.success("Despesa salva!")
                    st.rerun()

        # Gráficos
        if not df_agendamentos.empty:
            st.subheader("Agendamentos por Serviço")
            count_serv = valid_apps['servico'].value_counts().reset_index()
            count_serv.columns = ['Servico', 'Qtd']
            fig_pie = px.pie(count_serv, values='Qtd', names='Servico', color_discrete_sequence=px.colors.sequential.RdBu)
            st.plotly_chart(fig_pie)

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- MAIN ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    login_page()
else:
    if st.session_state['user']['role'] == 'admin':
        admin_dashboard()
    else:
        client_dashboard()
