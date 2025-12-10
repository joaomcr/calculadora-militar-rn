import streamlit as st
import pandas as pd
from datetime import date
from core import CalculadoraMilitar
from leitor_pdf import extrair_dados_pdf
from leitor_html import extrair_dados_html
from gerador_pdf import gerar_pdf

st.set_page_config(page_title="Calculadora Militares RN", layout="wide")
# --- ESCONDER MARCAS DO STREAMLIT (CSS BLINDADO) ---
hide_st_style = """
            <style>
            /* Esconde Menu Hambúrguer, Rodapé e Cabeçalho Padrão */
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            
            /* Esconde elementos específicos pelo ID interno (Mais forte) */
            [data-testid="stToolbar"] {visibility: hidden !important;}
            [data-testid="stDecoration"] {visibility: hidden !important;}
            [data-testid="stFooter"] {visibility: hidden !important;}
            [data-testid="stHeader"] {visibility: hidden !important;}
            
            /* Esconde o botão de Deploy */
            .stDeployButton {display:none;}
            
            /* Remove o espaço em branco extra no topo */
            .block-container {
                padding-top: 1rem;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)
# --- CABEÇALHO E INTRODUÇÃO ---
st.title("🛡️ Calculadora de Revisão de Subsídio Militares RN")
st.markdown("""
Esta ferramenta simula os valores a receber decorrentes da correção do escalonamento vertical e progressão de níveis.
Siga os passos numerados abaixo para realizar sua simulação.
""")

# --- INSTRUÇÕES DO PORTAL (EXPANDER) ---
with st.expander("ℹ️ **COMO CONSEGUIR SUA FICHA FINANCEIRA (Passo a Passo)**", expanded=False):
    st.markdown("""
    Para preencher os dados automaticamente, recomendamos usar a **Ficha Financeira em HTML**:
    
    1. Acesse o **[Portal do Servidor do RN](https://portaldoservidor.rn.gov.br/)** e faça login.
    2. Vá até a seção **Ficha Financeira**.
    3. Gere a ficha do período completo (ex: de 2014 até hoje).
    4. **DICA DE OURO:** Na tela onde aparece a ficha, clique com o **botão direito do mouse** e selecione **"Salvar como..."** (ou `Ctrl + S`).
    5. Salve o arquivo no seu computador (verifique se o tipo é "Página da Web" ou HTML).
    6. Arraste esse arquivo para o campo de upload na barra lateral esquerda deste site.
    """)

st.markdown("---")

# --- FUNÇÃO DE INTELIGÊNCIA: DETECTAR PROMOÇÕES ---
def inferir_historico_promocoes(df_extraido):
    """
    Analisa a coluna 'Cargo_Detectado' e cria o histórico baseado nas datas fixas.
    Datas RN: 21/04, 21/08, 25/12.
    """
    historico = []
    
    mapa_patentes = {
        # --- OFICIAIS ---
        "CORONEL": "Coronel", "CEL": "Coronel",
        "TENENTE CORONEL": "Tenente-Coronel", "TENENTE-CORONEL": "Tenente-Coronel", "TC": "Tenente-Coronel",
        "MAJOR": "Major", "MAJ": "Major",
        "CAPITÃO": "Capitão", "CAPITAO": "Capitão", "CAP": "Capitão",
        
        # Variações de Tenente
        "PRIMEIRO TENENTE": "1º Tenente", "1º TEN": "1º Tenente", "1 TEN": "1º Tenente",
        "SEGUNDO TENENTE": "2º Tenente", "2º TEN": "2º Tenente", "2 TEN": "2º Tenente",
        "ASPIRANTE": "Aspirante", "ASP": "Aspirante",
        "ALUNO": "Aluno CFO 1",
        
        # --- PRAÇAS ---
        "SUBTENENTE": "Subtenente", "SUB": "Subtenente", "ST": "Subtenente",
        
        # Variações de Sargento
        "PRIMEIRO SARGENTO": "1º Sargento", "1º SGT": "1º Sargento", "1 SGT": "1º Sargento",
        "SEGUNDO SARGENTO": "2º Sargento", "2º SGT": "2º Sargento", "2 SGT": "2º Sargento",
        "TERCEIRO SARGENTO": "3º Sargento", "3º SGT": "3º Sargento", "3 SGT": "3º Sargento",
        
        # Cabos e Soldados
        "CABO": "Cabo", "CB": "Cabo",
        "SOLDADO": "Soldado", "SD": "Soldado", "SD.": "Soldado"
    }

    cargo_atual = None
    
    # Remove duplicatas de meses e ordena
    df_unico = df_extraido.drop_duplicates(subset=['Competencia'], keep='first').sort_values('Competencia')

    for index, row in df_unico.iterrows():
        texto_cargo_html = str(row.get('Cargo_Detectado', '')).upper()
        data_ref = row['Competencia']
        
        patente_identificada = None
        for sigla, nome_sistema in mapa_patentes.items():
            if sigla in texto_cargo_html:
                patente_identificada = nome_sistema
                break
        
        if patente_identificada and patente_identificada != cargo_atual:
            if cargo_atual is None:
                data_promo = data_ref
            else:            
                mes = data_ref.month
                ano = data_ref.year
                if mes >= 5 and mes < 9:
                    data_promo = date(ano, 4, 21)
                elif mes >= 9 and mes <= 12:
                    data_promo = date(ano, 8, 21)
                else: 
                    data_promo = date(ano - 1, 12, 25)
            
            historico.append({"Data": data_promo, "Posto": patente_identificada})
            cargo_atual = patente_identificada
            
    return pd.DataFrame(historico)

# --- 1. SIDEBAR (CONFIGURAÇÕES) ---
with st.sidebar:
    st.header("⚙️ Parâmetros")
    
   # --- CORREÇÃO AQUI: ADICIONADO min_value PARA PERMITIR DATAS ANTIGAS ---
    data_ingresso = st.date_input(
        "Data de Ingresso", 
        value=date(2010, 2, 1), 
        min_value=date(1970, 1, 1), # Permite datas desde 1970
        format="DD/MM/YYYY"
    )
    data_ajuizamento = st.date_input("Data Estimada da Ação", value=date.today(), format="DD/MM/YYYY")
    
    st.markdown("---")
    st.header("📂 Automação (Opcional)")
    st.markdown("Para preencher histórico e valores automaticamente:")
    arquivo_upload = st.file_uploader("Subir Ficha (HTML ou PDF)", type=["html", "htm", "pdf"])

# --- PROCESSAMENTO DO ARQUIVO ---
# Controle de estado para processar arquivo apenas uma vez
if 'ultimo_arquivo_id' not in st.session_state:
    st.session_state['ultimo_arquivo_id'] = ""

df_importado = pd.DataFrame()

if arquivo_upload:
    arquivo_atual_id = f"{arquivo_upload.name}_{arquivo_upload.size}"
    
    # Se o arquivo mudou, processa e atualiza histórico
    if arquivo_atual_id != st.session_state['ultimo_arquivo_id']:
        try:
            if arquivo_upload.name.lower().endswith('.pdf'):
                df_importado = extrair_dados_pdf(arquivo_upload)
            else:
                html_content = arquivo_upload.getvalue().decode("utf-8", errors='ignore')
                df_importado = extrair_dados_html(html_content)
                
            if not df_importado.empty:
                st.sidebar.success(f"Arquivo lido! {len(df_importado)} meses.")
                
                # Auto-preenchimento do histórico
                if 'Cargo_Detectado' in df_importado.columns:
                    df_historico_auto = inferir_historico_promocoes(df_importado)
                    if not df_historico_auto.empty:
                        df_historico_auto["Data"] = pd.to_datetime(df_historico_auto["Data"])
                        st.session_state['df_template'] = df_historico_auto
                        # Força recarregamento da tabela de histórico
                        if 'chave_tabela' in st.session_state:
                            st.session_state['chave_tabela'] += 1
                        st.sidebar.success("✅ Histórico preenchido!")
            
            st.session_state['ultimo_arquivo_id'] = arquivo_atual_id
            
        except Exception as e:
            st.sidebar.error(f"Erro ao ler arquivo: {e}")

    # Se o arquivo já foi processado, apenas carrega os dados financeiros (sem mexer no histórico)
    elif arquivo_atual_id == st.session_state['ultimo_arquivo_id']:
        if arquivo_upload.name.lower().endswith('.pdf'):
            df_importado = extrair_dados_pdf(arquivo_upload)
        else:
            html_content = arquivo_upload.getvalue().decode("utf-8", errors='ignore')
            df_importado = extrair_dados_html(html_content)

# --- SEÇÃO 1: HISTÓRICO ---
st.header("1️⃣ Histórico de Carreira")

if arquivo_upload is None:
    st.info("💡 Preencha manualmente abaixo ou suba o arquivo na barra lateral.")

if 'df_template' not in st.session_state:
    df_init = pd.DataFrame([{"Data": "01/02/2010", "Posto": "Soldado"}])
    df_init["Data"] = pd.to_datetime(df_init["Data"], dayfirst=True)
    st.session_state['df_template'] = df_init

if 'chave_tabela' not in st.session_state:
    st.session_state['chave_tabela'] = 0

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

# --- BOTÃO DE AVANÇO (PASSO 1 -> 2) ---
st.markdown("---")
if st.button("Avançar para Conferência Financeira ➡️", type="primary"):
    historico_lista = historico_final.to_dict('records')
    
    calc = CalculadoraMilitar(data_ingresso, data_ajuizamento, historico_lista)
    df_calculo = calc.gerar_tabela_base()
    
    # Preenche valor pago se tiver arquivo
    if not df_importado.empty:
        df_calculo['Competencia'] = pd.to_datetime(df_calculo['Competencia'])
        registros = 0
        for index, row in df_importado.iterrows():
            data_ext = row['Competencia']
            valor_ext = row['Valor_Achado']
            mask = df_calculo['Competencia'] == data_ext
            if mask.any():
                df_calculo.loc[mask, 'Valor_Pago'] = valor_ext
                registros += 1
        st.toast(f"{registros} valores importados com sucesso!", icon="✅")

    # Salva no estado para o próximo passo
    st.session_state['df_base'] = df_calculo
    st.session_state['calculadora'] = calc
    st.session_state['passo'] = 2
    st.rerun()

# --- SEÇÃO 2: CONFERÊNCIA ---
if 'passo' in st.session_state and st.session_state['passo'] >= 2:
    st.header("2️⃣ Conferência Financeira")
    st.write("Abaixo, o sistema compara o que você **Deveria Receber (Lei)** com o que foi **Efetivamente Pago**.")
    st.info("📝 Se houver meses com valor pago zerado ou errado, você pode editar diretamente na tabela.")
    
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

    # Botão para calcular final
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


