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

# CSS Personalizado: Rosa Bebê, Bege, Laranja Claro
st.markdown("""
<style>
    /* Fundo Geral - Rosa bem claro */
    .stApp {
        background-color: #FFF0F5;
    }
    
    /* Botões - Laranja claro com texto escuro */
    .stButton>button {
        background-color: #FFDAB9;
        color: #4A4A4A;
        border-radius: 15px;
        border: 1px solid #E6E6FA;
        font-weight: 600;
        padding: 0.5rem 1rem;
    }
    .stButton>button:hover {
        background-color: #FAC898;
        border-color: #F08080;
        color: #000;
    }

    /* Inputs e Selectbox - Bege suave */
    .stTextInput>div>div>input, .stSelectbox>div>div>div, .stDateInput>div>div>input {
        background-color: #FDF5E6;
        color: #4A4A4A;
        border-radius: 10px;
        border: 1px solid #D3D3D3;
    }

    /* Títulos e Cabeçalhos - Tom Rosado/Marrom suave */
    h1, h2, h3 {
        color: #BC8F8F;
        font-family: 'Helvetica', sans-serif;
    }
    
    /* Sidebar - Bege */
    [data-testid="stSidebar"] {
        background-color: #FDF5E6;
        border-right: 2px solid #FFF0F5;
    }
    
    /* Métricas (Financeiro) */
    [data-testid="stMetricValue"] {
        color: #DB7093;
        font-weight: bold;
    }
    
    /* Tabelas */
    [data-testid="stDataFrame"] {
        background-color: white;
        border-radius: 10px;
        padding: 10px;
    }
</style>
""", unsafe_allow_html=True)

# --- CONEXÃO COM GOOGLE SHEETS (MODERNA) ---
def get_db_connection():
    try:
        # Define os escopos necessários
        scopes = [
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive"
        ]
        
        # Carrega credenciais dos secrets
        credentials_info = dict(st.secrets["gcp_service_account"])
        
        # Autentica
        credentials = Credentials.from_service_account_info(
            credentials_info,
            scopes=scopes
        )
        
        client = gspread.authorize(credentials)
        
        # Abre a planilha
        sheet = client.open("db_edilene")
        return sheet
        
    except gspread.exceptions.SpreadsheetNotFound:
        st.error("🚨 Erro Crítico: A planilha 'db_edilene' não foi encontrada. Verifique se o nome está exato e se você compartilhou com o e-mail do bot.")
        return None
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

# --- FUNÇÕES DE DADOS (CRUD) ---
def load_data(sheet_name):
    conn = get_db_connection()
    if conn:
        try:
            worksheet = conn.worksheet(sheet_name)
            data = worksheet.get_all_records()
            return pd.DataFrame(data)
        except gspread.exceptions.WorksheetNotFound:
            st.error(f"A aba '{sheet_name}' não existe na planilha.")
            return pd.DataFrame()
        except Exception as e:
            st.error(f"Erro ao ler dados: {e}")
            return pd.DataFrame()
    return pd.DataFrame()

def save_row(sheet_name, row_data):
    conn = get_db_connection()
    if conn:
        try:
            worksheet = conn.worksheet(sheet_name)
            worksheet.append_row(row_data)
        except Exception as e:
            st.error(f"Erro ao salvar: {e}")

def update_status(appointment_id, new_status):
    conn = get_db_connection()
    if conn:
        try:
            ws = conn.worksheet("agendamentos")
            # Procura a célula que contém o ID
            cell = ws.find(str(appointment_id))
            if cell:
                # Atualiza a coluna 'status' (Coluna I = 9) na mesma linha
                ws.update_cell(cell.row, 9, new_status) 
        except Exception as e:
            st.error(f"Erro ao atualizar status: {e}")

# --- LÓGICA DE AGENDAMENTO ---
def check_availability(date_str, duration_min, current_appointments):
    # Horário: 08:00 às 18:00
    start_work = datetime.strptime(f"{date_str} 08:00", "%Y-%m-%d %H:%M")
    end_work = datetime.strptime(f"{date_str} 18:00", "%Y-%m-%d %H:%M")
    
    slots = []
    current_time = start_work
    
    while current_time + timedelta(minutes=duration_min) <= end_work:
        slot_end = current_time + timedelta(minutes=duration_min)
        is_free = True
        
        if not current_appointments.empty:
            # Filtra agendamentos do dia que não estão cancelados
            daily_apps = current_appointments[
                (current_appointments['data'] == date_str) & 
                (current_appointments['status'] != 'Cancelado')
            ]
            
            for _, app in daily_apps.iterrows():
                try:
                    app_start = datetime.strptime(f"{app['data']} {app['hora_inicio']}", "%Y-%m-%d %H:%M:%S")
                    app_end = datetime.strptime(f"{app['data']} {app['hora_fim']}", "%Y-%m-%d %H:%M:%S")
                    
                    # Se o horário atual conflita com algum agendamento existente
                    # (Start < App_End) E (End > App_Start)
                    if current_time < app_end and slot_end > app_start:
                        is_free = False
                        break
                except ValueError:
                    # Tenta formato curto se der erro no formato com segundos
                    try:
                        app_start = datetime.strptime(f"{app['data']} {app['hora_inicio']}", "%Y-%m-%d %H:%M")
                        app_end = datetime.strptime(f"{app['data']} {app['hora_fim']}", "%Y-%m-%d %H:%M")
                        if current_time < app_end and slot_end > app_start:
                            is_free = False
                            break
                    except:
                        pass # Ignora erros de parse de data
        
        if is_free:
            slots.append(current_time.strftime("%H:%M"))
        
        current_time += timedelta(minutes=30) # Intervalo entre opções de horários
        
    return slots

# --- PAGINA: LOGIN ---
def login_page():
    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center; color: #DB7093;'>🌸 EDILENE EPILAÇÃO 🌸</h1>", unsafe_allow_html=True)
    st.markdown("<p style='text-align: center; color: #888;'>Agende seu momento de cuidado</p>", unsafe_allow_html=True)
    st.write("---")
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab_cli, tab_adm = st.tabs(["🙋‍♀️ Sou Cliente", "👩‍💼 Sou Gestora"])
        
        # --- LOGIN CLIENTE ---
        with tab_cli:
            st.markdown("### Acesso rápido")
            phone = st.text_input("Digite seu Telefone (apenas números)", key="login_phone")
            
            if st.button("Entrar / Cadastrar", key="btn_cli"):
                clean_phone = ''.join(filter(str.isdigit, phone))
                
                if len(clean_phone) < 8:
                    st.warning("Por favor, digite um telefone válido.")
                else:
                    df_clientes = load_data("clientes")
                    
                    # Verifica se cliente existe
                    user_found = False
                    user_name = ""
                    
                    if not df_clientes.empty:
                        # Converte para string para garantir comparação
                        df_clientes['telefone'] = df_clientes['telefone'].astype(str)
                        match = df_clientes[df_clientes['telefone'] == clean_phone]
                        if not match.empty:
                            user_found = True
                            user_name = match.iloc[0]['nome']
                    
                    if user_found:
                        st.session_state['user'] = {'role': 'client', 'name': user_name, 'phone': clean_phone}
                        st.success(f"Bem-vinda de volta, {user_name}!")
                        st.rerun()
                    else:
                        st.info("Não encontramos seu cadastro. Vamos criar agora?")
                        name = st.text_input("Seu Nome Completo")
                        if name and st.button("Finalizar Cadastro"):
                            save_row("clientes", [name, clean_phone])
                            st.session_state['user'] = {'role': 'client', 'name': name, 'phone': clean_phone}
                            st.success("Cadastro realizado!")
                            st.rerun()

        # --- LOGIN GESTOR ---
        with tab_adm:
            st.markdown("### Acesso Administrativo")
            u = st.text_input("Usuário")
            p = st.text_input("Senha", type="password")
            if st.button("Acessar Painel"):
                if u == "Edilene" and p == "senha123":
                    st.session_state['user'] = {'role': 'admin', 'name': 'Edilene'}
                    st.rerun()
                else:
                    st.error("Dados de acesso incorretos.")

# --- PAGINA: CLIENTE ---
def client_dashboard():
    st.sidebar.markdown(f"## Olá, {st.session_state['user']['name']}! 🌺")
    
    # Menu de navegação superior
    selected = option_menu(
        menu_title=None,
        options=["Agendar Serviço", "Meus Agendamentos"],
        icons=["calendar-plus", "clock-history"],
        default_index=0,
        orientation="horizontal",
        styles={
            "container": {"padding": "0!important", "background-color": "#FFF0F5"},
            "icon": {"color": "#DB7093", "font-size": "18px"}, 
            "nav-link": {"font-size": "16px", "text-align": "center", "margin":"0px", "--hover-color": "#FFDAB9"},
            "nav-link-selected": {"background-color": "#FFDAB9", "color": "black"},
        }
    )

    df_servicos = load_data("servicos")
    df_agendamentos = load_data("agendamentos")

    if selected == "Agendar Serviço":
        st.markdown("### ✨ Escolha seu procedimento")
        
        with st.container(border=True):
            if df_servicos.empty:
                st.warning("O sistema ainda não possui serviços cadastrados.")
            else:
                lista_servicos = df_servicos['nome'].tolist()
                servico_escolhido = st.selectbox("Serviço", lista_servicos)
                
                # Pega detalhes do serviço
                dados_servico = df_servicos[df_servicos['nome'] == servico_escolhido].iloc[0]
                duracao = int(dados_servico['duracao_min'])
                valor = float(str(dados_servico['valor']).replace(',', '.'))
                
                col_info1, col_info2 = st.columns(2)
                col_info1.info(f"⏱️ Duração estimada: {duracao} minutos")
                col_info2.info(f"💲 Investimento: R$ {valor:.2f}")
                
                st.markdown("---")
                st.markdown("### 📅 Escolha a Data")
                data_agendamento = st.date_input("Data", min_value=datetime.today(), label_visibility="collapsed")
                
                if data_agendamento:
                    # Busca horários livres
                    slots = check_availability(str(data_agendamento), duracao, df_agendamentos)
                    
                    if slots:
                        horario_escolhido = st.selectbox("Horários Disponíveis", slots)
                        
                        st.markdown("<br>", unsafe_allow_html=True)
                        if st.button("Confirmar Agendamento 💖", use_container_width=True):
                            # Monta dados para salvar
                            start_dt = datetime.strptime(f"{data_agendamento} {horario_escolhido}", "%Y-%m-%d %H:%M")
                            end_dt = start_dt + timedelta(minutes=duracao)
                            
                            novo_agendamento = [
                                str(uuid.uuid4()), # ID único
                                st.session_state['user']['name'],
                                st.session_state['user']['phone'],
                                servico_escolhido,
                                str(data_agendamento),
                                horario_escolhido + ":00",
                                end_dt.strftime("%H:%M:%S"),
                                valor,
                                "Agendado"
                            ]
                            
                            save_row("agendamentos", novo_agendamento)
                            st.success(f"Agendamento confirmado para {data_agendamento.strftime('%d/%m')} às {horario_escolhido}!")
                            st.balloons()
                            # Limpa cache para atualizar tabelas
                            st.cache_data.clear()
                    else:
                        st.error("Que pena! Não há horários disponíveis para este serviço nesta data. Tente outro dia.")

    elif selected == "Meus Agendamentos":
        st.markdown("### 🗓️ Seus horários marcados")
        
        if not df_agendamentos.empty:
            # Filtra agendamentos do usuário logado
            meus_agendamentos = df_agendamentos[
                (df_agendamentos['cliente_tel'].astype(str) == st.session_state['user']['phone']) &
                (df_agendamentos['status'] != 'Cancelado')
            ]
            
            if not meus_agendamentos.empty:
                for idx, row in meus_agendamentos.iterrows():
                    with st.container(border=True):
                        c1, c2 = st.columns([4, 1])
                        with c1:
                            st.markdown(f"**{row['servico']}**")
                            st.caption(f"📅 Data: {row['data']} | ⏰ Hora: {row['hora_inicio']}")
                            st.caption(f"Status: {row['status']}")
                        with c2:
                            # Botão com chave única baseada no ID
                            if st.button("Cancelar", key=f"btn_cancel_{row['id']}"):
                                update_status(row['id'], "Cancelado")
                                st.warning("Agendamento cancelado com sucesso.")
                                st.rerun()
            else:
                st.info("Você não tem agendamentos futuros.")
        else:
            st.info("Nenhum agendamento encontrado.")
            
    st.sidebar.divider()
    if st.sidebar.button("Sair / Logout"):
        st.session_state['user'] = None
        st.rerun()

# --- PAGINA: GESTOR ---
def admin_dashboard():
    st.sidebar.image("https://cdn-icons-png.flaticon.com/512/6997/6997662.png", width=100) # Ícone cosmético
    st.sidebar.title("Painel Edilene")
    
    page = st.sidebar.radio("Navegação", ["📅 Agenda", "⚙️ Serviços", "💰 Financeiro"])
    
    df_agendamentos = load_data("agendamentos")
    
    if page == "📅 Agenda":
        st.title("Agenda de Atendimentos")
        
        filtro_data = st.date_input("Ver agenda do dia:", datetime.today())
        
        if not df_agendamentos.empty:
            # Filtra pelo dia e remove cancelados
            agenda_dia = df_agendamentos[
                (df_agendamentos['data'] == str(filtro_data)) &
                (df_agendamentos['status'] != 'Cancelado')
            ].sort_values(by='hora_inicio')
            
            if not agenda_dia.empty:
                # Mostra tabela simples
                st.dataframe(agenda_dia[['hora_inicio', 'hora_fim', 'cliente_nome', 'servico', 'status']], hide_index=True, use_container_width=True)
                
                st.divider()
                st.subheader("Gerenciar Agendamento")
                
                # Selectbox para ações
                opcoes_agenda = agenda_dia.apply(lambda x: f"{x['hora_inicio']} - {x['cliente_nome']} ({x['servico']})", axis=1)
                selecionado_str = st.selectbox("Selecione um agendamento para editar:", options=opcoes_agenda)
                
                if selecionado_str:
                    # Recupera o ID baseado na seleção (lógica simples de índice)
                    index_selecionado = opcoes_agenda[opcoes_agenda == selecionado_str].index[0]
                    id_agendamento = agenda_dia.loc[index_selecionado, 'id']
                    
                    c1, c2 = st.columns(2)
                    if c1.button("✅ Marcar como Concluído"):
                        update_status(id_agendamento, "Concluido")
                        st.success("Serviço concluído!")
                        st.rerun()
                        
                    if c2.button("❌ Cancelar Agendamento"):
                        update_status(id_agendamento, "Cancelado")
                        st.warning("Agendamento cancelado.")
                        st.rerun()
            else:
                st.info("Nenhum agendamento para este dia.")
        else:
            st.info("Sem dados na planilha de agendamentos.")

    elif page == "⚙️ Serviços":
        st.title("Cadastro de Serviços")
        
        with st.form("form_servico", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            nome = col1.text_input("Nome do Serviço")
            duracao = col2.number_input("Duração (min)", min_value=5, step=5, value=30)
            valor = col3.number_input("Valor (R$)", min_value=0.0, step=1.0)
            
            if st.form_submit_button("Salvar Serviço"):
                if nome:
                    save_row("servicos", [nome, duracao, valor])
                    st.success(f"Serviço '{nome}' adicionado com sucesso!")
                    st.rerun()
                else:
                    st.warning("Preencha o nome do serviço.")
        
        st.divider()
        st.subheader("Serviços Ativos")
        df_servicos = load_data("servicos")
        if not df_servicos.empty:
            st.dataframe(df_servicos, use_container_width=True)
        else:
            st.info("Nenhum serviço cadastrado.")

    elif page == "💰 Financeiro":
        st.title("Controle Financeiro")
        
        # Carrega dados
        df_despesas = load_data("despesas")
        
        # Cálculos
        receita = 0.0
        despesas = 0.0
        
        # Receita: Considera agendamentos 'Concluido' ou 'Agendado' (excluindo cancelados)
        # Para um financeiro real, deveria somar apenas 'Concluido', mas aqui somaremos previsão
        if not df_agendamentos.empty:
            df_validos = df_agendamentos[df_agendamentos['status'] != 'Cancelado']
            # Tratamento de erro na conversão de valor
            try:
                receita = pd.to_numeric(df_validos['valor']).sum()
            except:
                pass # Se houver erro de formatação na planilha

        if not df_despesas.empty:
            try:
                despesas = pd.to_numeric(df_despesas['valor']).sum()
            except:
                pass

        lucro = receita - despesas
        
        # Métricas visuais
        col1, col2, col3 = st.columns(3)
        col1.metric("Receita Total (Previsão)", f"R$ {receita:,.2f}")
        col2.metric("Despesas Totais", f"R$ {despesas:,.2f}")
        col3.metric("Lucro Líquido", f"R$ {lucro:,.2f}", delta_color="normal")
        
        st.divider()
        
        c_graph1, c_graph2 = st.columns([2,1])
        
        with c_graph1:
            st.subheader("Cadastrar Despesa")
            with st.form("form_despesa", clear_on_submit=True):
                desc = st.text_input("Descrição da despesa")
                val_desp = st.number_input("Valor (R$)", min_value=0.0)
                data_desp = st.date_input("Data", datetime.today())
                
                if st.form_submit_button("Lançar Saída"):
                    save_row("despesas", [str(data_desp), desc, val_desp])
                    st.success("Despesa registrada.")
                    st.rerun()
                    
        with c_graph2:
            if not df_agendamentos.empty and receita > 0:
                st.subheader("Serviços Top")
                df_validos = df_agendamentos[df_agendamentos['status'] != 'Cancelado']
                contagem = df_validos['servico'].value_counts().reset_index()
                contagem.columns = ['Serviço', 'Qtd']
                
                # Gráfico de Rosca com cores personalizadas
                fig = px.pie(contagem, values='Qtd', names='Serviço', hole=0.4, 
                             color_discrete_sequence=px.colors.sequential.RdBu)
                fig.update_layout(showlegend=False, margin=dict(t=0, b=0, l=0, r=0))
                st.plotly_chart(fig, use_container_width=True)

    if st.sidebar.button("Sair"):
        st.session_state['user'] = None
        st.rerun()

# --- MAIN LOOP ---
if 'user' not in st.session_state:
    st.session_state['user'] = None

if st.session_state['user'] is None:
    login_page()
else:
    if st.session_state['user']['role'] == 'admin':
        admin_dashboard()
    else:
        client_dashboard()
