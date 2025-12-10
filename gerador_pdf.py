from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from io import BytesIO
import locale

# Tenta configurar moeda para Brasil
try:
    locale.setlocale(locale.LC_ALL, 'pt_BR.UTF-8')
except:
    pass

def formatar_moeda(valor):
    try:
        return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except:
        return str(valor)

def formatar_data(data):
    try:
        return data.strftime("%d/%m/%Y")
    except:
        return str(data)

def gerar_pdf(df_final, dados_militar, df_tabela_lei, df_escalonamento, df_historico):
    """
    Gera PDF com: Resumo, Memória de Cálculo, Anexo I (Leis) e Anexo II (Escalonamento).
    """
    buffer = BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, rightMargin=1.5*cm, leftMargin=1.5*cm, topMargin=2*cm, bottomMargin=2*cm)
    elementos = []

    # Estilos
    styles = getSampleStyleSheet()
    estilo_titulo = ParagraphStyle('Titulo', parent=styles['Heading1'], alignment=1, fontSize=14, spaceAfter=10)
    estilo_subtitulo = ParagraphStyle('Subtitulo', parent=styles['Heading2'], alignment=0, fontSize=12, spaceAfter=6, textColor=colors.darkblue)
    estilo_normal = ParagraphStyle('Normal', parent=styles['BodyText'], fontSize=10, leading=12)
    estilo_nota = ParagraphStyle('Nota', parent=styles['BodyText'], fontSize=9, leading=10, textColor=colors.grey)

    # --- 1. CABEÇALHO ---
    elementos.append(Paragraph("REVISÃO DE SUBSÍDIO - MILITARES RN", estilo_titulo))
    elementos.append(Spacer(1, 0.5*cm))

    # --- 2. DADOS DO MILITAR ---
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
# --- 3. HISTÓRICO DE CARREIRA CONSIDERADO (NOVO BLOCO) ---
    elementos.append(Paragraph("HISTÓRICO DE CARREIRA CONSIDERADO", estilo_subtitulo))
    elementos.append(Spacer(1, 0.2*cm))

    cabecalho_hist = [['Data Promoção', 'Posto / Graduação']]
    linhas_hist = []
    
    # Ordena por data para garantir cronologia
    if not df_historico.empty:
        df_historico_ord = df_historico.sort_values('Data')
        
        for idx, row in df_historico_ord.iterrows():
            linha = [
                formatar_data(row['Data']),
                str(row['Posto'])
            ]
            linhas_hist.append(linha)

    tabela_hist = Table(cabecalho_hist + linhas_hist, colWidths=[4*cm, 10*cm])
    tabela_hist.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'), # Cabeçalho Negrito
        ('ALIGN', (0,0), (-1,-1), 'CENTER'), # Centralizado
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey), # Fundo Cinza no Cabeçalho
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]), # Zebrado
    ]))
    elementos.append(tabela_hist)
    elementos.append(Spacer(1, 1*cm))
    # --- 4. QUADRO RESUMO (CORRIGIDO) ---
    
    # 1. FILTRAGEM DE SEGURANÇA:
    # Garante que vamos somar APENAS o que vai aparecer na tabela detalhada.
    # Ignora meses zerados ou erros de arredondamento negativo.
    df_para_somar = df_final[(df_final['Valor_Devido'] > 0.01) | (df_final['Valor_Pago'] > 0.01)].copy()

    # 2. CÁLCULO DOS TOTAIS
    total_principal = df_para_somar['Diferenca_Mensal'].sum()
    total_final_causa = df_para_somar['Total_Final'].sum()
    
    # Acessórios (Juros + CM) é a subtração simples do Total pelo Principal
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

    # --- 4. MEMÓRIA DETALHADA ---
    elementos.append(Paragraph("MEMÓRIA DE CÁLCULO DETALHADA (Mês a Mês)", estilo_subtitulo))
    elementos.append(Spacer(1, 0.2*cm))

    cabecalho_detalhado = [['Mês/Ref', 'Devido', 'Pago', 'Diferença', 'F. IPCA', 'F. Selic', 'Total']]
    linhas_detalhadas = []
    
    # Filtra linhas zeradas
    df_imprimir = df_final[(df_final['Valor_Devido'] > 0) | (df_final['Valor_Pago'] > 0)].copy()
    
    for idx, row in df_imprimir.iterrows():
        linha = [
            row['Competencia'].strftime('%m/%Y'),
            formatar_moeda(row['Valor_Devido']),
            formatar_moeda(row['Valor_Pago']),
            formatar_moeda(row['Diferenca_Mensal']),
            f"{row['IPCA_Fator']:.4f}",
            f"{row['Selic_Fator']:.4f}" if row['Selic_Fator'] > 0 else "-",
            formatar_moeda(row['Total_Final'])
        ]
        linhas_detalhadas.append(linha)

    tabela_longa = Table(cabecalho_detalhado + linhas_detalhadas, colWidths=[2*cm, 2.5*cm, 2.5*cm, 2.5*cm, 1.8*cm, 1.8*cm, 3*cm], repeatRows=1)
    tabela_longa.setStyle(TableStyle([
        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
        ('ALIGN', (0,0), (-1,-1), 'CENTER'),
        ('ALIGN', (1,1), (3,-1), 'RIGHT'),
        ('ALIGN', (6,1), (6,-1), 'RIGHT'),
        ('FONTSIZE', (0,0), (-1,-1), 8),
        ('GRID', (0,0), (-1,-1), 0.5, colors.grey),
        ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.whitesmoke, colors.white]),
    ]))
    elementos.append(tabela_longa)
    elementos.append(Spacer(1, 1*cm))

    # --- 5. NOTA METODOLÓGICA ---
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

    # --- 6. ANEXO I: TABELA DO CORONEL ---
    elementos.append(Paragraph("ANEXO I: HISTÓRICO DO SUBSÍDIO (CORONEL)", estilo_subtitulo))
    elementos.append(Paragraph("Base de cálculo para o escalonamento vertical.", estilo_nota))
    elementos.append(Spacer(1, 0.2*cm))

    cabecalho_lei = [['Data Início', 'Data Fim', 'Valor Base', 'Norma Legal']]
    linhas_lei = []
    
    for idx, row in df_tabela_lei.iterrows():
        norma = row.get('Norma', 'LCE 514/2014')
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

    # --- 7. ANEXO II: ESCALONAMENTO ---
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

    # --- 8. NOTA LEI 463/12 ---
    nota_aspirante = """
    <b>NOTA LEGAL ESPECÍFICA (FORMAÇÃO):</b><br/>
    Os subsídios de <b>Aspirante a Oficial</b> e <b>Alunos do CFO (I, II e III)</b> foram calculados observando a equivalência fixada pela 
    <b>Lei Estadual nº 463/2012</b>, recepcionada pela legislação posterior, garantindo a paridade com os níveis correspondentes das graduações de 
    Subtenente e Sargentos conforme estipulado.
    """
    elementos.append(Paragraph(nota_aspirante, estilo_nota))
    # --- 9. ASSINATURA ---
    # REMOVIDA O CAMPO DE ASSINATURA
    #elementos.append(Spacer(1, 2*cm))
    #elementos.append(Paragraph("_" * 50, ParagraphStyle('Centro', parent=styles['Normal'], alignment=1)))
    #elementos.append(Paragraph("Responsável Técnico / Calculista", ParagraphStyle('Centro', parent=styles['Normal'], alignment=1)))
    
    doc.build(elementos)
    buffer.seek(0)

    return buffer
