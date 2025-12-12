import pdfplumber
import pandas as pd
import streamlit as st
import re
import unicodedata

def remover_acentos(texto):
    """Remove acentos, coloca em maiúsculo e substitui quebras de linha por espaços"""
    try:
        if not texto: return ""
        # Remove quebras de linha
        t = str(texto).replace('\n', ' ').replace('\r', ' ')
        # Normaliza unicode
        nfkd = unicodedata.normalize('NFD', t)
        sem_acento = "".join([c for c in nfkd if not unicodedata.category(c) == 'Mn'])
        # Remove espaços duplos criados
        return re.sub(r'\s+', ' ', sem_acento.upper()).strip()
    except:
        return str(texto).upper()

def limpar_dinheiro_inteligente(valor_str):
    """
    Converte string para float detectando formato BR (1.000,00) ou US (1,000.00).
    """
    if not valor_str: return 0.0
    
    # Remove R$ e espaços
    v = valor_str.replace('R$', '').replace(' ', '').strip()
    
    # Detecção por posição do último separador
    last_comma = v.rfind(',')
    last_dot = v.rfind('.')
    
    # Lógica de decisão
    if last_comma != -1 and last_dot != -1:
        if last_comma > last_dot: # BR (1.000,00)
            v = v.replace('.', '').replace(',', '.')
        else: # US (1,000.00)
            v = v.replace(',', '')
    elif last_dot != -1: # Só ponto (1000.00 ou 1.000)
        # Se tem 3 casas após o ponto, assume milhar (US) -> remove ponto
        if len(v) - last_dot - 1 == 3: v = v.replace('.', '')
        # Caso contrário, assume decimal
    elif last_comma != -1: # Só vírgula (1000,00 ou 1,000)
        # Se tem 3 casas, assume milhar (US antigo ou erro) -> remove vírgula
        if len(v) - last_comma - 1 == 3: v = v.replace(',', '')
        # Caso contrário, assume decimal (BR)
        else: v = v.replace(',', '.')

    try:
        return float(v)
    except:
        return 0.0

def limpar_cargo(texto):
    """
    Limpa o texto do cargo:
    1. Remove código numérico inicial (ex: 106108)
    2. Corta no hífen para remover corporação/jornada (ex: - PM/CBM)
    """
    if not texto: return ""
    
    # Remove código numérico no início (sequência de digitos seguida de espaço)
    texto = re.sub(r'^\s*\d+\s+', '', texto)
    
    # Corta no primeiro hífen
    if '-' in texto:
        texto = texto.split('-')[0]
        
    return texto.strip()

def extrair_dados_pdf(arquivo_pdf):
    """
    Lê PDF e extrai dados.
    Estratégia: Varredura inteligente em tabelas e texto.
    """
    dados_encontrados = []
    
    # Regex Universal:
    # 1. Data (MM/AAAA)
    # 2. Texto qualquer até achar 355 (Rubrica)
    # 3. Valor OBRIGATÓRIO ter decimal
    # 4. Resto (Cargo)
    regex_subsidio = re.compile(r'\d{2}/\d{4}.*?(\d{2}/\d{4}).*?355.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s+(.*)')
    regex_natalina = re.compile(r'\d{2}/\d{4}.*?(\d{2}/\d{4}).*?351.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s+(.*)')
    regex_ferias = re.compile(r'\d{2}/\d{4}.*?(\d{2}/\d{4}).*?359.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s+(.*)')
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                texto_pagina = page.extract_text()
                if texto_pagina:
                    for linha in texto_pagina.split('\n'):
                        linha_limpa = remover_acentos(linha)
                        
                        # Filtra linhas de interesse
                        eh_subsidio = "355" in linha_limpa
                        eh_natalina = "351" in linha_limpa
                        eh_ferias   = "359" in linha_limpa # ou "359", confirme seu código

                        # Inicializa variáveis para este loop
                        match = None
                        tipo_pagamento = ""

                        # Lógica de decisão
                        if eh_subsidio:
                            match = regex_subsidio.search(linha_limpa)
                            tipo_pagamento = "mensal"
                        elif eh_natalina:
                            match = regex_natalina.search(linha_limpa)
                            tipo_pagamento = "natalina"
                        elif eh_ferias:
                            match = regex_ferias.search(linha_limpa)
                            tipo_pagamento = "ferias"

                        # Se houve match, processa
                        if match:
                            data_str = match.group(1)
                            valor_str = match.group(2)
                            cargo_str = match.group(3)
                            
                            val_final = limpar_dinheiro_inteligente(valor_str)
                            
                            if val_final > 0:
                                # --- PADRONIZAÇÃO DE DATAS ---
                                try:
                                    if tipo_pagamento == "natalina":
                                        # Natalina = Dia 13
                                        ano = data_str.split('/')[1]
                                        data_final = f"13/12/{ano}"
                                        
                                    elif tipo_pagamento == "ferias":
                                        # Férias = Dia 15 (Convenção para não misturar)
                                        mes, ano = data_str.split('/')
                                        data_final = f"15/{mes}/{ano}"
                                        
                                    else: 
                                        # Mensal = Dia 01
                                        data_final = f"01/{data_str}"
                                except:
                                    data_final = data_str

                                cargo_final = limpar_cargo(cargo_str)

                                dados_encontrados.append({
                                    'Competencia': data_final,
                                    'Valor_Achado': val_final,
                                    'Cargo_Detectado': cargo_final
                                })

        # --- CONSOLIDAÇÃO FORA DO LOOP ---
        if dados_encontrados:
            df = pd.DataFrame(dados_encontrados)
            
            # Função interna para aplicar no apply
            def definir_tipo(row):
                s = str(row['Competencia'])
                if s.startswith('13/'): return '13º Salário'
                if s.startswith('15/'): return 'Férias (1/3)'
                return 'Subsídio'

            df['Tipo'] = df.apply(definir_tipo, axis=1)

            # Converte para data com segurança (DD/MM/AAAA)
            df['Competencia'] = pd.to_datetime(df['Competencia'], dayfirst=True, errors='coerce')
            
            # Agrupa (caso haja férias parceladas no mesmo mês, ele soma)
            df = df.groupby(['Competencia', 'Tipo'], as_index=False).agg({
                'Valor_Achado': 'sum',
                'Cargo_Detectado': 'first'
            })
            
            return df.sort_values(['Competencia'])
        else:
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return pd.DataFrame()
