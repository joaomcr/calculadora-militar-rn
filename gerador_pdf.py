from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from io import BytesIO
import locale
import pandas as pd # Adicione o import do Pandas, pois ele é fundamental para df_final

# Tenta configurar moeda para Brasil
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except:
    pass

def formatar_moeda(valor):
    try:
        # Usa o método do locale para formatação de moeda brasileira (R$ 1.234,56)
        # O ReportLab aceita strings formatadas
        return locale.currency(valor, symbol=False, grouping=True)
    except:
        # Se o locale falhar (como no ambiente Streamlit/Cloud), usa a formatação manual
        try:
            return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
        except:
            return str(valor)

def formatar_data(data):
    try:
        # Usa a formatação do Pandas para lidar com Timestamps
        if isinstance(data, pd.Timestamp):
            return data.strftime("%m/%Y")
        return data.strftime("%m/%Y")
    except:
        return str(data)

# Seu DataFrame de exemplo (substitua pelos nomes reais das colunas de índices)
# Se o seu df_final não tiver estas colunas, o código vai falhar.
# Você deve adicioná-las no seu módulo 'core.py' onde df_final é criado.
"""
Colunas NECESSÁRIAS em df_final para o novo laudo:
'Competencia', 'Rubrica_Tipo', 'Posto_Grad', 'Nivel', 
'Valor_Devido', 'Valor_Pago', 'Diferenca_Mensal',
'IPCA_Acumulado', 'Juros_Fator', 'Selic_Acumulada', 'Valor_Atualizado'
"""

def gerar_pdf(df_final, dados_militar, df_tabela_lei, df_escalonamento, df_historico):
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=2*cm, bottomMargin=2*cm)
    elementos = []

    # Estilos
    styles = getSampleStyleSheet()
    
    # 💡 AJUSTE 1: NOVO ESTILO PARA TÍTULO PRINCIPAL DA MEMÓRIA (Centralizado, Grande)
    estilo_titulo_principal = ParagraphStyle('TituloPrincipal', 
                                              parent=styles['Heading1'], 
                                              alignment=1, # Centralizado
                                              fontSize=16, 
                                              spaceAfter=15, 
                                              textColor=colors.darkred)
    
    estilo_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], alignment=1, fontSize=14, spaceAfter=10)
    estilo_subtitulo = ParagraphStyle('Subtitulo', parent=styles['Heading2'], alignment=0, fontSize=12, spaceAfter=6, textColor=colors.darkblue)
    estilo_normal = ParagraphStyle('Normal', parent=styles['BodyText'], fontSize=10, leading=12)
    estilo_nota = ParagraphStyle('Nota', parent=styles['BodyText'], fontSize=9, leading=10, textColor=colors.grey)

    # ... (Seções 1, 2, 3 e Quadro Resumo permanecem as mesmas)
    
    # --- 1. CABEÇALHO ---
    elementos.append(Paragraph("REVISÃO DE SUBSÍDIO - MILITARES RN", estilo_titulo))
    elementos.append(Spacer(1, 0.5*cm))

    # --- 2. DADOS DO MILITAR ---
    # ... (código para DADOS DO MILITAR) ...
    dados_tabela = [
        ["Interessado:", dados_militar['nome'].upper()],
        ["Data de Ingresso:", dados_militar['inicio'].strftime('%d/%m/%Y')],
        ["Data do Ajuizamento:", dados_militar['ajuizamento'].strftime('%d/%m/%Y')],
        ["Objeto:", "Recálculo de Subsídio (Escalonamento Vertical e Níveis)"]
    ]
    
    tabela_dados = Table(dados_tabela, colWidths=[4*cm, 12*cm])
    tabela_dados.setStyle(TableStyle([
        ('FONTNAME', (0,0), (0,-1), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
        ('BOTTOMPADDING', (0,0), (-1,-1), 6),
        ('GRID', (0,0), (-1,-1), 0.25, colors.grey),
    ]))
    elementos.append(tabela_dados)
    elementos.append(Spacer(1, 0.5*cm))

    # --- 3. HISTÓRICO DE CARREIRA CONSIDERADO ---
    # ... (código para HISTÓRICO DE CARREIRA) ...
    elementos.append(Paragraph("HISTÓRICO DE CARREIRA CONSIDERADO", estilo_subtitulo))
    elementos.append(Spacer(1, 0.2*cm))

    cabecalho_hist = [['Data Promoção', 'Posto / Graduação']]
    linhas_hist = []
    
    if not df_historico.empty:
        df_historico_ord = df_historico.sort_values('Data')
        
        for idx, row in df_historico_ord.iterrows():
            linha = [
                row['Data'].strftime('%d/%m/%Y'), 
                str(row['Posto'])
        ]
            linhas_hist.append(linha)

    tabela_hist = Table(cabecalho_hist + linhas_hist, colWidths=[4*cm, 10*cm])
    tabela_hist.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabela_hist)
    elementos.append(Spacer(1, 1*cm))
    
    # --- 4. QUADRO RESUMO ---
    # ... (código para QUADRO RESUMO) ...
    df_para_somar = df_final[(df_final['Valor_Devido'] > 0.01) | (df_final['Valor_Pago'] > 0.01)].copy()

    total_principal = df_para_somar['Diferenca_Mensal'].sum()
    total_final_causa = df_para_somar['Total_Final'].sum()
    total_acessorios = total_final_causa - total_principal

    dados_resumo = [
        ["RESUMO DOS CÁLCULOS", ""],
        ["1. Diferença de Subsídio (Principal Nominal)", f"R$ {formatar_moeda(total_principal)}"],
        ["2. Atualização (IPCA-E) + Juros + SELIC", f"R$ {formatar_moeda(total_acessorios)}"],
        ["TOTAL DA CONDENAÇÃO", f"R$ {formatar_moeda(total_final_causa)}"]
    ]

    tabela_resumo = Table(dados_resumo, colWidths=[10*cm, 5*cm])
    tabela_resumo.setStyle(TableStyle([
        ('SPAN', (0,0), (1,0)),
        ('ALIGN', (0,0), (1,0), 'CENTER'),
        ('BACKGROUND', (0,0), (1,0), colors.lightgrey),
        ('FONTNAME', (0,0), (1,0), 'Helvetica-Bold'),
        ('GRID', (0,0), (-1,-1), 1, colors.black),
        ('ALIGN', (1,1), (1,-1), 'RIGHT'),
        ('PADDING', (0,0), (-1,-1), 8),
        ('BACKGROUND', (0,3), (-1,3), colors.whitesmoke),
        ('FONTNAME', (0,3), (-1,3), 'Helvetica-Bold'),
        ('TEXTCOLOR', (0,3), (-1,3), colors.darkblue),
        ('FONTSIZE', (0,3), (-1,3), 12),
    ]))
    elementos.append(tabela_resumo)
    elementos.append(Spacer(1, 1*cm))

    # --- 5. TÍTULO GERAL CENTRALIZADO ---
    elementos.append(Paragraph("MEMÓRIA DE CÁLCULO DETALHADA MÊS A MÊS", estilo_titulo_principal))
    elementos.append(Spacer(1, 0.2*cm))
    
    # [DENTRO DA FUNÇÃO gerar_pdf]

    # ... (código anterior)

    # -----------------------------------------------------
    # 💡 SEÇÃO 5A: TABELA 1 - MEMORIAL DE CÁLCULO NOMINAL
    # -----------------------------------------------------
    elementos.append(Paragraph("Memorial de Cálculo (Valores Nominais)", estilo_subtitulo))
    
    # Colunas: Mês/Ref; Tipo; Posto/Grad; Nível; Devido; Recebido; Diferença.
    cabecalho_nominal = [
        'Mês/Ref', 'Tipo', 'Posto/Grad', 'Nível', 
        'Devido', 'Recebido', 'Diferença'
    ]
    linhas_nominais = []
    
    # Filtra linhas zeradas
    df_imprimir = df_final[(df_final['Valor_Devido'] > 0) | (df_final['Valor_Pago'] > 0)].copy()


    for idx, row in df_imprimir.iterrows():
        # Calcula Diferença: max(devido - recebido, 0)
        diferenca = max(row['Valor_Devido'] - row['Valor_Pago'], 0)
        
        linha = [
            row['Competencia'].strftime('%m/%Y'),
            # 💡 USA A NOVA COLUNA CRIADA NO CORE:
            row['Rubrica_Tipo'], 
            row['Posto_Grad'], 
            str(row['Nivel']), 
            formatar_moeda(row['Valor_Devido']),
            formatar_moeda(row['Valor_Pago']),
            formatar_moeda(diferenca)
        ]
        linhas_nominais.append(linha)


    col_widths_nominal = [2*cm, 2.5*cm, 2.5*cm, 1.5*cm, 2.5*cm, 2.5*cm, 2.5*cm]
    tabela_nominal = Table([cabecalho_nominal] + linhas_nominais, colWidths=col_widths_nominal, repeatRows=1)
    
    tabela_nominal.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        # Alinha valores monetários à direita
        ('ALIGN', (4,1), (-1,-1), 'RIGHT'), 
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabela_nominal)
    elementos.append(Spacer(1, 1.0*cm))


    # -----------------------------------------------------
    # 💡 SEÇÃO 5B: TABELA 2 - ATUALIZAÇÃO DOS VALORES DEVIDOS
    # -----------------------------------------------------
    elementos.append(Paragraph("Atualização Monetária e Juros", estilo_subtitulo))
    
    # Colunas: Mês/Ref; Diferença; IPCA-E; Juros de Mora; Selic; Valor atualizado.
    cabecalho_atualizacao = [
        'Mês/Ref', 'Principal', 
        'IPCA-E', 'Juros Mora', 'SELIC (%)', 
        'Valor Atualizado'
    ]
    linhas_atualizacao = []
    
    # NOTA: O DF 'df_imprimir' já foi filtrado acima.
    Data_inicio_SELIC = pd.to_datetime('2021-12-01')
    
    for idx, row in df_imprimir.iterrows():
        # Diferença: max(devido - recebido, 0) - Recalculada para garantir consistência
        diferenca_nominal = max(row['Valor_Devido'] - row['Valor_Pago'], 0)
        
        # Recupera os fatores ou valores de atualização (ASSUME nomes de colunas do seu Core)
        ipca_perc = row['IPCA_Fator']
        juros_perc = row['Juros_Fator']
        selic_perc = row['Selic_Fator'] * 100 # Assumindo que este é o fator acumulado
        

        linha = [
            row['Competencia'].strftime('%m/%Y'),
            formatar_moeda(diferenca_nominal),
            f"{ipca_perc:.10f}" if row['Competencia'].replace(day=1) <= Data_inicio_SELIC else "-",
            f"{juros_perc:.10f}" if juros_perc > 0 else "-",
            f"{selic_perc:.2f}%" if selic_perc > 0 else "-",
            formatar_moeda(row['Total_Final']) # ASSUME que 'Total_Final' é o Valor Atualizado
        ]
        linhas_atualizacao.append(linha)

    col_widths_atualizacao = [2*cm, 2.5*cm, 2*cm, 2*cm, 2*cm, 3.5*cm]
    tabela_atualizacao = Table([cabecalho_atualizacao] + linhas_atualizacao, colWidths=col_widths_atualizacao, repeatRows=1)
    
    tabela_atualizacao.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,0), 'CENTER'),
        # Centraliza fatores (IPCA, Juros, Selic)
        ('ALIGN', (2,1), (4,-1), 'CENTER'), 
        # Alinha valores monetários à direita
        ('ALIGN', (1,1), (1,-1), 'RIGHT'), 
        ('ALIGN', (5,1), (5,-1), 'RIGHT'), 
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabela_atualizacao)
    elementos.append(Spacer(1, 1.0*cm))


    # --- 6. NOTA METODOLÓGICA ---
    # ... (restante do seu código)
    elementos.append(Paragraph("<b>NOTA METODOLÓGICA:</b>", estilo_normal))
    texto_nota = """
    1. O cálculo apura as diferenças remuneratórias decorrentes da aplicação incorreta do escalonamento vertical e progressão de níveis.<br/>
    2. Respeitou-se a prescrição quinquenal a partir da data de ajuizamento.<br/>
    3. <b>Correção Monetária:</b> Aplicação do IPCA-E (Índices Acumulados) até nov/2021.<br/>
    4. <b>Juros de Mora:</b> Aplicação da remuneração da Caderneta de Poupança (Lei 11.960/09) até nov/2021, incidindo a partir do mês subsequente ao vencimento.<br/>
    5. <b>Atualização EC 113/21:</b> A partir de dez/2021, aplica-se exclusivamente a Taxa SELIC acumulada (Soma Simples).<br/>
    """
    elementos.append(Paragraph(texto_nota, estilo_nota))
    
    # Anexos em nova página
    elementos.append(PageBreak())
    
    # --- ANEXOS (7, 8, 9) ---
    # ... (Código dos anexos I e II permanece o mesmo) ...
    # --- 7. ANEXO I: TABELA DO CORONEL ---
    elementos.append(Paragraph("ANEXO I: HISTÓRICO DO SUBSÍDIO (CORONEL)", estilo_subtitulo))
    elementos.append(Paragraph("Base de cálculo para o escalonamento vertical.", estilo_nota))
    elementos.append(Spacer(1, 0.2*cm))

    cabecalho_lei = [['Data Início', 'Data Fim', 'Valor Base', 'Norma Legal']]
    linhas_lei = []
    
    for idx, row in df_tabela_lei.iterrows():
        norma = row.get('Norma', 'LCE 515/2014')
        linha = [
            formatar_data(row['Data_Inicio']),
            formatar_data(row['Data_Fim']),
            formatar_moeda(row['Valor']),
            str(norma)
        ]
        linhas_lei.append(linha)

    tabela_lei = Table(cabecalho_lei + linhas_lei, colWidths=[3*cm, 3*cm, 4*cm, 7*cm])
    tabela_lei.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (3,1), (3,-1), 'LEFT'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabela_lei)
    elementos.append(Spacer(1, 1*cm))

    # --- 8. ANEXO II: ESCALONAMENTO ---
    elementos.append(Paragraph("ANEXO II: TABELA DE ESCALONAMENTO", estilo_subtitulo))
    elementos.append(Spacer(1, 0.2*cm))

    cabecalho_esc = [['Posto / Graduação', 'Percentual (%)']]
    linhas_esc = []
    
    for idx, row in df_escalonamento.iterrows():
        # Trata percentual para exibição
        perc_texto = str(row['Percentual']).replace('.', ',')
        # Se for decimal pequeno (ex: 0.2), converte pra 20%
        try:
            val = float(str(row['Percentual']).replace(',', '.'))
            if val < 1.5: val = val * 100
            perc_texto = f"{val:.2f}%"
        except: pass
            
        linha = [row['Posto'], perc_texto]
        linhas_esc.append(linha)

    tabela_esc = Table(cabecalho_esc + linhas_esc, colWidths=[10*cm, 4*cm])
    tabela_esc.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabela_esc)
    elementos.append(Spacer(1, 0.5*cm))

    # --- 9. NOTA LEI 463/12 ---
    nota_aspirante = """
    <b>NOTA LEGAL ESPECÍFICA (FORMAÇÃO):</b><br/>
    Os subsídios de <b>Aspirante a Oficial</b> e <b>Alunos do CFO (I, II e III)</b> foram calculados observando a equivalência fixada pela 
    <b>Lei Estadual nº 463/2012</b>, recepcionada pela legislação posterior, garantindo a paridade com os níveis correspondentes das graduações de 
    Subtenente e Sargentos conforme estipulado.
    """
    elementos.append(Paragraph(nota_aspirante, estilo_nota))

    doc.build(elementos)
    buffer.seek(0)
    return buffer
