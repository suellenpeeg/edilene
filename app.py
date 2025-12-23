import streamlit as st
import pandas as pd
from datetime import datetime, timedelta, date
import gspread
from google.oauth2.service_account import Credentials
import uuid

# --- CONFIGURAÇÃO E CONEXÃO ---
def get_db_connection():
    try:
        scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
        creds_dict = dict(st.secrets["gcp_service_account"])
        credentials = Credentials.from_service_account_info(creds_dict, scopes=scopes)
        client = gspread.authorize(credentials)
        return client.open_by_key("19FiUFG7daZKCTMZ8vtD023BPCPfnhpMaQ6UfD0KIhb0")
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
            # Converte tipos especiais do Pandas para strings/nativos
            clean_row = [str(x) if hasattr(x, "encode") or isinstance(x, (date, datetime)) else x for x in row_data]
            ws.append_row(clean_row)
        except Exception as e: st.error(f"Erro ao salvar: {e}")

# --- FILTRO DE DISPONIBILIDADE (O CORAÇÃO DO APP) ---
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
    
    # Filtro para não mostrar horários que já passaram se a data for HOJE
    now = datetime.now()
    
    df_ag = load_data("agendamentos")
    slots = []
    curr = start_work
    
    while curr + timedelta(minutes=duration_min) <= end_work:
        slot_end = curr + timedelta(minutes=duration_min)
        
        # 1. Verifica se o horário já passou (se for hoje)
        if date_obj == date.today() and curr < now:
            curr += timedelta(minutes=30)
            continue

        # 2. Verifica se está ocupado ou bloqueado
        is_free = True
        if not df_ag.empty:
            # Filtra apenas agendamentos ativos ou bloqueios para aquele dia
            busy = df_ag[(df_ag['data'] == date_str) & (df_ag['status'].isin(['Agendado', 'Bloqueado']))]
            for _, row in busy.iterrows():
                try:
                    # Tenta converter os formatos de hora da planilha
                    b_start = datetime.strptime(f"{date_str} {row['hora_inicio']}", "%Y-%m-%d %H:%M:%S")
                    b_end = datetime.strptime(f"{date_str} {row['hora_fim']}", "%Y-%m-%d %H:%M:%S")
                    if curr < b_end and slot_end > b_start:
                        is_free = False
                        break
                except: continue
        
        if is_free: slots.append(curr.strftime("%H:%M"))
        curr += timedelta(minutes=30)
    return slots

# --- PÁGINA GESTOR ---
def admin_dashboard():
    st.sidebar.title("Painel Gestora")
    aba = st.sidebar.radio("Navegação", ["Agenda", "Bloqueios", "Serviços", "💰 Financeiro"])
    
    if aba == "Agenda":
        st.header("📅 Compromissos")
        hoje = st.date_input("Ver data:", date.today())
        df = load_data("agendamentos")
        if not df.empty:
            dia = df[(df['data'] == str(hoje)) & (df['status'] != 'Cancelado')].sort_values('hora_inicio')
            if dia.empty: st.info("Nenhum agendamento para este dia.")
            else: st.dataframe(dia[['hora_inicio', 'cliente_nome', 'servico', 'status']], use_container_width=True, hide_index=True)

    elif aba == "Bloqueios":
        st.header("🚫 Bloquear Horários (Folgas/Almoço)")
        with st.form("f_bloq"):
            # Só permite bloquear de hoje em diante
            db = st.date_input("Data do Bloqueio", min_value=date.today())
            col1, col2 = st.columns(2)
            hi = col1.time_input("Início")
            hf = col2.time_input("Fim")
            motivo = st.text_input("Motivo (ex: Almoço)")
            if st.form_submit_button("Confirmar Bloqueio"):
                save_row("agendamentos", [str(uuid.uuid4()), f"BLOQUEIO: {motivo}", "00", "Bloqueio", str(db), hi.strftime("%H:%M:%S"), hf.strftime("%H:%M:%S"), 0, "Bloqueado"])
                st.success("Horário bloqueado com sucesso!")

    elif aba == "💰 Financeiro":
        st.header("Resumo Financeiro")
        df_ag = load_data("agendamentos")
        if not df_ag.empty:
            # Filtra apenas o que não é bloqueio e não foi cancelado
            df_fin = df_ag[(df_ag['status'] == 'Agendado') & (df_ag['cliente_tel'] != '00')]
            df_fin['valor'] = pd.to_numeric(df_fin['valor'], errors='coerce').fillna(0)
            
            c1, c2 = st.columns(2)
            c1.metric("Total Previsto (Mês)", f"R$ {df_fin['valor'].sum():,.2f}")
            c2.metric("Total de Atendimentos", len(df_fin))
            
            st.subheader("Detalhamento")
            st.dataframe(df_fin[['data', 'cliente_nome', 'servico', 'valor']], use_container_width=True)
        else:
            st.info("Nenhum dado financeiro disponível.")

# --- PÁGINA CLIENTE ---
def client_dashboard():
    st.header(f"Olá, {st.session_state['user']['name']}! ✨")
    df_s = load_data("servicos")
    if df_s.empty:
        st.warning("Nenhum serviço disponível no momento.")
        return

    serv = st.selectbox("Escolha o serviço", df_s['nome'].tolist())
    row_s = df_s[df_s['nome'] == serv].iloc[0]
    
    # Cliente só seleciona de hoje para o futuro
    data_sel = st.date_input("Selecione o dia", min_value=date.today())
    slots = check_availability(data_sel, int(row_s['duracao_min']))
    
    if slots:
        hora = st.selectbox("Horários disponíveis", slots)
        if st.button("Confirmar Agendamento"):
            h_f = (datetime.strptime(hora, "%H:%M") + timedelta(minutes=int(row_s['duracao_min']))).strftime("%H:%M:%S")
            save_row("agendamentos", [str(uuid.uuid4()), st.session_state['user']['name'], st.session_state['user']['phone'], serv, str(data_sel), hora+":00", h_f, row_s['valor'], "Agendado"])
            st.success("Agendamento realizado com sucesso!")
            st.balloons()
    else:
        st.error("Não há horários disponíveis para esta data. Tente outro dia!")

# --- INICIALIZAÇÃO ---
if 'user' not in st.session_state: st.session_state['user'] = None
# ... (incluir lógica de login_page aqui conforme versões anteriores) ...
