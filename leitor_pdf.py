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
    regex_universal = re.compile(r'\d{2}/\d{4}.*?(\d{2}/\d{4}).*?355.*?(\d{1,3}(?:[.,]\d{3})*[.,]\d{2})\s+(.*)')
    
    try:
        with pdfplumber.open(arquivo_pdf) as pdf:
            for page in pdf.pages:
                

                # --- ESTRATÉGIA B: TEXTO CORRIDO (Fallback) ---
                if True: # Executa sempre para garantir
                    texto_pagina = page.extract_text()
                    if texto_pagina:
                        for linha in texto_pagina.split('\n'):
                            linha_limpa = remover_acentos(linha)
                            
                            if "355" in linha_limpa and ("SUBSIDIO" in linha_limpa or "VANTAG" in linha_limpa):
                                match = regex_universal.search(linha_limpa)
                                if match:
                                    data_str = match.group(1)
                                    valor_str = match.group(2)
                                    cargo_str = match.group(3)
                                    
                                    val_final = limpar_dinheiro_inteligente(valor_str)
                                    
                                    if val_final > 10: 
                                        # Limpa o cargo
                                        cargo_final = limpar_cargo(cargo_str)
                                
                                    
                                        dados_encontrados.append({
                                            'Competencia': data_str,
                                            'Valor_Achado': val_final,
                                            'Cargo_Detectado': cargo_final
                                            })
                    

        # --- CONSOLIDAÇÃO ---
        if dados_encontrados:
            df = pd.DataFrame(dados_encontrados)
            df['Competencia'] = pd.to_datetime(df['Competencia'], format='%m/%Y', dayfirst=True, errors='coerce')
            df = df.sort_values(by='Valor_Achado', ascending=False)
            # AGORA A MÁGICA: SOMA TUDO DA MESMA COMPETÊNCIA
            # Ex: Jan (6.473) + Jan (1.153) = Jan (7.626)
            df = df.groupby('Competencia', as_index=False).agg({
                'Valor_Achado': 'sum',
                'Cargo_Detectado': 'first' # Mantém o primeiro nome de cargo encontrado
            })
            
            return df.sort_values('Competencia')
        else:
            return pd.DataFrame()

    except Exception as e:
        st.error(f"Erro ao ler PDF: {e}")
        return pd.DataFrame()
