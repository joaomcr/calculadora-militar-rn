import streamlit as st
import pandas as pd
from datetime import date
import json
from core import CalculadoraMilitar
from leitor_pdf import extrair_dados_pdf
from leitor_html import extrair_dados_html
from leitor_csv import extrair_dados_csv
from gerador_pdf import gerar_pdf

st.set_page_config(page_title="Calculadora Militares RN", layout="wide")

# --- CONFIGURAÇÃO VISUAL ---
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            [data-testid="stToolbar"] {visibility: hidden !important;}
            [data-testid="stDecoration"] {visibility: hidden !important;}
            [data-testid="stFooter"] {visibility: hidden !important;}
            .block-container {padding-top: 2rem;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# --- CABEÇALHO ---
st.title("🛡️ Calculadora de Revisão de Subsídio Militares RN")
st.markdown("""
Esta ferramenta simula os valores a receber decorrentes da correção do escalonamento vertical e progressão de níveis.
""")

# --- FUNÇÃO DE INTELIGÊNCIA ---
def inferir_historico_promocoes(df_extraido):
    historico = []
    mapa_patentes = {
        "CORONEL": "Coronel", "CEL": "Coronel", "TC": "Tenente-Coronel", 
        "MAJOR": "Major", "CAPITÃO": "Capitão", "CAP": "Capitão",
        "PRIMEIRO TENENTE": "1º Tenente", "1º TEN": "1º Tenente",
        "SEGUNDO TENENTE": "2º Tenente", "2º TEN": "2º Tenente",
        "ASPIRANTE": "Aspirante", "ASP": "Aspirante", "ALUNO": "Aluno CFO 1",
        "SUBTENENTE": "Subtenente", "SUB": "Subtenente", 
        "PRIMEIRO SARGENTO": "1º Sargento", "1º SGT": "1º Sargento",
        "SEGUNDO SARGENTO": "2º Sargento", "2º SGT": "2º Sargento",
        "TERCEIRO SARGENTO": "3º Sargento", "3º SGT": "3º Sargento",
        "CABO": "Cabo", "CB": "Cabo", "SOLDADO": "Soldado", "SD": "Soldado"
    }
    
    cargo_atual = None
    df_unico = df_extraido.drop_duplicates(subset=['Competencia'], keep='first').sort_values('Competencia')

    for index, row in df_unico.iterrows():
        texto_cargo = str(row.get('Cargo_Detectado', '')).upper()
        data_ref = row['Competencia']
        patente_identificada = None
        
        for sigla, nome in mapa_patentes.items():
            if sigla in texto_cargo:
                patente_identificada = nome
                break
        
        if patente_identificada and patente_identificada != cargo_atual:
            if cargo_atual is None: data_promo = data_ref
            else:
                mes, ano = data_ref.month, data_ref.year
                if 5 <= mes < 9: data_promo = date(ano, 4, 21)
                elif 9 <= mes <= 12: data_promo = date(ano, 8, 21)
                else: data_promo = date(ano - 1, 12, 25)
            
            historico.append({"Data": data_promo, "Posto": patente_identificada})
            cargo_atual = patente_identificada
            
    return pd.DataFrame(historico)

# --- 1. SIDEBAR ---
with st.sidebar:
    st.header("⚙️ Parâmetros")
    data_ingresso = st.date_input("Data de Ingresso", value=date(2010, 2, 1), min_value=date(1970, 1, 1), format="DD/MM/YYYY")
    data_ajuizamento = st.date_input("Data da Ação", value=date.today(), min_value=date(2000, 1, 1), format="DD/MM/YYYY")
    
    st.markdown("---")
    st.header("📂 Importação de Dados")
    
    csv_modelo = "Competencia;Valor;Cargo\n01/01/2018;4500,00;ALUNO CFO\n01/02/2018;4500,00;ALUNO CFO"
    st.download_button(
        label="📥 Baixar Modelo de Planilha (.csv)",
        data=csv_modelo,
        file_name="modelo_importacao.csv",
        mime="text/csv",
        help="Baixe este arquivo, preencha no Excel e suba aqui para garantir 100% de precisão."
    )
    
    st.markdown("---")
    arquivo_upload = st.file_uploader("Subir Ficha (HTML, PDF ou CSV)", type=["html", "htm", "pdf", "csv"])

# --- PROCESSAMENTO DO ARQUIVO ---
if 'ultimo_arquivo_id' not in st.session_state: st.session_state['ultimo_arquivo_id'] = ""
df_importado = pd.DataFrame()

if arquivo_upload:
    arquivo_atual_id = f"{arquivo_upload.name}_{arquivo_upload.size}"
    
    if arquivo_atual_id != st.session_state['ultimo_arquivo_id']:
        try:
            # --- SELETOR DE LEITURA ---
            if arquivo_upload.name.lower().endswith('.csv'):
                df_importado = extrair_dados_csv(arquivo_upload) 
            elif arquivo_upload.name.lower().endswith('.pdf'):
                df_importado = extrair_dados_pdf(arquivo_upload)
            else:
                html_content = arquivo_upload.getvalue().decode("utf-8", errors='ignore')
                df_importado = extrair_dados_html(html_content)
                
            if not df_importado.empty:
                st.sidebar.success(f"Arquivo lido! {len(df_importado)} registros.")
                st.session_state.df_importado = df_importado # Salva na sessão
                
                if 'Cargo_Detectado' in df_importado.columns:
                    df_historico_auto = inferir_historico_promocoes(df_importado)
                    if not df_historico_auto.empty:
                        df_historico_auto["Data"] = pd.to_datetime(df_historico_auto["Data"])
                        st.session_state['df_template'] = df_historico_auto
                        if 'chave_tabela' in st.session_state: st.session_state['chave_tabela'] += 1
                        st.sidebar.success("✅ Histórico preenchido!")
            
            st.session_state['ultimo_arquivo_id'] = arquivo_atual_id
            
        except Exception as e:
            st.sidebar.error(f"Erro ao ler arquivo: {e}")

    # Recupera da sessão se já foi processado
    elif arquivo_atual_id == st.session_state['ultimo_arquivo_id']:
        if 'df_importado' in st.session_state:
            df_importado = st.session_state.df_importado

# --- 2. ÁREA DE DADOS EXTRAÍDOS (NOVIDADE) ---
# Aqui mostramos os dados convertidos e permitimos o download
if not df_importado.empty:
    with st.expander("📊 Ver Dados Extraídos do Arquivo (Conversão)", expanded=True):
        st.write("Estes foram os dados financeiros encontrados no seu arquivo:")
        
        # Formata para exibição
        df_display = df_importado.copy()
        if 'Competencia' in df_display.columns:
            df_display['Competencia'] = df_display['Competencia'].dt.strftime('%m/%Y')
        if 'Valor_Achado' in df_display.columns:
            df_display['Valor_Achado'] = df_display['Valor_Achado'].apply(lambda x: f"R$ {x:,.2f}")
            
        st.dataframe(df_display, use_container_width=True, height=250)
        
        # --- BOTÃO DE DOWNLOAD DO CSV CONVERTIDO ---
        csv_extraido = df_importado.to_csv(sep=';', decimal=',', index=False).encode('utf-8')
        col_d1, col_d2 = st.columns([1, 2])
        with col_d1:
            st.download_button(
                label="📥 Baixar Dados em CSV",
                data=csv_extraido,
                file_name="dados_financeiros_extraidos.csv",
                mime="text/csv",
                help="Baixe os dados brutos que o sistema leu do seu PDF/HTML."
            )
        with col_d2:
            st.caption("ℹ️ Use este arquivo para conferência ou para guardar seus dados financeiros de forma organizada.")

# --- 3. HISTÓRICO (CENTRAL) ---
st.subheader("2. Histórico de Carreira")
if arquivo_upload is None: st.info("💡 Dica: Baixe o modelo CSV na lateral, preencha e suba para preencher tudo automático.")

if 'df_template' not in st.session_state:
    df_init = pd.DataFrame([{"Data": "01/02/2010", "Posto": "Soldado"}])
    df_init["Data"] = pd.to_datetime(df_init["Data"], dayfirst=True)
    st.session_state['df_template'] = df_init

if 'chave_tabela' not in st.session_state: st.session_state['chave_tabela'] = 0

historico_final = st.data_editor(
    st.session_state['df_template'], 
    num_rows="dynamic",
    key=f"editor_historico_{st.session_state['chave_tabela']}", 
    column_config={
        "Data": st.column_config.DateColumn("Data Promoção", format="DD/MM/YYYY"),
        "Posto": st.column_config.SelectboxColumn("Posto", options=[
            "Coronel", "Tenente-Coronel", "Major", "Capitão", "1º Tenente", "2º Tenente", "Aspirante",
            "Subtenente", "1º Sargento", "2º Sargento", "3º Sargento", "Cabo", "Soldado",
            "Aluno CFO 1", "Aluno CFO 2", "Aluno CFO 3"
        ], required=True)
    }, use_container_width=True
)

col_sort, col_void = st.columns([1, 4])
if col_sort.button("🔄 Reordenar por Data"):
    df_ordenado = historico_final.sort_values("Data").reset_index(drop=True)
    st.session_state['df_template'] = df_ordenado
    st.session_state['chave_tabela'] += 1
    st.rerun()

# --- 4. GERAÇÃO E CONFRONTO ---
# --- 4. GERAÇÃO E CONFRONTO ---
st.markdown("---")
if st.button("🚀 Gerar Cálculo e Confrontar Valores", type="primary"):
    
    # Prepara o histórico
    historico_lista = historico_final.to_dict('records')
    
    # [PASSO 1] Captura as datas de férias que o PDF encontrou
    datas_ferias_encontradas = []
    
    if not df_importado.empty:
        # Garante que é datetime
        df_importado['Competencia'] = pd.to_datetime(df_importado['Competencia'], dayfirst=True)
        
        # Filtra tudo que for dia 15 (nossa convenção para Férias)
        datas_ferias_encontradas = df_importado[df_importado['Competencia'].dt.day == 15]['Competencia'].tolist()
        
        st.caption(f"📅 Férias identificadas no PDF: {len(datas_ferias_encontradas)} períodos.")

    # [PASSO 2] Instancia a Calculadora PASSANDO essa lista
    calc = CalculadoraMilitar(
        data_ingresso, 
        data_ajuizamento, 
        historico_lista,
        datas_ferias_pdf=datas_ferias_encontradas
    )
    
    # [PASSO 3] Gera a tabela "Ideal"
    df_ideal = calc.gerar_tabela_base()
    
    # [PASSO 4] Consolida (Aqui corrigi o nome da variável para df_calculo)
    if not df_importado.empty:
        # Cruza Ideal vs Real
        df_calculo = calc.consolidar_com_pdf(df_ideal, df_importado)
        st.toast("Confronto realizado com sucesso!", icon="💰")
    else:
        # Se não tiver PDF, o cálculo é apenas a tabela ideal
        df_calculo = df_ideal
        st.warning("Nenhum dado financeiro importado. Mostrando apenas valores devidos.")

    # [PASSO 5] Salva na sessão (Isso resolve o NameError)
    st.session_state['df_base'] = df_calculo
    
    # Exibe
    st.dataframe(df_calculo)
 # Salva no estado para o próximo passo
    st.session_state['df_base'] = df_calculo
    st.session_state['calculadora'] = calc
    st.session_state['passo'] = 2
    st.rerun()
if 'passo' in st.session_state and st.session_state['passo'] >= 2:    
    # Exibe Tabela
    st.subheader("3. Conferência Financeira")
    st.write("Edite os valores pagos se necessário e confira o resultado final.")
    
    df_para_editar = st.session_state['df_base']

    editor_financeiro = st.data_editor(
        df_para_editar[['Competencia', 'Posto_Vigente', 'Valor_Devido', 'Valor_Pago']],
        key="editor_financeiro_final",
        column_config={
            "Competencia": st.column_config.DateColumn("Mês/Ano", format="MM/YYYY", disabled=True),
            "Posto_Vigente": st.column_config.TextColumn("Posto", disabled=True),
            "Valor_Devido": st.column_config.NumberColumn("Devido (Lei)", format="R$ %.2f", disabled=True),
            "Valor_Pago": st.column_config.NumberColumn("Valor Pago (Ficha)", format="%.2f", required=True)
        },
        use_container_width=True, height=500
    )

    col_calc, col_reset = st.columns([1, 4])
    

      # Botão de Cálculo
    if st.button("🚀 Calcular Resultado Final"):
        calc_obj = st.session_state['calculadora']
        resultado_final = calc_obj.aplicar_financeiro(editor_financeiro)
        # Salva o resultado final no estado para persistir após clique de download
        st.session_state['resultado_final'] = resultado_final
        st.session_state['passo'] = 3
        st.rerun()

# --- SEÇÃO 3: RESULTADOS E EXPORTAÇÃO ---
if 'passo' in st.session_state and st.session_state['passo'] >= 3:
    resultado_final = st.session_state['resultado_final']
    
    st.markdown("---")
    st.header("3️⃣ Resultado da Simulação")
    
    total_dif = resultado_final['Diferenca_Mensal'].sum()
    total_final = resultado_final['Total_Final'].sum()
    juros = total_final - total_dif
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Principal (Diferença Nominal)", f"R$ {total_dif:,.2f}")
    c2.metric("Juros + Correção Monetária", f"R$ {juros:,.2f}")
    c3.metric("💰 TOTAL ESTIMADO DA AÇÃO", f"R$ {total_final:,.2f}")
    
    with st.expander("Ver Detalhamento Mês a Mês"):
        df_visual = resultado_final.copy()
        df_visual['Competencia'] = df_visual['Competencia'].dt.strftime('%m/%Y')
        colunas_visuais = ['Valor_Devido', 'Valor_Pago', 'Diferenca_Mensal', 'Total_Final']
        for col in colunas_visuais:
            df_visual[col] = df_visual[col].apply(lambda x: f"R$ {x:,.2f}")
        st.dataframe(df_visual[['Competencia', 'Valor_Devido', 'Valor_Pago', 'Diferenca_Mensal', 'Total_Final']], use_container_width=True)

    st.markdown("---")
    st.header("4️⃣ Emitir Relatório e Laudo")
    st.write("Para baixar os documentos finais (Planilha e Laudo PDF), identifique-se abaixo:")
    
    # Campo de nome com Key única para evitar erro de duplicidade
    nome_militar = st.text_input("Nome Completo do Militar", placeholder="Digite seu nome aqui...", key="input_nome_final")
    
    if nome_militar:
        # Prepara dados
        dados_militar = {
            'nome': nome_militar,
            'inicio': data_ingresso,
            'ajuizamento': data_ajuizamento
        }
        
        # --- CARREGA DADOS PARA O ANEXO DO PDF ---
        # 1. Recupera o histórico da memória da calculadora
        if 'calculadora' in st.session_state:
            calc_obj = st.session_state['calculadora']
            df_tabela_lei_pdf = calc_obj.df_tabela_lei.copy()
            df_historico_pdf = calc_obj.df_carreira.copy() # <--- NOVO: Pega o histórico usado no cálculo
        else:
            df_tabela_lei_pdf = pd.read_csv('dados/tabelas_lei.csv', sep=';')
            df_historico_pdf = pd.DataFrame() # Fallback

        try:
            df_escalonamento_pdf = pd.read_csv('dados/escalonamento.csv', sep=';')
        except:
            df_escalonamento_pdf = pd.DataFrame([["Erro ao ler arquivo", "0"]], columns=["Posto", "Percentual"])

        # Gera arquivos
        csv = resultado_final.to_csv(sep=';', decimal=',', index=False).encode('utf-8')
        
        # Passa o df_historico_pdf como 5º argumento
        pdf_buffer = gerar_pdf(
            resultado_final, 
            dados_militar, 
            df_tabela_lei_pdf, 
            df_escalonamento_pdf,
            df_historico_pdf # <--- NOVO ARGUMENTO
        )
        
        nome_arquivo_base = f"calculo_{nome_militar.replace(' ', '_')}"
        
        st.success("✅ Documentos gerados! Clique abaixo para baixar.")
        
        btn1, btn2 = st.columns(2)
        with btn1:
            st.download_button(
                label="📥 Baixar Planilha Detalhada (CSV)", 
                data=csv, 
                file_name=f"{nome_arquivo_base}.csv", 
                mime="text/csv"
            )
        with btn2:
            st.download_button(
                label="📄 Baixar Laudo Técnico (PDF)", 
                data=pdf_buffer, 
                file_name=f"LAUDO_{nome_arquivo_base}.pdf", 
                mime="application/pdf"
            )
    else:
        st.warning("☝️ Digite seu nome acima para liberar os botões de download.")

    if st.button("🔄 Reiniciar Simulação"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]

        st.rerun()

